import copy

from aktreader.validators.dates import (
    validate_dates,
    validate_dual_date_gaps,
    validate_registration_event_order,
)


def _field(value, confidence="PROBABLE"):
    return {
        "value": value,
        "confidence": confidence,
        "observation_state": "PRESENT",
    }


def _record(registration, event):
    return {
        "record_id": "synthetic-date-record",
        "observations": {
            "registration_date": _field(registration),
            "event_date": _field(event),
        },
    }


def test_registration_before_event_is_flagged_without_mutation() -> None:
    record = _record("1890-01-01", "1890-01-02")
    before = copy.deepcopy(record)

    findings = validate_registration_event_order(record)

    assert [finding.code for finding in findings] == ["REGISTRATION_BEFORE_EVENT"]
    assert findings[0].blocks_confident is True
    assert record == before


def test_registration_on_or_after_event_passes() -> None:
    assert validate_registration_event_order(_record("1890-01-02", "1890-01-01")) == ()
    assert validate_registration_event_order(_record("1890-01-01", "1890-01-01")) == ()


def test_valid_12_and_13_day_dual_dates_pass() -> None:
    before_1900 = _record(
        {"gregorian": "1890-01-13", "julian": "1890-01-01"},
        {"gregorian": "1890-01-11", "julian": "1889-12-30"},
    )
    after_1900 = _record(
        {"gregorian": "1901-01-14", "julian": "1901-01-01"},
        {"gregorian": "1901-01-13", "julian": "1900-12-31"},
    )

    assert validate_dual_date_gaps(before_1900) == ()
    assert validate_dual_date_gaps(after_1900) == ()


def test_wrong_dual_date_gap_is_flagged() -> None:
    record = _record(
        {"gregorian": "1890-01-12", "julian": "1890-01-01"},
        "1890-01-01",
    )

    findings = validate_dual_date_gaps(record)

    assert [finding.code for finding in findings] == ["DUAL_DATE_GAP"]
    assert findings[0].evidence["actual_gap_days"] == 11
    assert findings[0].evidence["expected_gap_days"] == 12


def test_1900_gap_boundary_is_applied_by_gregorian_date() -> None:
    february = _record(
        {"gregorian": "1900-02-28", "julian": "1900-02-16"},
        "1900-02-01",
    )
    march = _record(
        {"gregorian": "1900-03-01", "julian": "1900-02-16"},
        "1900-02-01",
    )

    assert validate_dual_date_gaps(february) == ()
    assert validate_dual_date_gaps(march) == ()


def test_unclear_dates_are_not_mechanically_decided() -> None:
    record = _record("1890-01-01", "1890-01-02")
    record["observations"]["event_date"]["confidence"] = "UNCLEAR"

    assert validate_dates(record) == ()
