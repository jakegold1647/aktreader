"""Strict local-only configuration helpers for the command-line interface."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aktreader.batch import BatchJob
from aktreader.local_reader import LocalReader, LocalReaderConfig, PinnedArtifact

READER_CONFIG_VERSION = "1.0.0"
_REQUIRED_ARTIFACTS = frozenset(
    {"executable", "model", "mmproj", "prompt", "schema", "model_schema"}
)
_OPTIONAL_ARTIFACTS = frozenset({"lora"})
_GENERATION_KEYS = frozenset(
    {
        "context_size",
        "max_output_tokens",
        "image_max_tokens",
        "seed",
        "gpu_layers",
        "timeout_seconds",
    }
)
_FORBIDDEN_CONFIG_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "base_url",
        "endpoint",
        "host",
        "password",
        "port",
        "secret",
        "token",
        "url",
    }
)


class CliConfigurationError(ValueError):
    """Raised when a CLI input could permit ambiguity or remote access."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise CliConfigurationError(f"duplicate JSON key is forbidden: {key!r}")
        value[key] = child
    return value


def _reject_json_constant(value: str) -> None:
    raise CliConfigurationError(f"non-standard JSON number is forbidden: {value}")


def raw_local_path(path: Path | str, *, role: str) -> str:
    """Reject URL and UNC syntax before asking ``pathlib`` to interpret a path."""
    raw = os.fspath(path)
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise CliConfigurationError(f"{role} must be a local path, not a URL or UNC path")
    return raw


def local_input_path(path: Path | str, *, role: str) -> Path:
    """Resolve an existing local input without accessing a network path."""
    raw = raw_local_path(path, role=role)
    try:
        resolved = Path(raw).resolve(strict=True)
    except OSError as error:
        raise CliConfigurationError(f"{role} is missing or inaccessible: {raw}") from error
    raw_local_path(resolved, role=role)
    if not resolved.is_file() and not resolved.is_dir():
        raise CliConfigurationError(f"{role} is not a file or directory: {resolved}")
    return resolved


def local_output_path(path: Path | str, *, role: str) -> Path:
    """Resolve a not-yet-existing local output path without creating it."""
    resolved = Path(raw_local_path(path, role=role)).resolve()
    raw_local_path(resolved, role=role)
    return resolved


def load_strict_json(path: Path | str, *, role: str) -> Any:
    """Load UTF-8 JSON while rejecting duplicates and non-finite numbers."""
    source = local_input_path(path, role=role)
    if not source.is_file():
        raise CliConfigurationError(f"{role} is not a file: {source}")
    try:
        return json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except UnicodeError as error:
        raise CliConfigurationError(f"{role} is not UTF-8: {source}") from error
    except json.JSONDecodeError as error:
        raise CliConfigurationError(f"{role} is not valid JSON: {source}: {error}") from error


def load_json_object(path: Path | str, *, role: str) -> dict[str, Any]:
    """Load one strict JSON object."""
    payload = load_strict_json(path, role=role)
    if not isinstance(payload, dict):
        raise CliConfigurationError(f"{role} must contain one JSON object")
    return payload


def _normalized_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def _forbidden_setting_key(key: str) -> bool:
    normalized = _normalized_key(key)
    return normalized in _FORBIDDEN_CONFIG_KEYS or normalized.endswith(
        ("_api_key", "_endpoint", "_password", "_secret", "_token", "_url")
    )


def require_local_only_data(value: Any, *, location: str) -> None:
    """Recursively reject hosted-service settings, credentials, URLs, and UNC paths."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _forbidden_setting_key(str(key)):
                raise CliConfigurationError(
                    f"{location}.{key}: hosted-service or credential settings are forbidden"
                )
            if key == "$schema" and isinstance(child, str):
                continue
            require_local_only_data(child, location=f"{location}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            require_local_only_data(child, location=f"{location}[{index}]")
        return
    if isinstance(value, str) and (
        "://" in value or value.startswith(("\\\\", "//"))
    ):
        raise CliConfigurationError(f"{location}: URLs and UNC paths are forbidden")


def require_keys(
    value: Mapping[str, Any],
    *,
    required: set[str] | frozenset[str],
    optional: set[str] | frozenset[str] = frozenset(),
    location: str,
) -> None:
    """Require an exact JSON-object key set with an optional extension set."""
    keys = set(value)
    missing = set(required) - keys
    unexpected = keys - set(required) - set(optional)
    if missing:
        raise CliConfigurationError(f"{location}: missing keys {sorted(missing)}")
    if unexpected:
        raise CliConfigurationError(f"{location}: unexpected keys {sorted(unexpected)}")


def _artifact_from_config(
    raw: Any,
    *,
    role: str,
    config_dir: Path,
) -> PinnedArtifact:
    if not isinstance(raw, Mapping):
        raise CliConfigurationError(f"reader config.artifacts.{role} must be an object")
    require_keys(
        raw,
        required={"path", "sha256"},
        location=f"reader config.artifacts.{role}",
    )
    path_value = raw["path"]
    digest = raw["sha256"]
    if not isinstance(path_value, str) or not path_value.strip():
        raise CliConfigurationError(f"reader config.artifacts.{role}.path must be a string")
    if not isinstance(digest, str):
        raise CliConfigurationError(f"reader config.artifacts.{role}.sha256 must be a string")
    raw_local_path(path_value, role=f"reader config.artifacts.{role}.path")
    artifact_path = Path(path_value)
    if not artifact_path.is_absolute():
        artifact_path = config_dir / artifact_path
    return PinnedArtifact(path=artifact_path.resolve(), sha256=digest)


def _validated_generation(raw: Mapping[str, Any]) -> dict[str, Any]:
    generation = dict(raw)
    for key in ("context_size", "max_output_tokens", "image_max_tokens"):
        value = generation.get(key)
        if key in generation and (
            isinstance(value, bool) or not isinstance(value, int) or value < 1
        ):
            raise CliConfigurationError(
                f"reader config.generation.{key} must be a positive integer"
            )
    if "seed" in generation and (
        isinstance(generation["seed"], bool) or not isinstance(generation["seed"], int)
    ):
        raise CliConfigurationError("reader config.generation.seed must be an integer")
    if "gpu_layers" in generation:
        gpu_layers = generation["gpu_layers"]
        if not (
            gpu_layers == "all"
            or isinstance(gpu_layers, int)
            and not isinstance(gpu_layers, bool)
            and gpu_layers >= 0
        ):
            raise CliConfigurationError(
                "reader config.generation.gpu_layers must be 'all' or a non-negative integer"
            )
    if "timeout_seconds" in generation:
        timeout = generation["timeout_seconds"]
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or timeout <= 0
        ):
            raise CliConfigurationError(
                "reader config.generation.timeout_seconds must be positive or null"
            )
    return generation


def load_local_reader_config(path: Path | str) -> LocalReaderConfig:
    """Load one strict local-only, content-pinned Reader configuration."""
    config_path = local_input_path(path, role="reader config")
    if not config_path.is_file():
        raise CliConfigurationError(f"reader config is not a file: {config_path}")
    payload = load_json_object(config_path, role="reader config")
    require_local_only_data(payload, location="reader config")
    require_keys(
        payload,
        required={"schema_version", "artifacts"},
        optional={"generation"},
        location="reader config",
    )
    if payload["schema_version"] != READER_CONFIG_VERSION:
        raise CliConfigurationError(
            f"reader config.schema_version must be {READER_CONFIG_VERSION!r}"
        )

    artifacts = payload["artifacts"]
    if not isinstance(artifacts, Mapping):
        raise CliConfigurationError("reader config.artifacts must be an object")
    require_keys(
        artifacts,
        required=_REQUIRED_ARTIFACTS,
        optional=_OPTIONAL_ARTIFACTS,
        location="reader config.artifacts",
    )
    pin_roles = _REQUIRED_ARTIFACTS
    pins = {
        role: _artifact_from_config(artifacts[role], role=role, config_dir=config_path.parent)
        for role in sorted(pin_roles)
    }
    lora = (
        _artifact_from_config(artifacts["lora"], role="lora", config_dir=config_path.parent)
        if "lora" in artifacts
        else None
    )

    generation = payload.get("generation", {})
    if not isinstance(generation, Mapping):
        raise CliConfigurationError("reader config.generation must be an object")
    require_keys(
        generation,
        required=frozenset(),
        optional=_GENERATION_KEYS,
        location="reader config.generation",
    )
    validated_generation = _validated_generation(generation)
    return LocalReaderConfig(
        executable=pins["executable"],
        model=pins["model"],
        mmproj=pins["mmproj"],
        prompt=pins["prompt"],
        schema=pins["schema"],
        model_schema=pins["model_schema"],
        lora=lora,
        **validated_generation,
    )


def generation_report(config: LocalReaderConfig) -> dict[str, Any]:
    """Return every deterministic decoding setting used in batch fingerprints."""
    return {
        "context_size": config.context_size,
        "max_output_tokens": config.max_output_tokens,
        "image_max_tokens": config.image_max_tokens,
        "seed": config.seed,
        "gpu_layers": config.gpu_layers,
        "timeout_seconds": config.timeout_seconds,
        "temperature": 0,
        "top_k": 1,
        "repeat_penalty": None,
        "frontend": "mtmd-cli",
    }


def reader_report(reader: LocalReader) -> dict[str, Any]:
    """Render verified local artifact pins without executing the runtime."""
    pins = {
        "executable": reader.config.executable,
        "model": reader.config.model,
        "mmproj": reader.config.mmproj,
        "prompt": reader.config.prompt,
        "schema": reader.config.schema,
        "model_schema": reader.config.model_schema,
    }
    if reader.config.lora is not None:
        pins["lora"] = reader.config.lora
    return {
        "status": "READY",
        "reader": "LOCAL_OPEN_WEIGHTS_ONLY",
        "network_required": False,
        "runtime_fingerprint": reader.runtime_fingerprint,
        "artifacts": {
            role: {"path": str(pin.path), "sha256": pin.sha256}
            for role, pin in sorted(pins.items())
        },
        "generation": generation_report(reader.config),
    }


def model_identity(reader: LocalReader) -> str:
    """Hash the model, projector, and optional LoRA pins as one model identity."""
    hashes = reader.artifact_hashes
    material = {
        key: hashes[key] for key in ("model", "mmproj", "lora") if key in hashes
    }
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def brief_for_job(job: BatchJob) -> Mapping[str, Any]:
    """Bind a manifest job to its inline, metadata-only local Reader brief."""
    brief = job.metadata.get("batch_brief")
    if not isinstance(brief, Mapping):
        raise CliConfigurationError(
            f"{job.job_id}: manifest metadata.batch_brief must be an inline JSON object"
        )
    require_local_only_data(brief, location=f"{job.job_id}.batch_brief")
    target = brief.get("target")
    if not isinstance(target, Mapping):
        raise CliConfigurationError(f"{job.job_id}: batch brief target must be an object")
    if target.get("act_type") != job.act_type or target.get("year") != job.act_year:
        raise CliConfigurationError(
            f"{job.job_id}: manifest act type/year disagree with the batch brief"
        )
    if isinstance(job.target, Mapping) and job.target.get("kind") == "act":
        expected_act = job.target.get("act_no")
        if expected_act is not None and target.get("act_no") != expected_act:
            raise CliConfigurationError(
                f"{job.job_id}: manifest target act number disagrees with the batch brief"
            )
    return brief
