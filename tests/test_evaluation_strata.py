"""Stratified benchmark report: per-field families x script era (roadmap item 1).

The headline number per stratum is wrong-but-confident, not overall accuracy;
coverage, exact accuracy, and abstention are reported alongside so abstention
is never mistaken for success.
"""

from copy import deepcopy

import pytest

from aktreader.evaluation import (
    EvaluationIntegrityError,
    evaluate_predictions,
    field_family,
    render_stratified_markdown,
)


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


def gold_record(language: str | None = "ru") -> dict[str, object]:
    register: dict[str, object] = {
        "clerk_year": {
            "id": "fond|sample|1890|clerk-unknown",
            "basis": "REGISTER_YEAR_PROXY",
            "clerk_id": None,
        }
    }
    if language is not None:
        register["language"] = language
    return {
        "record_id": "sample-1890-death-1",
        "register": register,
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
            "principal": {
                "age": {
                    "value": "67",
                    "confidence": "PROBABLE",
                    "observation_state": "PRESENT",
                }
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


def test_field_family_groups_gold_leaves_and_keeps_unknowns_visible() -> None:
    assert field_family("father.name") == "names"
    assert field_family("spouse_parents.mother.maiden_name") == "names"
    assert field_family("event_date") == "dates"
    assert field_family("principal.age") == "ages"
    assert field_family("mother.occupation") == "person_attributes"
    assert field_family("marginalia") == "register_other"


def test_stratified_report_counts_by_family_and_era() -> None:
    gold = gold_record()
    prediction = {
        "record_id": gold["record_id"],
        "observations": {
            "father.name": evidence("Abram Goldsztejn", "CONFIDENT"),
            "mother.name": evidence("Wrong Name", "CONFIDENT"),
            "mother.maiden_name": evidence("Kana?", "UNCLEAR"),
        },
    }

    report = evaluate_predictions([gold], [prediction], holdout_for(gold))
    names = report["stratified"]["ru"]["names"]
    ages = report["stratified"]["ru"]["ages"]

    assert names["gold_scorable"] == 3
    assert names["predicted"] == 3
    assert names["coverage"] == 1.0
    assert names["exact"] == 1
    assert names["wrong_but_confident"] == {"wrong": 1, "confident": 2, "rate": 0.5}
    assert names["abstention"] == {"abstained": 1, "rate": 1 / 3}
    assert ages == {
        "gold_scorable": 1,
        "predicted": 0,
        "coverage": 0.0,
        "exact": 0,
        "exact_rate": None,
        "wrong_but_confident": {"wrong": 0, "confident": 0, "rate": None},
        "abstention": {"abstained": 0, "rate": None},
    }


def test_stratified_markdown_is_one_count_backed_table() -> None:
    gold = gold_record()
    prediction = {
        "record_id": gold["record_id"],
        "observations": {
            "father.name": evidence("Abram Goldsztejn", "CONFIDENT"),
            "mother.name": evidence("Wrong Name", "CONFIDENT"),
            "mother.maiden_name": evidence("Kana?", "UNCLEAR"),
        },
    }
    report = evaluate_predictions([gold], [prediction], holdout_for(gold))

    rendered = render_stratified_markdown(report)

    assert rendered == "\n".join(
        [
            "# SerockBench-v1 stratified field results",
            "",
            "Matched prediction records: 100.00% (1/1).",
            "Holdout integrity: PASS.",
            "",
            "| Register language | Field family | Gold scorable | Predicted | Coverage | "
            "Wrong but CONFIDENT | Exact accuracy | Abstention |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            "| ru | names | 3 | 3 | 100.00% (3/3) | 50.00% (1/2) | 33.33% (1/3) | 33.33% (1/3) |",
            "| ru | ages | 1 | 0 | 0.00% (0/1) | N/A (0/0) | N/A (0/0) | N/A (0/0) |",
            "",
            "Wrong but CONFIDENT is the headline risk metric. Coverage uses gold-scorable "
            "fields; wrong-but-CONFIDENT uses CONFIDENT predictions; exact accuracy and "
            "abstention use predicted fields.",
            "Register language is copied from the gold record and is never inferred from its "
            "year. `unknown` remains explicit.",
            "",
        ]
    )


def test_stratified_markdown_keeps_an_empty_result_explicit() -> None:
    gold = gold_record()
    report = evaluate_predictions([gold], [], holdout_for(gold))

    rendered = render_stratified_markdown(report)

    assert "Matched prediction records: 0.00% (0/1)." in rendered
    assert "No stratum rows are available" in rendered
    assert rendered.count("| ru |") == 0


def test_stratified_markdown_fails_closed_on_bad_integrity_or_counts() -> None:
    gold = gold_record()
    prediction = {
        "record_id": gold["record_id"],
        "observations": {"father.name": evidence("Abram Goldsztejn", "CONFIDENT")},
    }
    report = evaluate_predictions([gold], [prediction], holdout_for(gold))
    failed_holdout = deepcopy(report)
    failed_holdout["holdout_integrity"]["status"] = "FAIL"
    impossible_counts = deepcopy(report)
    impossible_counts["stratified"]["ru"]["names"]["predicted"] = 4

    with pytest.raises(EvaluationIntegrityError, match="passing holdout integrity"):
        render_stratified_markdown(failed_holdout)
    with pytest.raises(EvaluationIntegrityError, match="numerator exceeds denominator"):
        render_stratified_markdown(impossible_counts)


def test_unpredicted_scorable_fields_lower_coverage_not_accuracy() -> None:
    gold = gold_record()
    prediction = {
        "record_id": gold["record_id"],
        "observations": {"father.name": evidence("Abram Goldsztejn", "CONFIDENT")},
    }

    report = evaluate_predictions([gold], [prediction], holdout_for(gold))
    names = report["stratified"]["ru"]["names"]

    assert names["gold_scorable"] == 3
    assert names["predicted"] == 1
    assert names["coverage"] == 1 / 3
    assert names["exact_rate"] == 1.0


def test_missing_register_language_is_reported_as_unknown_not_guessed() -> None:
    gold = gold_record(language=None)
    prediction = {
        "record_id": gold["record_id"],
        "observations": {"father.name": evidence("Abram Goldsztejn")},
    }

    report = evaluate_predictions([gold], [prediction], holdout_for(gold))

    assert set(report["stratified"]) == {"unknown"}
