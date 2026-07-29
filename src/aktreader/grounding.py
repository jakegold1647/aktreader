"""Mechanical groundedness gates for reader labels and blind-reader pairs.

Coverage measures how much a reader asserted.  Groundedness measures whether those
assertions are tied to the reader's own transcription.  The two metrics are deliberately
returned together so downstream summaries cannot reward coverage in isolation.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

from aktreader.labels import LabelValidationError, ReaderLabel, load_reader_label
from aktreader.validators.models import ValidationFinding

CYRILLIC_RE = re.compile(r"[\u0400-\u052f\u2de0-\u2dff\ua640-\ua69f]")
SPACE_RE = re.compile(r"\s+")
AGE_COMPONENT_RE = re.compile(
    r"(?P<number>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>"
    r"hours?|hrs?|час(?:а|ов)?|"
    r"days?|дн(?:я|ей)?|dni|dzień|"
    r"weeks?|нед(?:еля|ели|ель|ѣль)?|tygod(?:ni|nie|nia)|"
    r"months?|мес(?:яц(?:а|ев)?)?|mies(?:iąc|iące|ięcy)?|"
    r"years?|yrs?|л[еѣ]т|года?|lat|rok(?:u|i|ów)?"
    r")",
    re.IGNORECASE,
)
NUMERIC_AGE_RE = re.compile(r"\d+(?:[.,]\d+)?")


class GroundingValidationError(LabelValidationError):
    """Raised when a label asserts PRESENT evidence without textual support."""


def _normalized_text(value: str) -> str:
    return SPACE_RE.sub(" ", unicodedata.normalize("NFC", value)).strip().casefold()


def _continuous_transcription(label: ReaderLabel) -> str:
    transcription = label.raw.get("transcription")
    if isinstance(transcription, Mapping):
        original = transcription.get("original_script")
        if isinstance(original, str):
            return original
    # Legacy Reader A labels are preserved as evidence, but their old format has no
    # continuous transcription.  We do not synthesize one from field claims.
    return ""


def grounding_findings(label: ReaderLabel) -> tuple[ValidationFinding, ...]:
    """Return fail-closed, field-addressed groundedness violations for one label."""
    findings: list[ValidationFinding] = []
    transcription = _normalized_text(_continuous_transcription(label))
    requires_cyrillic = str(label.target.get("language", "")).casefold() == "ru"

    for field_path, evidence in label.observations.items():
        if evidence.get("observation_state") != "PRESENT":
            continue
        original = evidence.get("original_script")
        original_text = original if isinstance(original, str) else ""

        if requires_cyrillic and not CYRILLIC_RE.search(original_text):
            findings.append(
                ValidationFinding(
                    code="PRESENT_RU_ORIGINAL_SCRIPT_HAS_NO_CYRILLIC",
                    message=(
                        f"{field_path}: PRESENT evidence on a Russian-language act must "
                        "include Cyrillic in original_script"
                    ),
                    record_ids=(label.record_id,),
                    field_paths=(str(field_path),),
                    severity="GROUNDEDNESS_FAILURE",
                    evidence={
                        "label_id": label.label_id,
                        "reader_id": label.reader_id,
                    },
                )
            )

        normalized_original = _normalized_text(original_text)
        if (
            not normalized_original
            or not transcription
            or normalized_original not in transcription
        ):
            findings.append(
                ValidationFinding(
                    code="PRESENT_ORIGINAL_SCRIPT_NOT_IN_TRANSCRIPTION",
                    message=(
                        f"{field_path}: original_script for PRESENT evidence must be a "
                        "continuous substring of the reader's own transcription"
                    ),
                    record_ids=(label.record_id,),
                    field_paths=(str(field_path),),
                    severity="GROUNDEDNESS_FAILURE",
                    evidence={
                        "label_id": label.label_id,
                        "reader_id": label.reader_id,
                        "continuous_transcription_present": bool(transcription),
                    },
                )
            )
    return tuple(findings)


def require_grounded(label: ReaderLabel) -> ReaderLabel:
    """Return ``label`` or reject it before it can enter consensus/training."""
    findings = grounding_findings(label)
    if findings:
        rendered = "; ".join(f"{item.code}:{item.field_paths[0]}" for item in findings[:8])
        remainder = len(findings) - min(len(findings), 8)
        if remainder:
            rendered += f"; plus {remainder} more"
        raise GroundingValidationError(
            f"{label.label_id}: {len(findings)} groundedness violation(s): {rendered}"
        )
    return label


def require_grounded_payload(payload: Mapping[str, Any]) -> None:
    """Reject a schema-validated, pipeline-stamped payload that is not grounded."""
    target = payload.get("target")
    if not isinstance(target, Mapping):
        target = payload.get("target_check")
    transcription = payload.get("transcription")
    observations = payload.get("observations")
    if not isinstance(target, Mapping) or not isinstance(transcription, Mapping):
        raise GroundingValidationError("payload has no target or continuous transcription")
    if not isinstance(observations, Mapping):
        raise GroundingValidationError("payload has no observations")
    continuous = transcription.get("original_script")
    if isinstance(continuous, list) and all(
        isinstance(line, str) for line in continuous
    ):
        continuous = "\n".join(continuous)
    normalized_transcription = (
        _normalized_text(continuous) if isinstance(continuous, str) else ""
    )
    requires_cyrillic = str(target.get("language", "")).casefold() == "ru"
    violations: list[str] = []
    for field_path, evidence in observations.items():
        if not isinstance(evidence, Mapping) or evidence.get("observation_state") != "PRESENT":
            continue
        original = evidence.get("original_script")
        original_text = original if isinstance(original, str) else ""
        if requires_cyrillic and not CYRILLIC_RE.search(original_text):
            violations.append(
                f"PRESENT_RU_ORIGINAL_SCRIPT_HAS_NO_CYRILLIC:{field_path}"
            )
        normalized_original = _normalized_text(original_text)
        if (
            not normalized_original
            or not normalized_transcription
            or normalized_original not in normalized_transcription
        ):
            violations.append(
                f"PRESENT_ORIGINAL_SCRIPT_NOT_IN_TRANSCRIPTION:{field_path}"
            )
    if violations:
        rendered = "; ".join(violations[:8])
        if len(violations) > 8:
            rendered += f"; plus {len(violations) - 8} more"
        raise GroundingValidationError(
            f"{payload.get('label_id', 'reader payload')}: "
            f"{len(violations)} groundedness violation(s): {rendered}"
        )

def load_grounded_reader_label(path: Any) -> ReaderLabel:
    """Load a label and enforce the groundedness contract at ingest."""
    return require_grounded(load_reader_label(path))


def paired_quality_metrics(labels: Iterable[ReaderLabel]) -> dict[str, Any]:
    """Aggregate coverage and groundedness, always returning both metric families."""
    materialized = tuple(labels)
    reported = 0
    present = 0
    cyrillic_applicable = 0
    cyrillic_supported = 0
    transcription_supported = 0
    fully_grounded = 0
    violation_count = 0

    for label in materialized:
        transcription = _normalized_text(_continuous_transcription(label))
        requires_cyrillic = str(label.target.get("language", "")).casefold() == "ru"
        for evidence in label.observations.values():
            reported += 1
            if evidence.get("observation_state") != "PRESENT":
                continue
            present += 1
            original = evidence.get("original_script")
            original_text = original if isinstance(original, str) else ""
            cyrillic_ok = not requires_cyrillic or bool(CYRILLIC_RE.search(original_text))
            if requires_cyrillic:
                cyrillic_applicable += 1
                cyrillic_supported += int(cyrillic_ok)
            normalized_original = _normalized_text(original_text)
            transcription_ok = bool(
                normalized_original
                and transcription
                and normalized_original in transcription
            )
            transcription_supported += int(transcription_ok)
            fully_grounded += int(cyrillic_ok and transcription_ok)
        violation_count += len(grounding_findings(label))

    def rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 6) if denominator else 1.0

    return {
        "coverage": {
            "label_count": len(materialized),
            "reported_observation_count": reported,
            "present_observation_count": present,
            "non_present_observation_count": reported - present,
            "present_rate": rate(present, reported),
        },
        "groundedness": {
            "present_observation_count": present,
            "cyrillic_applicable_count": cyrillic_applicable,
            "cyrillic_supported_count": cyrillic_supported,
            "transcription_supported_count": transcription_supported,
            "fully_grounded_count": fully_grounded,
            "violation_count": violation_count,
            "groundedness_rate": rate(fully_grounded, present),
        },
    }


def _age_years(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if value >= 0 else None
    if isinstance(value, Mapping):
        units = {
            "hours": 1 / (24 * 365.2425),
            "days": 1 / 365.2425,
            "weeks": 7 / 365.2425,
            "months": 1 / 12,
            "years": 1,
        }
        total = 0.0
        seen = False
        for key, multiplier in units.items():
            component = value.get(key)
            if isinstance(component, int | float) and not isinstance(component, bool):
                if component < 0:
                    return None
                total += float(component) * multiplier
                seen = True
        return total if seen else None
    if not isinstance(value, str) or value.casefold().startswith("[unclear:"):
        return None
    stripped = value.strip()
    if NUMERIC_AGE_RE.fullmatch(stripped):
        return float(stripped.replace(",", "."))

    total = 0.0
    seen = False
    for match in AGE_COMPONENT_RE.finditer(stripped):
        number = float(match.group("number").replace(",", "."))
        unit = match.group("unit").casefold()
        if unit.startswith(("hour", "hr", "час")):
            multiplier = 1 / (24 * 365.2425)
        elif unit.startswith(("day", "дн", "dni", "dzie")):
            multiplier = 1 / 365.2425
        elif unit.startswith(("week", "нед", "tygod")):
            multiplier = 7 / 365.2425
        elif unit.startswith(("month", "мес", "mies")):
            multiplier = 1 / 12
        else:
            multiplier = 1
        total += number * multiplier
        seen = True
    return total if seen else None


def _life_stage(age_years: float) -> str:
    if age_years < 2:
        return "infant"
    if age_years < 18:
        return "child"
    return "adult"


def validate_cross_reader_grounding(
    left: ReaderLabel,
    right: ReaderLabel,
) -> tuple[ValidationFinding, ...]:
    """Escalate impossible principal-age divergence as groundedness, not arbitration."""
    left_age = left.observations.get("principal.age")
    right_age = right.observations.get("principal.age")
    if not isinstance(left_age, Mapping) or not isinstance(right_age, Mapping):
        return ()
    if (
        left_age.get("observation_state") != "PRESENT"
        or right_age.get("observation_state") != "PRESENT"
    ):
        return ()
    left_years = _age_years(left_age.get("value"))
    right_years = _age_years(right_age.get("value"))
    if left_years is None or right_years is None:
        return ()

    left_stage = _life_stage(left_years)
    right_stage = _life_stage(right_years)
    minimum = min(left_years, right_years)
    maximum = max(left_years, right_years)
    ratio = float("inf") if minimum == 0 and maximum > 0 else (
        maximum / minimum if minimum > 0 else 1.0
    )
    reasons: list[str] = []
    if left_stage != right_stage:
        reasons.append("LIFE_STAGE_MISMATCH")
    if ratio > 10:
        reasons.append("AGE_RATIO_GT_10")
    if not reasons:
        return ()

    return (
        ValidationFinding(
            code="CROSS_READER_PRINCIPAL_AGE_IMPOSSIBILITY",
            message=(
                "Principal age readings are mutually implausible; route as a "
                "groundedness incident before ordinary field arbitration"
            ),
            record_ids=(left.record_id,),
            field_paths=("principal.age",),
            severity="GROUNDEDNESS_INCIDENT",
            evidence={
                "left_label_id": left.label_id,
                "right_label_id": right.label_id,
                "left_value": left_age.get("value"),
                "right_value": right_age.get("value"),
                "left_life_stage": left_stage,
                "right_life_stage": right_stage,
                "age_ratio": "Infinity" if ratio == float("inf") else round(ratio, 6),
                "reasons": reasons,
            },
        ),
    )


__all__ = [
    "GroundingValidationError",
    "grounding_findings",
    "load_grounded_reader_label",
    "paired_quality_metrics",
    "require_grounded",
    "require_grounded_payload",
    "validate_cross_reader_grounding",
]
