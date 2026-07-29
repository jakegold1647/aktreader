"""Deterministic two-reader batch-brief generation."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SLUG = re.compile(r"[^a-z0-9]+")
AUTHORITY_WARNING = "extraction is not authority â€” verify against the scan"


class BriefGenerationError(ValueError):
    """Raised when a wave specification cannot produce blind, attributable briefs."""


def _slug(value: str) -> str:
    return _SLUG.sub("-", value.lower()).strip("-")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _blind_group(spec: dict[str, Any]) -> str:
    identity = {
        "register_unit": spec["register_unit"],
        "act_range": spec["act_range"],
        "prompt": spec["prompt"],
        "artifacts": [
            {
                "act_start": artifact["act_start"],
                "act_end": artifact["act_end"],
                "sha256": artifact["sha256"],
            }
            for artifact in spec["artifacts"]
        ],
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    unit = _slug(str(spec["register_unit"]["unit_id"]))
    return f"blind-{unit}-{spec['act_range']['start']}-{spec['act_range']['end']}-{digest}"


def _validate_reader(reader: Any, role: str) -> dict[str, Any]:
    if not isinstance(reader, dict):
        raise BriefGenerationError(f"{role} must be an object")
    required = {"reader_id", "reader_family", "reader_version", "mode"}
    if set(reader) != required:
        raise BriefGenerationError(f"{role} keys must be exactly {sorted(required)}")
    if reader["mode"] not in {"subscription_session", "local"}:
        raise BriefGenerationError(f"{role}.mode is invalid")
    if not all(isinstance(reader[key], str) and reader[key] for key in required):
        raise BriefGenerationError(f"{role} fields must be non-empty strings")
    return reader


def build_reader_briefs(
    spec: dict[str, Any],
    *,
    verify_artifacts: bool = True,
) -> dict[str, Any]:
    """Build paired Reader A/B briefs with one shared deterministic blind-group ID."""
    required = {
        "schema_version",
        "created_at",
        "register_unit",
        "act_range",
        "artifacts",
        "prompt",
        "readers",
    }
    if set(spec) != required or spec.get("schema_version") != "1.0.0":
        raise BriefGenerationError(f"wave specification keys must be exactly {sorted(required)}")
    unit = spec["register_unit"]
    unit_required = {
        "unit_id",
        "fond",
        "town",
        "year",
        "act_type",
        "language",
        "clerk_year_id",
    }
    if not isinstance(unit, dict) or set(unit) != unit_required:
        raise BriefGenerationError(f"register_unit keys must be exactly {sorted(unit_required)}")
    act_range = spec["act_range"]
    if not isinstance(act_range, dict) or set(act_range) != {"start", "end"}:
        raise BriefGenerationError("act_range requires exactly start and end")
    start, end = act_range["start"], act_range["end"]
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 1
        or end < start
    ):
        raise BriefGenerationError("act_range must be positive increasing integers")

    prompt = spec["prompt"]
    if (
        not isinstance(prompt, dict)
        or set(prompt) != {"version", "sha256", "path"}
        or not _SHA256.fullmatch(str(prompt.get("sha256", "")))
        or prompt.get("path") != "prompts/reader_prompt.md"
        or prompt.get("version") != "1.4.0"
    ):
        raise BriefGenerationError("prompt pin is invalid")
    readers = spec["readers"]
    if not isinstance(readers, dict) or set(readers) != {"A", "B"}:
        raise BriefGenerationError("readers must contain exactly A and B")
    reader_a = _validate_reader(readers["A"], "readers.A")
    reader_b = _validate_reader(readers["B"], "readers.B")
    if reader_a["reader_id"] == reader_b["reader_id"]:
        raise BriefGenerationError("blind readers must have distinct reader IDs")

    artifacts = spec["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise BriefGenerationError("artifacts must be a non-empty list")
    by_act: dict[int, dict[str, Any]] = {}
    artifact_keys = {
        "act_start",
        "act_end",
        "path",
        "sha256",
        "width_px",
        "height_px",
        "page_index",
    }
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != artifact_keys:
            raise BriefGenerationError(f"artifact keys must be exactly {sorted(artifact_keys)}")
        if not _SHA256.fullmatch(str(artifact["sha256"])):
            raise BriefGenerationError("artifact SHA-256 is invalid")
        if verify_artifacts:
            path = Path(artifact["path"])
            if not path.is_file():
                raise BriefGenerationError(f"artifact is not a file: {path}")
            if _sha256(path) != artifact["sha256"]:
                raise BriefGenerationError(f"artifact SHA-256 mismatch: {path}")
        for act_no in range(artifact["act_start"], artifact["act_end"] + 1):
            if act_no in by_act:
                raise BriefGenerationError(f"act {act_no} is covered by multiple artifacts")
            by_act[act_no] = artifact
    missing = [act_no for act_no in range(start, end + 1) if act_no not in by_act]
    outside = [act_no for act_no in by_act if act_no < start or act_no > end]
    if missing or outside:
        raise BriefGenerationError(
            f"artifact coverage must exactly match act range; missing={missing}, outside={outside}"
        )

    blind_group_id = _blind_group(spec)
    output: dict[str, Any] = {
        "schema_version": "1.0.0",
        "blind_group_id": blind_group_id,
        "register_unit": unit,
        "act_range": act_range,
        "independence": {
            "distinct_reader_ids": True,
            "distinct_model_families": (reader_a["reader_family"] != reader_b["reader_family"]),
            "correlated_blind_spots_possible": True,
        },
        "reader_a": [],
        "reader_b": [],
    }
    for act_no in range(start, end + 1):
        artifact = by_act[act_no]
        record_id = f"{_slug(unit['town'])}-{unit['year']}-{unit['act_type']}-{act_no}"
        artifact_payload = {
            "path": artifact["path"],
            "sha256": artifact["sha256"],
            "width_px": artifact["width_px"],
            "height_px": artifact["height_px"],
            "page_index": artifact["page_index"],
            "act_region": {
                "x": 0,
                "y": 0,
                "width": artifact["width_px"],
                "height": artifact["height_px"],
                "coordinate_space": "source_pixels",
            },
        }
        for role, reader, key in (
            ("a", reader_a, "reader_a"),
            ("b", reader_b, "reader_b"),
        ):
            output[key].append(
                {
                    "$schema": "schemas/reader-label-1.0.0-v1.4.schema.json",
                    "schema_version": "1.0.0",
                    "label_id": f"{record_id}.reader-{role}-{_slug(reader['reader_id'])}",
                    "record_id": record_id,
                    "created_at": spec["created_at"],
                    "reader": {
                        **reader,
                        "blind_group_id": blind_group_id,
                        "other_reader_output_seen": False,
                    },
                    "prompt": prompt,
                    "clerk_year": {
                        "id": unit["clerk_year_id"],
                        "basis": "REGISTER_YEAR_PROXY",
                        "clerk_id": None,
                    },
                    "artifact": artifact_payload,
                    "target": {
                        "town": unit["town"],
                        "fond": unit["fond"],
                        "year": unit["year"],
                        "act_type": unit["act_type"],
                        "act_no": act_no,
                        "language": unit["language"],
                    },
                    "compliance": {
                        "restricted_sources_used": False,
                        "privacy_decision": "ALLOW",
                        "privacy_basis": "coordinator-approved historical register wave",
                        "training_eligible": True,
                        "training_basis": (
                            "blind factory output; tier assigned only after resolution"
                        ),
                    },
                    "authority_warning": AUTHORITY_WARNING,
                }
            )
    return output
