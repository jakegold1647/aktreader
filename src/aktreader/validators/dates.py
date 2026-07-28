"""Date-order and dual-calendar validators from the grading contract."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from aktreader.validators.models import ValidationFinding
from aktreader.validators.support import evidence_value, observations_of, record_id_of

ISO_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str) or not ISO_DATE_PREFIX.match(value):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None


def _calendar_dates(value: Any) -> dict[str, date]:
    if isinstance(value, str):
        parsed = _parse_iso_date(value)
        return {"unspecified": parsed} if parsed is not None else {}
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, date] = {}
    for calendar in ("gregorian", "julian"):
        parsed = _parse_iso_date(value.get(calendar))
        if parsed is not None:
            result[calendar] = parsed
    if not result:
        parsed = _parse_iso_date(value.get("date"))
        if parsed is not None:
            result["unspecified"] = parsed
    return result


def validate_registration_event_order(record: Any) -> tuple[ValidationFinding, ...]:
    """Flag a registration date earlier than the event date."""
    observations = observations_of(record)
    registration = _calendar_dates(evidence_value(observations, "registration_date"))
    event = _calendar_dates(evidence_value(observations, "event_date"))
    if not registration or not event:
        return ()
    shared = [
        calendar
        for calendar in ("gregorian", "julian", "unspecified")
        if calendar in registration and calendar in event
    ]
    if not shared:
        return ()
    calendar = shared[0]
    if registration[calendar] >= event[calendar]:
        return ()
    return (
        ValidationFinding(
            code="REGISTRATION_BEFORE_EVENT",
            message=(
                f"Registration date {registration[calendar].isoformat()} precedes event date "
                f"{event[calendar].isoformat()} in the {calendar} representation."
            ),
            record_ids=(record_id_of(record),),
            field_paths=("registration_date", "event_date"),
            evidence={
                "calendar": calendar,
                "registration_date": registration[calendar].isoformat(),
                "event_date": event[calendar].isoformat(),
            },
        ),
    )


def _expected_dual_gap(gregorian: date) -> int:
    # In this corpus, 12 days applies through 28 February 1900 Gregorian and 13 thereafter.
    return 13 if gregorian >= date(1900, 3, 1) else 12


def validate_dual_date_gaps(record: Any) -> tuple[ValidationFinding, ...]:
    """Flag written/derived Julian-Gregorian pairs outside the historical 12/13-day gap."""
    observations = observations_of(record)
    findings: list[ValidationFinding] = []
    for path, evidence in observations.items():
        if not isinstance(evidence, Mapping):
            continue
        if (
            evidence.get("observation_state") != "PRESENT"
            or evidence.get("confidence") == "UNCLEAR"
        ):
            continue
        dates = _calendar_dates(evidence.get("value"))
        if "gregorian" not in dates or "julian" not in dates:
            continue
        actual = (dates["gregorian"] - dates["julian"]).days
        expected = _expected_dual_gap(dates["gregorian"])
        if actual == expected:
            continue
        findings.append(
            ValidationFinding(
                code="DUAL_DATE_GAP",
                message=(
                    f"{path} has a {actual}-day Julian/Gregorian gap; "
                    f"{expected} days is expected for {dates['gregorian'].isoformat()}."
                ),
                record_ids=(record_id_of(record),),
                field_paths=(str(path),),
                evidence={
                    "gregorian": dates["gregorian"].isoformat(),
                    "julian": dates["julian"].isoformat(),
                    "actual_gap_days": actual,
                    "expected_gap_days": expected,
                },
            )
        )
    return tuple(findings)


def validate_dates(record: Any) -> tuple[ValidationFinding, ...]:
    """Run all date validators without mutating the record."""
    return validate_registration_event_order(record) + validate_dual_date_gaps(record)
