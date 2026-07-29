import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from tools.audit_gold_attestation import build_report, render_markdown

ROOT = Path(__file__).resolve().parents[1]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_gold_attestation_audit_is_read_only_and_reports_stored_state() -> None:
    paths = tuple(sorted((ROOT / "gold" / "acts").glob("*.json")))
    before = {path: _digest(path) for path in paths}

    report = build_report(ROOT)

    assert report["policy"]["machine_transcription_support_applies"] is False
    assert report["summary"]["record_count"] == 36
    assert report["summary"]["fully_image_verified_record_count"] == 0
    assert report["summary"]["benchmark_eligible_record_count"] == 0
    assert report["summary"]["claim_count"] > 0
    assert {path: _digest(path) for path in paths} == before
    markdown = render_markdown(report)
    assert "0/36" in markdown
    assert "no per-field image reference" in markdown


def test_gold_attestation_schema_separates_image_verified_and_research() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "gold-attestation-1.0.0.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    base = {
        "$schema": "../../schemas/gold-attestation-1.0.0.schema.json",
        "schema_version": "1.0.0",
        "record_id": "serock-1890-death-6",
        "record_sha256": "a" * 64,
        "field_attestations": {
            "principal.name": {
                "evidence_class": "VERIFIED_FROM_IMAGE",
                "image_reference": {
                    "artifact_sha256": "b" * 64,
                    "act_locator": "act 6",
                },
                "attestation": {
                    "attestor_id": "owner",
                    "method": "LETTERFORM_LINEUP",
                    "attested_at": "2026-07-28T22:15:00-04:00",
                    "verbatim_answer": "those are clearly different endings",
                    "adjudication_packet_sha256": None,
                },
                "benchmark_eligible": True,
            }
        },
    }
    assert list(validator.iter_errors(base)) == []

    invalid = json.loads(json.dumps(base))
    field = invalid["field_attestations"]["principal.name"]
    field["evidence_class"] = "DERIVED_FROM_RESEARCH"
    assert list(validator.iter_errors(invalid))
