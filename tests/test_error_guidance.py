import json
from pathlib import Path

import pytest

from aktreader.gold import GoldValidationError, load_gold_records, validate_gold_record
from aktreader.labels import LabelValidationError, parse_canonical_reader_label

ROOT = Path(__file__).resolve().parents[1]


def test_reader_label_errors_keep_the_detail_and_name_the_contract() -> None:
    payload = json.loads(
        (ROOT / "labels" / "readerB" / "serock-1890-death-1.json").read_text(encoding="utf-8")
    )
    payload["observations"]["act_no"]["value"] = None

    with pytest.raises(LabelValidationError) as error:
        parse_canonical_reader_label(payload)

    message = str(error.value)
    assert "PRESENT requires a value" in message
    assert "Rule: reader-label evidence contract" in message
    assert "docs/architecture.md" in message
    assert "schemas/reader-label-1.0.0.schema.json" in message


def test_gold_errors_keep_the_detail_and_name_the_contract() -> None:
    record = load_gold_records(ROOT)[0]
    record["fields"]["act_type"]["value"] = None

    with pytest.raises(GoldValidationError) as error:
        validate_gold_record(record)

    message = str(error.value)
    assert "PRESENT requires a value" in message
    assert "Rule: gold evidence contract" in message
    assert "docs/architecture.md" in message
    assert "docs/serockbench.md" in message
