"""Fail-closed training exports and deterministic training-readiness reports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aktreader.grounding import grounding_findings
from aktreader.labels import load_reader_label


class TrainingExportError(ValueError):
    """Raised when provenance, grounding, or evaluation isolation fails closed."""


def sha256_path(path: Path) -> str:
    """Return the lowercase SHA-256 of one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_object(path: Path, *, role: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TrainingExportError(f"{role} is not readable strict JSON: {path}") from error
    if not isinstance(payload, dict):
        raise TrainingExportError(f"{role} must be a JSON object: {path}")
    return payload


def _workspace_path(root: Path, relative: Any, *, role: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise TrainingExportError(f"{role} must be a non-empty workspace-relative path")
    candidate = Path(relative)
    if candidate.is_absolute():
        raise TrainingExportError(f"{role} must be workspace-relative: {relative}")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise TrainingExportError(f"{role} escapes workspace: {relative}") from error
    return resolved


def validate_training_split(
    clerk_year_ids: set[str],
    evaluation_holdout: Mapping[str, Any],
) -> None:
    """Reject any training clerk-year represented in the chosen evaluation holdout."""
    if evaluation_holdout.get("training_overlap_allowed") is not False:
        raise TrainingExportError(
            "evaluation holdout must explicitly set training_overlap_allowed=false"
        )
    holdout_ids = evaluation_holdout.get("holdout_clerk_year_ids")
    if not isinstance(holdout_ids, list) or not all(
        isinstance(item, str) and item for item in holdout_ids
    ):
        raise TrainingExportError("evaluation holdout has invalid holdout_clerk_year_ids")
    overlap = sorted(clerk_year_ids & set(holdout_ids))
    if overlap:
        raise TrainingExportError(f"training/evaluation clerk-year leakage: {overlap}")


def _source_labels(entry: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    provenance = entry.get("provenance")
    sources = provenance.get("source_labels") if isinstance(provenance, Mapping) else None
    if not isinstance(sources, list) or not sources:
        raise TrainingExportError(
            f"{entry.get('record_id')}: provenance.source_labels must be non-empty"
        )
    if not all(isinstance(source, Mapping) for source in sources):
        raise TrainingExportError(
            f"{entry.get('record_id')}: provenance source labels must be objects"
        )
    return sources


def _grounding_failures(
    root: Path,
    entry: Mapping[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for source in _source_labels(entry):
        relative = source.get("path")
        expected_sha = source.get("sha256")
        try:
            source_path = _workspace_path(root, relative, role="source label")
            actual_sha = sha256_path(source_path)
            if not isinstance(expected_sha, str) or actual_sha != expected_sha:
                raise TrainingExportError("source label SHA-256 mismatch")
            label = load_reader_label(source_path)
            if label.record_id != entry.get("record_id"):
                raise TrainingExportError("source label record ID mismatch")
            expected_clerk_year = entry.get("clerk_year_id")
            if label.clerk_year_id and label.clerk_year_id != expected_clerk_year:
                raise TrainingExportError("source label clerk-year mismatch")
            findings = grounding_findings(label)
            if findings:
                failures.append(
                    {
                        "path": relative,
                        "failure": "GROUNDEDNESS_VIOLATIONS",
                        "violation_count": len(findings),
                        "codes": sorted({finding.code for finding in findings}),
                    }
                )
        except (OSError, UnicodeError, ValueError) as error:
            failures.append(
                {
                    "path": relative,
                    "failure": "SOURCE_LABEL_INVALID",
                    "detail": str(error),
                }
            )
    return failures


def _require_grounded_sources(root: Path, entry: Mapping[str, Any]) -> None:
    failures = _grounding_failures(root, entry)
    if failures:
        first = failures[0]
        raise TrainingExportError(
            f"{entry.get('record_id')}: source label is not grounded: "
            f"{first.get('path')}: {first.get('failure')}"
        )


def build_training_export(
    *,
    workspace_root: Path,
    silver_manifest_path: Path,
    evaluation_holdout_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build JSONL-ready examples and their content-addressed export manifest."""
    root = workspace_root.resolve()
    silver_manifest_path = silver_manifest_path.resolve()
    evaluation_holdout_path = evaluation_holdout_path.resolve()
    silver = _load_object(silver_manifest_path, role="silver manifest")
    holdout = _load_object(evaluation_holdout_path, role="evaluation holdout")
    records = silver.get("records")
    if not isinstance(records, list) or not records:
        raise TrainingExportError("silver manifest contains no records")

    clerk_year_ids: set[str] = set()
    for entry in records:
        if not isinstance(entry, dict):
            raise TrainingExportError("silver manifest record must be an object")
        if entry.get("training_eligible") is not True:
            raise TrainingExportError(f"{entry.get('record_id')}: record is not training eligible")
        if entry.get("training_materialized") is not True:
            raise TrainingExportError(f"{entry.get('record_id')}: record is not materialized")
        clerk_year_id = entry.get("clerk_year_id")
        if not isinstance(clerk_year_id, str) or not clerk_year_id:
            raise TrainingExportError(f"{entry.get('record_id')}: invalid clerk-year ID")
        clerk_year_ids.add(clerk_year_id)

    validate_training_split(clerk_year_ids, holdout)
    for entry in records:
        _require_grounded_sources(root, entry)

    examples: list[dict[str, Any]] = []
    record_pins: list[dict[str, str]] = []
    for entry in records:
        resolved = entry.get("resolved_fields")
        if not isinstance(resolved, dict) or resolved.get("storage") != "MATERIALIZED_JSON":
            raise TrainingExportError(f"{entry.get('record_id')}: invalid materialized payload")
        relative = resolved.get("path")
        expected_sha = resolved.get("sha256")
        if not isinstance(expected_sha, str):
            raise TrainingExportError(f"{entry.get('record_id')}: incomplete payload pin")
        record_path = _workspace_path(root, relative, role="silver payload")
        actual_sha = sha256_path(record_path)
        if actual_sha != expected_sha:
            raise TrainingExportError(f"{entry.get('record_id')}: silver payload SHA-256 mismatch")
        record = _load_object(record_path, role="materialized silver record")
        if record.get("record_id") != entry.get("record_id"):
            raise TrainingExportError(f"{entry.get('record_id')}: payload record ID mismatch")
        if record.get("clerk_year", {}).get("id") != entry.get("clerk_year_id"):
            raise TrainingExportError(f"{entry.get('record_id')}: payload clerk-year mismatch")

        examples.append(
            {
                "schema_version": "1.0.0",
                "record_id": record["record_id"],
                "clerk_year_id": entry["clerk_year_id"],
                "image": record["artifact"],
                "input": {"target": record["target"]},
                "output": {"observations": record["observations"]},
                "authority_warning": record["authority_warning"],
            }
        )
        record_pins.append({"path": str(relative), "sha256": actual_sha})

    manifest = {
        "schema_version": "1.0.0",
        "format": "AKTREADER_PROVIDER_NEUTRAL_JSONL",
        "example_count": len(examples),
        "clerk_year_ids": sorted(clerk_year_ids),
        "silver_manifest": {
            "path": str(silver_manifest_path),
            "sha256": sha256_path(silver_manifest_path),
        },
        "evaluation_holdout": {
            "path": str(evaluation_holdout_path),
            "sha256": sha256_path(evaluation_holdout_path),
        },
        "materialized_records": record_pins,
        "split_validation": "PASS_NO_CLERK_YEAR_OVERLAP",
        "grounding_validation": "PASS_ALL_SOURCE_LABELS_GROUNDED",
    }
    return examples, manifest


def build_training_readiness(
    *,
    workspace_root: Path,
    plan_path: Path,
) -> dict[str, Any]:
    """Measure all launch gates without mutating labels or starting paid compute."""
    root = workspace_root.resolve()
    plan_path = plan_path.resolve()
    plan = _load_object(plan_path, role="training plan")
    inputs = plan.get("inputs")
    minimums = plan.get("minimums")
    if not isinstance(inputs, Mapping) or not isinstance(minimums, Mapping):
        raise TrainingExportError("training plan requires object inputs and minimums")

    silver_path = _workspace_path(root, inputs.get("silver_manifest"), role="silver manifest")
    holdout_path = _workspace_path(
        root, inputs.get("evaluation_holdout"), role="evaluation holdout"
    )
    attestation_path = _workspace_path(
        root, inputs.get("gold_attestation_audit"), role="gold attestation audit"
    )
    recipe_path = _workspace_path(root, inputs.get("lora_recipe"), role="LoRA recipe")
    silver = _load_object(silver_path, role="silver manifest")
    holdout = _load_object(holdout_path, role="evaluation holdout")
    attestation = _load_object(attestation_path, role="gold attestation audit")
    recipe = _load_object(recipe_path, role="LoRA recipe")

    records = silver.get("records")
    if not isinstance(records, list):
        raise TrainingExportError("silver manifest records must be a list")
    record_reports: list[dict[str, Any]] = []
    training_clerk_year_ids: set[str] = set()
    for raw_entry in records:
        if not isinstance(raw_entry, Mapping):
            raise TrainingExportError("silver manifest record must be an object")
        clerk_year_id = raw_entry.get("clerk_year_id")
        if isinstance(clerk_year_id, str):
            training_clerk_year_ids.add(clerk_year_id)
        failures = _grounding_failures(root, raw_entry)
        record_reports.append(
            {
                "record_id": raw_entry.get("record_id"),
                "grounded": not failures,
                "failures": failures,
            }
        )

    holdout_ids = holdout.get("holdout_clerk_year_ids")
    holdout_set = set(holdout_ids) if isinstance(holdout_ids, list) else set()
    overlap = sorted(training_clerk_year_ids & holdout_set)
    grounded_count = sum(item["grounded"] for item in record_reports)
    attestation_summary = attestation.get("summary")
    image_attested_count = (
        attestation_summary.get("fully_image_verified_record_count", 0)
        if isinstance(attestation_summary, Mapping)
        else 0
    )
    minimum_grounded = int(minimums.get("grounded_training_records", 0))
    minimum_holdout = int(minimums.get("image_attested_holdout_records", 0))

    lora = recipe.get("lora")
    trainer = recipe.get("trainer")
    target_modules = lora.get("target_modules") if isinstance(lora, Mapping) else None
    recipe_ready = (
        isinstance(recipe.get("base_model_repository"), str)
        and isinstance(recipe.get("base_model_revision"), str)
        and recipe.get("weights_format") == "safetensors"
        and isinstance(target_modules, list)
        and bool(target_modules)
        and isinstance(trainer, Mapping)
        and all(
            isinstance(trainer.get(key), str) and trainer.get(key)
            for key in ("implementation", "version", "container_digest")
        )
    )
    bakeoff = plan.get("model_bakeoff")
    candidates = bakeoff.get("candidates") if isinstance(bakeoff, Mapping) else None
    calibration_ids = (
        bakeoff.get("calibration_record_ids") if isinstance(bakeoff, Mapping) else None
    )
    calibration_target = (
        bakeoff.get("calibration_record_target") if isinstance(bakeoff, Mapping) else None
    )
    calibration_ready = (
        isinstance(calibration_ids, list)
        and isinstance(calibration_target, int)
        and not isinstance(calibration_target, bool)
        and calibration_target > 0
        and len(calibration_ids) >= calibration_target
        and len(calibration_ids) == len(set(calibration_ids))
        and all(isinstance(item, str) and item for item in calibration_ids)
    )
    pins_ready = (
        isinstance(candidates, list)
        and bool(candidates)
        and all(
            isinstance(candidate, Mapping)
            and isinstance(candidate.get("repository"), str)
            and isinstance(candidate.get("revision"), str)
            and len(candidate["revision"]) == 40
            for candidate in candidates
        )
    )

    def gate(code: str, passed: bool, detail: str) -> dict[str, str]:
        return {"code": code, "status": "PASS" if passed else "BLOCKED", "detail": detail}

    gates = [
        gate(
            "GROUNDED_TRAINING_MINIMUM",
            grounded_count >= minimum_grounded,
            f"{grounded_count}/{minimum_grounded} grounded records",
        ),
        gate(
            "IMAGE_ATTESTED_HOLDOUT_MINIMUM",
            isinstance(image_attested_count, int) and image_attested_count >= minimum_holdout,
            f"{image_attested_count}/{minimum_holdout} fully image-verified holdout records",
        ),
        gate(
            "CLERK_YEAR_ISOLATION",
            holdout.get("training_overlap_allowed") is False and not overlap,
            f"overlap={overlap}",
        ),
        gate(
            "TRAINER_RECIPE_PINNED",
            recipe_ready,
            (
                "requires trainable base revision, non-empty target modules, "
                "and pinned trainer/container"
            ),
        ),
        gate(
            "CALIBRATION_SET_MINIMUM",
            bool(calibration_ready),
            f"{len(calibration_ids) if isinstance(calibration_ids, list) else 0}/"
            f"{calibration_target or 0} sequestered calibration records",
        ),
        gate(
            "MODEL_BAKEOFF_REVISIONS_PINNED",
            bool(pins_ready),
            "all bakeoff candidates require exact 40-character repository revisions",
        ),
    ]
    ready = all(item["status"] == "PASS" for item in gates)
    return {
        "schema_version": "1.0.0",
        "plan_id": plan.get("plan_id"),
        "measured_on": plan.get("measured_on"),
        "status": "READY" if ready else "BLOCKED",
        "paid_training_authorized": plan.get("paid_training_authorized") is True,
        "paid_training_launch_allowed": ready and plan.get("paid_training_authorized") is True,
        "metrics": {
            "silver_record_count": len(records),
            "grounded_training_record_count": grounded_count,
            "minimum_grounded_training_records": minimum_grounded,
            "image_attested_holdout_record_count": image_attested_count,
            "minimum_image_attested_holdout_records": minimum_holdout,
            "training_clerk_year_ids": sorted(training_clerk_year_ids),
            "evaluation_overlap_clerk_year_ids": overlap,
            "calibration_record_count": (
                len(calibration_ids) if isinstance(calibration_ids, list) else 0
            ),
            "minimum_calibration_records": (
                calibration_target if isinstance(calibration_target, int) else 0
            ),
        },
        "gates": gates,
        "record_grounding": record_reports,
        "input_pins": {
            "plan": {"path": str(plan_path), "sha256": sha256_path(plan_path)},
            "silver_manifest": {"path": str(silver_path), "sha256": sha256_path(silver_path)},
            "evaluation_holdout": {
                "path": str(holdout_path),
                "sha256": sha256_path(holdout_path),
            },
            "gold_attestation_audit": {
                "path": str(attestation_path),
                "sha256": sha256_path(attestation_path),
            },
            "lora_recipe": {"path": str(recipe_path), "sha256": sha256_path(recipe_path)},
        },
    }
