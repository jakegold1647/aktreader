"""SerockBench evaluation with clerk-year leakage guards and honest calibration."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

FILIATION_PATHS = {
    "principal.name",
    "principal.maiden_name",
    "father.name",
    "mother.name",
    "mother.maiden_name",
    "spouse.name",
    "spouse.maiden_name",
    "spouse_parents.father.name",
    "spouse_parents.mother.name",
    "spouse_parents.mother.maiden_name",
}


class EvaluationIntegrityError(ValueError):
    """Raised when a benchmark or training split violates evaluation integrity."""


def _is_evidence(value: Any) -> bool:
    return isinstance(value, dict) and {"value", "observation_state"}.issubset(value)


def flatten_gold_fields(value: Any, prefix: str = "") -> dict[str, dict[str, Any]]:
    """Flatten the recursive P1 field tree into stable dotted observation paths."""
    if _is_evidence(value):
        return {prefix: value}
    flattened: dict[str, dict[str, Any]] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            flattened.update(flatten_gold_fields(child, child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_prefix = f"{prefix}.{index}" if prefix else str(index)
            flattened.update(flatten_gold_fields(child, child_prefix))
    return flattened


def canonical_exact(value: Any) -> str:
    """Apply only mechanical normalization; never bridge names or transliterations."""
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFC", value)
        return re.sub(r"\s+", " ", normalized).strip().casefold()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _prediction_observations(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    observations = record.get("observations")
    if not isinstance(observations, dict):
        raise EvaluationIntegrityError(
            f"{record.get('record_id', '<unknown>')}: predictions require an observations map"
        )
    return observations


def _gold_is_scorable(field: dict[str, Any]) -> bool:
    return (
        field.get("observation_state") != "NOT_ANNOTATED"
        and field.get("confidence") != "UNCLEAR"
        and field.get("value") is not None
    )


def _alternative_contains(prediction: dict[str, Any], gold_value: Any) -> bool:
    wanted = canonical_exact(gold_value)
    for alternative in prediction.get("alternatives", []):
        value = alternative.get("value") if isinstance(alternative, dict) else alternative
        if canonical_exact(value) == wanted:
            return True
    return False


def validate_holdout_integrity(
    gold_records: Iterable[dict[str, Any]],
    holdout: dict[str, Any],
    *,
    training_clerk_year_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Verify permanent clerk-year sequestering and reject any training leakage."""
    records = list(gold_records)
    gold_ids = {record["record_id"] for record in records}
    gold_clerk_years = {record["register"]["clerk_year"]["id"] for record in records}
    holdout_ids = set(holdout.get("record_ids", []))
    holdout_clerk_years = set(holdout.get("holdout_clerk_year_ids", []))
    training = set(training_clerk_year_ids)

    if holdout.get("training_overlap_allowed") is not False:
        raise EvaluationIntegrityError("holdout manifest must explicitly forbid training overlap")
    if gold_ids != holdout_ids:
        missing = sorted(gold_ids - holdout_ids)
        extra = sorted(holdout_ids - gold_ids)
        raise EvaluationIntegrityError(
            f"holdout record mismatch; missing={missing}, extra={extra}"
        )
    if gold_clerk_years != holdout_clerk_years:
        raise EvaluationIntegrityError("holdout clerk-year set does not match the gold corpus")
    leakage = sorted(training & holdout_clerk_years)
    if leakage:
        raise EvaluationIntegrityError(f"training/eval clerk-year leakage: {leakage}")

    return {
        "status": "PASS",
        "records": len(gold_ids),
        "clerk_years": len(gold_clerk_years),
        "training_overlap": 0,
    }


def evaluate_predictions(
    gold_records: Iterable[dict[str, Any]],
    prediction_records: Iterable[dict[str, Any]],
    holdout: dict[str, Any],
    *,
    training_clerk_year_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Score predictions without treating abstention or zero denominators as success."""
    gold = list(gold_records)
    prediction_list = list(prediction_records)
    prediction_ids = [record["record_id"] for record in prediction_list]
    if len(prediction_ids) != len(set(prediction_ids)):
        raise EvaluationIntegrityError("duplicate prediction record IDs")
    predictions = {record["record_id"]: record for record in prediction_list}

    leakage = validate_holdout_integrity(
        gold, holdout, training_clerk_year_ids=training_clerk_year_ids
    )
    calibration: dict[str, Counter[str]] = {
        grade: Counter() for grade in ("CONFIDENT", "PROBABLE", "UNCLEAR")
    }
    filiation_correct = 0
    filiation_total = 0
    filiation_acts_correct = 0
    filiation_acts_total = 0
    wrong_confident = 0
    confident_scorable = 0
    state_correct = 0
    state_total = 0
    unclear_count = 0
    illegible_count = 0
    scored_fields = 0

    for gold_record in gold:
        prediction = predictions.get(gold_record["record_id"])
        if prediction is None:
            continue
        predicted_fields = _prediction_observations(prediction)
        gold_fields = flatten_gold_fields(gold_record["fields"])
        act_filiation_results: list[bool] = []

        for path, gold_field in gold_fields.items():
            predicted = predicted_fields.get(path)
            if predicted is None:
                if path in FILIATION_PATHS and _gold_is_scorable(gold_field):
                    filiation_total += 1
                    act_filiation_results.append(False)
                continue

            gold_state = gold_field.get("observation_state")
            predicted_state = predicted.get("observation_state")
            if gold_state != "NOT_ANNOTATED":
                state_total += 1
                state_correct += int(gold_state == predicted_state)

            if predicted_state == "ILLEGIBLE":
                illegible_count += 1
            grade = predicted.get("confidence")
            if grade == "UNCLEAR":
                unclear_count += 1

            if not _gold_is_scorable(gold_field):
                continue
            scored_fields += 1
            exact = (
                predicted_state == gold_state
                and canonical_exact(predicted.get("value"))
                == canonical_exact(gold_field.get("value"))
            )

            if grade in calibration:
                calibration[grade]["scored"] += 1
                supported = exact or (grade == "UNCLEAR" and _alternative_contains(
                    predicted, gold_field.get("value")
                ))
                calibration[grade]["supported"] += int(supported)
                calibration[grade]["exact"] += int(exact)

            if grade == "CONFIDENT":
                confident_scorable += 1
                wrong_confident += int(not exact)

            if path in FILIATION_PATHS:
                filiation_total += 1
                filiation_correct += int(exact)
                act_filiation_results.append(exact)

        if act_filiation_results:
            filiation_acts_total += 1
            filiation_acts_correct += int(all(act_filiation_results))

    calibration_table: dict[str, dict[str, Any]] = {}
    for grade, counts in calibration.items():
        scored = counts["scored"]
        calibration_table[grade] = {
            "scored": scored,
            "exact": counts["exact"],
            "supported": counts["supported"],
            "exact_rate": counts["exact"] / scored if scored else None,
            "support_rate": counts["supported"] / scored if scored else None,
        }

    matched_records = len(set(predictions) & {record["record_id"] for record in gold})
    total_records = len(gold)
    wrong_rate = wrong_confident / confident_scorable if confident_scorable else None
    return {
        "benchmark": "SerockBench-v1",
        "records": {
            "gold": total_records,
            "predicted": matched_records,
            "coverage": matched_records / total_records if total_records else math.nan,
        },
        "holdout_integrity": leakage,
        "filiation_exact_match": {
            "fields_correct": filiation_correct,
            "fields_total": filiation_total,
            "field_rate": filiation_correct / filiation_total if filiation_total else None,
            "acts_exact": filiation_acts_correct,
            "acts_total": filiation_acts_total,
            "act_rate": filiation_acts_correct / filiation_acts_total
            if filiation_acts_total
            else None,
        },
        "wrong_but_confident": {
            "wrong": wrong_confident,
            "confident_scorable": confident_scorable,
            "rate": wrong_rate,
            "display": (
                f"{wrong_rate:.2%} ({wrong_confident}/{confident_scorable})"
                if wrong_rate is not None
                else "N/A (0/0)"
            ),
        },
        "calibration": calibration_table,
        "abstention": {
            "unclear_fields": unclear_count,
            "illegible_fields": illegible_count,
            "scored_fields": scored_fields,
        },
        "observation_state_accuracy": {
            "correct": state_correct,
            "total": state_total,
            "rate": state_correct / state_total if state_total else None,
        },
    }


def load_prediction_records(path: Path) -> list[dict[str, Any]]:
    """Load either one prediction JSON or every JSON in a directory."""
    paths = sorted(path.glob("*.json")) if path.is_dir() else [path]
    records = [json.loads(item.read_text(encoding="utf-8")) for item in paths]
    ids = [record.get("record_id") for record in records]
    if len(ids) != len(set(ids)):
        raise EvaluationIntegrityError("duplicate prediction record IDs")
    return records
