import copy
import json
from pathlib import Path

import pytest

from aktreader.grounding import (
    GroundingValidationError,
    load_grounded_reader_label,
    paired_quality_metrics,
    require_grounded,
    validate_cross_reader_grounding,
)
from aktreader.labels import parse_canonical_reader_label

ROOT = Path(__file__).resolve().parents[1]
READER_B = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"


def _payload(*, value: object = "Fruma", original_script: str = "Фрума") -> dict:
    payload = json.loads(READER_B.read_text(encoding="utf-8"))
    payload["transcription"]["original_script"] = f"Состоялось в Сероцке. {original_script}."
    payload["observations"] = {
        "principal.name": {
            "value": value,
            "original_script": original_script,
            "confidence": "PROBABLE",
            "observation_state": "PRESENT",
            "alternatives": [],
            "source_span_ids": ["principal"],
            "notes": [],
        }
    }
    return payload


def _pair(left_age: object, right_age: object):
    left_payload = _payload(value=left_age, original_script="три дня")
    right_payload = _payload(value=right_age, original_script="тридцать три года")
    left_payload["observations"] = {
        "principal.age": left_payload["observations"].pop("principal.name")
    }
    right_payload["observations"] = {
        "principal.age": right_payload["observations"].pop("principal.name")
    }
    left_payload["label_id"] = "synthetic.grounding-left"
    left_payload["reader"]["reader_id"] = "grounding-left"
    left_payload["reader"]["reader_family"] = "claude"
    right_payload["label_id"] = "synthetic.grounding-right"
    right_payload["reader"]["reader_id"] = "grounding-right"
    right_payload["reader"]["reader_family"] = "gpt"
    return (
        parse_canonical_reader_label(left_payload),
        parse_canonical_reader_label(right_payload),
    )


def test_grounded_ingest_accepts_cyrillic_substring(tmp_path: Path) -> None:
    path = tmp_path / "label.json"
    path.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")

    label = load_grounded_reader_label(path)

    assert label.record_id == "serock-1890-death-1"
    assert paired_quality_metrics((label,)) == {
        "coverage": {
            "label_count": 1,
            "reported_observation_count": 1,
            "present_observation_count": 1,
            "non_present_observation_count": 0,
            "present_rate": 1.0,
        },
        "groundedness": {
            "present_observation_count": 1,
            "cyrillic_applicable_count": 1,
            "cyrillic_supported_count": 1,
            "transcription_supported_count": 1,
            "fully_grounded_count": 1,
            "violation_count": 0,
            "groundedness_rate": 1.0,
        },
    }


def test_ru_present_evidence_without_cyrillic_fails_closed() -> None:
    label = parse_canonical_reader_label(
        _payload(value="previous day", original_script="previous day")
    )

    with pytest.raises(
        GroundingValidationError,
        match="PRESENT_RU_ORIGINAL_SCRIPT_HAS_NO_CYRILLIC",
    ):
        require_grounded(label)


def test_present_original_script_not_in_own_transcription_fails_closed() -> None:
    payload = _payload()
    payload["transcription"]["original_script"] = "Состоялось в Сероцке."
    label = parse_canonical_reader_label(payload)

    with pytest.raises(
        GroundingValidationError,
        match="PRESENT_ORIGINAL_SCRIPT_NOT_IN_TRANSCRIPTION",
    ):
        require_grounded(label)


def test_cross_reader_life_stage_or_order_of_magnitude_is_incident() -> None:
    left, right = _pair("3 days", "33 years")

    findings = validate_cross_reader_grounding(left, right)

    assert len(findings) == 1
    assert findings[0].severity == "GROUNDEDNESS_INCIDENT"
    assert findings[0].code == "CROSS_READER_PRINCIPAL_AGE_IMPOSSIBILITY"
    assert set(findings[0].evidence["reasons"]) == {
        "LIFE_STAGE_MISMATCH",
        "AGE_RATIO_GT_10",
    }


def test_plausible_same_stage_age_disagreement_remains_ordinary() -> None:
    left, right = _pair("9 weeks", "6 months")

    assert validate_cross_reader_grounding(left, right) == ()


def test_metrics_never_report_coverage_without_groundedness() -> None:
    label = parse_canonical_reader_label(_payload())
    unsupported = copy.deepcopy(_payload())
    unsupported["observations"]["principal.name"]["original_script"] = "Фрейда"
    unsupported_label = parse_canonical_reader_label(unsupported)

    metrics = paired_quality_metrics((label, unsupported_label))

    assert set(metrics) == {"coverage", "groundedness"}
    assert metrics["coverage"]["present_observation_count"] == 2
    assert metrics["groundedness"]["fully_grounded_count"] == 1
    assert metrics["groundedness"]["violation_count"] == 1
