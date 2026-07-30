import copy
import json
from pathlib import Path

import pytest

from aktreader.human_gold import HumanGoldSubmissionError, validate_human_transcription

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "schemas" / "human-transcription-submission-1.0.0.schema.json").read_text(
        encoding="utf-8"
    )
)
EXAMPLE = json.loads(
    (ROOT / "examples" / "human-transcription-submission.example.json").read_text(encoding="utf-8")
)


def test_example_human_transcription_passes_qualification_gate() -> None:
    validate_human_transcription(EXAMPLE, SCHEMA, qualification=True)


def test_qualification_rejects_machine_assistance() -> None:
    payload = copy.deepcopy(EXAMPLE)
    payload["worker"]["machine_assistance_used"] = True
    payload["worker"]["machine_assistance_detail"] = "OCR"

    with pytest.raises(HumanGoldSubmissionError, match="must not use OCR or AI"):
        validate_human_transcription(payload, SCHEMA, qualification=True)


def test_line_count_must_match_actual_transcription() -> None:
    payload = copy.deepcopy(EXAMPLE)
    payload["transcription"]["line_count"] = 3

    with pytest.raises(HumanGoldSubmissionError, match="actual line count is 2"):
        validate_human_transcription(payload, SCHEMA)


def test_replacement_character_is_rejected() -> None:
    payload = copy.deepcopy(EXAMPLE)
    payload["transcription"]["original_script"] += "\ufffd"

    with pytest.raises(HumanGoldSubmissionError, match="replacement characters"):
        validate_human_transcription(payload, SCHEMA)
