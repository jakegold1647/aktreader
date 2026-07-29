"""Strictly local command-line interface for the P2 pipeline."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aktreader import __version__
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
from aktreader.consensus import merge_labels
from aktreader.consensus_record import build_consensus_record, write_consensus_record
from aktreader.evaluation import evaluate_predictions, load_prediction_records
from aktreader.grounding import (
    load_grounded_reader_label,
    paired_quality_metrics,
    validate_cross_reader_grounding,
)
from aktreader.local_reader import LocalReader, LocalReaderError
from aktreader.prompt import verify_reader_prompt
from aktreader.validators.dates import validate_dates
from aktreader.validators.formula import validate_formula_positions

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _emit_json(payload: Mapping[str, Any], *, stream: Any = None) -> None:
    print(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        file=sys.stdout if stream is None else stream,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the local-only parser without import-time runtime execution."""
    parser = argparse.ArgumentParser(
        prog="aktreader",
        description="Local-only, uncertainty-honest civil-register extraction (P2).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    doctor = subparsers.add_parser("doctor", help="report the local pipeline environment")
    doctor.add_argument("--json", action="store_true", help="emit machine-readable JSON")

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
        default=PROJECT_ROOT / "schemas" / "act-record-2.0.0.schema.json",
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

    evaluate = subparsers.add_parser(
        "eval", help="generate the clerk-year-sequestered SerockBench report"
    )
    evaluate.add_argument("--predictions", required=True, type=Path)
    evaluate.add_argument("--gold-dir", type=Path, default=PROJECT_ROOT / "gold" / "acts")
    evaluate.add_argument(
        "--holdout",
        type=Path,
        default=PROJECT_ROOT / "gold" / "clerk_year_holdout.json",
    )
    evaluate.add_argument("--training-clerk-years", type=Path)
    evaluate.add_argument("--output", type=Path)
    return parser


def environment_report() -> dict[str, object]:
    """Return deterministic facts useful at the P2 gate."""
    supported = sys.version_info >= (3, 10)
    return {
        "aktreader_version": __version__,
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_supported": supported,
        "phase": "P2",
        "pipeline_available": True,
        "reader_backend": "local-open-weights-only",
        "network_required": False,
    }


def _command_doctor(args: argparse.Namespace) -> int:
    report = environment_report()
    if args.json:
        _emit_json(report)
    else:
        print(f"AKTREADER {report['aktreader_version']} ({report['phase']} local pipeline)")
        print(f"Python {report['python_version']} ({report['implementation']})")
        print(f"Python >= 3.10: {'yes' if report['python_supported'] else 'no'}")
        print("Reader backend: local open weights only")
        print("Network required: no")
    return 0 if report["python_supported"] else 1


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
    if args.output is not None:
        output = local_output_path(args.output, role="evaluation output")
        protected_inputs = {prediction_path, holdout_path, *gold_paths}
        if args.training_clerk_years is not None:
            protected_inputs.add(
                local_input_path(
                    args.training_clerk_years,
                    role="training clerk-year manifest",
                )
            )
        if output in protected_inputs:
            raise CliConfigurationError("evaluation output must not overwrite any input file")
        atomic_write_json(output, report)
    _emit_json(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run one local-only CLI command with concise, non-secret error reporting."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "doctor": _command_doctor,
        "prompt-verify": _command_prompt_verify,
        "label-validate": _command_label_validate,
        "consensus-merge": _command_consensus_merge,
        "reader-inspect": _command_reader_inspect,
        "reader-infer": _command_reader_infer,
        "batch-run": _command_batch_run,
        "eval": _command_eval,
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
