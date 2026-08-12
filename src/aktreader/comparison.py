"""Deterministic, local reader-to-reader comparison reports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from aktreader.evaluation import canonical_exact
from aktreader.grounding import (
    grounding_findings,
    load_grounded_reader_label,
    paired_quality_metrics,
    validate_cross_reader_grounding,
)
from aktreader.labels import (
    AUTHORITY_WARNING,
    LabelValidationError,
    ReaderLabel,
    load_reader_label,
    parse_legacy_reader_a,
)


class ComparisonError(ValueError):
    """Raised when a comparison input cannot be interpreted safely."""


CSV_FIELDNAMES = (
    "record_id",
    "field_path",
    "disagreement_kind",
    "left_observation_state",
    "right_observation_state",
    "left_value",
    "right_value",
    "left_confidence",
    "right_confidence",
    "left_original_script",
    "right_original_script",
)


def _spreadsheet_cell(value: Any) -> str:
    """Render one human-facing cell without allowing formula execution."""
    if value is None:
        rendered = ""
    elif isinstance(value, str):
        rendered = value
    else:
        rendered = json.dumps(
            _json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    candidate = rendered.lstrip(" \t\r\n")
    if candidate.startswith(("=", "+", "-", "@")):
        return f"'{rendered}"
    return rendered


def render_disagreements_csv(disagreements: Iterable[Mapping[str, Any]]) -> str:
    """Render every supplied disagreement as an Excel-friendly UTF-8 CSV."""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=CSV_FIELDNAMES,
        lineterminator="\r\n",
    )
    writer.writeheader()
    for item in disagreements:
        left = item.get("left")
        right = item.get("right")
        left_snapshot = left if isinstance(left, Mapping) else {}
        right_snapshot = right if isinstance(right, Mapping) else {}
        writer.writerow(
            {
                "record_id": _spreadsheet_cell(item.get("record_id")),
                "field_path": _spreadsheet_cell(item.get("field_path")),
                "disagreement_kind": _spreadsheet_cell(item.get("kind")),
                "left_observation_state": _spreadsheet_cell(
                    left_snapshot.get("observation_state")
                ),
                "right_observation_state": _spreadsheet_cell(
                    right_snapshot.get("observation_state")
                ),
                "left_value": _spreadsheet_cell(left_snapshot.get("value")),
                "right_value": _spreadsheet_cell(right_snapshot.get("value")),
                "left_confidence": _spreadsheet_cell(left_snapshot.get("confidence")),
                "right_confidence": _spreadsheet_cell(right_snapshot.get("confidence")),
                "left_original_script": _spreadsheet_cell(
                    left_snapshot.get("original_script")
                ),
                "right_original_script": _spreadsheet_cell(
                    right_snapshot.get("original_script")
                ),
            }
        )
    return "\ufeff" + stream.getvalue()


def _finding_report(finding: Any) -> dict[str, Any]:
    return {
        "code": finding.code,
        "message": finding.message,
        "record_ids": list(finding.record_ids),
        "field_paths": list(finding.field_paths),
        "severity": finding.severity,
        "blocks_confident": finding.blocks_confident,
        "evidence": _json_value(finding.evidence),
    }


def _json_value(value: Any) -> Any:
    """Convert frozen label data into ordinary JSON-compatible containers."""
    if isinstance(value, Mapping):
        return {str(key): _json_value(child) for key, child in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(child) for child in value]
    return value


def _looks_like_reader_label(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return True
    if not isinstance(payload, Mapping):
        return False
    canonical_keys = {"schema_version", "label_id", "reader", "observations"}
    legacy_keys = {"reader", "artifact", "register", "fields", "translation"}
    return canonical_keys.issubset(payload) or legacy_keys.issubset(payload)


def _label_paths(path: Path) -> tuple[list[Path], list[str]]:
    if path.is_file():
        return [path], []
    if not path.is_dir():
        raise ComparisonError(f"comparison input is not a file or directory: {path}")
    paths: list[Path] = []
    ignored: list[str] = []
    for item in sorted(path.rglob("*.json")):
        if not item.is_file():
            continue
        relative_parts = item.relative_to(path).parts[:-1]
        if any(part.casefold() == "superseded" for part in relative_parts):
            ignored.append(f"{item}: ignored because it is under superseded/")
            continue
        if _looks_like_reader_label(item):
            paths.append(item)
        else:
            ignored.append(f"{item}: ignored because it is not a reader-label JSON object")
    if not paths:
        raise ComparisonError(f"comparison input contains no reader-label JSON files: {path}")
    return paths, ignored


def _legacy_warning_compatibility(
    label_path: Path,
    *,
    error: LabelValidationError,
) -> tuple[ReaderLabel, str] | None:
    if "legacy label.authority_warning" not in str(error):
        return None
    try:
        payload = json.loads(label_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    warning = payload.get("authority_warning") if isinstance(payload, Mapping) else None
    if not (
        isinstance(warning, str)
        and warning.startswith("extraction is not authority - verify against the scan")
    ):
        return None
    normalized = dict(payload)
    normalized["authority_warning"] = AUTHORITY_WARNING
    try:
        digest = hashlib.sha256(label_path.read_bytes()).hexdigest()
        label = parse_legacy_reader_a(
            normalized,
            source_path=str(label_path),
            source_sha256=digest,
        )
    except (OSError, LabelValidationError, ValueError):
        return None
    note = (
        f"{label_path}: comparison loader normalized the known legacy authority-warning "
        "punctuation variant; strict label validation remains unchanged"
    )
    return replace(label, binding_notes=label.binding_notes + (note,)), note


def _load_labels(
    path: Path,
    *,
    require_grounded: bool,
) -> tuple[list[ReaderLabel], list[Path], list[str]]:
    labels: list[ReaderLabel] = []
    compatibility_warnings: list[str] = []
    paths, ignored_files = _label_paths(path)
    seen_ids: dict[str, Path] = {}
    loader = load_grounded_reader_label if require_grounded else load_reader_label
    for label_path in paths:
        try:
            label = loader(label_path)
        except (OSError, LabelValidationError, ValueError) as error:
            compatible = (
                None
                if require_grounded or not isinstance(error, LabelValidationError)
                else _legacy_warning_compatibility(label_path, error=error)
            )
            if compatible is None:
                raise ComparisonError(
                    f"{label_path}: cannot load comparison label: {error}"
                ) from error
            label, note = compatible
            compatibility_warnings.append(note)
        previous = seen_ids.get(label.record_id)
        if previous is not None:
            raise ComparisonError(
                f"{path}: duplicate record_id {label.record_id!r} in {previous} and {label_path}"
            )
        seen_ids[label.record_id] = label_path
        labels.append(label)
    return labels, paths, compatibility_warnings + ignored_files


def _input_report(
    path: Path,
    labels: list[ReaderLabel],
    paths: list[Path],
    compatibility_warnings: list[str],
) -> dict[str, Any]:
    quality = paired_quality_metrics(labels)
    return {
        "path": str(path),
        "label_count": len(labels),
        "record_ids": sorted(label.record_id for label in labels),
        "schema_kinds": dict(sorted(Counter(label.schema_kind for label in labels).items())),
        "reader_ids": sorted({label.reader_id for label in labels}),
        "reader_families": sorted({label.reader_family for label in labels}),
        "grounded_label_count": sum(not grounding_findings(label) for label in labels),
        "quality_metrics": quality,
        "files": [str(item) for item in paths],
        "input_discovery_notes": compatibility_warnings,
    }


def _evidence_snapshot(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "value": _json_value(evidence.get("value")),
        "original_script": _json_value(evidence.get("original_script")),
        "confidence": _json_value(evidence.get("confidence")),
        "observation_state": _json_value(evidence.get("observation_state")),
    }


def _compare_field(
    left: Mapping[str, Any] | None,
    right: Mapping[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    if left is None:
        return "FIELD_MISSING_LEFT", {"right": _evidence_snapshot(right or {})}
    if right is None:
        return "FIELD_MISSING_RIGHT", {"left": _evidence_snapshot(left)}

    left_state = left.get("observation_state")
    right_state = right.get("observation_state")
    left_value = _json_value(left.get("value"))
    right_value = _json_value(right.get("value"))
    state_agreement = left_state == right_state
    value_agreement = canonical_exact(left_value) == canonical_exact(right_value)
    if state_agreement and value_agreement:
        kind = "AGREE"
    elif not state_agreement:
        kind = "STATE_DISAGREEMENT"
    else:
        kind = "VALUE_DISAGREEMENT"
    return kind, {
        "left": _evidence_snapshot(left),
        "right": _evidence_snapshot(right),
        "state_agreement": state_agreement,
        "value_agreement": value_agreement,
        "confidence_agreement": left.get("confidence") == right.get("confidence"),
        "original_script_agreement": canonical_exact(
            _json_value(left.get("original_script"))
        )
        == canonical_exact(_json_value(right.get("original_script"))),
    }


def compare_reader_labels(
    left_path: Path,
    right_path: Path,
    *,
    max_disagreements: int | None = 100,
    require_grounded: bool = False,
) -> dict[str, Any]:
    """Compare two local label collections without inference or network access.

    The default accepts legacy labels so the repository's historical fixtures can be
    compared immediately.  Their unverified provenance remains visible in the report;
    ``require_grounded=True`` is the fail-closed mode for publication-grade inputs.
    """
    if max_disagreements is not None and max_disagreements < 0:
        raise ComparisonError("max_disagreements must be zero or greater")
    left_labels, left_files, left_warnings = _load_labels(
        left_path, require_grounded=require_grounded
    )
    right_labels, right_files, right_warnings = _load_labels(
        right_path, require_grounded=require_grounded
    )
    left_by_id = {label.record_id: label for label in left_labels}
    right_by_id = {label.record_id: label for label in right_labels}
    common_ids = sorted(set(left_by_id) & set(right_by_id))

    if not common_ids:
        raise ComparisonError(
            "comparison inputs have no common record_id; compare two label sets for the same acts"
        )

    field_counts: Counter[str] = Counter()
    disagreements: list[dict[str, Any]] = []
    disagreement_total = 0
    records_agree = 0
    record_summaries: list[dict[str, Any]] = []

    for record_id in common_ids:
        left = left_by_id[record_id]
        right = right_by_id[record_id]
        field_paths = sorted(set(left.observations) | set(right.observations))
        record_disagreement_count = 0
        for field_path in field_paths:
            kind, detail = _compare_field(
                left.observations.get(field_path), right.observations.get(field_path)
            )
            field_counts[kind] += 1
            if kind == "AGREE":
                continue
            record_disagreement_count += 1
            disagreement_total += 1
            if max_disagreements is None or len(disagreements) < max_disagreements:
                disagreements.append(
                    {
                        "record_id": record_id,
                        "field_path": field_path,
                        "kind": kind,
                        **detail,
                    }
                )
        if record_disagreement_count == 0:
            records_agree += 1
        record_summaries.append(
            {
                "record_id": record_id,
                "field_count": len(field_paths),
                "disagreement_count": record_disagreement_count,
                "status": "AGREE" if record_disagreement_count == 0 else "DISAGREE",
            }
        )

    left_quality = paired_quality_metrics(left_labels)
    right_quality = paired_quality_metrics(right_labels)
    grounding_incidents: list[dict[str, Any]] = []
    for record_id in common_ids:
        findings = validate_cross_reader_grounding(left_by_id[record_id], right_by_id[record_id])
        grounding_incidents.extend(_finding_report(item) for item in findings)

    total_fields = sum(field_counts.values())
    grounded_input = (
        all(label.schema_kind == "canonical" for label in left_labels + right_labels)
        and left_quality["groundedness"]["violation_count"] == 0
        and right_quality["groundedness"]["violation_count"] == 0
    )
    return {
        "comparison": "reader-to-reader-labels",
        "status": "PASS",
        "safety_status": (
            "READY_FOR_GROUNDED_COMPARISON"
            if grounded_input
            else "LIMITED_UNGROUNDED_INPUT"
        ),
        "authority_warning": "agreement is not proof of truth; verify against the source scan",
        "network_used": False,
        "require_grounded": require_grounded,
        "inputs": {
            "left": _input_report(left_path, left_labels, left_files, left_warnings),
            "right": _input_report(right_path, right_labels, right_files, right_warnings),
        },
        "records": {
            "left": len(left_labels),
            "right": len(right_labels),
            "common": len(common_ids),
            "left_only": sorted(set(left_by_id) - set(right_by_id)),
            "right_only": sorted(set(right_by_id) - set(left_by_id)),
            "agreement_count": records_agree,
            "agreement_rate": records_agree / len(common_ids),
            "details": record_summaries,
        },
        "fields": {
            "total": total_fields,
            "agreement_count": field_counts["AGREE"],
            "agreement_rate": field_counts["AGREE"] / total_fields if total_fields else None,
            "counts": dict(sorted(field_counts.items())),
        },
        "grounding_incidents": grounding_incidents,
        "disagreements": {
            "total": disagreement_total,
            "returned": len(disagreements),
            "truncated": disagreement_total > len(disagreements),
            "items": disagreements,
        },
    }
