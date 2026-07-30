"""Deterministic scoring for blind human-transcriber qualification adjudication."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import jsonschema


class QualificationScoringError(ValueError):
    """Raised when a qualification adjudication cannot be scored safely."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path, *, role: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise QualificationScoringError(f"{role} is not readable strict JSON: {path}") from error
    if not isinstance(payload, dict):
        raise QualificationScoringError(f"{role} must be a JSON object: {path}")
    return payload


def _validate_adjudication(
    adjudication: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> None:
    try:
        jsonschema.Draft202012Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        ).validate(adjudication)
    except jsonschema.ValidationError as error:
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        raise QualificationScoringError(f"{location}: {error.message}") from error


def _resolve_pin_path(raw: Any, *, base: Path, role: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise QualificationScoringError(f"{role} path must be non-empty")
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def score_qualification_adjudication(
    *,
    intake_path: Path,
    adjudication_path: Path,
    adjudication_schema_path: Path,
) -> dict[str, Any]:
    """Score one complete adjudication against the frozen qualification thresholds."""
    intake_path = intake_path.resolve()
    adjudication_path = adjudication_path.resolve()
    adjudication_schema_path = adjudication_schema_path.resolve()
    intake = _load_object(intake_path, role="qualification intake")
    adjudication = _load_object(adjudication_path, role="qualification adjudication")
    schema = _load_object(adjudication_schema_path, role="adjudication schema")
    _validate_adjudication(adjudication, schema)

    if intake.get("status") != "COMPLETE":
        raise QualificationScoringError("qualification intake is not complete")
    if intake.get("machine_assistance_detected") is not False:
        raise QualificationScoringError("qualification intake reports machine assistance")
    packet_id = intake.get("packet_id")
    if adjudication.get("packet_id") != packet_id:
        raise QualificationScoringError("adjudication packet ID mismatch")
    intake_pin = adjudication["intake_report"]
    pinned_intake_path = _resolve_pin_path(
        intake_pin["path"],
        base=adjudication_path.parent,
        role="intake report",
    )
    if pinned_intake_path != intake_path:
        raise QualificationScoringError("adjudication intake path mismatch")
    if intake_pin["sha256"] != _sha256(intake_path):
        raise QualificationScoringError("adjudication intake SHA-256 mismatch")

    matrix = intake.get("matrix")
    if not isinstance(matrix, Mapping):
        raise QualificationScoringError("qualification intake matrix is missing")
    candidate_codes = matrix.get("candidate_codes")
    record_ids = matrix.get("record_ids")
    if (
        not isinstance(candidate_codes, list)
        or not candidate_codes
        or not all(isinstance(code, str) and code for code in candidate_codes)
        or len(candidate_codes) != len(set(candidate_codes))
    ):
        raise QualificationScoringError("qualification intake candidate matrix is invalid")
    if (
        not isinstance(record_ids, list)
        or not record_ids
        or not all(isinstance(record_id, str) and record_id for record_id in record_ids)
        or len(record_ids) != len(set(record_ids))
    ):
        raise QualificationScoringError("qualification intake record matrix is invalid")

    aggregates = {
        code: {
            "legible_character_count": 0,
            "character_error_count": 0,
            "material_error_count": 0,
            "material_hallucination_count": 0,
            "uncertain_regions_guessed_count": 0,
            "unreadable_regions_marked": True,
            "original_spelling_preserved": True,
            "independence_declaration_complete": True,
        }
        for code in candidate_codes
    }
    seen_records: set[str] = set()
    records = adjudication["records"]
    for record in records:
        record_id = record["record_id"]
        if record_id not in record_ids:
            raise QualificationScoringError(f"unexpected adjudication record: {record_id}")
        if record_id in seen_records:
            raise QualificationScoringError(f"duplicate adjudication record: {record_id}")
        seen_records.add(record_id)
        transcription = record["adjudicated_original_script"]
        if "\ufffd" in transcription:
            raise QualificationScoringError(
                f"{record_id}: adjudicated transcription has replacement characters"
            )
        actual_line_count = len(transcription.splitlines())
        if record["line_count"] != actual_line_count:
            raise QualificationScoringError(
                f"{record_id}: adjudicated transcription line count mismatch"
            )

        seen_candidates: set[str] = set()
        for assessment in record["candidate_assessments"]:
            candidate_code = assessment["candidate_code"]
            if candidate_code not in candidate_codes:
                raise QualificationScoringError(
                    f"{record_id}: unexpected candidate {candidate_code}"
                )
            if candidate_code in seen_candidates:
                raise QualificationScoringError(
                    f"{record_id}: duplicate candidate assessment {candidate_code}"
                )
            seen_candidates.add(candidate_code)
            if assessment["character_error_count"] > assessment["legible_character_count"]:
                raise QualificationScoringError(
                    f"{record_id}/{candidate_code}: character errors exceed legible characters"
                )
            aggregate = aggregates[candidate_code]
            for key in (
                "legible_character_count",
                "character_error_count",
                "material_error_count",
                "material_hallucination_count",
                "uncertain_regions_guessed_count",
            ):
                aggregate[key] += assessment[key]
            for key in (
                "unreadable_regions_marked",
                "original_spelling_preserved",
                "independence_declaration_complete",
            ):
                aggregate[key] = aggregate[key] and assessment[key]
        missing_candidates = sorted(set(candidate_codes) - seen_candidates)
        if missing_candidates:
            raise QualificationScoringError(
                f"{record_id}: missing candidate assessments {missing_candidates}"
            )

    missing_records = sorted(set(record_ids) - seen_records)
    if missing_records:
        raise QualificationScoringError(f"adjudication is missing records: {missing_records}")

    candidate_results: list[dict[str, Any]] = []
    for candidate_code in candidate_codes:
        aggregate = aggregates[candidate_code]
        legible = aggregate["legible_character_count"]
        errors = aggregate["character_error_count"]
        threshold_pass = errors * 100 <= legible * 3
        accuracy = round((legible - errors) / legible, 6)
        passed = (
            threshold_pass
            and aggregate["material_error_count"] == 0
            and aggregate["material_hallucination_count"] == 0
            and aggregate["uncertain_regions_guessed_count"] == 0
            and aggregate["unreadable_regions_marked"]
            and aggregate["original_spelling_preserved"]
            and aggregate["independence_declaration_complete"]
        )
        candidate_results.append(
            {
                "candidate_code": candidate_code,
                **aggregate,
                "character_accuracy": accuracy,
                "character_accuracy_threshold": 0.97,
                "character_accuracy_pass": threshold_pass,
                "qualification_status": "PASS" if passed else "FAIL",
            }
        )

    ranked = sorted(
        candidate_results,
        key=lambda item: (
            item["qualification_status"] != "PASS",
            -item["character_accuracy"],
            item["candidate_code"],
        ),
    )
    passed_codes = [
        item["candidate_code"] for item in ranked if item["qualification_status"] == "PASS"
    ]
    return {
        "schema_version": "1.0.0",
        "score_id": f"{packet_id}-score",
        "packet_id": packet_id,
        "status": "COMPLETE",
        "inputs": {
            "intake": {"path": str(intake_path), "sha256": _sha256(intake_path)},
            "adjudication": {
                "path": str(adjudication_path),
                "sha256": _sha256(adjudication_path),
            },
            "adjudication_schema": {
                "path": str(adjudication_schema_path),
                "sha256": _sha256(adjudication_schema_path),
            },
        },
        "thresholds": {
            "character_accuracy_minimum": 0.97,
            "material_error_maximum": 0,
            "material_hallucination_maximum": 0,
            "uncertain_regions_guessed_maximum": 0,
            "minimum_passing_candidates": 2,
        },
        "candidate_results": candidate_results,
        "ranked_candidate_codes": [item["candidate_code"] for item in ranked],
        "passing_candidate_codes": passed_codes,
        "production_hiring_gate": (
            "PASS_TWO_OR_MORE_QUALIFIED" if len(passed_codes) >= 2 else "BLOCKED_RECRUIT_AGAIN"
        ),
        "payment_approval": "NOT_GRANTED_BY_SCORER",
        "gold_promotion": "NONE",
        "authority_warning": "extraction is not authority — verify against the scan",
    }
