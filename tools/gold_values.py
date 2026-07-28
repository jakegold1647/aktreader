"""Compact evidence markers used by the deterministic gold-data definitions."""

from __future__ import annotations

from typing import Any


def original(value: Any, script: str) -> dict[str, Any]:
    return {"__evidence__": True, "value": value, "original_script": script}


def unclear(*alternatives: str, original_script: str | None = None) -> dict[str, Any]:
    if not alternatives:
        raise ValueError("unclear evidence requires at least one candidate")
    rendered = "/".join(alternatives)
    return {
        "__evidence__": True,
        "value": f"[unclear: {rendered}]",
        "original_script": original_script,
        "confidence": "UNCLEAR",
        "observation_state": "PRESENT",
        "alternatives": list(alternatives),
    }


def observed_state(state: str, *, original_script: str | None = None) -> dict[str, Any]:
    return {
        "__evidence__": True,
        "value": None,
        "original_script": original_script,
        "confidence": "PROBABLE",
        "observation_state": state,
        "alternatives": [],
    }
