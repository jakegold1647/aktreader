"""Immutable loading for canonical and legacy blind-reader labels.

Canonical Reader B labels follow ``schemas/reader-label-1.0.0.schema.json``.  The first
Reader A labels pre-date that schema.  They are adapted without pretending that they contain
prompt hashes, scan hashes, source boxes, clerk identifiers, or a verified blind-group binding.
Those missing bindings remain explicit and cap downstream grades at ``PROBABLE``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import ntpath
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

AUTHORITY_WARNING = "extraction is not authority — verify against the scan"
CANONICAL_SCHEMA_VERSION = "1.0.0"
SUPPORTED_PROMPT_VERSIONS = frozenset({"1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0"})
KNOWN_STALE_READER_A_PROMPT_SHA256 = (
    "a2e6c50ca84a2e0141dfc785680a79429372e54e882120b6d908cefdad110fe5"
)
CANONICAL_READER_PROMPT_V1_SHA256 = (
    "88e56abd110b1f206a2d4cf0d699fbd449e667ea810ae1854a0c6a8d63269d82"
)
KNOWN_READER_A_IDENTITY = "claude-fable-5 (subscription session, Reader A)"
KNOWN_READER_A_DATE = "2026-07-28"
PROVENANCE_ERRATA_SOURCE = "labels/consensus/FOR_SOL_wave002_brief.md#1-prompt-hash-drift-resolved"
CANONICAL_TOP_LEVEL_KEYS = {
    "$schema",
    "schema_version",
    "label_id",
    "record_id",
    "created_at",
    "reader",
    "prompt",
    "clerk_year",
    "artifact",
    "target",
    "source_spans",
    "mentions",
    "transcription",
    "observations",
    "compliance",
    "authority_warning",
}
EVIDENCE_KEYS = {
    "value",
    "original_script",
    "confidence",
    "observation_state",
    "alternatives",
    "source_span_ids",
    "notes",
}
OBSERVATION_STATES = {
    "PRESENT",
    "ABSENT_ON_FORM",
    "BLANK",
    "STATED_UNKNOWN",
    "ILLEGIBLE",
}
FIELD_PATH_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_-]+)*$")
SOURCE_SPAN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]+$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
LABEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]+$")
RECORD_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]+$")
MENTION_ID_RE = re.compile(r"^[a-z0-9-]+#[a-z0-9-]+$")
UNCLEAR_RE = re.compile(r"\[unclear:\s*(.+?)\]", re.IGNORECASE)


LABEL_CONTRACT_GUIDANCE = (
    " [Rule: reader-label evidence contract; see docs/architecture.md and "
    "schemas/reader-label-1.0.0.schema.json.]"
)


class LabelValidationError(ValueError):
    """Raised when a reader label violates its declared contract."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"{detail}{LABEL_CONTRACT_GUIDANCE}")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(child) for key, child in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(child) for child in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw(child) for child in value]
    return value


@dataclass(frozen=True)
class ReaderLabel:
    """An immutable normalized reader observation."""

    label_id: str
    record_id: str
    schema_kind: str
    reader_id: str
    reader_family: str
    reader_version: str
    reader_mode: str
    blind_attested: bool
    blind_group_id: str | None
    prompt_sha256: str | None
    prompt_binding_verified: bool
    artifact_path: str
    artifact_sha256: str | None
    artifact_binding_verified: bool
    clerk_year_id: str | None
    target: Mapping[str, Any]
    source_spans: Mapping[str, Any]
    observations: Mapping[str, Any]
    raw: Mapping[str, Any]
    source_path: str | None
    source_sha256: str | None
    binding_notes: tuple[str, ...]
    provenance_errata: tuple[Mapping[str, Any], ...]

    @property
    def confidence_cap(self) -> str:
        """Return the highest grade this observation may support."""
        if not (
            self.prompt_binding_verified and self.artifact_binding_verified and self.blind_group_id
        ):
            return "PROBABLE"
        return "CONFIDENT_ELIGIBLE"

    def mutable_observations(self) -> dict[str, Any]:
        """Return a detached mutable copy for pure downstream transforms."""
        return _thaw(self.observations)


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], location: str) -> None:
    actual = set(value)
    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        bits = []
        if missing:
            bits.append(f"missing {sorted(missing)}")
        if extra:
            bits.append(f"unexpected {sorted(extra)}")
        raise LabelValidationError(f"{location}: {'; '.join(bits)}")


def _require_mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LabelValidationError(f"{location}: expected an object")
    return value


def _require_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise LabelValidationError(f"{location}: expected a non-empty string")
    return value


def _validate_sha256(value: Any, location: str) -> str:
    text = _require_string(value, location)
    if not SHA256_RE.fullmatch(text):
        raise LabelValidationError(f"{location}: expected a lowercase SHA-256 digest")
    return text


def _validate_bbox(
    value: Any, location: str, *, image_width: int, image_height: int
) -> Mapping[str, Any]:
    bbox = _require_mapping(value, location)
    keys = {"x", "y", "width", "height", "coordinate_space"}
    _require_exact_keys(bbox, keys, location)
    if bbox["coordinate_space"] != "source_pixels":
        raise LabelValidationError(f"{location}.coordinate_space: must be source_pixels")
    for key in ("x", "y", "width", "height"):
        if type(bbox[key]) is not int:
            raise LabelValidationError(f"{location}.{key}: expected an integer")
    if bbox["x"] < 0 or bbox["y"] < 0 or bbox["width"] < 1 or bbox["height"] < 1:
        raise LabelValidationError(f"{location}: invalid non-positive bounds")
    if bbox["x"] + bbox["width"] > image_width:
        raise LabelValidationError(f"{location}: extends past image width")
    if bbox["y"] + bbox["height"] > image_height:
        raise LabelValidationError(f"{location}: extends past image height")
    return bbox


def _validate_canonical_evidence(
    field: Any,
    location: str,
    *,
    source_span_ids: set[str],
) -> None:
    evidence = _require_mapping(field, location)
    _require_exact_keys(evidence, EVIDENCE_KEYS, location)
    state = evidence["observation_state"]
    confidence = evidence["confidence"]
    value = evidence["value"]
    if state not in OBSERVATION_STATES:
        raise LabelValidationError(f"{location}.observation_state: invalid state {state!r}")
    if confidence not in {"PROBABLE", "UNCLEAR", None}:
        raise LabelValidationError(
            f"{location}.confidence: a single reader cannot assert {confidence!r}"
        )
    if state == "PRESENT":
        if value is None:
            raise LabelValidationError(f"{location}: PRESENT requires a value")
        if confidence not in {"PROBABLE", "UNCLEAR"}:
            raise LabelValidationError(f"{location}: PRESENT requires a reader confidence")
    elif value is not None or confidence is not None:
        raise LabelValidationError(f"{location}: non-present states require null value/confidence")

    original_script = evidence["original_script"]
    if original_script is not None and not isinstance(original_script, str):
        raise LabelValidationError(f"{location}.original_script: expected string or null")

    alternatives = evidence["alternatives"]
    if not isinstance(alternatives, list):
        raise LabelValidationError(f"{location}.alternatives: expected an array")
    for index, alternative in enumerate(alternatives):
        alt = _require_mapping(alternative, f"{location}.alternatives[{index}]")
        _require_exact_keys(alt, {"value", "original_script"}, f"{location}.alternatives[{index}]")
        if alt["original_script"] is not None and not isinstance(alt["original_script"], str):
            raise LabelValidationError(
                f"{location}.alternatives[{index}].original_script: expected string or null"
            )
    if confidence == "UNCLEAR":
        if not isinstance(value, str) or not re.fullmatch(r"\[unclear: .+\]", value):
            raise LabelValidationError(f"{location}: UNCLEAR requires [unclear: X/Y]")
        if not alternatives:
            raise LabelValidationError(f"{location}: UNCLEAR requires alternatives")

    spans = evidence["source_span_ids"]
    if not isinstance(spans, list) or not spans:
        raise LabelValidationError(f"{location}.source_span_ids: expected a non-empty array")
    if len(spans) != len(set(spans)):
        raise LabelValidationError(f"{location}.source_span_ids: duplicate source span")
    for span_id in spans:
        if not isinstance(span_id, str) or span_id not in source_span_ids:
            raise LabelValidationError(
                f"{location}.source_span_ids: unknown source span {span_id!r}"
            )
    notes = evidence["notes"]
    if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
        raise LabelValidationError(f"{location}.notes: expected an array of strings")


def parse_canonical_reader_label(
    payload: Mapping[str, Any],
    *,
    source_path: str | None = None,
    source_sha256: str | None = None,
) -> ReaderLabel:
    """Strictly validate and freeze a canonical Reader label."""
    data = copy.deepcopy(dict(payload))
    _require_exact_keys(data, CANONICAL_TOP_LEVEL_KEYS, "label")
    if data["schema_version"] != CANONICAL_SCHEMA_VERSION:
        raise LabelValidationError("label.schema_version: unsupported version")
    schema_ref = data["$schema"]
    accepted_schema_refs = (
        "schemas/reader-label-1.0.0.schema.json",
        "schemas/reader-label-1.0.0-v1.4.schema.json",
        "https://aktreader.org/schema/reader-label-1.0.0.json",
    )
    if not isinstance(schema_ref, str) or not any(
        schema_ref.endswith(reference) for reference in accepted_schema_refs
    ):
        raise LabelValidationError("label.$schema: unexpected canonical schema reference")
    label_id = _require_string(data["label_id"], "label.label_id")
    if not LABEL_ID_RE.fullmatch(label_id):
        raise LabelValidationError("label.label_id: invalid identifier")
    record_id = _require_string(data["record_id"], "label.record_id")
    if not RECORD_ID_RE.fullmatch(record_id):
        raise LabelValidationError("label.record_id: invalid identifier")
    created_at = _require_string(data["created_at"], "label.created_at")
    try:
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise LabelValidationError("label.created_at: expected an ISO date-time") from error
    if data["authority_warning"] != AUTHORITY_WARNING:
        raise LabelValidationError("label.authority_warning: required warning changed")

    reader = _require_mapping(data["reader"], "label.reader")
    reader_keys = {
        "reader_id",
        "reader_family",
        "reader_version",
        "mode",
        "blind_group_id",
        "other_reader_output_seen",
    }
    _require_exact_keys(reader, reader_keys, "label.reader")
    reader_id = _require_string(reader["reader_id"], "label.reader.reader_id")
    reader_family = _require_string(reader["reader_family"], "label.reader.reader_family")
    reader_version = _require_string(reader["reader_version"], "label.reader.reader_version")
    if reader["mode"] not in {"subscription_session", "local"}:
        raise LabelValidationError("label.reader.mode: invalid mode")
    blind_group_id = _require_string(reader["blind_group_id"], "label.reader.blind_group_id")
    if reader["other_reader_output_seen"] is not False:
        raise LabelValidationError("label.reader: blind pass must not see the other output")

    prompt = _require_mapping(data["prompt"], "label.prompt")
    _require_exact_keys(prompt, {"version", "sha256", "path"}, "label.prompt")
    if (
        prompt["version"] not in SUPPORTED_PROMPT_VERSIONS
        or prompt["path"] != "prompts/reader_prompt.md"
    ):
        raise LabelValidationError("label.prompt: unsupported prompt binding")
    prompt_sha256 = _validate_sha256(prompt["sha256"], "label.prompt.sha256")

    clerk_year = _require_mapping(data["clerk_year"], "label.clerk_year")
    _require_exact_keys(clerk_year, {"id", "basis", "clerk_id"}, "label.clerk_year")
    clerk_year_id = _require_string(clerk_year["id"], "label.clerk_year.id")
    if clerk_year["basis"] not in {"IDENTIFIED_CLERK", "REGISTER_YEAR_PROXY"}:
        raise LabelValidationError("label.clerk_year.basis: invalid basis")
    if clerk_year["clerk_id"] is not None and not isinstance(clerk_year["clerk_id"], str):
        raise LabelValidationError("label.clerk_year.clerk_id: expected string or null")

    artifact = _require_mapping(data["artifact"], "label.artifact")
    artifact_keys = {
        "path",
        "sha256",
        "width_px",
        "height_px",
        "page_index",
        "act_region",
    }
    _require_exact_keys(artifact, artifact_keys, "label.artifact")
    artifact_path = _require_string(artifact["path"], "label.artifact.path")
    artifact_sha256 = _validate_sha256(artifact["sha256"], "label.artifact.sha256")
    width = artifact["width_px"]
    height = artifact["height_px"]
    if type(width) is not int or width < 1 or type(height) is not int or height < 1:
        raise LabelValidationError("label.artifact: image dimensions must be positive integers")
    if type(artifact["page_index"]) is not int or artifact["page_index"] < 0:
        raise LabelValidationError("label.artifact.page_index: expected a non-negative integer")
    _validate_bbox(
        artifact["act_region"],
        "label.artifact.act_region",
        image_width=width,
        image_height=height,
    )

    target = _require_mapping(data["target"], "label.target")
    target_keys = {"town", "fond", "year", "act_type", "act_no", "language"}
    _require_exact_keys(target, target_keys, "label.target")
    for key in ("town", "fond"):
        _require_string(target[key], f"label.target.{key}")
    if type(target["year"]) is not int or not 1800 <= target["year"] <= 2100:
        raise LabelValidationError("label.target.year: invalid year")
    if target["act_type"] not in {"birth", "marriage", "death", "annex", "index_page"}:
        raise LabelValidationError("label.target.act_type: invalid act type")
    if target["act_no"] is not None and (type(target["act_no"]) is not int or target["act_no"] < 1):
        raise LabelValidationError("label.target.act_no: invalid act number")
    if target["language"] not in {"ru", "pl", "mixed", "unknown"}:
        raise LabelValidationError("label.target.language: invalid language")

    source_spans = _require_mapping(data["source_spans"], "label.source_spans")
    if not source_spans:
        raise LabelValidationError("label.source_spans: at least one source span is required")
    for span_id, raw_span in source_spans.items():
        if not SOURCE_SPAN_ID_RE.fullmatch(str(span_id)):
            raise LabelValidationError(f"label.source_spans: invalid span id {span_id!r}")
        span = _require_mapping(raw_span, f"label.source_spans.{span_id}")
        _require_exact_keys(span, {"bbox", "description"}, f"label.source_spans.{span_id}")
        _validate_bbox(
            span["bbox"],
            f"label.source_spans.{span_id}.bbox",
            image_width=width,
            image_height=height,
        )
        _require_string(span["description"], f"label.source_spans.{span_id}.description")

    mentions = data["mentions"]
    if not isinstance(mentions, list):
        raise LabelValidationError("label.mentions: expected an array")
    mention_ids: set[str] = set()
    for index, raw_mention in enumerate(mentions):
        mention = _require_mapping(raw_mention, f"label.mentions[{index}]")
        _require_exact_keys(mention, {"mention_id", "role"}, f"label.mentions[{index}]")
        mention_id = _require_string(mention["mention_id"], f"label.mentions[{index}].mention_id")
        if (
            not MENTION_ID_RE.fullmatch(mention_id)
            or not mention_id.startswith(f"{record_id}#")
            or mention_id in mention_ids
        ):
            raise LabelValidationError(f"label.mentions[{index}]: invalid or duplicate mention id")
        mention_ids.add(mention_id)
        if mention["role"] not in {
            "principal",
            "father",
            "mother",
            "spouse",
            "spouse_father",
            "spouse_mother",
            "declarant",
            "witness",
            "officiant",
            "survivor",
        }:
            raise LabelValidationError(f"label.mentions[{index}].role: invalid role")

    transcription = _require_mapping(data["transcription"], "label.transcription")
    _require_exact_keys(transcription, {"original_script", "translation"}, "label.transcription")
    _require_string(transcription["original_script"], "label.transcription.original_script")
    _require_string(transcription["translation"], "label.transcription.translation")

    observations = _require_mapping(data["observations"], "label.observations")
    if not observations:
        raise LabelValidationError("label.observations: at least one observation is required")
    span_ids = set(source_spans)
    for field_path, field in observations.items():
        if not FIELD_PATH_RE.fullmatch(str(field_path)):
            raise LabelValidationError(f"label.observations: invalid path {field_path!r}")
        _validate_canonical_evidence(
            field,
            f"label.observations.{field_path}",
            source_span_ids=span_ids,
        )

    compliance = _require_mapping(data["compliance"], "label.compliance")
    compliance_keys = {
        "restricted_sources_used",
        "privacy_decision",
        "privacy_basis",
        "training_eligible",
        "training_basis",
    }
    _require_exact_keys(compliance, compliance_keys, "label.compliance")
    if compliance["restricted_sources_used"] is not False:
        raise LabelValidationError("label.compliance: restricted sources must be false")
    if compliance["privacy_decision"] not in {"ALLOW", "REFUSE"}:
        raise LabelValidationError("label.compliance.privacy_decision: invalid decision")
    _require_string(compliance["privacy_basis"], "label.compliance.privacy_basis")
    if type(compliance["training_eligible"]) is not bool:
        raise LabelValidationError("label.compliance.training_eligible: expected boolean")
    _require_string(compliance["training_basis"], "label.compliance.training_basis")

    return ReaderLabel(
        label_id=label_id,
        record_id=record_id,
        schema_kind="canonical",
        reader_id=reader_id,
        reader_family=reader_family,
        reader_version=reader_version,
        reader_mode=str(reader["mode"]),
        blind_attested=True,
        blind_group_id=blind_group_id,
        prompt_sha256=prompt_sha256,
        prompt_binding_verified=True,
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
        artifact_binding_verified=True,
        clerk_year_id=clerk_year_id,
        target=_freeze(target),
        source_spans=_freeze(source_spans),
        observations=_freeze(observations),
        raw=_freeze(data),
        source_path=source_path,
        source_sha256=source_sha256,
        binding_notes=(),
        provenance_errata=(),
    )


def _legacy_reader_family(identity: str) -> str:
    folded = identity.casefold()
    if "claude" in folded:
        return "claude"
    if "gpt" in folded or "openai" in folded or "sol" in folded:
        return "gpt"
    return "legacy-unverified-family"


def _legacy_town(value: str) -> str:
    """Strip only an explicit parenthesized script gloss from legacy town metadata."""
    return unicodedata.normalize("NFC", value.split(" (", 1)[0].strip())


def _legacy_record_id(register: Mapping[str, Any]) -> str:
    town = re.sub(r"[^a-z0-9]+", "-", _legacy_town(str(register["town"])).casefold()).strip("-")
    act_type = re.sub(r"[^a-z0-9]+", "-", str(register["act_type"]).casefold()).strip("-")
    return f"{town}-{register['year']}-{act_type}-{register['act_no']}"


def _legacy_alternatives(value: Any, original_script: Any) -> list[dict[str, Any]]:
    if not isinstance(value, str):
        return []
    match = UNCLEAR_RE.search(value)
    if not match:
        return []
    rendered = match.group(1)
    values = [item.strip() for item in rendered.split("/") if item.strip()]
    script_values: list[str | None] = [None] * len(values)
    if isinstance(original_script, str):
        script_match = UNCLEAR_RE.search(original_script)
        if script_match:
            scripts = [item.strip() for item in script_match.group(1).split("/")]
            if len(scripts) == len(values):
                script_values = scripts
    return [
        {"value": candidate, "original_script": script_values[index]}
        for index, candidate in enumerate(values)
    ]


def _legacy_evidence(
    value: Any,
    *,
    original_script: str | None = None,
    confidence: str | None = None,
    observation_state: str | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    adapted_notes = list(notes or [])
    if confidence == "CONFIDENT":
        confidence = "PROBABLE"
        adapted_notes.append(
            "Legacy single-reader CONFIDENT was downgraded to PROBABLE; dual-reader "
            "agreement was not yet established."
        )
    state = observation_state or ("PRESENT" if value is not None else "UNVERIFIED")
    if state not in OBSERVATION_STATES | {"UNVERIFIED"}:
        raise LabelValidationError(f"legacy evidence has invalid observation state {state!r}")
    if state != "PRESENT":
        if value is not None:
            adapted_notes.append(f"Legacy normalized state token preserved verbatim: {value!r}.")
        value = None
        confidence = None
    elif confidence not in {"PROBABLE", "UNCLEAR"}:
        confidence = "PROBABLE"
    return {
        "value": copy.deepcopy(value),
        "original_script": original_script,
        "confidence": confidence,
        "observation_state": state,
        "alternatives": _legacy_alternatives(value, original_script),
        "source_span_ids": [],
        "notes": adapted_notes,
        "provenance_status": "UNVERIFIED_LEGACY",
    }


def _flatten_legacy_fields(
    value: Any,
    *,
    path: str,
    output: dict[str, Any],
    inherited_confidence: str | None = None,
) -> None:
    if isinstance(value, list):
        for index, child in enumerate(value):
            _flatten_legacy_fields(
                child,
                path=f"{path}.{index}" if path else str(index),
                output=output,
                inherited_confidence=inherited_confidence,
            )
        return
    if isinstance(value, Mapping):
        leaf_keys = {
            "value",
            "original_script",
            "confidence",
            "observation_state",
            "note",
            "unclear",
        }
        if "value" in value or (path and set(value).issubset(leaf_keys)):
            notes = []
            if isinstance(value.get("note"), str):
                notes.append(value["note"])
            if isinstance(value.get("unclear"), str):
                notes.append(value["unclear"])
            output[path] = _legacy_evidence(
                value.get("value"),
                original_script=(
                    value.get("original_script")
                    if isinstance(value.get("original_script"), str)
                    else None
                ),
                confidence=(
                    value.get("confidence")
                    if isinstance(value.get("confidence"), str)
                    else inherited_confidence
                ),
                observation_state=(
                    value.get("observation_state")
                    if isinstance(value.get("observation_state"), str)
                    else None
                ),
                notes=notes,
            )
            return
        child_confidence = (
            value.get("confidence")
            if isinstance(value.get("confidence"), str)
            else inherited_confidence
        )
        shared_original = (
            value.get("original_script") if isinstance(value.get("original_script"), str) else None
        )
        for key, child in value.items():
            if key in {"confidence", "note", "original_script", "unclear"}:
                continue
            child_path = f"{path}.{key}" if path else str(key)
            if isinstance(child, (Mapping, list)):
                _flatten_legacy_fields(
                    child,
                    path=child_path,
                    output=output,
                    inherited_confidence=child_confidence,
                )
            else:
                output[child_path] = _legacy_evidence(
                    child,
                    original_script=shared_original if key == "name" else None,
                    confidence=child_confidence,
                    notes=[value["note"]] if isinstance(value.get("note"), str) else None,
                )
        return
    output[path] = _legacy_evidence(value, confidence=inherited_confidence)


def parse_legacy_reader_a(
    payload: Mapping[str, Any],
    *,
    source_path: str | None = None,
    source_sha256: str | None = None,
) -> ReaderLabel:
    """Adapt the pre-schema Reader A format without fabricating missing bindings."""
    data = copy.deepcopy(dict(payload))
    required = {
        "reader",
        "artifact",
        "register",
        "fields",
        "translation",
        "authority_warning",
    }
    missing = required - set(data)
    if missing:
        raise LabelValidationError(f"legacy label: missing {sorted(missing)}")
    if data["authority_warning"] != AUTHORITY_WARNING:
        raise LabelValidationError("legacy label.authority_warning: required warning changed")

    reader = _require_mapping(data["reader"], "legacy.reader")
    identity = _require_string(reader.get("identity"), "legacy.reader.identity")
    if reader.get("blind") is not True:
        raise LabelValidationError("legacy.reader.blind: blind attestation is required")
    reader_date = _require_string(reader.get("date"), "legacy.reader.date")
    recorded_prompt_sha256 = reader.get("prompt_sha256")
    if isinstance(recorded_prompt_sha256, str) and SHA256_RE.fullmatch(
        recorded_prompt_sha256.casefold()
    ):
        recorded_prompt_sha256 = recorded_prompt_sha256.casefold()
    else:
        recorded_prompt_sha256 = None
    artifact = _require_mapping(data["artifact"], "legacy.artifact")
    artifact_path = _require_string(artifact.get("path"), "legacy.artifact.path")
    _require_string(artifact.get("position"), "legacy.artifact.position")
    register = _require_mapping(data["register"], "legacy.register")
    for key in ("town", "year", "act_type", "act_no", "language"):
        if key not in register:
            raise LabelValidationError(f"legacy.register: missing {key!r}")
    if type(register["year"]) is not int or type(register["act_no"]) is not int:
        raise LabelValidationError("legacy.register: year and act_no must be integers")
    record_id = _legacy_record_id(register)

    observations: dict[str, Any] = {}
    _flatten_legacy_fields(data["fields"], path="", output=observations)
    metadata_fields = {
        "act_type": register["act_type"],
        "act_no": register["act_no"],
        "year": register["year"],
        "town": _legacy_town(str(register["town"])),
    }
    for path, value in metadata_fields.items():
        if path not in observations:
            observations[path] = _legacy_evidence(
                value,
                notes=["Adapted from explicit legacy register metadata, not inferred."],
            )

    target = {
        "town": _legacy_town(str(register["town"])),
        "fond": None,
        "year": register["year"],
        "act_type": register["act_type"],
        "act_no": register["act_no"],
        "language": register["language"],
    }
    label_id = f"{record_id}.legacy-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:12]}"
    provenance_errata: list[dict[str, Any]] = []
    known_batch_member = (
        identity == KNOWN_READER_A_IDENTITY
        and reader_date == KNOWN_READER_A_DATE
        and target["town"] == "Serock"
        and target["year"] == 1890
        and target["act_type"] == "death"
        and target["act_no"] in range(1, 7)
        and target["language"] == "ru"
    )
    hash_field_status: str | None = None
    claimed_sha256: str | None = None
    if (
        known_batch_member
        and target["act_no"] in {1, 2}
        and "prompt_sha256" not in reader
        and "prompt_version" not in reader
    ):
        hash_field_status = "ABSENT_IN_FILE"
    elif (
        known_batch_member
        and target["act_no"] in {3, 4, 5, 6}
        and recorded_prompt_sha256 == KNOWN_STALE_READER_A_PROMPT_SHA256
        and reader.get("prompt_version") == "1.0.0"
    ):
        hash_field_status = "PRESENT_STALE"
        claimed_sha256 = recorded_prompt_sha256

    if hash_field_status is not None:
        provenance_errata.append(
            {
                "code": "PROVENANCE_ERRATA",
                "kind": "STALE_INTERMEDIATE_PROMPT_HASH",
                "claimed_hash_field_status": hash_field_status,
                "claimed_sha256": claimed_sha256,
                "coordinator_reported_sha256": KNOWN_STALE_READER_A_PROMPT_SHA256,
                "canonical_sha256": CANONICAL_READER_PROMPT_V1_SHA256,
                "prompt_version": "1.0.0",
                "status": "KNOWN_ERRATUM",
                "effect": "CONTENT_STANDS_PROMPT_BINDING_UNVERIFIED",
                "source": PROVENANCE_ERRATA_SOURCE,
            }
        )
        if hash_field_status == "ABSENT_IN_FILE":
            prompt_note = (
                "PROVENANCE_ERRATA: prompt hash/version fields are ABSENT_IN_FILE; the "
                "coordinator reports the known stale intermediate v1.0.0 hash, the canonical "
                "hash is recorded separately, no prompt_sha256 was synthesized, and prompt "
                "binding remains UNVERIFIED."
            )
        else:
            prompt_note = (
                "PROVENANCE_ERRATA: the legacy label's claimed prompt hash is the known stale "
                "intermediate v1.0.0 hash; the claim is preserved, the coordinator-reported "
                "and canonical hashes are recorded separately, and prompt binding remains "
                "UNVERIFIED."
            )
    elif recorded_prompt_sha256 is not None:
        prompt_note = (
            "Legacy label records a prompt hash, but lacks the canonical prompt path and binding "
            "contract; the hash is preserved with status UNVERIFIED."
        )
    else:
        prompt_note = "Legacy label has no prompt hash; prompt binding is UNVERIFIED."
    clerk_note = (
        "Legacy label records a clerk-year proxy, but it is not mapped to a canonical "
        "clerk-year identifier; no binding was invented."
        if isinstance(register.get("clerk_year_proxy"), str)
        else "Legacy label has no clerk-year identifier; no identifier was invented."
    )
    notes = (
        prompt_note,
        "Legacy label has no artifact hash or source boxes; pixel binding is UNVERIFIED.",
        "Legacy label has no blind-group ID; pair binding is UNVERIFIED.",
        clerk_note,
    )
    normalized = {
        "legacy": data,
        "adapted_record_id": record_id,
        "adapted_reader_date": reader_date,
        "binding_notes": list(notes),
        "provenance_errata": provenance_errata,
    }
    return ReaderLabel(
        label_id=label_id,
        record_id=record_id,
        schema_kind="legacy_reader_a",
        reader_id=identity,
        reader_family=_legacy_reader_family(identity),
        reader_version=identity,
        reader_mode="subscription_session",
        blind_attested=True,
        blind_group_id=None,
        prompt_sha256=recorded_prompt_sha256,
        prompt_binding_verified=False,
        artifact_path=artifact_path,
        artifact_sha256=None,
        artifact_binding_verified=False,
        clerk_year_id=None,
        target=_freeze(target),
        source_spans=_freeze({}),
        observations=_freeze(observations),
        raw=_freeze(normalized),
        source_path=source_path,
        source_sha256=source_sha256,
        binding_notes=notes,
        provenance_errata=tuple(_freeze(item) for item in provenance_errata),
    )


def load_reader_label(path: Path | str) -> ReaderLabel:
    """Load a canonical label or explicitly adapt a legacy Reader A label."""
    label_path = Path(path)
    raw_bytes = label_path.read_bytes()
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LabelValidationError(f"{label_path}: invalid UTF-8 JSON: {error}") from error
    if not isinstance(payload, Mapping):
        raise LabelValidationError(f"{label_path}: label root must be an object")
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if payload.get("schema_version") == CANONICAL_SCHEMA_VERSION:
        return parse_canonical_reader_label(
            payload, source_path=str(label_path), source_sha256=digest
        )
    return parse_legacy_reader_a(payload, source_path=str(label_path), source_sha256=digest)


def normalized_windows_path(path: str) -> str:
    """Return a comparison-only Windows path without touching the filesystem."""
    return ntpath.normcase(ntpath.normpath(path))
