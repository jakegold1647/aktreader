"""Blind, field-level consensus for immutable reader observations."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from aktreader.labels import (
    CANONICAL_READER_PROMPT_V1_SHA256,
    KNOWN_STALE_READER_A_PROMPT_SHA256,
    PROVENANCE_ERRATA_SOURCE,
    ReaderLabel,
    normalized_windows_path,
)

WHITESPACE_RE = re.compile(r"\s+")
FULL_UNCLEAR_RE = re.compile(r"^\[unclear:\s*(.+)\]$", re.IGNORECASE)


class ConsensusError(ValueError):
    """Raised when two labels cannot form a legitimate blind pair."""


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(child) for key, child in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(child) for child in value)
    return value


def _normalize_string(value: str) -> str:
    return WHITESPACE_RE.sub(" ", unicodedata.normalize("NFC", value)).strip()


def canonicalize(value: Any) -> Any:
    """Apply only Unicode NFC and whitespace normalization, preserving types."""
    if isinstance(value, str):
        return _normalize_string(value)
    if isinstance(value, Mapping):
        return {key: canonicalize(child) for key, child in value.items()}
    if isinstance(value, list | tuple):
        return [canonicalize(child) for child in value]
    return value


def strictly_equal(left: Any, right: Any) -> bool:
    """Compare values without fuzzy, onomastic, or numeric coercion."""
    if isinstance(left, str):
        if not isinstance(right, str):
            return False
        return _normalize_string(left) == _normalize_string(right)
    if isinstance(left, Mapping):
        if not isinstance(right, Mapping):
            return False
        if set(left) != set(right):
            return False
        return all(strictly_equal(left[key], right[key]) for key in left)
    if isinstance(left, list | tuple):
        if not isinstance(right, list | tuple):
            return False
        return len(left) == len(right) and all(
            strictly_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    if type(left) is not type(right):
        return False
    return left == right


def _identity_key(value: str) -> str:
    return _normalize_string(value).casefold()


def _metadata_equal(left: Any, right: Any) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        return _normalize_string(left) == _normalize_string(right)
    return type(left) is type(right) and left == right


def _known_prompt_erratum_status(label: ReaderLabel) -> str | None:
    """Return the status of the exact frozen Reader A v1.0.0 prompt-hash erratum."""
    if label.schema_kind != "legacy_reader_a" or label.prompt_binding_verified:
        return None
    for erratum in label.provenance_errata:
        status = erratum.get("claimed_hash_field_status")
        if status == "PRESENT_STALE":
            claimed_sha256 = KNOWN_STALE_READER_A_PROMPT_SHA256
        elif status == "ABSENT_IN_FILE":
            claimed_sha256 = None
        else:
            continue
        expected = {
            "code": "PROVENANCE_ERRATA",
            "kind": "STALE_INTERMEDIATE_PROMPT_HASH",
            "claimed_hash_field_status": status,
            "claimed_sha256": claimed_sha256,
            "coordinator_reported_sha256": KNOWN_STALE_READER_A_PROMPT_SHA256,
            "canonical_sha256": CANONICAL_READER_PROMPT_V1_SHA256,
            "prompt_version": "1.0.0",
            "status": "KNOWN_ERRATUM",
            "effect": "CONTENT_STANDS_PROMPT_BINDING_UNVERIFIED",
            "source": PROVENANCE_ERRATA_SOURCE,
        }
        if dict(erratum) != expected:
            continue
        if status == "PRESENT_STALE" and label.prompt_sha256 == claimed_sha256:
            return status
        if status == "ABSENT_IN_FILE" and label.prompt_sha256 is None:
            return status
    return None


@dataclass(frozen=True)
class PairAssessment:
    """Binding facts established before field comparison."""

    prompt_binding_verified: bool
    artifact_binding_verified: bool
    blind_group_verified: bool
    clerk_year_verified: bool
    fully_verified: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ConsensusResult:
    """Immutable consensus projection retaining both reader attributions."""

    record_id: str
    target: Mapping[str, Any]
    clerk_year_id: str | None
    fields: Mapping[str, Any]
    reader_label_ids: tuple[str, str]
    pair: PairAssessment

    def field(self, path: str) -> Mapping[str, Any]:
        return self.fields[path]


def assess_pair(left: ReaderLabel, right: ReaderLabel) -> PairAssessment:
    """Reject invalid pairings and report which provenance bindings are verified."""
    if left.record_id != right.record_id:
        raise ConsensusError(f"record mismatch: {left.record_id!r} != {right.record_id!r}")
    if _identity_key(left.reader_id) == _identity_key(right.reader_id):
        raise ConsensusError("blind pair requires distinct reader identities")
    if _identity_key(left.reader_family) == _identity_key(right.reader_family):
        raise ConsensusError("blind pair requires distinct reader families")
    if not left.blind_attested or not right.blind_attested:
        raise ConsensusError("both readers must attest that the other output was unseen")

    target_keys = ("town", "year", "act_type", "act_no", "language")
    for key in target_keys:
        if key not in left.target or key not in right.target:
            raise ConsensusError(f"target metadata missing {key!r}")
        if not _metadata_equal(left.target[key], right.target[key]):
            raise ConsensusError(
                f"target mismatch at {key}: {left.target[key]!r} != {right.target[key]!r}"
            )
    left_fond = left.target.get("fond")
    right_fond = right.target.get("fond")
    if (
        left_fond is not None
        and right_fond is not None
        and not _metadata_equal(left_fond, right_fond)
    ):
        raise ConsensusError(f"target mismatch at fond: {left_fond!r} != {right_fond!r}")

    notes: list[str] = []
    if left.artifact_sha256 is not None and right.artifact_sha256 is not None:
        if left.artifact_sha256 != right.artifact_sha256:
            raise ConsensusError("artifact SHA-256 mismatch")
        artifact_verified = left.artifact_binding_verified and right.artifact_binding_verified
        if not artifact_verified:
            notes.append(
                "Artifact hashes agree, but at least one observation marks its artifact "
                "binding UNVERIFIED."
            )
    else:
        if normalized_windows_path(left.artifact_path) != normalized_windows_path(
            right.artifact_path
        ):
            raise ConsensusError("artifact paths differ where a hash binding is unavailable")
        artifact_verified = False
        notes.append(
            "Artifact path agrees, but at least one label lacks a scan hash; artifact binding "
            "is UNVERIFIED."
        )

    if left.prompt_sha256 is not None and right.prompt_sha256 is not None:
        if left.prompt_sha256 != right.prompt_sha256:
            known_erratum = (
                _known_prompt_erratum_status(left) == "PRESENT_STALE"
                and right.prompt_sha256 == CANONICAL_READER_PROMPT_V1_SHA256
            ) or (
                _known_prompt_erratum_status(right) == "PRESENT_STALE"
                and left.prompt_sha256 == CANONICAL_READER_PROMPT_V1_SHA256
            )
            if not known_erratum:
                raise ConsensusError("prompt SHA-256 mismatch")
            prompt_verified = False
            notes.append(
                "PROVENANCE_ERRATA permits this one known Reader A v1.0.0 stale prompt-hash "
                "pair; the claimed and canonical hashes are both retained, prompt binding is "
                "UNVERIFIED, and all agreement is capped at PROBABLE."
            )
        else:
            prompt_verified = left.prompt_binding_verified and right.prompt_binding_verified
    else:
        prompt_verified = False
        absent_erratum_counterpart = None
        if _known_prompt_erratum_status(left) == "ABSENT_IN_FILE":
            absent_erratum_counterpart = right.prompt_sha256
        elif _known_prompt_erratum_status(right) == "ABSENT_IN_FILE":
            absent_erratum_counterpart = left.prompt_sha256
        if absent_erratum_counterpart is not None:
            if absent_erratum_counterpart != CANONICAL_READER_PROMPT_V1_SHA256:
                raise ConsensusError(
                    "prompt SHA-256 conflicts with PROVENANCE_ERRATA canonical hash"
                )
            notes.append(
                "PROVENANCE_ERRATA records the Reader A prompt hash field as ABSENT_IN_FILE "
                "and the coordinator-reported v1.0.0 hash as stale; no prompt_sha256 was "
                "synthesized, prompt binding is UNVERIFIED, and all agreement is capped at "
                "PROBABLE."
            )
        else:
            notes.append(
                "At least one label lacks a prompt hash; prompt binding is UNVERIFIED and all "
                "agreement is capped at PROBABLE."
            )

    if left.blind_group_id is not None and right.blind_group_id is not None:
        if left.blind_group_id != right.blind_group_id:
            raise ConsensusError("blind-group ID mismatch")
        blind_group_verified = True
    else:
        blind_group_verified = False
        notes.append(
            "At least one label lacks a blind-group ID; the blind attestations are retained "
            "but their pair binding is UNVERIFIED."
        )

    if left.clerk_year_id is not None and right.clerk_year_id is not None:
        if left.clerk_year_id != right.clerk_year_id:
            raise ConsensusError("clerk-year mismatch")
        clerk_year_verified = True
    else:
        clerk_year_verified = False
        notes.append(
            "At least one label lacks clerk-year metadata; the available identifier is retained "
            "without attributing it to the other observation."
        )

    fully_verified = (
        prompt_verified and artifact_verified and blind_group_verified and clerk_year_verified
    )
    return PairAssessment(
        prompt_binding_verified=prompt_verified,
        artifact_binding_verified=artifact_verified,
        blind_group_verified=blind_group_verified,
        clerk_year_verified=clerk_year_verified,
        fully_verified=fully_verified,
        notes=tuple(notes),
    )


def _reported_alternative(label: ReaderLabel, evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reader_id": label.reader_id,
        "reader_family": label.reader_family,
        "label_id": label.label_id,
        "reported": True,
        "observation_state": evidence["observation_state"],
        "value": canonicalize(evidence["value"]),
        "original_script": canonicalize(evidence.get("original_script")),
        "reported_alternatives": canonicalize(evidence.get("alternatives", ())),
        "source_span_ids": canonicalize(evidence.get("source_span_ids", ())),
    }


def _unreported_alternative(label: ReaderLabel) -> dict[str, Any]:
    return {
        "reader_id": label.reader_id,
        "reader_family": label.reader_family,
        "label_id": label.label_id,
        "reported": False,
        "observation_state": "UNREPORTED",
        "value": None,
        "original_script": None,
        "reported_alternatives": [],
        "source_span_ids": [],
    }


def _candidate_text(alternative: Mapping[str, Any]) -> str:
    if not alternative["reported"]:
        return "UNREPORTED"
    state = alternative["observation_state"]
    if state != "PRESENT":
        return str(state)
    value = alternative["value"]
    if isinstance(value, str):
        match = FULL_UNCLEAR_RE.fullmatch(value)
        return match.group(1) if match else value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _unclear_field(
    left: ReaderLabel,
    right: ReaderLabel,
    left_evidence: Mapping[str, Any] | None,
    right_evidence: Mapping[str, Any] | None,
    *,
    reason: str,
) -> dict[str, Any]:
    alternatives = [
        (
            _reported_alternative(left, left_evidence)
            if left_evidence is not None
            else _unreported_alternative(left)
        ),
        (
            _reported_alternative(right, right_evidence)
            if right_evidence is not None
            else _unreported_alternative(right)
        ),
    ]
    states = {
        alternative["observation_state"] for alternative in alternatives if alternative["reported"]
    }
    all_reported = all(alternative["reported"] for alternative in alternatives)
    output_state = "PRESENT" if all_reported and states == {"PRESENT"} else "UNRESOLVED"
    marker = f"[unclear: {_candidate_text(alternatives[0])}/{_candidate_text(alternatives[1])}]"
    return {
        "value": marker,
        "original_script": None,
        "confidence": "UNCLEAR",
        "observation_state": output_state,
        "alternatives": alternatives,
        "agreement": "DISAGREEMENT",
        "confidence_eligible": False,
        "confidence_cap": "UNCLEAR",
        "reason": reason,
    }


def _agreement_field(
    left: ReaderLabel,
    right: ReaderLabel,
    left_evidence: Mapping[str, Any],
    right_evidence: Mapping[str, Any],
    *,
    pair: PairAssessment,
) -> dict[str, Any]:
    left_original = left_evidence.get("original_script")
    right_original = right_evidence.get("original_script")
    original_binding_verified = (left_original is None and right_original is None) or (
        left_original is not None
        and right_original is not None
        and strictly_equal(left_original, right_original)
    )
    confidence_eligible = pair.fully_verified and original_binding_verified
    state = str(left_evidence["observation_state"])
    return {
        "value": canonicalize(left_evidence["value"]),
        "original_script": (canonicalize(left_original) if original_binding_verified else None),
        "confidence": "PROBABLE" if state == "PRESENT" else None,
        "observation_state": state,
        "alternatives": [],
        "agreement": "EXACT",
        "confidence_eligible": confidence_eligible,
        "confidence_cap": ("CONFIDENT_ELIGIBLE" if confidence_eligible else "PROBABLE"),
        "reason": (
            "Strict field agreement; eligible for later CONFIDENT grading after validators."
            if confidence_eligible
            else "Strict normalized agreement, but provenance or original-script binding is "
            "unverified; capped at PROBABLE."
        ),
        "reader_attribution": [
            _reported_alternative(left, left_evidence),
            _reported_alternative(right, right_evidence),
        ],
    }


def merge_labels(left: ReaderLabel, right: ReaderLabel) -> ConsensusResult:
    """Merge two blind observations without treating agreement as truth."""
    pair = assess_pair(left, right)
    merged: dict[str, Any] = {}
    all_paths = sorted(set(left.observations) | set(right.observations))
    for path in all_paths:
        left_evidence = left.observations.get(path)
        right_evidence = right.observations.get(path)
        if left_evidence is None or right_evidence is None:
            merged[path] = _unclear_field(
                left,
                right,
                left_evidence,
                right_evidence,
                reason="One blind reader did not report this field; missing output is not a blank.",
            )
            continue

        states_agree = strictly_equal(
            left_evidence["observation_state"], right_evidence["observation_state"]
        )
        values_agree = strictly_equal(left_evidence["value"], right_evidence["value"])
        alternatives_agree = strictly_equal(
            list(left_evidence.get("alternatives", ())),
            list(right_evidence.get("alternatives", ())),
        )
        left_original = left_evidence.get("original_script")
        right_original = right_evidence.get("original_script")
        originals_conflict = (
            left_original is not None
            and right_original is not None
            and not strictly_equal(left_original, right_original)
        )
        if states_agree and values_agree and alternatives_agree and not originals_conflict:
            merged[path] = _agreement_field(
                left,
                right,
                left_evidence,
                right_evidence,
                pair=pair,
            )
        else:
            disagreements = []
            if not states_agree:
                disagreements.append("observation state")
            if not values_agree:
                disagreements.append("value")
            if not alternatives_agree:
                disagreements.append("alternatives")
            if originals_conflict:
                disagreements.append("original script")
            merged[path] = _unclear_field(
                left,
                right,
                left_evidence,
                right_evidence,
                reason=f"Blind readers disagree on {', '.join(disagreements)}.",
            )

    target = right.target if right.schema_kind == "canonical" else left.target
    clerk_year_id = right.clerk_year_id or left.clerk_year_id
    return ConsensusResult(
        record_id=left.record_id,
        target=_freeze(target),
        clerk_year_id=clerk_year_id,
        fields=_freeze(merged),
        reader_label_ids=(left.label_id, right.label_id),
        pair=pair,
    )
