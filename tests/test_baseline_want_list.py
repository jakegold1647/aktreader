import json
from pathlib import Path

from tools.build_baseline_want_list import build_want_list

ROOT = Path(__file__).resolve().parents[1]
WANT_LIST = ROOT / "examples" / "p2-baseline.want-list.json"


def test_want_list_is_deterministic_and_covers_every_not_localized_gold_record() -> None:
    payload = json.loads(WANT_LIST.read_text(encoding="utf-8"))

    assert payload == build_want_list()
    assert payload["network_actions_performed"] is False
    assert payload["summary"] == {
        "not_localized_total": 12,
        "ready_for_owner_fetch": 0,
        "source_object_415": 5,
        "collection_mapping_required": 7,
    }

    expected = set()
    for path in (ROOT / "gold" / "acts").glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["artifact"]["status"] == "NOT_LOCALIZED":
            expected.add(record["record_id"])
    assert {record["record_id"] for record in payload["records"]} == expected


def test_serock_routes_are_exact_and_pultusk_routes_fail_closed() -> None:
    payload = json.loads(WANT_LIST.read_text(encoding="utf-8"))
    by_id = {record["record_id"]: record for record in payload["records"]}

    assert by_id["serock-1882-birth-2"]["skanoteka"]["file_range"] == "01-02"
    assert by_id["serock-1903-marriage-23"]["skanoteka"]["file_range"] == "23-26"
    assert by_id["serock-1902-marriage-3"]["skanoteka"]["sy"] == 1900

    source_object_415 = {
        "serock-1882-birth-2",
        "serock-1899-birth-5",
        "serock-1899-birth-6",
        "serock-1902-marriage-3",
        "serock-1903-marriage-23",
    }
    for record_id in source_object_415:
        assert by_id[record_id]["status"] == "NOT_LOCALIZED"
        assert by_id[record_id]["reason"] == "SOURCE_OBJECT_415"

    for record in payload["records"]:
        if record["register"]["fond"] == "84":
            assert record["status"] == "COLLECTION_MAPPING_REQUIRED"
            assert record["skanoteka"] is None
