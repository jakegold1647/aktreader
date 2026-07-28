"""Build deterministic per-act JSON files from source-faithful P1 definitions."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from aktreader.gold import sha256_file, validate_corpus
from tools.gold_pultusk import ACT_SPECS as PULTUSK_ACTS
from tools.gold_serock import ACT_SPECS as SEROCK_ACTS

ROOT = Path(__file__).resolve().parents[1]
ACTS_DIR = ROOT / "gold" / "acts"
SCHEMA_REF = "../schema.json"

PERSON_KEYS = (
    "name",
    "maiden_name",
    "age",
    "occupation",
    "residence",
    "birthplace",
    "sex",
    "marital_status",
    "relationship",
)


def not_annotated() -> dict[str, Any]:
    return {
        "value": None,
        "original_script": None,
        "confidence": None,
        "observation_state": "NOT_ANNOTATED",
        "alternatives": [],
        "source_spans": [],
        "transcription_status": "NOT_APPLICABLE",
    }


def person() -> dict[str, Any]:
    return {key: not_annotated() for key in PERSON_KEYS}


def fields_template() -> dict[str, Any]:
    return {
        "act_type": not_annotated(),
        "act_no": not_annotated(),
        "year": not_annotated(),
        "registration_date": not_annotated(),
        "event_date": not_annotated(),
        "town": not_annotated(),
        "principal": person(),
        "father": person(),
        "mother": person(),
        "spouse": person(),
        "spouse_parents": {"father": person(), "mother": person()},
        "declarants": [],
        "witnesses": [],
        "officiant": not_annotated(),
        "signatures_note": not_annotated(),
        "marginalia": not_annotated(),
        "deceased_left_behind": not_annotated(),
        "banns_dates": [],
        "permission_notes": not_annotated(),
        "prenup_note": not_annotated(),
        "rabbi": not_annotated(),
    }


def evidence(value: Any, source_note: str, locator: str) -> dict[str, Any]:
    marker = value if isinstance(value, dict) and value.get("__evidence__") else {"value": value}
    original_script = marker.get("original_script")
    state = marker.get("observation_state", "PRESENT")
    return {
        "value": marker.get("value"),
        "original_script": original_script,
        "confidence": marker.get("confidence", "PROBABLE"),
        "observation_state": state,
        "alternatives": marker.get("alternatives", []),
        "source_spans": [{"kind": "research_note", "source_note": source_note, "locator": locator}],
        "transcription_status": (
            "PRESERVED" if original_script is not None else "NOT_RECORDED_IN_SOURCE_NOTE"
        ),
    }


def materialize(value: Any, source_note: str, locator: str) -> Any:
    if isinstance(value, dict) and value.get("__evidence__"):
        return evidence(value, source_note, locator)
    if isinstance(value, dict):
        return {key: materialize(child, source_note, locator) for key, child in value.items()}
    if isinstance(value, list):
        return [materialize(child, source_note, locator) for child in value]
    return evidence(value, source_note, locator)


def apply_updates(
    base: dict[str, Any], updates: dict[str, Any], source_note: str, locator: str
) -> None:
    for key, raw_value in updates.items():
        if key not in base:
            raise KeyError(f"unknown field path component: {key}")
        if isinstance(base[key], dict) and "value" in base[key]:
            base[key] = evidence(raw_value, source_note, locator)
        elif isinstance(base[key], dict) and isinstance(raw_value, dict):
            apply_updates(base[key], raw_value, source_note, locator)
        else:
            base[key] = materialize(raw_value, source_note, locator)


def make_record(spec: dict[str, Any]) -> dict[str, Any]:
    source_note = Path(spec["source_note"])
    if not source_note.is_file():
        raise FileNotFoundError(source_note)

    artifact_path = Path(spec["artifact_path"]) if spec.get("artifact_path") else None
    if artifact_path is not None and not artifact_path.is_file():
        raise FileNotFoundError(artifact_path)

    locator = spec["source_locator"]
    fields = fields_template()
    automatic = {
        "act_type": spec["act_type"],
        "act_no": spec["act_no"],
        "year": spec["year"],
        "town": spec["town"],
    }
    apply_updates(fields, {**automatic, **spec["facts"]}, str(source_note), locator)

    return {
        "$schema": SCHEMA_REF,
        "schema_version": "1.1.0",
        "record_id": spec["record_id"],
        "register": {
            "town": spec["town"],
            "fond": spec["fond"],
            "year": spec["year"],
            "act_type": spec["act_type"],
            "act_no": spec["act_no"],
            "language": spec.get("language", "ru"),
            "clerk_year": clerk_year(spec),
        },
        "artifact": {
            "status": "LOCAL" if artifact_path is not None else "NOT_LOCALIZED",
            "path": str(artifact_path) if artifact_path is not None else None,
            "sha256": sha256_file(artifact_path) if artifact_path is not None else None,
            "source_spans_captured": False,
        },
        "provenance": {
            "source_note": str(source_note),
            "source_note_sha256": sha256_file(source_note),
            "source_locator": locator,
            "source_author": spec["source_author"],
            "restricted_sources_used": False,
        },
        "annotation": {
            "tier": "PROJECT_VERIFIED_RESEARCH_NOTE",
            "expert_verified": False,
            "evaluation_eligible": True,
            "correction_consent": {"status": "NOT_RECORDED", "training_eligible": False},
            "correction_history": [],
        },
        "privacy": {
            "decision": "ALLOW",
            "basis": "pre-1915 civil act; older than the configured 100-year default",
            "evaluated_on": "2026-07-28",
        },
        "fields": fields,
        "authority_warning": "extraction is not authority — verify against the scan",
    }


def clerk_year(spec: dict[str, Any]) -> dict[str, Any]:
    """Return a conservative handwriting-group proxy without claiming a known clerk."""
    normalized_town = unicodedata.normalize("NFKD", spec["town"])
    town_slug = "".join(character for character in normalized_town if character.isascii())
    town_slug = "-".join(town_slug.lower().split())
    fond_slug = spec["fond"].replace("/", "-")
    return {
        "id": f"{fond_slug}|{town_slug}|{spec['year']}|clerk-unknown",
        "basis": "REGISTER_YEAR_PROXY",
        "clerk_id": None,
    }


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    specs = SEROCK_ACTS + PULTUSK_ACTS
    expected_names = {f"{spec['record_id']}.json" for spec in specs}
    ACTS_DIR.mkdir(parents=True, exist_ok=True)
    unexpected = {path.name for path in ACTS_DIR.glob("*.json")} - expected_names
    if unexpected:
        raise RuntimeError(f"refusing to delete unexpected gold files: {sorted(unexpected)}")

    records = [make_record(spec) for spec in specs]
    coverage = validate_corpus(records)
    for record in records:
        write_json(ACTS_DIR / f"{record['record_id']}.json", record)

    manifest = {
        "schema_version": "1.1.0",
        "built_on": "2026-07-28",
        "coverage": coverage,
        "restricted_sources_used": False,
        "serock_seeded": True,
        "known_gaps": [
            {
                "target": "Polish-language acts",
                "status": "UNMET",
                "reason": (
                    "No independently verified permitted Polish act was available; "
                    "tentative memorial-derived material was excluded."
                ),
            }
        ],
        "training_eligibility": "NONE_WITHOUT_RECORDED_CORRECTOR_CONSENT",
    }
    write_json(ROOT / "gold" / "manifest.json", manifest)

    holdout = {
        "schema_version": "1.0.0",
        "policy": "CLERK_YEAR_SEQUESTERED_EVALUATION_ONLY",
        "created_on": "2026-07-28",
        "holdout_clerk_year_ids": sorted(
            {record["register"]["clerk_year"]["id"] for record in records}
        ),
        "record_ids": sorted(record["record_id"] for record in records),
        "training_overlap_allowed": False,
        "note": (
            "All P1 gold records are evaluation-only and correction consent is not recorded; "
            "future training exports must reject every listed clerk-year."
        ),
    }
    write_json(ROOT / "gold" / "clerk_year_holdout.json", holdout)

    spot_ids = [
        "serock-1876-marriage-11",
        "serock-1883-birth-28",
        "serock-1884-death-8",
        "serock-1888-death-37",
        "serock-1903-death-6",
    ]
    by_id = {record["record_id"]: record for record in records}
    spot_check = {
        "instructions": (
            "Compare each JSON field only to the cited research-note section and local scan. "
            "Do not fill omitted fields."
        ),
        "records": [
            {
                "record_id": record_id,
                "json": f"gold/acts/{record_id}.json",
                "artifact": by_id[record_id]["artifact"]["path"],
                "source_note": by_id[record_id]["provenance"]["source_note"],
                "source_locator": by_id[record_id]["provenance"]["source_locator"],
            }
            for record_id in spot_ids
        ],
    }
    write_json(ROOT / "gold" / "spot_check.json", spot_check)
    print(json.dumps(coverage, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
