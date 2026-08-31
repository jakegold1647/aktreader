import csv
import io
import json
from pathlib import Path

from aktreader.cli import main
from aktreader.comparison import (
    CSV_FIELDNAMES,
    _label_paths,
    compare_reader_labels,
    render_disagreements_csv,
)

ROOT = Path(__file__).resolve().parents[1]
READER_B = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"
READER_A_DIR = ROOT / "labels" / "readerA"
READER_B_DIR = ROOT / "labels" / "readerB"


def test_label_discovery_uses_platform_independent_path_order(tmp_path: Path) -> None:
    payload = READER_B.read_text(encoding="utf-8")
    upper = tmp_path / "B.json"
    lower = tmp_path / "a.json"
    upper.write_text(payload, encoding="utf-8")
    lower.write_text(payload, encoding="utf-8")

    paths, ignored = _label_paths(tmp_path)

    assert paths == [upper, lower]
    assert ignored == []


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


def test_compare_can_return_every_disagreement_for_complete_exports(tmp_path: Path) -> None:
    left_payload = json.loads(READER_B.read_text(encoding="utf-8"))
    right_payload = json.loads(READER_B.read_text(encoding="utf-8"))
    right_payload["label_id"] = "synthetic.reader-right"
    right_payload["observations"]["principal.name"]["value"] = (
        "[unclear: Different name/Other name]"
    )
    right_payload["observations"]["principal.age"]["value"] = "99 years"

    left_path = tmp_path / "left.json"
    right_path = tmp_path / "right.json"
    left_path.write_text(json.dumps(left_payload, ensure_ascii=False), encoding="utf-8")
    right_path.write_text(json.dumps(right_payload, ensure_ascii=False), encoding="utf-8")

    report = compare_reader_labels(left_path, right_path, max_disagreements=None)

    assert report["disagreements"]["total"] == 2
    assert report["disagreements"]["returned"] == 2
    assert report["disagreements"]["truncated"] is False
    assert [item["field_path"] for item in report["disagreements"]["items"]] == [
        "principal.age",
        "principal.name",
    ]


def test_csv_is_utf8_bom_formula_safe_and_preserves_unicode() -> None:
    rendered = render_disagreements_csv(
        [
            {
                "record_id": "=2+2",
                "field_path": "principal.name",
                "kind": "VALUE_DISAGREEMENT",
                "left": {
                    "observation_state": "PRESENT",
                    "value": " =HYPERLINK(\"https://invalid.example\")",
                    "confidence": "+SUM(1,1)",
                    "original_script": "@Сроль",
                },
                "right": {
                    "observation_state": "PRESENT",
                    "value": ["Żółć", "Гольдштейнъ"],
                    "confidence": "HIGH",
                    "original_script": "Гольдштейнъ",
                },
            }
        ]
    )

    assert rendered.encode("utf-8").startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(rendered.removeprefix("\ufeff"))))
    assert len(rows) == 1
    row = rows[0]
    assert row["record_id"] == "'=2+2"
    assert row["left_value"].startswith("' =HYPERLINK")
    assert row["left_confidence"] == "'+SUM(1,1)"
    assert row["left_original_script"] == "'@Сроль"
    assert row["right_value"] == '["Żółć","Гольдштейнъ"]'
    assert row["right_original_script"] == "Гольдштейнъ"


def test_empty_csv_has_only_the_stable_header() -> None:
    report = compare_reader_labels(READER_B, READER_B, max_disagreements=None)
    rendered = render_disagreements_csv(report["disagreements"]["items"])

    assert report["disagreements"]["total"] == 0
    reader = csv.DictReader(io.StringIO(rendered.removeprefix("\ufeff")))
    assert tuple(reader.fieldnames or ()) == CSV_FIELDNAMES
    assert list(reader) == []
    assert rendered.endswith("\r\n")


def test_cli_csv_contains_all_disagreements_even_when_json_is_capped(
    tmp_path: Path, capsys
) -> None:
    csv_path = tmp_path / "reader-disagreements.csv"
    json_path = tmp_path / "reader-comparison.json"

    exit_code = main(
        [
            "compare",
            str(READER_A_DIR),
            str(READER_B_DIR),
            "--max-disagreements",
            "1",
            "--csv",
            str(csv_path),
            "--output",
            str(json_path),
        ]
    )

    assert exit_code == 0
    stdout_report = json.loads(capsys.readouterr().out)
    saved_report = json.loads(json_path.read_text(encoding="utf-8"))
    assert stdout_report == saved_report
    assert stdout_report["disagreements"]["total"] > 1
    assert stdout_report["disagreements"]["returned"] == 1
    assert stdout_report["disagreements"]["truncated"] is True
    assert stdout_report["csv_output"] == str(csv_path.resolve())
    assert csv_path.read_bytes().startswith(b"\xef\xbb\xbf")
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == stdout_report["disagreements"]["total"]
    assert tuple(rows[0]) == CSV_FIELDNAMES


def test_cli_rejects_one_path_for_both_json_and_csv(tmp_path: Path, capsys) -> None:
    destination = tmp_path / "comparison.out"

    exit_code = main(
        [
            "compare",
            str(READER_A_DIR),
            str(READER_B_DIR),
            "--output",
            str(destination),
            "--csv",
            str(destination),
        ]
    )

    assert exit_code == 2
    assert "must be distinct paths" in capsys.readouterr().err
    assert not destination.exists()
