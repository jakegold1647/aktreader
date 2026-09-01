"""Strict local JSON-Schema validation without remote reference retrieval."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource, Unresolvable
from referencing.jsonschema import DRAFT202012


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


def _file_uri_path(uri: str) -> Path:
    parsed = urlsplit(uri)
    if parsed.scheme != "file" or parsed.netloc or parsed.query or parsed.fragment:
        raise NoSuchResource(ref=uri)
    converted = unquote(parsed.path)
    if (
        os.name == "nt"
        and len(converted) >= 3
        and converted[0] in {"/", "\\"}
        and converted[2] == ":"
    ):
        converted = converted[1:]
    return Path(converted)


def _local_schema_registry(
    schema: dict[str, Any],
    *,
    schema_path: Path,
    schema_root: Path,
) -> tuple[dict[str, Any], Registry]:
    schema_uri = schema_path.as_uri()
    rooted_schema = schema if "$id" in schema else {**schema, "$id": schema_uri}

    def retrieve(uri: str) -> Resource:
        try:
            candidate = _file_uri_path(uri).resolve(strict=True)
            candidate.relative_to(schema_root)
            if not candidate.is_file():
                raise OSError("schema reference is not a file")
            payload = load_json(candidate)
        except (ContractValidationError, OSError, RuntimeError, ValueError) as error:
            raise NoSuchResource(ref=uri) from error
        return Resource.from_contents(payload, default_specification=DRAFT202012)

    resource = Resource.from_contents(rooted_schema, default_specification=DRAFT202012)
    return rooted_schema, Registry(retrieve=retrieve).with_resource(schema_uri, resource)


def validate_instance(
    instance: dict[str, Any],
    schema_path: Path,
    *,
    schema_root: Path | None = None,
) -> None:
    """Validate one object against a local draft-2020-12 schema."""
    try:
        resolved_schema = schema_path.resolve(strict=True)
        resolved_root = (
            resolved_schema.parent if schema_root is None else schema_root.resolve(strict=True)
        )
        resolved_schema.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError) as error:
        raise ContractValidationError(
            f"{schema_path}: schema must resolve inside its local root"
        ) from error
    schema = load_json(resolved_schema)
    rooted_schema, registry = _local_schema_registry(
        schema,
        schema_path=resolved_schema,
        schema_root=resolved_root,
    )
    validator = Draft202012Validator(
        rooted_schema,
        format_checker=FormatChecker(),
        registry=registry,
    )
    try:
        errors = sorted(
            validator.iter_errors(instance), key=lambda item: list(item.absolute_path)
        )
    except Unresolvable as error:
        raise ContractValidationError(
            f"schema validation against {resolved_schema} could not resolve a reference "
            "inside the local schema root"
        ) from error
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
    validate_instance(document, schema_path, schema_root=root)
    return document
