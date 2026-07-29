"""Read-only audit of the human-attestation contract for benchmark gold."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

AUDIT_VERSION = "1.0.0"
CONTRACT_VERSION = "1.0.0"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _walk_claims(value: Any, path: str, output: dict[str, Mapping[str, Any]]) -> None:
    if isinstance(value, Mapping) and {"value", "observation_state"}.issubset(value):
        if value.get("observation_state") != "NOT_ANNOTATED":
            output[path] = value
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            _walk_claims(child, f"{path}.{key}" if path else str(key), output)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_claims(child, f"{path}.{index}" if path else str(index), output)


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected one JSON object")
    return payload


def build_report(root: Path) -> dict[str, Any]:
    """Audit all stored gold acts without modifying a record or inventing attestations."""
    root = root.resolve()
    schema_path = root / "schemas" / "gold-attestation-1.0.0.schema.json"
    schema = _load_object(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    attestation_dir = root / "gold" / "attestations"
    record_reports: list[dict[str, Any]] = []

    for record_path in sorted((root / "gold" / "acts").glob("*.json")):
        record = _load_object(record_path)
        claims: dict[str, Mapping[str, Any]] = {}
        _walk_claims(record.get("fields", {}), "", claims)
        sidecar_path = attestation_dir / f"{record_path.stem}.json"
        sidecar: dict[str, Any] | None = None
        schema_errors: list[str] = []
        if sidecar_path.is_file():
            sidecar = _load_object(sidecar_path)
            errors = sorted(
                validator.iter_errors(sidecar),
                key=lambda item: list(item.path),
            )
            schema_errors = [
                f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: "
                f"{error.message}"
                for error in errors
            ]
            if sidecar.get("record_id") != record.get("record_id"):
                schema_errors.append("record_id: does not match gold record")
            if sidecar.get("record_sha256") != _sha256_file(record_path):
                schema_errors.append("record_sha256: does not match gold record bytes")

        attestations = (
            sidecar.get("field_attestations", {})
            if sidecar is not None and not schema_errors
            else {}
        )
        if not isinstance(attestations, Mapping):
            attestations = {}
        claim_paths = set(claims)
        attested_paths = claim_paths.intersection(attestations)
        verified_paths = {
            path
            for path in attested_paths
            if attestations[path].get("evidence_class") == "VERIFIED_FROM_IMAGE"
            and attestations[path].get("benchmark_eligible") is True
        }
        research_paths = {
            path
            for path in attested_paths
            if attestations[path].get("evidence_class") == "DERIVED_FROM_RESEARCH"
        }
        missing = sorted(claim_paths - attested_paths)
        unexpected = sorted(set(attestations) - claim_paths)
        fully_verified = bool(claim_paths) and verified_paths == claim_paths
        record_reports.append(
            {
                "record_id": record.get("record_id", record_path.stem),
                "path": record_path.relative_to(root).as_posix(),
                "sha256": _sha256_file(record_path),
                "attestation_sidecar": (
                    sidecar_path.relative_to(root).as_posix() if sidecar_path.is_file() else None
                ),
                "schema_errors": schema_errors,
                "claim_count": len(claim_paths),
                "attested_claim_count": len(attested_paths),
                "image_verified_claim_count": len(verified_paths),
                "research_derived_claim_count": len(research_paths),
                "benchmark_eligible_claim_count": len(verified_paths),
                "missing_field_attestations": missing,
                "unexpected_field_attestations": unexpected,
                "fully_image_verified": fully_verified,
                "benchmark_eligible": fully_verified,
            }
        )

    total_claims = sum(record["claim_count"] for record in record_reports)
    attested_claims = sum(record["attested_claim_count"] for record in record_reports)
    verified_claims = sum(record["image_verified_claim_count"] for record in record_reports)
    fully_verified_records = sum(record["fully_image_verified"] for record in record_reports)
    return {
        "audit_version": AUDIT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "policy": {
            "machine_transcription_support_applies": False,
            "gold_requirement": (
                "Every asserted gold field requires an artifact hash plus region or act locator, "
                "and a dated human attestation. Research-derived fields are not benchmark truth."
            ),
            "labels_modified": False,
        },
        "summary": {
            "record_count": len(record_reports),
            "claim_count": total_claims,
            "attested_claim_count": attested_claims,
            "image_verified_claim_count": verified_claims,
            "fully_image_verified_record_count": fully_verified_records,
            "benchmark_eligible_record_count": fully_verified_records,
            "attestation_coverage_rate": (
                round(attested_claims / total_claims, 6) if total_claims else 1.0
            ),
            "image_verified_claim_rate": (
                round(verified_claims / total_claims, 6) if total_claims else 1.0
            ),
        },
        "records": record_reports,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Gold attestation audit — 2026-07-29",
        "",
        "This is a read-only audit under the gold-specific contract. Machine-reader continuous",
        "transcription support is intentionally not applied to human gold.",
        "",
        "## Result",
        "",
        f"- Stored gold acts audited: **{summary['record_count']}**",
        f"- Asserted fields: **{summary['claim_count']}**",
        f"- Fields with contract-valid attestations: **{summary['attested_claim_count']}**",
        f"- Fields verified directly from images: **{summary['image_verified_claim_count']}**",
        (
            "- Fully image-verified, benchmark-eligible acts: "
            f"**{summary['fully_image_verified_record_count']}/{summary['record_count']}**"
        ),
        "",
        "The honest stored-state result is zero benchmark-eligible acts. The existing records",
        "carry research-note provenance but no per-field image reference and dated attestation",
        "sidecars. The 28 July human packet verified acts 6, 34, and 39, but those acts have not",
        "been materialized in `gold/acts`; the audit does not infer or backfill attestations.",
        "",
        "The earlier machine-reader retro-audit's 0% transcription score for gold is void as a",
        "gold-quality judgment. This audit supersedes that interpretation while preserving the",
        "original read-only measurement.",
        "",
        "## Benchmark limitation",
        "",
        "The reported P2 baseline remains a measurement against the frozen 36-record corpus, but",
        "that corpus is research-derived and currently has no contract-valid image-attested acts.",
        "Its accuracy figures must not be presented as publication-grade image-verified benchmark",
        "truth until adjudication sidecars satisfy this contract.",
        "",
    ]
    return "\n".join(lines)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_report(args.root)
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.json_output:
        _atomic_write(args.json_output, serialized)
    if args.markdown_output:
        _atomic_write(args.markdown_output, render_markdown(report))
    if not args.json_output and not args.markdown_output:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
