import json
from pathlib import Path

import pytest

from aktreader.qualification_scoring import (
    QualificationScoringError,
    score_qualification_adjudication,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "human-qualification-adjudication-1.0.0.schema.json"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _assessment(code: str, errors: int) -> dict[str, object]:
    return {
        "candidate_code": code,
        "legible_character_count": 100,
        "character_error_count": errors,
        "material_error_count": 0,
        "material_hallucination_count": 0,
        "uncertain_regions_guessed_count": 0,
        "unreadable_regions_marked": True,
        "original_spelling_preserved": True,
        "independence_declaration_complete": True,
        "notes": [],
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    intake_path = tmp_path / "intake.json"
    _write_json(
        intake_path,
        {
            "schema_version": "1.0.0",
            "packet_id": "qualification-test",
            "status": "COMPLETE",
            "machine_assistance_detected": False,
            "matrix": {
                "candidate_codes": ["H1", "H2", "H3"],
                "record_ids": ["synthetic-1"],
                "candidate_count": 3,
                "record_count": 1,
                "submission_count": 3,
            },
        },
    )
    import hashlib

    intake_sha = hashlib.sha256(intake_path.read_bytes()).hexdigest()
    adjudication: dict[str, object] = {
        "$schema": "../schemas/human-qualification-adjudication-1.0.0.schema.json",
        "schema_version": "1.0.0",
        "packet_id": "qualification-test",
        "intake_report": {"path": "intake.json", "sha256": intake_sha},
        "adjudicator": {
            "adjudicator_code": "ADJ1",
            "qualifications": "pre-1917 Russian civil-register paleography",
            "independent_of_candidates": True,
            "adjudicated_at": "2026-07-30T02:00:00Z",
        },
        "records": [
            {
                "record_id": "synthetic-1",
                "adjudicated_original_script": "Строка",
                "line_count": 1,
                "candidate_assessments": [
                    _assessment("H1", 2),
                    _assessment("H2", 3),
                    _assessment("H3", 4),
                ],
            }
        ],
        "authority_warning": "extraction is not authority — verify against the scan",
    }
    adjudication_path = tmp_path / "adjudication.json"
    _write_json(adjudication_path, adjudication)
    return intake_path, adjudication_path, adjudication


def _score(intake_path: Path, adjudication_path: Path) -> dict[str, object]:
    return score_qualification_adjudication(
        intake_path=intake_path,
        adjudication_path=adjudication_path,
        adjudication_schema_path=SCHEMA,
    )


def test_scores_exact_threshold_and_requires_two_passing_candidates(tmp_path: Path) -> None:
    intake_path, adjudication_path, _ = _fixture(tmp_path)

    report = _score(intake_path, adjudication_path)

    results = {item["candidate_code"]: item for item in report["candidate_results"]}
    assert results["H1"]["character_accuracy"] == 0.98
    assert results["H2"]["character_accuracy"] == 0.97
    assert results["H3"]["character_accuracy"] == 0.96
    assert report["passing_candidate_codes"] == ["H1", "H2"]
    assert report["production_hiring_gate"] == "PASS_TWO_OR_MORE_QUALIFIED"
    assert report["payment_approval"] == "NOT_GRANTED_BY_SCORER"
    assert report["gold_promotion"] == "NONE"


def test_material_error_blocks_candidate_even_above_character_threshold(
    tmp_path: Path,
) -> None:
    intake_path, adjudication_path, adjudication = _fixture(tmp_path)
    records = adjudication["records"]
    records[0]["candidate_assessments"][0]["material_error_count"] = 1
    _write_json(adjudication_path, adjudication)

    report = _score(intake_path, adjudication_path)

    assert report["passing_candidate_codes"] == ["H2"]
    assert report["production_hiring_gate"] == "BLOCKED_RECRUIT_AGAIN"


def test_scoring_rejects_intake_pin_drift(tmp_path: Path) -> None:
    intake_path, adjudication_path, adjudication = _fixture(tmp_path)
    adjudication["intake_report"]["sha256"] = "0" * 64
    _write_json(adjudication_path, adjudication)

    with pytest.raises(QualificationScoringError, match="SHA-256 mismatch"):
        _score(intake_path, adjudication_path)


def test_scoring_rejects_missing_candidate_assessment(tmp_path: Path) -> None:
    intake_path, adjudication_path, adjudication = _fixture(tmp_path)
    records = adjudication["records"]
    records[0]["candidate_assessments"].pop()
    _write_json(adjudication_path, adjudication)

    with pytest.raises(QualificationScoringError, match="missing candidate assessments"):
        _score(intake_path, adjudication_path)


def test_scoring_rejects_more_errors_than_legible_characters(tmp_path: Path) -> None:
    intake_path, adjudication_path, adjudication = _fixture(tmp_path)
    records = adjudication["records"]
    records[0]["candidate_assessments"][0]["character_error_count"] = 101
    _write_json(adjudication_path, adjudication)

    with pytest.raises(QualificationScoringError, match="errors exceed legible"):
        _score(intake_path, adjudication_path)


def test_scoring_rejects_adjudicated_line_count_mismatch(tmp_path: Path) -> None:
    intake_path, adjudication_path, adjudication = _fixture(tmp_path)
    records = adjudication["records"]
    records[0]["line_count"] = 2
    _write_json(adjudication_path, adjudication)

    with pytest.raises(QualificationScoringError, match="line count mismatch"):
        _score(intake_path, adjudication_path)
