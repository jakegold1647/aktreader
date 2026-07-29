"""Strict local JSON-Schema validation without remote reference retrieval."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


class ContractValidationError(ValueError):
    """Raised when an AKTREADER artifact violates its declared contract."""


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object with a path-rich error."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractValidationError(f"cannot load JSON {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ContractValidationError(f"{path}: top-level JSON value must be an object")
    return payload


def validate_instance(instance: dict[str, Any], schema_path: Path) -> None:
    """Validate one object against a local draft-2020-12 schema."""
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    if errors:
        rendered: list[str] = []
        for error in errors[:20]:
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            rendered.append(f"{location}: {error.message}")
        suffix = f" (+{len(errors) - 20} more)" if len(errors) > 20 else ""
        raise ContractValidationError(
            f"schema validation failed against {schema_path}: "
            + "; ".join(rendered)
            + suffix
        )

    grounding_contract = schema.get("x-aktreader-grounding-contract")
    if isinstance(grounding_contract, Mapping):
        if grounding_contract.get("version") != "1.0.0":
            raise ContractValidationError(
                f"{schema_path}: unsupported grounding contract version"
            )
        from aktreader.grounding import (
            GroundingValidationError,
            require_grounded_payload,
        )

        try:
            require_grounded_payload(instance)
        except GroundingValidationError as error:
            raise ContractValidationError(
                f"grounding validation failed against {schema_path}: {error}"
            ) from error


def validate_declared_document(path: Path, *, workspace_root: Path) -> dict[str, Any]:
    """Validate a document whose `$schema` is a local relative path.

    Network schema resolution is intentionally unsupported: preservation contracts must be
    available in the repository and inference must remain offline.
    """
    document = load_json(path)
    declared = document.get("$schema")
    if not isinstance(declared, str) or not declared:
        raise ContractValidationError(f"{path}: missing local $schema declaration")
    if "://" in declared:
        raise ContractValidationError(f"{path}: remote $schema declarations are forbidden")
    schema_path = (path.parent / declared).resolve()
    root = workspace_root.resolve()
    if schema_path != root and root not in schema_path.parents:
        raise ContractValidationError(f"{path}: declared schema escapes the workspace")
    validate_instance(document, schema_path)
    return document
