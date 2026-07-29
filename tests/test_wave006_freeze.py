import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELAY = ROOT / "coordination" / "wave006_artifacts.json"
SPEC = ROOT / "coordination" / "wave006_brief_spec.json"
BRIEFS = ROOT / "coordination" / "wave006_briefs.json"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_wave006_briefs_match_coordinator_relay_and_v14_contract() -> None:
    relay = _load(RELAY)
    spec = _load(SPEC)
    briefs = _load(BRIEFS)

    assert spec["blind_group_id"] == relay["blind_group_id"]
    assert spec["prompt"]["version"] == relay["prompt_version"] == "1.4.0"
    assert spec["prompt"]["sha256"] == relay["prompt_sha256"]
    assert spec["act_range"] == {"start": 1, "end": 10}
    assert briefs["artifact_verification"] == {
        "basis": "COORDINATOR_RELAYED_PINS",
        "bytes_reverified": False,
    }
    assert briefs["independence"] == {
        "correlated_blind_spots_possible": True,
        "distinct_model_families": False,
        "distinct_reader_ids": True,
    }

    relay_by_act = {}
    for artifact in relay["artifacts"]:
        for act_no in artifact["acts_covered"]:
            relay_by_act[act_no] = artifact

    for key in ("reader_a", "reader_b"):
        records = briefs[key]
        assert [record["target"]["act_no"] for record in records] == list(range(1, 11))
        for record in records:
            act_no = record["target"]["act_no"]
            artifact = relay_by_act[act_no]
            assert record["$schema"] == relay["label_schema"]
            assert record["prompt"] == spec["prompt"]
            assert record["target"]["language"] == "pl"
            assert record["reader"]["other_reader_output_seen"] is False
            assert record["artifact"]["path"] == artifact["path"]
            assert record["artifact"]["sha256"] == artifact["sha256"]
            assert record["artifact"]["width_px"] == artifact["width_px"]
            assert record["artifact"]["height_px"] == artifact["height_px"]
            assert record["artifact"]["page_index"] == artifact["page_index"]
