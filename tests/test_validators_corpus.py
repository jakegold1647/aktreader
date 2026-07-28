from pathlib import Path
from types import SimpleNamespace

from aktreader.labels import load_reader_label
from aktreader.validators.corpus import (
    validate_attestor_age_continuity,
    validate_corpus,
    validate_within_clerk_year_names,
)
from aktreader.validators.formula import validate_formula_positions

ROOT = Path(__file__).resolve().parents[1]
READER_A = ROOT / "labels" / "readerA" / "serock-1890-death-1.json"
READER_B = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"


def _evidence(value, original_script=None):
    return {
        "value": value,
        "original_script": original_script,
        "confidence": "PROBABLE",
        "observation_state": "PRESENT",
        "alternatives": [],
        "source_span_ids": ["declarants"],
        "notes": [],
    }


def _record(
    record_id,
    year,
    *,
    name="Abram Rozenberg",
    age=50,
    clerk_year=None,
    original_script="Абрамъ Розенбергъ",
):
    return {
        "record_id": record_id,
        "target": {
            "town": "Serock",
            "fond": "73/826/0",
            "year": year,
        },
        "clerk_year": {"id": clerk_year or f"73/826/0|serock|{year}|clerk-unknown"},
        "observations": {
            "declarants.0.name": _evidence(name, original_script),
            "declarants.0.age": _evidence(age, str(age)),
        },
    }


def test_zero_to_two_year_age_noise_is_not_flagged() -> None:
    records = [
        _record("act-1", 1890, age=50),
        _record("act-2", 1891, age=52),
    ]

    assert validate_attestor_age_continuity(records) == ()


def test_five_or_more_year_age_jump_is_flagged_but_not_decided() -> None:
    records = [
        _record("act-1", 1890, age=50),
        _record("act-2", 1891, age=56),
    ]

    findings = validate_attestor_age_continuity(records)

    assert [finding.code for finding in findings] == ["ATTESTOR_AGE_DISCONTINUITY"]
    assert "different person" in findings[0].message
    assert findings[0].evidence["age_jump"] == 6


def test_no_fuzzy_name_equivalence_is_used_for_age_pairing() -> None:
    records = [
        _record("act-1", 1890, name="Abram Rozenberg", age=50),
        _record("act-2", 1891, name="Abran Rosenberg", age=70),
    ]

    assert validate_attestor_age_continuity(records) == ()


def test_exact_anchor_recurring_name_variants_are_flagged() -> None:
    clerk_year = "73/826/0|serock|1890|clerk-unknown"
    same_normalized = [
        _record("act-1", 1890, clerk_year=clerk_year, original_script="Абрамъ"),
        _record("act-2", 1890, clerk_year=clerk_year, original_script="Аврамъ"),
    ]
    same_original = [
        _record(
            "act-3",
            1890,
            clerk_year=clerk_year,
            name="Abram",
            original_script="Абрамъ",
        ),
        _record(
            "act-4",
            1890,
            clerk_year=clerk_year,
            name="Avram",
            original_script="Абрамъ",
        ),
    ]

    script_findings = validate_within_clerk_year_names(same_normalized)
    normalization_findings = validate_within_clerk_year_names(same_original)

    assert any(finding.code == "RECURRING_NAME_SCRIPT_VARIANT" for finding in script_findings)
    assert any(
        finding.code == "RECURRING_NAME_NORMALIZATION_VARIANT" for finding in normalization_findings
    )


def test_different_names_do_not_create_recurring_name_claim() -> None:
    records = [
        _record("act-1", 1890, name="Abram Rozenberg", original_script="Абрамъ"),
        _record("act-2", 1890, name="Jankel Goldfarb", original_script="Янкель"),
    ]

    assert validate_within_clerk_year_names(records) == ()
    assert validate_corpus(records) == ()


def test_supplied_reader_b_formula_spans_pass_and_legacy_is_unverified() -> None:
    canonical = load_reader_label(READER_B)
    legacy = load_reader_label(READER_A)

    canonical_codes = {finding.code for finding in validate_formula_positions(canonical)}
    legacy_codes = {finding.code for finding in validate_formula_positions(legacy)}

    assert "FORMULA_POSITION" not in canonical_codes
    assert legacy_codes == {"SOURCE_SPANS_UNVERIFIED"}


def test_formula_position_mismatch_is_a_finding_only() -> None:
    observation = {
        "registration_date": {
            "value": "1890-01-01",
            "original_script": "first January",
            "confidence": "PROBABLE",
            "observation_state": "PRESENT",
            "alternatives": [],
            "source_span_ids": ["event"],
            "notes": [],
        }
    }
    record = SimpleNamespace(
        record_id="synthetic-formula",
        observations=observation,
        source_spans={"registration": {}, "event": {}},
    )

    findings = validate_formula_positions(record)

    assert [finding.code for finding in findings] == ["FORMULA_POSITION"]
    assert observation["registration_date"]["value"] == "1890-01-01"
