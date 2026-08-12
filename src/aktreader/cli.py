"""Strictly local command-line interface for the P2 pipeline."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aktreader import (
    COMMAND_NAME,
    DISTRIBUTION_NAME,
    PACKAGE_NAMESPACE,
    PROJECT_NAME,
    PROJECT_ROLE,
    REPOSITORY_URL,
    __version__,
)
from aktreader.adjudication import generate_packet, ingest_answers
from aktreader.assets import inspect_packaged_runtime_assets, runtime_asset_path
from aktreader.batch import (
    BatchJob,
    BatchRunner,
    InferenceIdentity,
    atomic_write_json,
    atomic_write_text,
    load_manifest_jobs,
)
from aktreader.cli_support import (
    CliConfigurationError,
    brief_for_job,
    generation_report,
    load_json_object,
    load_local_reader_config,
    load_strict_json,
    local_input_path,
    local_output_path,
    model_identity,
    reader_report,
    require_keys,
    require_local_only_data,
)
from aktreader.comparison import compare_reader_labels, render_disagreements_csv
from aktreader.consensus import merge_labels
from aktreader.consensus_record import build_consensus_record, write_consensus_record
from aktreader.evaluation import (
    evaluate_predictions,
    load_prediction_records,
    render_stratified_markdown,
)
from aktreader.grounding import (
    load_grounded_reader_label,
    paired_quality_metrics,
    validate_cross_reader_grounding,
)
from aktreader.installation import inspect_application_checkout
from aktreader.local_reader import LocalReader, LocalReaderError
from aktreader.prompt import verify_reader_prompt
from aktreader.validators.dates import validate_dates
from aktreader.validators.formula import validate_formula_positions
from aktreader.verification import CHECK_NAMES, verify_application_checkout

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACT_RECORD_SCHEMA_PATH = runtime_asset_path("schemas/act-record-2.0.0.schema.json")


def _source_checkout_default(relative_path: str) -> Path | None:
    candidate = PROJECT_ROOT / relative_path
    return candidate if candidate.exists() else None


def _emit_json(payload: Mapping[str, Any], *, stream: Any = None) -> None:
    target = sys.stdout if stream is None else stream
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    encoding = getattr(target, "encoding", None)
    if encoding:
        try:
            rendered.encode(encoding)
        except UnicodeEncodeError:
            rendered = rendered.encode(encoding, errors="backslashreplace").decode(encoding)
    target.write(rendered)
    target.write("\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the local-only parser without import-time runtime execution."""
    parser = argparse.ArgumentParser(
        prog=COMMAND_NAME,
        description="AKT Reader Application: Local-only civil-register extraction (P2).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=(
            f"%(prog)s {__version__} "
            f"({PROJECT_NAME}; distribution: {DISTRIBUTION_NAME})"
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    doctor = subparsers.add_parser("doctor", help="report the local pipeline environment")
    doctor.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    doctor.add_argument(
        "--inspect-root",
        type=Path,
        help=(
            "diagnose contracts in another local checkout without reconfiguring "
            "the running Application"
        ),
    )

    checkout_verify = subparsers.add_parser(
        "checkout-verify",
        help="verify the public Application checkout without scans or model weights",
    )
    checkout_verify.add_argument("--root", type=Path, default=PROJECT_ROOT)
    checkout_verify.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    prompt = subparsers.add_parser(
        "prompt-verify", help="verify the frozen Reader prompt and source-skill bindings"
    )
    prompt.add_argument("--root", type=Path, default=PROJECT_ROOT)

    labels = subparsers.add_parser(
        "label-validate", help="validate external blind-reader label JSON files"
    )
    labels.add_argument("labels", nargs="+", type=Path)

    consensus = subparsers.add_parser(
        "consensus-merge",
        help="merge exactly two explicitly named blind-reader labels",
    )
    consensus.add_argument("left_label", type=Path)
    consensus.add_argument("right_label", type=Path)
    consensus.add_argument("--output", required=True, type=Path)
    consensus.add_argument(
        "--schema",
        type=Path,
        default=ACT_RECORD_SCHEMA_PATH,
    )
    consensus.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly permit atomic replacement of an existing consensus output",
    )

    inspect_reader = subparsers.add_parser(
        "reader-inspect", help="verify pinned local Reader artifacts without running inference"
    )
    inspect_reader.add_argument("--config", required=True, type=Path)

    infer = subparsers.add_parser(
        "reader-infer", help="run one explicitly configured local Reader inference"
    )
    infer.add_argument("--config", required=True, type=Path)
    infer.add_argument("--scan", required=True, type=Path)
    infer.add_argument("--brief", required=True, type=Path)
    infer.add_argument("--output", required=True, type=Path)

    batch = subparsers.add_parser(
        "batch-run", help="resume a manifest-driven local inference run"
    )
    batch.add_argument("--config", required=True, type=Path)
    batch.add_argument("--manifest", required=True, type=Path)
    batch.add_argument("--checkpoint", required=True, type=Path)
    batch.add_argument("--output-dir", required=True, type=Path)
    batch.add_argument("--as-of-year", type=int)
    batch.add_argument("--max-retries", type=int, default=2)
    batch.add_argument(
        "--rebind-failed-fingerprints",
        action="store_true",
        help=(
            "explicitly preserve FAILED retry counts while auditing a changed "
            "runtime fingerprint; changed non-FAILED rows are rejected"
        ),
    )

    adjudicate = subparsers.add_parser(
        "adjudicate",
        help="generate an offline human adjudication packet or ingest its answers",
    )
    adjudicate.add_argument("--wave", required=True)
    adjudicate.add_argument(
        "--spec",
        type=Path,
        help="wave specification; defaults to human_check/waves/wave-<id>.json",
    )
    adjudicate.add_argument(
        "--output-dir",
        type=Path,
        help="packet directory; defaults to human_check/generated/wave-<id>",
    )
    adjudicate.add_argument(
        "--answers",
        type=Path,
        help="ingest a downloaded answers JSON into an existing packet directory",
    )
    adjudicate.add_argument("--max-questions", type=int, default=10)
    adjudicate.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly replace generation artifacts; ingested results remain immutable",
    )
    evaluate = subparsers.add_parser(
        "eval", help="generate the clerk-year-sequestered SerockBench report"
    )
    evaluate.add_argument("--predictions", required=True, type=Path)
    evaluate.add_argument(
        "--gold-dir",
        type=Path,
        default=_source_checkout_default("gold/acts"),
        help="gold records directory; required outside an Application source checkout",
    )
    evaluate.add_argument(
        "--holdout",
        type=Path,
        default=_source_checkout_default("gold/clerk_year_holdout.json"),
        help="clerk-year holdout manifest; required outside a source checkout",
    )
    evaluate.add_argument("--training-clerk-years", type=Path)
    evaluate.add_argument("--output", type=Path)
    evaluate.add_argument(
        "--strata-table",
        type=Path,
        help="optional Markdown table of count-backed field-family and language strata",
    )

    compare = subparsers.add_parser(
        "compare",
        help="compare two local reader-label collections without inference or network access",
    )
    compare.add_argument("left", type=Path, help="left label file or directory")
    compare.add_argument("right", type=Path, help="right label file or directory")
    compare.add_argument("--output", type=Path, help="optional JSON report path")
    compare.add_argument(
        "--csv",
        type=Path,
        help="optional spreadsheet-safe CSV containing every field disagreement",
    )
    compare.add_argument(
        "--max-disagreements",
        type=int,
        default=100,
        help="maximum disagreement details to include in the report (default: 100)",
    )
    compare.add_argument(
        "--require-grounded",
        action="store_true",
        help="fail closed unless every input label passes the continuous-transcription gate",
    )
    return parser


def environment_report(inspect_root: Path | str | None = None) -> dict[str, object]:
    """Return deterministic installed-runtime and checkout-readiness facts."""
    supported = sys.version_info >= (3, 11)
    runtime_root = PROJECT_ROOT.resolve()
    inspected_root = runtime_root if inspect_root is None else Path(inspect_root).resolve()
    checkout = inspect_application_checkout(inspected_root)
    runtime_checkout = (
        checkout
        if inspected_root == runtime_root
        else inspect_application_checkout(runtime_root)
    )
    runtime_assets = inspect_packaged_runtime_assets()
    inspected_root_is_runtime_root = inspected_root == runtime_root
    runtime_mode = (
        "source-checkout"
        if runtime_checkout["identity_status"] == "MATCH"
        else "installed-distribution"
    )
    source_checkout_verification_available = bool(
        supported and inspected_root_is_runtime_root and checkout["ready"]
    )
    standalone_distribution_ready = bool(
        supported and runtime_assets["runtime_assets_available"]
    )
    if inspect_root is not None:
        pipeline_available = source_checkout_verification_available
    elif runtime_mode == "source-checkout":
        pipeline_available = bool(
            source_checkout_verification_available and standalone_distribution_ready
        )
    else:
        pipeline_available = standalone_distribution_ready
    return {
        "doctor_report_version": "1.1.0",
        "aktreader_version": __version__,
        "project_name": PROJECT_NAME,
        "project_role": PROJECT_ROLE,
        "distribution_name": DISTRIBUTION_NAME,
        "package_namespace": PACKAGE_NAMESPACE,
        "command_name": COMMAND_NAME,
        "repository_url": REPOSITORY_URL,
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_supported": supported,
        "phase": "P2",
        "cli_available": True,
        "runtime_mode": runtime_mode,
        "runtime_root": str(runtime_root),
        "inspected_root": checkout["root"],
        "inspected_root_is_runtime_root": inspected_root_is_runtime_root,
        "checkout_identity_status": checkout["identity_status"],
        "observed_distribution_name": checkout["observed_distribution_name"],
        "contract_asset_count": checkout["contract_asset_count"],
        "available_contract_asset_count": checkout["available_contract_asset_count"],
        "contract_assets_available": checkout["contract_assets_available"],
        "missing_contract_assets": checkout["missing_contract_assets"],
        "contract_assets": checkout["contract_assets"],
        "inspected_checkout_ready": checkout["ready"],
        **runtime_assets,
        "source_checkout_verification_available": (
            source_checkout_verification_available
        ),
        "pipeline_available": pipeline_available,
        "source_checkout_required": False,
        "standalone_distribution_ready": standalone_distribution_ready,
        "reader_backend": "local-open-weights-only",
        "network_required": False,
    }


def _command_doctor(args: argparse.Namespace) -> int:
    inspect_root = (
        None
        if args.inspect_root is None
        else local_output_path(args.inspect_root, role="inspected application root")
    )
    report = environment_report(inspect_root)
    if args.json:
        _emit_json(report)
    else:
        print(f"{report['project_name']} {report['aktreader_version']}")
        print(f"Repository role: {report['project_role']}")
        print(
            "Runtime identity: "
            f"distribution {report['distribution_name']} | "
            f"package {report['package_namespace']} | command {report['command_name']}"
        )
        print(f"Repository: {report['repository_url']}")
        print(f"Runtime mode: {report['runtime_mode']}")
        print(f"Runtime root: {report['runtime_root']}")
        if not report["inspected_root_is_runtime_root"]:
            print(f"Inspected root: {report['inspected_root']} (diagnostic only)")
        print(
            "Checkout identity: "
            f"{report['checkout_identity_status']} "
            f"(observed: {report['observed_distribution_name'] or 'none'})"
        )
        print(
            "Checkout assets: "
            f"{report['available_contract_asset_count']}/"
            f"{report['contract_asset_count']} available"
        )
        for path in report["missing_contract_assets"]:
            print(f"  missing: {path}")
        print(
            "Packaged runtime assets: "
            f"{report['available_runtime_asset_count']}/"
            f"{report['runtime_asset_count']} available"
        )
        for path in report["missing_runtime_assets"]:
            print(f"  missing from package: {path}")
        print(
            "Full checkout verification available: "
            f"{'yes' if report['source_checkout_verification_available'] else 'no'}"
        )
        print(f"Pipeline available: {'yes' if report['pipeline_available'] else 'no'}")
        print(
            "Standalone wheel ready: "
            + (
                "yes (explicit external reader artifacts required)"
                if report["standalone_distribution_ready"]
                else "no (packaged runtime contracts are incomplete)"
            )
        )
        print(f"Pipeline phase: {report['phase']}")
        print(f"Python {report['python_version']} ({report['implementation']})")
        print(f"Python >= 3.11: {'yes' if report['python_supported'] else 'no'}")
        print("Reader backend: local open weights only")
        print("Network required: no")
    return 0 if report["pipeline_available"] else 1


def _command_prompt_verify(args: argparse.Namespace) -> int:
    root = local_input_path(args.root, role="project root")
    if not root.is_dir():
        raise CliConfigurationError(f"project root is not a directory: {root}")
    digest = verify_reader_prompt(root)
    _emit_json(
        {
            "status": "PASS",
            "prompt": str(root / "prompts" / "reader_prompt.md"),
            "sha256": digest,
            "verbatim_skill_count": 3,
        }
    )
    return 0


def _command_checkout_verify(args: argparse.Namespace) -> int:
    root = local_input_path(args.root, role="application checkout")
    if not root.is_dir():
        raise CliConfigurationError(f"application checkout is not a directory: {root}")
    report = verify_application_checkout(root)
    if args.json:
        _emit_json(report)
    else:
        print(f"{PROJECT_NAME} public checkout verification")
        print(f"Root: {report['root']}")
        for name in CHECK_NAMES:
            check = report["checks"][name]
            detail = check.get("summary") or check.get("error") or check.get("reason")
            print(f"{check['status']:>7}  {name}: {detail}")
        print(
            f"Result: {report['status']} "
            f"({report['passed_check_count']}/{report['check_count']})"
        )
        print("Requires source scans: no")
        print("Requires model/runtime files: no")
        print("Requires network access: no")
    return 0 if report["status"] == "PASS" else 1


def _command_label_validate(args: argparse.Namespace) -> int:
    results = []
    for raw_path in args.labels:
        path = local_input_path(raw_path, role="reader label")
        if not path.is_file():
            raise CliConfigurationError(f"reader label is not a file: {path}")
        label = load_grounded_reader_label(path)
        results.append(
            {
                "path": str(path),
                "label_id": label.label_id,
                "record_id": label.record_id,
                "reader_id": label.reader_id,
                "reader_family": label.reader_family,
                "schema_kind": label.schema_kind,
                "confidence_cap": label.confidence_cap,
                "source_sha256": label.source_sha256,
                "quality_metrics": paired_quality_metrics((label,)),
            }
        )
    _emit_json({"status": "PASS", "labels": results, "count": len(results)})
    return 0


def _command_consensus_merge(args: argparse.Namespace) -> int:
    left_path = local_input_path(args.left_label, role="left reader label")
    right_path = local_input_path(args.right_label, role="right reader label")
    if not left_path.is_file() or not right_path.is_file():
        raise CliConfigurationError("consensus inputs must both be label files")
    if left_path == right_path:
        raise CliConfigurationError("consensus requires two distinct label files")

    output = local_output_path(args.output, role="consensus output")
    if output in {left_path, right_path}:
        raise CliConfigurationError("consensus output must not overwrite either source label")
    if output.exists() and not args.replace_existing:
        raise CliConfigurationError(
            "consensus output already exists; pass --replace-existing to replace it atomically"
        )
    schema_path = local_input_path(args.schema, role="consensus schema")
    if not schema_path.is_file():
        raise CliConfigurationError(f"consensus schema is not a file: {schema_path}")
    if output == schema_path:
        raise CliConfigurationError("consensus output must not overwrite its schema")

    left = load_grounded_reader_label(left_path)
    right = load_grounded_reader_label(right_path)
    result = merge_labels(left, right)
    grounding_incidents = validate_cross_reader_grounding(left, right)
    findings = (
        validate_dates(result)
        + validate_formula_positions(left)
        + validate_formula_positions(right)
        + grounding_incidents
    )
    record = build_consensus_record(
        result,
        left,
        right,
        findings=findings,
        schema_ref=schema_path.name,
        workspace_root=PROJECT_ROOT,
    )
    write_consensus_record(output, record, schema_path=schema_path)
    summary = record["derivation"]["confidence_summary"]
    _emit_json(
        {
            "status": "SUCCEEDED",
            "record_id": record["record_id"],
            "output": str(output),
            "source_label_ids": list(result.reader_label_ids),
            "field_count": summary["field_count"],
            "dual_disagreement_count": summary["dual_disagreement_count"],
            "validator_finding_count": summary["validator_finding_count"],
            "groundedness_incident_count": len(grounding_incidents),
            "quality_metrics": paired_quality_metrics((left, right)),
            "arbitration_request_count": len(record["arbitration"]["requests"]),
        }
    )
    return 0


def _command_reader_inspect(args: argparse.Namespace) -> int:
    config_path = local_input_path(args.config, role="reader config")
    reader = LocalReader(load_local_reader_config(config_path))
    _emit_json(reader_report(reader))
    return 0


def _command_reader_infer(args: argparse.Namespace) -> int:
    config_path = local_input_path(args.config, role="reader config")
    reader = LocalReader(load_local_reader_config(config_path))
    scan = local_input_path(args.scan, role="input scan")
    if not scan.is_file():
        raise CliConfigurationError(f"input scan is not a file: {scan}")
    brief_path = local_input_path(args.brief, role="batch brief")
    brief = load_json_object(brief_path, role="batch brief")
    require_local_only_data(brief, location="batch brief")
    output = local_output_path(args.output, role="inference output")
    if output in {config_path, scan, brief_path}:
        raise CliConfigurationError("inference output must not overwrite any input file")
    result = reader.read(scan, batch_brief=brief)
    atomic_write_json(output, result.payload)
    stdout_path = output.with_suffix(".stdout.txt")
    stderr_path = output.with_suffix(".stderr.txt")
    atomic_write_text(stdout_path, result.stdout)
    atomic_write_text(stderr_path, result.stderr)
    _emit_json(
        {
            "status": "SUCCEEDED",
            "output": str(output),
            "raw_stdout": str(stdout_path),
            "raw_stderr": str(stderr_path),
            "runtime_fingerprint": reader.runtime_fingerprint,
            "inference_fingerprint": result.inference_fingerprint,
        }
    )
    return 0


def _command_batch_run(args: argparse.Namespace) -> int:
    config_path = local_input_path(args.config, role="reader config")
    reader = LocalReader(load_local_reader_config(config_path))
    manifest = local_input_path(args.manifest, role="batch manifest")
    manifest_payload = load_strict_json(manifest, role="batch manifest")
    require_local_only_data(manifest_payload, location="batch manifest")
    output_dir = local_output_path(args.output_dir, role="batch output directory")
    checkpoint = local_output_path(args.checkpoint, role="batch checkpoint")
    if checkpoint in {config_path, manifest}:
        raise CliConfigurationError("batch checkpoint must not overwrite config or manifest")
    jobs = load_manifest_jobs(manifest, output_root=output_dir)
    protected_inputs = {config_path, manifest, checkpoint}
    for job in jobs:
        output_path = job.output_path.resolve()
        if output_path in protected_inputs or output_path == job.scan_path.resolve():
            raise CliConfigurationError(
                f"{job.job_id}: batch output must not overwrite a scan or run-control file"
            )

    def read_job(job: BatchJob) -> Mapping[str, Any]:
        try:
            result = reader.read(job.scan_path, batch_brief=brief_for_job(job))
            atomic_write_text(job.output_path.with_suffix(".stdout.txt"), result.stdout)
            atomic_write_text(job.output_path.with_suffix(".stderr.txt"), result.stderr)
            return result.payload
        except LocalReaderError as error:
            if not error.has_process_diagnostics:
                raise
            stdout_path = job.output_path.with_suffix(".failed.stdout.txt")
            stderr_path = job.output_path.with_suffix(".failed.stderr.txt")
            atomic_write_text(stdout_path, error.stdout or "")
            atomic_write_text(stderr_path, error.stderr or "")
            raise LocalReaderError(
                f"{error}; raw_stdout={stdout_path}; raw_stderr={stderr_path}",
                stdout=error.stdout,
                stderr=error.stderr,
            ) from error

    def report_progress(progress: Any, snapshot: Any) -> None:
        payload: dict[str, Any] = {"progress": progress.as_dict()}
        if snapshot is not None:
            payload["job_id"] = snapshot.job_id
            payload["status"] = snapshot.status.value
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)

    identity = InferenceIdentity(
        model_hash=model_identity(reader),
        prompt_hash=reader.artifact_hashes["prompt"],
        schema=(
            f"label:{reader.artifact_hashes['schema']};"
            f"model:{reader.artifact_hashes.get('model_schema', reader.artifact_hashes['schema'])}"
        ),
        decoding_config={
            **generation_report(reader.config),
            "runtime_fingerprint": reader.runtime_fingerprint,
        },
    )
    runner = BatchRunner(
        jobs=jobs,
        reader=read_job,
        identity=identity,
        checkpoint_path=checkpoint,
        as_of_year=args.as_of_year,
        max_retries=args.max_retries,
        progress_callback=report_progress,
        preserve_failed_retry_history=args.rebind_failed_fingerprints,
    )
    progress = runner.run()
    report = {
        "status": (
            "COMPLETE"
            if not (progress.pending or progress.running or progress.failed or progress.interrupted)
            else "INCOMPLETE"
        ),
        "checkpoint": str(checkpoint),
        "output_dir": str(output_dir),
        "runtime_fingerprint": reader.runtime_fingerprint,
        "progress": progress.as_dict(),
        "failed_fingerprint_rebind": (
            "enabled" if args.rebind_failed_fingerprints else "disabled"
        ),
    }
    _emit_json(report)
    return 0 if report["status"] == "COMPLETE" else 1


def _command_adjudicate(args: argparse.Namespace) -> int:
    wave_id = args.wave.strip()
    if not wave_id:
        raise CliConfigurationError("--wave must be a nonblank identifier")
    wave_slug = wave_id if wave_id.casefold().startswith("wave-") else f"wave-{wave_id}"
    output_raw = args.output_dir or PROJECT_ROOT / "human_check" / "generated" / wave_slug

    if args.answers is not None:
        if args.spec is not None or args.replace_existing:
            raise CliConfigurationError(
                "--spec and --replace-existing are generation-only options"
            )
        packet_dir = local_input_path(output_raw, role="adjudication packet directory")
        if not packet_dir.is_dir():
            raise CliConfigurationError(
                f"adjudication packet directory is not a directory: {packet_dir}"
            )
        answers = local_input_path(args.answers, role="adjudication answers")
        if not answers.is_file():
            raise CliConfigurationError(f"adjudication answers is not a file: {answers}")
        report = ingest_answers(
            project_root=PROJECT_ROOT,
            packet_dir=packet_dir,
            answers_path=answers,
        )
    else:
        spec_raw = args.spec or PROJECT_ROOT / "human_check" / "waves" / f"{wave_slug}.json"
        spec = local_input_path(spec_raw, role="adjudication wave specification")
        if not spec.is_file():
            raise CliConfigurationError(
                f"adjudication wave specification is not a file: {spec}"
            )
        output_dir = local_output_path(output_raw, role="adjudication packet directory")
        if output_dir == spec or output_dir in spec.parents:
            raise CliConfigurationError(
                "adjudication output directory must not contain or overwrite its specification"
            )
        report = generate_packet(
            project_root=PROJECT_ROOT,
            spec_path=spec,
            output_dir=output_dir,
            wave_id=wave_id,
            max_questions=args.max_questions,
            replace_existing=args.replace_existing,
        )
    _emit_json(report)
    return 0

def _training_clerk_year_ids(path: Path | None) -> list[str]:
    if path is None:
        return []
    payload = load_strict_json(path, role="training clerk-year manifest")
    if isinstance(payload, dict):
        require_keys(
            payload,
            required={"clerk_year_ids"},
            location="training clerk-year manifest",
        )
        payload = payload["clerk_year_ids"]
    if not isinstance(payload, list) or not all(
        isinstance(item, str) and item.strip() for item in payload
    ):
        raise CliConfigurationError(
            "training clerk-year manifest must be a string list or "
            '{"clerk_year_ids": [...]}'
        )
    if len(payload) != len(set(payload)):
        raise CliConfigurationError("training clerk-year manifest contains duplicate IDs")
    return payload


def _command_eval(args: argparse.Namespace) -> int:
    if args.gold_dir is None or args.holdout is None:
        raise CliConfigurationError(
            "eval requires --gold-dir and --holdout outside an Application source checkout"
        )
    gold_dir = local_input_path(args.gold_dir, role="gold directory")
    if not gold_dir.is_dir():
        raise CliConfigurationError(f"gold directory is not a directory: {gold_dir}")
    gold_paths = sorted(gold_dir.glob("*.json"))
    if not gold_paths:
        raise CliConfigurationError(f"gold directory contains no JSON records: {gold_dir}")
    gold_records = [
        load_json_object(path, role=f"gold record {path.name}") for path in gold_paths
    ]
    prediction_path = local_input_path(args.predictions, role="prediction input")
    predictions = load_prediction_records(prediction_path)
    holdout_path = local_input_path(args.holdout, role="holdout manifest")
    holdout = load_json_object(holdout_path, role="holdout manifest")
    report = evaluate_predictions(
        gold_records,
        predictions,
        holdout,
        training_clerk_year_ids=_training_clerk_year_ids(args.training_clerk_years),
    )
    output = local_output_path(args.output, role="evaluation output") if args.output else None
    table_output = (
        local_output_path(args.strata_table, role="stratified table output")
        if args.strata_table
        else None
    )
    destinations = [path for path in (output, table_output) if path is not None]
    protected_inputs = {holdout_path, *gold_paths}
    if args.training_clerk_years is not None:
        protected_inputs.add(
            local_input_path(
                args.training_clerk_years,
                role="training clerk-year manifest",
            )
        )
    for destination in destinations:
        if destination in protected_inputs or _path_is_within(
            destination, prediction_path
        ) or _path_is_within(destination, gold_dir):
            raise CliConfigurationError("evaluation outputs must not overwrite any input file")
    if output is not None and output == table_output:
        raise CliConfigurationError(
            "evaluation JSON and stratified table outputs must be distinct paths"
        )
    if table_output is not None:
        atomic_write_text(table_output, render_stratified_markdown(report))
    if output is not None:
        atomic_write_json(output, report)
    _emit_json(report)
    return 0


def _path_is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _command_compare(args: argparse.Namespace) -> int:
    left_path = local_input_path(args.left, role="left comparison input")
    right_path = local_input_path(args.right, role="right comparison input")
    if left_path == right_path:
        raise CliConfigurationError("comparison requires two distinct input paths")

    if args.max_disagreements < 0:
        raise CliConfigurationError("max_disagreements must be zero or greater")

    output = local_output_path(args.output, role="comparison output") if args.output else None
    csv_output = local_output_path(args.csv, role="comparison CSV output") if args.csv else None
    destinations = [path for path in (output, csv_output) if path is not None]
    for destination in destinations:
        if _path_is_within(destination, left_path) or _path_is_within(
            destination, right_path
        ):
            raise CliConfigurationError(
                "comparison outputs must not be inside either input file or directory"
            )
    if output is not None and output == csv_output:
        raise CliConfigurationError("comparison JSON and CSV outputs must be distinct paths")

    report = compare_reader_labels(
        left_path,
        right_path,
        max_disagreements=None if csv_output is not None else args.max_disagreements,
        require_grounded=args.require_grounded,
    )
    if csv_output is not None:
        all_disagreements = report["disagreements"]["items"]
        atomic_write_text(csv_output, render_disagreements_csv(all_disagreements))
        returned = all_disagreements[: args.max_disagreements]
        report = {
            **report,
            "csv_output": str(csv_output),
            "disagreements": {
                **report["disagreements"],
                "returned": len(returned),
                "truncated": report["disagreements"]["total"] > len(returned),
                "items": returned,
            },
        }
    if output is not None:
        report = {**report, "output": str(output)}
        atomic_write_json(output, report)
    _emit_json(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run one local-only CLI command with concise, non-secret error reporting."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "doctor": _command_doctor,
        "checkout-verify": _command_checkout_verify,
        "prompt-verify": _command_prompt_verify,
        "label-validate": _command_label_validate,
        "consensus-merge": _command_consensus_merge,
        "reader-inspect": _command_reader_inspect,
        "reader-infer": _command_reader_infer,
        "batch-run": _command_batch_run,
        "adjudicate": _command_adjudicate,
        "eval": _command_eval,
        "compare": _command_compare,
    }
    if args.command is None:
        parser.print_help()
        return 0

    try:
        return handlers[args.command](args)
    except KeyboardInterrupt:
        print("aktreader: interrupted; checkpoint state was preserved", file=sys.stderr)
        return 130
    except (CliConfigurationError, LocalReaderError, OSError, TypeError, ValueError) as error:
        print(f"aktreader: error: {error}", file=sys.stderr)
        return 2
