"""Validation helpers for the P1 gold corpus."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

EVIDENCE_KEYS = {
    "value",
    "original_script",
    "confidence",
    "observation_state",
    "alternatives",
    "source_spans",
    "transcription_status",
}
CONFIDENCE = {"CONFIDENT", "PROBABLE", "UNCLEAR"}
OBSERVATION_STATES = {
    "PRESENT",
    "ABSENT_ON_FORM",
    "BLANK",
    "STATED_UNKNOWN",
    "ILLEGIBLE",
    "NOT_ANNOTATED",
}
FORBIDDEN_GOLD_SOURCES = ("yad vashem", "ushmm", "arolsen")


class GoldValidationError(ValueError):
    """Raised when a gold record violates the evidence contract."""


def sha256_file(path: Path) -> str:
    """Return a file's SHA-256 digest without modifying it."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_gold_records(root: Path) -> list[dict[str, Any]]:
    """Load every generated act record in stable filename order."""
    acts_dir = root / "gold" / "acts"
    return [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(acts_dir.glob("*.json"))
    ]


def _is_evidence_field(value: Any) -> bool:
    return isinstance(value, dict) and EVIDENCE_KEYS.issubset(value)


def _validate_evidence(field: dict[str, Any], location: str) -> None:
    missing = EVIDENCE_KEYS - set(field)
    if missing:
        raise GoldValidationError(f"{location}: missing evidence keys {sorted(missing)}")

    state = field["observation_state"]
    confidence = field["confidence"]
    value = field["value"]
    alternatives = field["alternatives"]

    if state not in OBSERVATION_STATES:
        raise GoldValidationError(f"{location}: invalid observation_state {state!r}")
    if confidence is not None and confidence not in CONFIDENCE:
        raise GoldValidationError(f"{location}: invalid confidence {confidence!r}")

    if state == "PRESENT" and value is None:
        raise GoldValidationError(f"{location}: PRESENT requires a value")
    if state == "NOT_ANNOTATED" and (value is not None or confidence is not None):
        raise GoldValidationError(f"{location}: NOT_ANNOTATED must not invent a value or grade")
    if state in {"ABSENT_ON_FORM", "BLANK", "STATED_UNKNOWN", "ILLEGIBLE"} and value is not None:
        raise GoldValidationError(f"{location}: {state} must use a null normalized value")
    if confidence == "UNCLEAR":
        if not isinstance(value, str) or not value.startswith("[unclear: "):
            raise GoldValidationError(f"{location}: UNCLEAR must use the [unclear: X/Y] convention")
        if not alternatives:
            raise GoldValidationError(f"{location}: UNCLEAR must retain alternatives")
    if state != "NOT_ANNOTATED" and not field["source_spans"]:
        raise GoldValidationError(f"{location}: annotated evidence requires a source span")


def _walk_fields(value: Any, location: str) -> None:
    if _is_evidence_field(value):
        _validate_evidence(value, location)
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _walk_fields(child, f"{location}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _walk_fields(child, f"{location}[{index}]")
        return
    raise GoldValidationError(f"{location}: schema leaf is not an evidence field")


def validate_gold_record(record: dict[str, Any]) -> None:
    """Validate one act record against P1's source and uncertainty rules."""
    required = {
        "$schema",
        "schema_version",
        "record_id",
        "register",
        "artifact",
        "provenance",
        "annotation",
        "privacy",
        "fields",
        "authority_warning",
    }
    missing = required - set(record)
    if missing:
        raise GoldValidationError(
            f"{record.get('record_id', '<unknown>')}: missing {sorted(missing)}"
        )

    record_id = record["record_id"]
    if record["schema_version"] != "1.0.0":
        raise GoldValidationError(f"{record_id}: unsupported schema version")
    if record["authority_warning"] != "extraction is not authority — verify against the scan":
        raise GoldValidationError(f"{record_id}: authority warning changed or missing")
    if record["provenance"].get("restricted_sources_used") is not False:
        raise GoldValidationError(
            f"{record_id}: restricted-source provenance must be explicitly false"
        )

    serialized_provenance = json.dumps(record["provenance"], ensure_ascii=False).lower()
    for forbidden in FORBIDDEN_GOLD_SOURCES:
        if forbidden in serialized_provenance:
            raise GoldValidationError(f"{record_id}: prohibited source appears in provenance")

    consent = record["annotation"]["correction_consent"]
    if consent["status"] != "GRANTED" and consent["training_eligible"] is not False:
        raise GoldValidationError(f"{record_id}: training requires explicit correction consent")
    if record["annotation"].get("expert_verified") is not False:
        raise GoldValidationError(f"{record_id}: imported project notes are not expert-tier labels")

    _walk_fields(record["fields"], f"{record_id}.fields")


def validate_corpus(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate uniqueness and return a compact coverage summary."""
    for record in records:
        validate_gold_record(record)

    ids = [record["record_id"] for record in records]
    if len(ids) != len(set(ids)):
        duplicates = [key for key, count in Counter(ids).items() if count > 1]
        raise GoldValidationError(f"duplicate record IDs: {duplicates}")

    return {
        "total": len(records),
        "towns": dict(sorted(Counter(record["register"]["town"] for record in records).items())),
        "languages": dict(
            sorted(Counter(record["register"]["language"] for record in records).items())
        ),
        "act_types": dict(
            sorted(Counter(record["fields"]["act_type"]["value"] for record in records).items())
        ),
    }
