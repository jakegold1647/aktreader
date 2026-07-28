import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "examples" / "p2-baseline.jobs.json"
GOLD_ACTS = ROOT / "gold" / "acts"


def _gold() -> dict[str, dict]:
    return {
        payload["record_id"]: payload
        for path in sorted(GOLD_ACTS.glob("*.json"))
        if isinstance(payload := json.loads(path.read_text(encoding="utf-8")), dict)
    }


def test_baseline_manifest_truthfully_separates_localized_gold() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    gold = _gold()
    localized = {key for key, value in gold.items() if value["artifact"]["status"] == "LOCAL"}
    excluded = set(gold) - localized

    assert manifest["scope"] == {
        "gold_records": 36,
        "scan_backed_jobs": 17,
        "not_localized_exclusions": 19,
        "coverage_ceiling": "17/36",
    }
    assert {job["id"] for job in manifest["jobs"]} == localized
    assert {item["record_id"] for item in manifest["excluded"]} == excluded


def test_baseline_jobs_bind_gold_artifact_target_and_clerk_year() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    gold = _gold()

    for job in manifest["jobs"]:
        record = gold[job["id"]]
        brief = job["metadata"]["batch_brief"]
        region = brief["artifact"]["act_region"]
        assert job["scan"] == record["artifact"]["path"]
        assert brief["artifact"]["sha256"] == record["artifact"]["sha256"]
        assert brief["clerk_year"] == record["register"]["clerk_year"]
        assert brief["target"]["act_no"] == record["register"]["act_no"]
        assert job["target"] == {"kind": "act", "act_no": record["register"]["act_no"]}
        assert region == {
            "x": 0,
            "y": 0,
            "width": brief["artifact"]["width_px"],
            "height": brief["artifact"]["height_px"],
            "coordinate_space": "source_pixels",
        }
        assert brief["compliance"]["training_eligible"] is False
