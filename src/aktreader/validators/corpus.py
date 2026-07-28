"""Conservative cross-act validators that never resolve identity."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aktreader.validators.models import ValidationFinding
from aktreader.validators.support import (
    clerk_year_of,
    evidence_value,
    observations_of,
    record_id_of,
    target_of,
)

ATTESTOR_NAME_RE = re.compile(r"^(?:declarants|witnesses)\.(\d+)\.name$")
YEAR_AGE_RE = re.compile(r"^\s*(\d+)(?:\s*(?:years?|yrs?))?\s*$", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")
NAME_PATH_RE = re.compile(
    r"^(?:principal|father|mother|spouse|spouse_parents\.(?:father|mother)|"
    r"declarants\.\d+|witnesses\.\d+)\.name$"
)


def _strict_text(value: str) -> str:
    return WHITESPACE_RE.sub(" ", unicodedata.normalize("NFC", value)).strip()


def _age_years(value: Any) -> int | None:
    if type(value) is int and value >= 0:
        return value
    if not isinstance(value, str):
        return None
    folded = value.casefold()
    if "month" in folded or "day" in folded or "week" in folded:
        return None
    match = YEAR_AGE_RE.fullmatch(value)
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class _Attestor:
    record_id: str
    town: str | None
    fond: str | None
    year: int
    role_path: str
    name: str
    age: int


def _attestors(record: Any) -> list[_Attestor]:
    observations = observations_of(record)
    target = target_of(record)
    year = target.get("year")
    if type(year) is not int:
        return []
    result: list[_Attestor] = []
    for path in observations:
        match = ATTESTOR_NAME_RE.fullmatch(str(path))
        if not match:
            continue
        prefix = str(path).rsplit(".", 1)[0]
        name = evidence_value(observations, str(path))
        age = _age_years(evidence_value(observations, f"{prefix}.age"))
        if not isinstance(name, str) or age is None:
            continue
        result.append(
            _Attestor(
                record_id=record_id_of(record),
                town=target.get("town") if isinstance(target.get("town"), str) else None,
                fond=target.get("fond") if isinstance(target.get("fond"), str) else None,
                year=year,
                role_path=prefix,
                name=_strict_text(name),
                age=age,
            )
        )
    return result


def validate_attestor_age_continuity(
    records: list[Any] | tuple[Any, ...],
) -> tuple[ValidationFinding, ...]:
    """Flag exact-name attestors whose age jumps by five or more in the same/adjacent year."""
    grouped: dict[tuple[str | None, str | None, str], list[_Attestor]] = defaultdict(list)
    for record in records:
        for attestor in _attestors(record):
            grouped[(attestor.town, attestor.fond, attestor.name)].append(attestor)

    findings: list[ValidationFinding] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    for (_, _, name), occurrences in grouped.items():
        ordered = sorted(occurrences, key=lambda item: (item.year, item.record_id, item.role_path))
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                year_gap = right.year - left.year
                if year_gap > 1:
                    break
                if left.record_id == right.record_id:
                    continue
                age_jump = abs(right.age - left.age)
                if age_jump < 5:
                    continue
                pair_key = tuple(sorted((left.record_id, right.record_id))) + (name,)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                findings.append(
                    ValidationFinding(
                        code="ATTESTOR_AGE_DISCONTINUITY",
                        message=(
                            f"Exact-name attestor {name!r} changes from age {left.age} to "
                            f"{right.age} across {year_gap} register year(s). This may be a "
                            "misread or a different person; no identity decision was made."
                        ),
                        record_ids=(left.record_id, right.record_id),
                        field_paths=(f"{left.role_path}.age", f"{right.role_path}.age"),
                        evidence={
                            "name": name,
                            "left_year": left.year,
                            "right_year": right.year,
                            "left_age": left.age,
                            "right_age": right.age,
                            "age_jump": age_jump,
                        },
                    )
                )
    return tuple(findings)


@dataclass(frozen=True)
class _NameReading:
    record_id: str
    path: str
    normalized: str
    original: str


def validate_within_clerk_year_names(
    records: list[Any] | tuple[Any, ...],
) -> tuple[ValidationFinding, ...]:
    """Flag only exact-anchor inconsistencies; never use fuzzy name equivalence."""
    by_clerk: dict[str, list[_NameReading]] = defaultdict(list)
    officiants: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for record in records:
        clerk_year = clerk_year_of(record)
        if clerk_year is None:
            continue
        observations = observations_of(record)
        for path, evidence in observations.items():
            if not isinstance(evidence, Mapping):
                continue
            value = evidence_value(observations, str(path))
            original = evidence.get("original_script")
            if str(path) == "officiant" and isinstance(value, str):
                officiants[clerk_year].append((record_id_of(record), _strict_text(value)))
            if (
                NAME_PATH_RE.fullmatch(str(path))
                and isinstance(value, str)
                and isinstance(original, str)
            ):
                by_clerk[clerk_year].append(
                    _NameReading(
                        record_id=record_id_of(record),
                        path=str(path),
                        normalized=_strict_text(value),
                        original=_strict_text(original),
                    )
                )

    findings: list[ValidationFinding] = []
    for clerk_year, readings in by_clerk.items():
        by_normalized: dict[str, list[_NameReading]] = defaultdict(list)
        by_original: dict[str, list[_NameReading]] = defaultdict(list)
        for reading in readings:
            by_normalized[reading.normalized].append(reading)
            by_original[reading.original].append(reading)
        for normalized, matches in by_normalized.items():
            originals = {match.original for match in matches}
            if len(originals) > 1:
                findings.append(
                    ValidationFinding(
                        code="RECURRING_NAME_SCRIPT_VARIANT",
                        message=(
                            f"Within clerk-year {clerk_year}, exact normalized name "
                            f"{normalized!r} has multiple literal-script readings. Flagged "
                            "without choosing among them."
                        ),
                        record_ids=tuple(sorted({match.record_id for match in matches})),
                        field_paths=tuple(match.path for match in matches),
                        evidence={"normalized": normalized, "original_scripts": sorted(originals)},
                    )
                )
        for original, matches in by_original.items():
            normalized_values = {match.normalized for match in matches}
            if len(normalized_values) > 1:
                findings.append(
                    ValidationFinding(
                        code="RECURRING_NAME_NORMALIZATION_VARIANT",
                        message=(
                            f"Within clerk-year {clerk_year}, exact literal reading "
                            f"{original!r} has multiple normalized values. Flagged without "
                            "fuzzy equivalence or correction."
                        ),
                        record_ids=tuple(sorted({match.record_id for match in matches})),
                        field_paths=tuple(match.path for match in matches),
                        evidence={
                            "original_script": original,
                            "normalized_values": sorted(normalized_values),
                        },
                    )
                )

    for clerk_year, values in officiants.items():
        distinct = sorted({value for _, value in values})
        if len(distinct) <= 1:
            continue
        findings.append(
            ValidationFinding(
                code="OFFICIANT_WITHIN_CLERK_YEAR_VARIANT",
                message=(
                    f"Clerk-year {clerk_year} contains multiple strict officiant readings. "
                    "This may be a substitution or a misread; no identity decision was made."
                ),
                record_ids=tuple(sorted({record_id for record_id, _ in values})),
                field_paths=("officiant",),
                evidence={"officiant_values": distinct},
            )
        )
    return tuple(findings)


def validate_corpus(records: list[Any] | tuple[Any, ...]) -> tuple[ValidationFinding, ...]:
    """Run all conservative cross-act validators."""
    return validate_attestor_age_continuity(records) + validate_within_clerk_year_names(records)
