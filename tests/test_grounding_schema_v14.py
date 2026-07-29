import json
from pathlib import Path

import pytest

from aktreader.schema import ContractValidationError, validate_instance

ROOT = Path(__file__).resolve().parents[1]
FULL_SCHEMA = ROOT / "schemas" / "reader-label-1.0.0-v1.4.schema.json"
MODEL_SCHEMA = ROOT / "schemas" / "model-output-1.1.0.schema.json"
READER_B = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"


def _full_payload() -> dict:
    payload = json.loads(READER_B.read_text(encoding="utf-8"))
    payload["$schema"] = "https://aktreader.org/schema/reader-label-1.0.0.json"
    payload["prompt"]["version"] = "1.4.0"
    payload["transcription"]["original_script"] = "Состоялось в Сероцке. Фрума умерла."
    payload["observations"] = {
        "principal.name": {
            "value": "Fruma",
            "original_script": "Фрума",
            "confidence": "PROBABLE",
            "observation_state": "PRESENT",
            "alternatives": [],
            "source_span_ids": ["principal"],
            "notes": [],
        }
    }
    return payload


def _model_payload() -> dict:
    return {
        "target_check": {
            "year": 1890,
            "act_type": "death",
            "act_no": 1,
            "language": "ru",
        },
        "transcription": {
            "original_script": ["Состоялось в Сероцке.", "Фрума умерла."],
            "translation": ["Registered in Serock.", "Fruma died."],
        },
        "observations": {
            "principal.name": {
                "value": "Fruma",
                "original_script": "Фрума",
                "confidence": "PROBABLE",
                "observation_state": "PRESENT",
                "alternatives": [],
                "notes": [],
            }
        },
    }


def test_v14_full_label_enforces_structural_and_semantic_grounding() -> None:
    payload = _full_payload()
    validate_instance(payload, FULL_SCHEMA)

    payload["observations"]["principal.name"]["original_script"] = "Ривка"
    with pytest.raises(ContractValidationError, match="NOT_IN_TRANSCRIPTION"):
        validate_instance(payload, FULL_SCHEMA)


def test_v14_full_label_rejects_blank_present_original_script() -> None:
    payload = _full_payload()
    payload["observations"]["principal.name"]["original_script"] = "   "

    with pytest.raises(ContractValidationError, match="schema validation failed"):
        validate_instance(payload, FULL_SCHEMA)


def test_v14_model_schema_enforces_line_array_substring_and_cyrillic() -> None:
    payload = _model_payload()
    validate_instance(payload, MODEL_SCHEMA)

    payload["observations"]["principal.name"]["original_script"] = "previous day"
    payload["transcription"]["original_script"].append("previous day")
    with pytest.raises(ContractValidationError, match="HAS_NO_CYRILLIC"):
        validate_instance(payload, MODEL_SCHEMA)


def test_v14_model_schema_requires_nonblank_continuous_transcription() -> None:
    payload = _model_payload()
    payload["transcription"]["original_script"] = ["   "]

    with pytest.raises(ContractValidationError, match="schema validation failed"):
        validate_instance(payload, MODEL_SCHEMA)
