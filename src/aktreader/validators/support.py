"""Internal adapters shared by mechanical validators."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def observations_of(record: Any) -> Mapping[str, Any]:
    if hasattr(record, "observations"):
        return record.observations
    if hasattr(record, "fields"):
        return record.fields
    if isinstance(record, Mapping):
        if isinstance(record.get("observations"), Mapping):
            return record["observations"]
        if isinstance(record.get("fields"), Mapping):
            return record["fields"]
        return record
    raise TypeError("record must expose observations or fields")


def record_id_of(record: Any) -> str:
    if hasattr(record, "record_id"):
        return str(record.record_id)
    if isinstance(record, Mapping):
        return str(record.get("record_id", "<unknown>"))
    return "<unknown>"


def target_of(record: Any) -> Mapping[str, Any]:
    if hasattr(record, "target"):
        return record.target
    if isinstance(record, Mapping):
        target = record.get("target")
        if isinstance(target, Mapping):
            return target
        register = record.get("register")
        if isinstance(register, Mapping):
            return register
    return {}


def clerk_year_of(record: Any) -> str | None:
    if hasattr(record, "clerk_year_id"):
        return record.clerk_year_id
    if isinstance(record, Mapping):
        raw = record.get("clerk_year_id")
        if isinstance(raw, str):
            return raw
        clerk_year = record.get("clerk_year")
        if isinstance(clerk_year, Mapping) and isinstance(clerk_year.get("id"), str):
            return clerk_year["id"]
    return None


def evidence_value(observations: Mapping[str, Any], path: str) -> Any:
    evidence = observations.get(path)
    if not isinstance(evidence, Mapping):
        return None
    if evidence.get("observation_state") != "PRESENT":
        return None
    if evidence.get("confidence") == "UNCLEAR":
        return None
    return evidence.get("value")
