import hashlib
import json
from pathlib import Path

from tools.build_silver_manifest import build_manifest

from aktreader.schema import validate_instance

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "labels" / "silver" / "manifest.json"
SCHEMA = ROOT / "schemas" / "silver-tier-manifest-1.0.0.schema.json"


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
    assert all(record["training_materialized"] is False for record in records)
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
