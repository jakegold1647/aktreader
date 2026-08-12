import json
from pathlib import Path

import pytest

from aktreader.evaluation import (
    EvaluationIntegrityError,
    evaluate_predictions,
    flatten_gold_fields,
    load_model_output_field_map,
    validate_holdout_integrity,
)

ROOT = Path(__file__).resolve().parents[1]


def evidence(value: object, confidence: str = "PROBABLE") -> dict[str, object]:
    return {
        "value": value,
        "original_script": None,
        "confidence": confidence,
        "observation_state": "PRESENT",
        "alternatives": [],
        "source_span_ids": ["act"],
        "notes": [],
    }


def gold_record(record_id: str = "sample-1890-death-1") -> dict[str, object]:
    return {
        "record_id": record_id,
        "register": {
            "clerk_year": {
                "id": "fond|sample|1890|clerk-unknown",
                "basis": "REGISTER_YEAR_PROXY",
                "clerk_id": None,
            }
        },
        "fields": {
            "father": {
                "name": {
                    "value": "Abram Goldsztejn",
                    "confidence": "PROBABLE",
                    "observation_state": "PRESENT",
                }
            },
            "mother": {
                "name": {
                    "value": "Ruchla Goldsztejn",
                    "confidence": "PROBABLE",
                    "observation_state": "PRESENT",
                },
                "maiden_name": {
                    "value": "Kanarek",
                    "confidence": "PROBABLE",
                    "observation_state": "PRESENT",
                },
            },
            "registration_date": {
                "value": None,
                "confidence": None,
                "observation_state": "NOT_ANNOTATED",
            },
        },
    }


def holdout_for(record: dict[str, object]) -> dict[str, object]:
    return {
        "record_ids": [record["record_id"]],
        "holdout_clerk_year_ids": [record["register"]["clerk_year"]["id"]],
        "training_overlap_allowed": False,
    }


def test_flatten_gold_fields_uses_stable_dotted_paths() -> None:
    flattened = flatten_gold_fields(gold_record()["fields"])

    assert set(flattened) == {
        "father.name",
        "mother.name",
        "mother.maiden_name",
        "registration_date",
    }


def test_evaluation_reports_filiation_and_wrong_confident_rate() -> None:
    gold = gold_record()
    prediction = {
        "record_id": gold["record_id"],
        "observations": {
            "father.name": evidence("Abram Goldsztejn", "CONFIDENT"),
            "mother.name": evidence("Ruchla Goldsztejn", "CONFIDENT"),
            "mother.maiden_name": evidence("KanaleK", "CONFIDENT"),
        },
    }

    report = evaluate_predictions([gold], [prediction], holdout_for(gold))

    assert report["filiation_exact_match"]["fields_correct"] == 2
    assert report["filiation_exact_match"]["fields_total"] == 3
    assert report["wrong_but_confident"]["display"] == "33.33% (1/3)"


def test_zero_confident_predictions_are_na_not_zero_percent() -> None:
    gold = gold_record()
    prediction = {
        "record_id": gold["record_id"],
        "observations": {
            "father.name": evidence("Abram Goldsztejn"),
            "mother.name": evidence("Ruchla Goldsztejn"),
            "mother.maiden_name": evidence("Kanarek"),
        },
    }

    report = evaluate_predictions([gold], [prediction], holdout_for(gold))

    assert report["wrong_but_confident"]["rate"] is None
    assert report["wrong_but_confident"]["display"] == "N/A (0/0)"


def test_exact_match_requires_the_observation_state_to_match() -> None:
    gold = gold_record()
    wrong_state = evidence("Abram Goldsztejn", "CONFIDENT")
    wrong_state["observation_state"] = "STATED_UNKNOWN"
    prediction = {
        "record_id": gold["record_id"],
        "observations": {
            "father.name": wrong_state,
            "mother.name": evidence("Ruchla Goldsztejn", "CONFIDENT"),
            "mother.maiden_name": evidence("Kanarek", "CONFIDENT"),
        },
    }

    report = evaluate_predictions([gold], [prediction], holdout_for(gold))

    assert report["filiation_exact_match"]["fields_correct"] == 2
    assert report["wrong_but_confident"]["display"] == "33.33% (1/3)"
    assert report["observation_state_accuracy"]["correct"] == 2


def test_clerk_year_training_leakage_fails_closed() -> None:
    gold = gold_record()

    with pytest.raises(EvaluationIntegrityError, match="leakage"):
        validate_holdout_integrity(
            [gold],
            holdout_for(gold),
            training_clerk_year_ids=[gold["register"]["clerk_year"]["id"]],
        )


def test_duplicate_gold_record_ids_fail_closed() -> None:
    gold = gold_record()

    with pytest.raises(EvaluationIntegrityError, match="duplicate gold record IDs"):
        validate_holdout_integrity([gold, gold], holdout_for(gold))


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("record_ids", "duplicate holdout record IDs"),
        ("holdout_clerk_year_ids", "duplicate holdout clerk-year IDs"),
    ],
)
def test_duplicate_holdout_entries_fail_closed(field: str, message: str) -> None:
    gold = gold_record()
    holdout = holdout_for(gold)
    values = holdout[field]
    assert isinstance(values, list)
    values.append(values[0])

    with pytest.raises(EvaluationIntegrityError, match=message):
        validate_holdout_integrity([gold], holdout)


def test_repository_holdout_matches_every_gold_record() -> None:
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / "gold" / "acts").glob("*.json"))
    ]
    holdout = json.loads((ROOT / "gold" / "clerk_year_holdout.json").read_text(encoding="utf-8"))

    result = validate_holdout_integrity(records, holdout)

    assert result == {
        "status": "PASS",
        "records": 36,
        "clerk_years": 21,
        "training_overlap": 0,
    }


def test_reduced_snake_case_keys_map_to_nested_gold_paths() -> None:
    gold = gold_record()
    prediction = {
        "record_id": gold["record_id"],
        "observations": {
            "father": evidence("Abram Goldsztejn"),
            "mother": evidence("Ruchla Goldsztejn"),
            "mother_maiden_name": evidence("Kanarek"),
        },
    }

    report = evaluate_predictions([gold], [prediction], holdout_for(gold))

    assert report["filiation_exact_match"]["fields_correct"] == 3
    assert report["filiation_exact_match"]["fields_total"] == 3
    assert report["field_vocabulary"]["mapping_version"] == "1.0.0"
    assert report["field_vocabulary"]["dispositions"] == {"MAP": 3}


def test_unmapped_model_key_fails_instead_of_scoring_as_missing() -> None:
    gold = gold_record()
    prediction = {
        "record_id": gold["record_id"],
        "observations": {"new_silent_mismatch": evidence("invented")},
    }

    with pytest.raises(EvaluationIntegrityError, match="unmapped model observation key"):
        evaluate_predictions([gold], [prediction], holdout_for(gold))


def test_field_map_is_bound_to_the_current_reduced_schema() -> None:
    mapping = load_model_output_field_map()

    assert mapping["schema_version"] == "1.0.0"
    assert len(mapping["entries"]) == 81
    assert mapping["entries"]["principal_name"]["gold_path"] == "principal.name"
    assert mapping["entries"]["deceased_filiation"]["status"].startswith("UNSCORABLE_")
