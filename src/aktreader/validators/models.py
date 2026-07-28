"""Shared immutable validator contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(child) for key, child in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(child) for child in value)
    return value


@dataclass(frozen=True)
class ValidationFinding:
    """A non-mutating mechanical flag with provenance."""

    code: str
    message: str
    record_ids: tuple[str, ...]
    field_paths: tuple[str, ...]
    severity: str = "FLAG"
    blocks_confident: bool = True
    evidence: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", _freeze(self.evidence))
