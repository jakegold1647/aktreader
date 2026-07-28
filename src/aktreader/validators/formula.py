"""Formula-slot and source-span validation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from aktreader.validators.models import ValidationFinding
from aktreader.validators.support import observations_of, record_id_of

PERSON_FILIATION_RE = re.compile(r"^(?:father|mother|spouse|spouse_parents\.(?:father|mother))\.")
ATTESTOR_RE = re.compile(r"^(?:declarants|witnesses)\.\d+\.")


def _allowed_spans(path: str) -> set[str] | None:
    if path in {"act_no", "year", "registration_date"}:
        return {"registration"}
    if path == "town":
        return {"registration", "event"}
    if path == "act_type" or path.startswith("principal."):
        # Death certifications commonly repeat the principal's name in the closing formula.
        return {"principal", "event", "filiation", "closing"}
    if path == "event_date":
        return {"event"}
    if PERSON_FILIATION_RE.match(path) or path == "deceased_left_behind":
        return {"filiation", "principal", "event"}
    if ATTESTOR_RE.match(path):
        return {"declarants", "witnesses"}
    if path in {"officiant", "signatures_note"}:
        return {"closing"}
    if path == "marginalia":
        return {"marginalia", "registration", "closing"}
    return None


def validate_formula_positions(record: Any) -> tuple[ValidationFinding, ...]:
    """Flag absent, dangling, or formula-inconsistent source-span references."""
    observations = observations_of(record)
    source_spans = getattr(record, "source_spans", {})
    record_id = record_id_of(record)
    if not isinstance(source_spans, Mapping) or not source_spans:
        return (
            ValidationFinding(
                code="SOURCE_SPANS_UNVERIFIED",
                message=(
                    "No source boxes are bound to this observation; formula position cannot "
                    "be verified and fields remain capped at PROBABLE."
                ),
                record_ids=(record_id,),
                field_paths=tuple(sorted(str(path) for path in observations)),
                evidence={"source_span_count": 0},
            ),
        )

    findings: list[ValidationFinding] = []
    known = set(source_spans)
    for path, evidence in observations.items():
        if not isinstance(evidence, Mapping):
            continue
        span_ids = evidence.get("source_span_ids")
        if not isinstance(span_ids, (list, tuple)) or not span_ids:
            findings.append(
                ValidationFinding(
                    code="SOURCE_SPAN_MISSING",
                    message=f"{path} has no source-span reference.",
                    record_ids=(record_id,),
                    field_paths=(str(path),),
                )
            )
            continue
        dangling = [span_id for span_id in span_ids if span_id not in known]
        if dangling:
            findings.append(
                ValidationFinding(
                    code="SOURCE_SPAN_DANGLING",
                    message=f"{path} refers to unknown source spans {dangling!r}.",
                    record_ids=(record_id,),
                    field_paths=(str(path),),
                    evidence={"unknown_source_span_ids": dangling},
                )
            )
            continue
        allowed = _allowed_spans(str(path))
        if allowed is None:
            continue
        unexpected = [span_id for span_id in span_ids if span_id not in allowed]
        if unexpected:
            findings.append(
                ValidationFinding(
                    code="FORMULA_POSITION",
                    message=(
                        f"{path} is sourced from {unexpected!r}, outside its expected "
                        f"rhetorical slot(s) {sorted(allowed)!r}."
                    ),
                    record_ids=(record_id,),
                    field_paths=(str(path),),
                    evidence={
                        "source_span_ids": list(span_ids),
                        "allowed_source_span_ids": sorted(allowed),
                    },
                )
            )
    return tuple(findings)
