import json
from pathlib import Path

from aktreader.comparison import compare_reader_labels

ROOT = Path(__file__).resolve().parents[1]
READER_B = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"


def test_compare_reports_field_disagreement_without_inference(tmp_path: Path) -> None:
    left_payload = json.loads(READER_B.read_text(encoding="utf-8"))
    right_payload = json.loads(READER_B.read_text(encoding="utf-8"))
    right_payload["label_id"] = "synthetic.reader-right"
    right_payload["observations"]["principal.name"]["value"] = "[unclear: Different reading]"

    left_path = tmp_path / "left.json"
    right_path = tmp_path / "right.json"
    left_path.write_text(json.dumps(left_payload, ensure_ascii=False), encoding="utf-8")
    right_path.write_text(json.dumps(right_payload, ensure_ascii=False), encoding="utf-8")

    report = compare_reader_labels(left_path, right_path, max_disagreements=1)

    assert report["status"] == "PASS"
    assert report["network_used"] is False
    assert report["records"]["common"] == 1
    assert report["fields"]["counts"]["VALUE_DISAGREEMENT"] == 1
    assert report["disagreements"]["total"] == 1
    assert report["disagreements"]["items"][0]["field_path"] == "principal.name"
