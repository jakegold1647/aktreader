"""Canonical serialization and append-only third-reader arbitration for consensus records."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from aktreader.consensus import ConsensusResult, strictly_equal
from aktreader.labels import AUTHORITY_WARNING, ReaderLabel
from aktreader.schema import validate_instance
from aktreader.validators.models import ValidationFinding

ACT_RECORD_VERSION = "2.0.0"
CONSENSUS_POLICY_VERSION = "1.0.0"
ARBITRATION_POLICY_VERSION = "1.0.0"
FULL_UNCLEAR_RE = re.compile(r"^\[unclear:\s*(.+)\]$", re.IGNORECASE)


class ConsensusRecordError(ValueError):
    """Raised when a canonical consensus record cannot be built safely."""


@dataclass(frozen=True)
class ThirdReaderVote:
    """A candidate-only vote from an independent third reader."""

    field_path: str
    reader_id: str
    reader_family: str
    reader_version: str
    session_id: str
    independence_basis: str
    occurred_at: str
    selected_candidate_id: str | None = None
    novel_candidate: Mapping[str, Any] | None = None
    independence_attested: bool = True
    candidate_only_context: bool = True
    reader_identities_seen: bool = False
    full_labels_seen: bool = False


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(child) for key, child in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(child) for child in value]
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def record_sha256(record: Mapping[str, Any]) -> str:
    """Hash a record's canonical JSON representation."""
    return hashlib.sha256(_canonical_bytes(record)).hexdigest()


def _stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256("\x00".join(str(part) for part in parts).encode("utf-8")).hexdigest()[
        :16
    ]
    return f"{prefix}-{digest}"


def _portable_path(path: str | None, workspace_root: Path | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if workspace_root is None:
        return candidate.as_posix()
    try:
        return candidate.resolve().relative_to(workspace_root.resolve()).as_posix()
    except ValueError:
        return str(candidate)


def _source_label(label: ReaderLabel, workspace_root: Path | None) -> dict[str, Any]:
    return {
        "label_id": label.label_id,
        "source_path": _portable_path(label.source_path, workspace_root),
        "source_sha256": label.source_sha256,
        "schema_kind": label.schema_kind,
        "reader": {
            "reader_id": label.reader_id,
            "reader_family": label.reader_family,
            "reader_version": label.reader_version,
            "mode": label.reader_mode,
        },
        "blind_attested": label.blind_attested,
        "blind_group_id": label.blind_group_id,
        "prompt_sha256": label.prompt_sha256,
        "prompt_binding_verified": label.prompt_binding_verified,
        "artifact_binding_verified": label.artifact_binding_verified,
        "clerk_year_id": label.clerk_year_id,
        "binding_notes": list(label.binding_notes),
        "provenance_errata": _jsonable(label.provenance_errata),
    }


def _artifact(result: ConsensusResult, labels: tuple[ReaderLabel, ReaderLabel]) -> dict[str, Any]:
    regions: list[dict[str, Any]] = []
    for label in labels:
        if label.schema_kind != "canonical":
            continue
        raw_artifact = label.raw.get("artifact")
        if not isinstance(raw_artifact, Mapping):
            continue
        regions.append(
            {
                "source_label_id": label.label_id,
                "width_px": raw_artifact["width_px"],
                "height_px": raw_artifact["height_px"],
                "page_index": raw_artifact["page_index"],
                "act_region": _jsonable(raw_artifact["act_region"]),
            }
        )
    sha256 = next(
        (label.artifact_sha256 for label in labels if label.artifact_sha256 is not None),
        None,
    )
    if result.pair.artifact_binding_verified:
        status = "VERIFIED"
    elif sha256 is not None:
        status = "SINGLE_READER_HASH"
    else:
        status = "PATH_ONLY_UNVERIFIED"
    path_label = next(
        (label for label in labels if label.schema_kind == "canonical"),
        labels[0],
    )
    return {
        "path": path_label.artifact_path,
        "sha256": sha256,
        "binding_status": status,
        "regions": regions,
    }


def _mentions(labels: tuple[ReaderLabel, ReaderLabel]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for label in labels:
        if label.schema_kind != "canonical":
            continue
        raw_mentions = label.raw.get("mentions", ())
        if not isinstance(raw_mentions, (tuple, list)):
            continue
        for raw_mention in raw_mentions:
            if not isinstance(raw_mention, Mapping):
                continue
            mention_id = str(raw_mention["mention_id"])
            role = str(raw_mention["role"])
            existing = grouped.get(mention_id)
            if existing is not None and existing["role"] != role:
                raise ConsensusRecordError(
                    f"mention {mention_id!r} has conflicting roles across labels"
                )
            if existing is None:
                existing = {
                    "mention_id": mention_id,
                    "role": role,
                    "source_label_ids": [],
                }
                grouped[mention_id] = existing
            existing["source_label_ids"].append(label.label_id)
    output = []
    for mention_id in sorted(grouped):
        mention = grouped[mention_id]
        source_ids = sorted(set(mention["source_label_ids"]))
        output.append(
            {
                "mention_id": mention_id,
                "role": mention["role"],
                "metadata_status": (
                    "AGREED" if len(source_ids) == len(labels) else "SINGLE_READER_METADATA"
                ),
                "source_label_ids": source_ids,
            }
        )
    return output


def _serialized_finding(finding: ValidationFinding) -> dict[str, Any]:
    core = {
        "code": finding.code,
        "message": finding.message,
        "record_ids": sorted(set(finding.record_ids)),
        "field_paths": list(finding.field_paths),
        "severity": finding.severity,
        "blocks_confident": finding.blocks_confident,
        "evidence": _jsonable(finding.evidence),
    }
    return {
        "finding_id": _stable_id("finding", _canonical_bytes(core).hex()),
        **core,
    }


def _candidate(
    record_id: str,
    field_path: str,
    index: int,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    label_id = source.get("label_id")
    candidate_id = _stable_id("cand", record_id, field_path, index, label_id)
    return {
        "candidate_id": candidate_id,
        "source_kind": "BLIND_READER_LABEL",
        "reader_label_id": label_id,
        "reader_id": str(source["reader_id"]),
        "reader_family": str(source["reader_family"]),
        "reported": bool(source["reported"]),
        "observation_state": str(source["observation_state"]),
        "value": _jsonable(source.get("value")),
        "original_script": _jsonable(source.get("original_script")),
        "reported_alternatives": _jsonable(source.get("reported_alternatives", ())),
        "source_span_ids": _jsonable(source.get("source_span_ids", ())),
    }


def _field_findings(field_path: str, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [finding for finding in findings if field_path in finding["field_paths"]]


def _fields(
    result: ConsensusResult,
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field_path, raw_field in result.fields.items():
        if raw_field["agreement"] == "EXACT":
            raw_candidates = raw_field["reader_attribution"]
            status = "EXACT_AGREEMENT"
        else:
            raw_candidates = raw_field["alternatives"]
            status = "DUAL_DISAGREEMENT"
        candidates = [
            _candidate(result.record_id, field_path, index, source)
            for index, source in enumerate(raw_candidates)
        ]
        relevant_findings = _field_findings(field_path, findings)
        blocking = any(finding["blocks_confident"] for finding in relevant_findings)
        eligible = bool(raw_field["confidence_eligible"]) and not blocking
        cap = str(raw_field["confidence_cap"])
        reason = str(raw_field["reason"])
        if blocking and cap == "CONFIDENT_ELIGIBLE":
            cap = "PROBABLE"
            reason += " A mechanical validator finding blocks CONFIDENT grading."
        output[field_path] = {
            "value": _jsonable(raw_field["value"]),
            "original_script": _jsonable(raw_field["original_script"]),
            "confidence": raw_field["confidence"],
            "observation_state": raw_field["observation_state"],
            "candidates": candidates,
            "resolution": {
                "status": status,
                "confidence_eligible": eligible,
                "confidence_cap": cap,
                "reason": reason,
                "arbitration_id": None,
            },
            "validator_finding_ids": [finding["finding_id"] for finding in relevant_findings],
        }
    return output


def _arbitration_spans(
    field_path: str,
    labels: tuple[ReaderLabel, ReaderLabel],
) -> tuple[list[dict[str, Any]], str]:
    spans: list[dict[str, Any]] = []
    labels_with_spans = 0
    seen: set[bytes] = set()
    for label in labels:
        evidence = label.observations.get(field_path)
        if not isinstance(evidence, Mapping) or label.artifact_sha256 is None:
            continue
        label_spans = []
        for span_id in evidence.get("source_span_ids", ()):
            span = label.source_spans.get(span_id)
            if not isinstance(span, Mapping):
                continue
            serialized = {
                "artifact_sha256": label.artifact_sha256,
                "bbox": _jsonable(span["bbox"]),
                "description": str(span["description"]),
            }
            key = _canonical_bytes(serialized)
            if key not in seen:
                seen.add(key)
                spans.append(serialized)
            label_spans.append(serialized)
        if label_spans:
            labels_with_spans += 1
    if labels_with_spans == len(labels):
        status = "VERIFIED"
    elif labels_with_spans:
        status = "PARTIAL"
    else:
        status = "UNVERIFIED"
    return spans, status


def _public_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate["candidate_id"],
        "observation_state": candidate["observation_state"],
        "value": _jsonable(candidate["value"]),
        "original_script": _jsonable(candidate["original_script"]),
        "reported_alternatives": _jsonable(candidate["reported_alternatives"]),
    }


def _arbitration_requests(
    record_id: str,
    fields: Mapping[str, Any],
    labels: tuple[ReaderLabel, ReaderLabel],
) -> list[dict[str, Any]]:
    requests = []
    for field_path, field in fields.items():
        if field["resolution"]["status"] != "DUAL_DISAGREEMENT":
            continue
        arbitration_id = _stable_id("arb", record_id, field_path)
        spans, span_status = _arbitration_spans(field_path, labels)
        public_candidates = [
            _public_candidate(candidate)
            for candidate in field["candidates"]
            if candidate["reported"]
        ]
        requests.append(
            {
                "arbitration_id": arbitration_id,
                "field_path": field_path,
                "status": "PENDING",
                "span_binding_status": span_status,
                "source_spans": spans,
                "candidates": public_candidates,
                "context_policy": {
                    "span_and_candidates_only": True,
                    "reader_identities_hidden": True,
                    "full_labels_hidden": True,
                },
            }
        )
    return requests


def _confidence_summary(
    fields: Mapping[str, Any],
    finding_count: int,
) -> dict[str, int]:
    values = list(fields.values())
    return {
        "field_count": len(values),
        "exact_agreement_count": sum(
            field["resolution"]["status"] == "EXACT_AGREEMENT" for field in values
        ),
        "dual_disagreement_count": sum(
            field["resolution"]["status"] == "DUAL_DISAGREEMENT" for field in values
        ),
        "confident_eligible_count": sum(
            field["resolution"]["confidence_eligible"] for field in values
        ),
        "probable_count": sum(field["confidence"] == "PROBABLE" for field in values),
        "unclear_count": sum(field["confidence"] == "UNCLEAR" for field in values),
        "unresolved_state_count": sum(
            field["observation_state"] == "UNRESOLVED" for field in values
        ),
        "validator_finding_count": finding_count,
    }


def _compliance(
    pair: ConsensusResult,
    labels: tuple[ReaderLabel, ReaderLabel],
) -> dict[str, Any]:
    canonical_compliance = []
    for label in labels:
        if label.schema_kind != "canonical":
            continue
        raw = label.raw.get("compliance")
        if isinstance(raw, Mapping):
            canonical_compliance.append(raw)
    if not canonical_compliance:
        raise ConsensusRecordError(
            "no canonical reader supplied compliance metadata; act record cannot be serialized"
        )
    privacy_decisions = {str(item["privacy_decision"]) for item in canonical_compliance}
    if len(privacy_decisions) != 1:
        raise ConsensusRecordError("reader privacy decisions disagree")
    all_attested = len(canonical_compliance) == len(labels)
    training_eligible = (
        pair.pair.fully_verified
        and all_attested
        and all(bool(item["training_eligible"]) for item in canonical_compliance)
    )
    return {
        "restricted_sources_used": False,
        "restricted_sources_status": (
            "ALL_READERS_ATTESTED" if all_attested else "SINGLE_READER_ATTESTED"
        ),
        "privacy_decision": next(iter(privacy_decisions)),
        "privacy_binding_status": (
            "ALL_READERS_ATTESTED" if all_attested else "SINGLE_READER_ATTESTED"
        ),
        "training_eligible": training_eligible,
        "training_basis": (
            "Both canonical blind labels are training-eligible and all pair bindings verify."
            if training_eligible
            else "Not training-eligible: provenance, privacy, or dual canonical-label "
            "attestation is incomplete."
        ),
    }


def build_consensus_record(
    result: ConsensusResult,
    left: ReaderLabel,
    right: ReaderLabel,
    *,
    findings: Iterable[ValidationFinding] = (),
    schema_ref: str = "../../schemas/act-record-2.0.0.schema.json",
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic canonical record without adjudicating disagreements."""
    labels = (left, right)
    if result.reader_label_ids != (left.label_id, right.label_id):
        raise ConsensusRecordError("consensus result does not derive from the supplied labels")
    if result.clerk_year_id is None:
        raise ConsensusRecordError("canonical act records require a clerk-year identifier")
    serialized_findings = [
        _serialized_finding(finding)
        for finding in findings
        if result.record_id in finding.record_ids
    ]
    serialized_findings.sort(key=lambda item: item["finding_id"])
    fields = _fields(result, serialized_findings)
    clerk_sources = [
        label.label_id for label in labels if label.clerk_year_id == result.clerk_year_id
    ]
    record = {
        "$schema": schema_ref,
        "schema_version": ACT_RECORD_VERSION,
        "record_id": result.record_id,
        "record_kind": "DUAL_READER_CONSENSUS",
        "revision": 1,
        "parent_record_sha256": None,
        "target": _jsonable(result.target),
        "clerk_year": {
            "id": result.clerk_year_id,
            "binding_status": (
                "VERIFIED" if result.pair.clerk_year_verified else "SINGLE_READER_METADATA"
            ),
            "source_label_ids": clerk_sources,
        },
        "artifact": _artifact(result, labels),
        "mentions": _mentions(labels),
        "fields": fields,
        "derivation": {
            "method": "blind-field-consensus",
            "policy_version": CONSENSUS_POLICY_VERSION,
            "source_labels": [_source_label(label, workspace_root) for label in labels],
            "pair_assessment": {
                "prompt_binding_verified": result.pair.prompt_binding_verified,
                "artifact_binding_verified": result.pair.artifact_binding_verified,
                "blind_group_verified": result.pair.blind_group_verified,
                "clerk_year_verified": result.pair.clerk_year_verified,
                "fully_verified": result.pair.fully_verified,
                "notes": list(result.pair.notes),
            },
            "confidence_summary": _confidence_summary(fields, len(serialized_findings)),
        },
        "validation": {
            "policy_version": "1.0.0",
            "findings": serialized_findings,
        },
        "arbitration": {
            "policy_version": ARBITRATION_POLICY_VERSION,
            "default_tie_break": "INDEPENDENT_THIRD_READER",
            "requests": _arbitration_requests(result.record_id, fields, labels),
            "events": [],
        },
        "compliance": _compliance(result, labels),
        "correction_events": [],
        "authority_warning": AUTHORITY_WARNING,
    }
    return record


def write_consensus_record(
    path: Path,
    record: Mapping[str, Any],
    *,
    schema_path: Path,
) -> None:
    """Validate and atomically write canonical JSON with stable LF line endings."""
    serializable = _jsonable(record)
    validate_instance(serializable, schema_path)
    rendered = json.dumps(serializable, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(rendered)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _candidate_text(candidate: Mapping[str, Any]) -> str:
    state = candidate["observation_state"]
    if state != "PRESENT":
        return str(state)
    value = candidate["value"]
    if isinstance(value, str):
        match = FULL_UNCLEAR_RE.fullmatch(value)
        return match.group(1) if match else value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_vote(record: Mapping[str, Any], vote: ThirdReaderVote) -> dict[str, Any]:
    if vote.independence_basis not in {"DIFFERENT_MODEL", "FRESH_SESSION"}:
        raise ConsensusRecordError("third reader must use a different model or fresh session")
    if not vote.independence_attested:
        raise ConsensusRecordError("third-reader independence attestation is required")
    if not vote.candidate_only_context or vote.reader_identities_seen or vote.full_labels_seen:
        raise ConsensusRecordError("arbiter may see only the disputed span and pooled candidates")
    if not all(
        (
            vote.field_path,
            vote.reader_id,
            vote.reader_family,
            vote.reader_version,
            vote.session_id,
            vote.occurred_at,
        )
    ):
        raise ConsensusRecordError("third-reader identity/session metadata is incomplete")
    try:
        datetime.fromisoformat(vote.occurred_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ConsensusRecordError("third-reader occurred_at is not an ISO date-time") from error
    source_reader_ids = {
        item["reader"]["reader_id"] for item in record["derivation"]["source_labels"]
    }
    if vote.reader_id in source_reader_ids:
        raise ConsensusRecordError("arbiter reader identity must differ from both blind passes")
    if (vote.selected_candidate_id is None) == (vote.novel_candidate is None):
        raise ConsensusRecordError(
            "vote must select exactly one pooled candidate or provide one novel candidate"
        )
    requests = [
        item for item in record["arbitration"]["requests"] if item["field_path"] == vote.field_path
    ]
    if len(requests) != 1:
        raise ConsensusRecordError("field has no unique pending arbitration request")
    request = requests[0]
    if request["status"] != "PENDING":
        raise ConsensusRecordError("arbitration request is no longer pending")
    return request


def apply_third_reader_vote(
    record: Mapping[str, Any],
    vote: ThirdReaderVote,
) -> dict[str, Any]:
    """Return a new revision; never promote a dual disagreement above PROBABLE."""
    request = _validate_vote(record, vote)
    updated = copy.deepcopy(_jsonable(record))
    request = next(
        item for item in updated["arbitration"]["requests"] if item["field_path"] == vote.field_path
    )
    field = updated["fields"][vote.field_path]
    if field["resolution"]["status"] != "DUAL_DISAGREEMENT":
        raise ConsensusRecordError("only an unresolved dual disagreement can be arbitrated")

    public_by_id = {item["candidate_id"]: item for item in request["candidates"]}
    arbitration_id = request["arbitration_id"]
    arbiter_candidate_id = _stable_id(
        "cand", updated["record_id"], vote.field_path, "arbiter", vote.session_id
    )
    if vote.selected_candidate_id is not None:
        selected = public_by_id.get(vote.selected_candidate_id)
        if selected is None:
            raise ConsensusRecordError("selected candidate is not in the pooled candidate set")
        arbiter_candidate = {
            **selected,
            "candidate_id": arbiter_candidate_id,
        }
        field["candidates"].append(
            {
                **arbiter_candidate,
                "source_kind": "ARBITER_VOTE",
                "reader_label_id": None,
                "reader_id": vote.reader_id,
                "reader_family": vote.reader_family,
                "reported": True,
                "source_span_ids": [],
            }
        )
        field["value"] = copy.deepcopy(selected["value"])
        field["original_script"] = selected["original_script"]
        field["observation_state"] = selected["observation_state"]
        field["confidence"] = "PROBABLE" if selected["observation_state"] == "PRESENT" else None
        field["resolution"] = {
            "status": "ARBITRATED_2_OF_3",
            "confidence_eligible": False,
            "confidence_cap": "PROBABLE",
            "reason": (
                "Independent third reader selected one pooled candidate; 2-of-3 agreement "
                "is consensus-PROBABLE, never CONFIDENT."
            ),
            "arbitration_id": arbitration_id,
        }
        request["status"] = "RESOLVED_2_OF_3"
        event_vote = {
            "selected_candidate_id": vote.selected_candidate_id,
            "novel_candidate": None,
        }
        outcome = "RESOLVED_2_OF_3"
        result_confidence = "PROBABLE"
    else:
        assert vote.novel_candidate is not None
        required = {"observation_state", "value", "original_script"}
        if not required.issubset(vote.novel_candidate):
            raise ConsensusRecordError(
                f"novel candidate is missing {sorted(required - set(vote.novel_candidate))}"
            )
        novel_public = {
            "candidate_id": arbiter_candidate_id,
            "observation_state": vote.novel_candidate["observation_state"],
            "value": _jsonable(vote.novel_candidate["value"]),
            "original_script": _jsonable(vote.novel_candidate["original_script"]),
            "reported_alternatives": _jsonable(
                vote.novel_candidate.get("reported_alternatives", ())
            ),
        }
        for existing in request["candidates"]:
            if (
                strictly_equal(novel_public["observation_state"], existing["observation_state"])
                and strictly_equal(novel_public["value"], existing["value"])
                and strictly_equal(novel_public["original_script"], existing["original_script"])
            ):
                raise ConsensusRecordError(
                    "novel candidate matches a pooled candidate; select its candidate_id"
                )
        request["candidates"].append(copy.deepcopy(novel_public))
        field["candidates"].append(
            {
                **novel_public,
                "source_kind": "ARBITER_VOTE",
                "reader_label_id": None,
                "reader_id": vote.reader_id,
                "reader_family": vote.reader_family,
                "reported": True,
                "source_span_ids": [],
            }
        )
        displayed = [_candidate_text(candidate) for candidate in request["candidates"]]
        field["value"] = f"[unclear: {'/'.join(displayed)}]"
        field["original_script"] = None
        states = {candidate["observation_state"] for candidate in request["candidates"]}
        field["observation_state"] = "PRESENT" if states == {"PRESENT"} else "UNRESOLVED"
        field["confidence"] = "UNCLEAR"
        field["resolution"] = {
            "status": "ARBITRATION_ALL_DIVERGE",
            "confidence_eligible": False,
            "confidence_cap": "UNCLEAR",
            "reason": (
                "Independent third reader supplied a third distinct reading; all candidates "
                "remain unresolved."
            ),
            "arbitration_id": arbitration_id,
        }
        request["status"] = "ALL_DIVERGE"
        event_vote = {
            "selected_candidate_id": None,
            "novel_candidate": copy.deepcopy(novel_public),
        }
        outcome = "ALL_DIVERGE"
        result_confidence = "UNCLEAR"

    updated["arbitration"]["events"].append(
        {
            "arbitration_id": arbitration_id,
            "field_path": vote.field_path,
            "occurred_at": vote.occurred_at,
            "arbiter": {
                "reader_id": vote.reader_id,
                "reader_family": vote.reader_family,
                "reader_version": vote.reader_version,
                "session_id": vote.session_id,
                "independence_basis": vote.independence_basis,
                "independence_attested": vote.independence_attested,
                "candidate_only_context": vote.candidate_only_context,
                "reader_identities_seen": vote.reader_identities_seen,
                "full_labels_seen": vote.full_labels_seen,
            },
            "vote": event_vote,
            "outcome": outcome,
            "result_confidence": result_confidence,
        }
    )
    parent_hash = record_sha256(record)
    updated["revision"] = int(updated["revision"]) + 1
    updated["parent_record_sha256"] = parent_hash
    finding_count = len(updated["validation"]["findings"])
    updated["derivation"]["confidence_summary"] = _confidence_summary(
        updated["fields"], finding_count
    )
    return updated
