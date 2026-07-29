import hashlib
import json
from pathlib import Path

from tools.build_silver_manifest import build_manifest
from tools.silver_records import build_record

from aktreader.schema import validate_instance

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "labels" / "silver" / "manifest.json"
SCHEMA = ROOT / "schemas" / "silver-tier-manifest-1.0.0.schema.json"
RECORD_SCHEMA = ROOT / "schemas" / "silver-record-1.0.0.schema.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_silver_manifest_is_schema_valid_and_deterministic() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))

    validate_instance(payload, SCHEMA)
    assert payload == build_manifest()


def test_silver_is_training_only_and_act_six_is_untiered() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    records = payload["records"]

    assert [record["record_id"] for record in records] == [
        f"serock-1890-death-{act_no}" for act_no in range(1, 6)
    ]
    assert all(record["tier"] == "SILVER" for record in records)
    assert all(record["training_eligible"] is True for record in records)
    assert all(record["training_materialized"] is True for record in records)
    assert all(record["eval_eligible"] is False for record in records)
    assert all(record["human_verified"] is False for record in records)
    assert payload["quarantine"][0]["record_id"] == "serock-1890-death-6"
    assert payload["quarantine"][0]["tier"] is None
    assert payload["quarantine"][0]["training_eligible"] is False


def test_every_silver_provenance_pin_matches_frozen_source_bytes() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for record in [*payload["records"], *payload["quarantine"]]:
        provenance = record["provenance"]
        sources = [
            *provenance["source_labels"],
            provenance["consensus_document"],
            provenance["arbitration_document"],
        ]
        for source in sources:
            assert _sha256(ROOT / source["path"]) == source["sha256"]


def test_materialized_records_are_schema_valid_deterministic_and_content_addressed() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for act_no, entry in enumerate(manifest["records"], start=1):
        resolved = entry["resolved_fields"]
        path = ROOT / resolved["path"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        validate_instance(payload, RECORD_SCHEMA)
        assert payload == build_record(act_no)
        assert _sha256(path) == resolved["sha256"]
        assert payload["record_id"] == entry["record_id"]
        assert payload["clerk_year"]["id"] == entry["clerk_year_id"]
        assert payload["tier"] == "SILVER"
        assert payload["resolution"]["method"] == entry["resolution_method"]
        assert payload["resolution"]["confidence_cap"] == entry["confidence_cap"]
