"""Fully local, content-pinned llama.cpp Reader backend.

The application deliberately has no hosted Reader abstraction.  ``LocalReader`` invokes one
explicitly configured ``llama-mtmd-cli`` executable with local files and returns one JSON object.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aktreader.schema import ContractValidationError, validate_instance

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_CONFIDENCE_VALUES = {"PROBABLE", "UNCLEAR", None}
_OUTPUT_ONLY_BRIEF_KEYS = {"mentions", "observations", "source_spans", "transcription"}
_REQUIRED_BRIEF_KEYS = {
    "artifact",
    "clerk_year",
    "label_id",
    "prompt",
    "reader",
    "record_id",
    "target",
}
_SAFE_ENVIRONMENT_KEYS = {
    "COMSPEC",
    "CUDA_PATH",
    "CUDA_VISIBLE_DEVICES",
    "LD_LIBRARY_PATH",
    "NUMBER_OF_PROCESSORS",
    "OMP_NUM_THREADS",
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "VK_ICD_FILENAMES",
    "WINDIR",
}
_CONTRACT_VERSION = "aktreader-local-reader-1.1.0"


class LocalReaderError(RuntimeError):
    """Base error raised by the fully local Reader."""

    def __init__(
        self,
        message: str,
        *,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr

    @property
    def has_process_diagnostics(self) -> bool:
        """Whether a llama.cpp process ran and supplied raw output streams."""

        return self.stdout is not None and self.stderr is not None


class ArtifactValidationError(LocalReaderError):
    """A required local artifact is absent, remote-looking, or fails its checksum pin."""


class BatchBriefError(LocalReaderError):
    """The metadata-only batch brief violates the blind-reader contract."""


class LocalInferenceError(LocalReaderError):
    """The local llama.cpp process failed or timed out."""


class LocalReaderOutputError(LocalReaderError):
    """The process did not return one uncertainty-honest JSON object."""


@dataclass(frozen=True)
class PinnedArtifact:
    """An explicit local file and its required lowercase SHA-256 digest."""

    path: Path
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        if not _SHA256.fullmatch(self.sha256):
            raise ArtifactValidationError(
                f"invalid SHA-256 pin for {self.path}: expected 64 lowercase hex characters"
            )


@dataclass(frozen=True)
class LocalReaderConfig:
    """Pinned runtime assets and deterministic extraction settings."""

    executable: PinnedArtifact
    model: PinnedArtifact
    mmproj: PinnedArtifact
    prompt: PinnedArtifact
    schema: PinnedArtifact
    model_schema: PinnedArtifact
    lora: PinnedArtifact | None = None
    context_size: int = 16_384
    max_output_tokens: int = 8_192
    image_max_tokens: int = 4_096
    seed: int = 0
    gpu_layers: int | str = "all"
    timeout_seconds: float | None = 1_800.0

    def __post_init__(self) -> None:
        if self.context_size < 1:
            raise ValueError("context_size must be positive")
        if self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        if self.image_max_tokens < 1:
            raise ValueError("image_max_tokens must be positive")
        if not isinstance(self.seed, int):
            raise TypeError("seed must be an integer")
        if not (
            self.gpu_layers == "all"
            or isinstance(self.gpu_layers, int)
            and not isinstance(self.gpu_layers, bool)
            and self.gpu_layers >= 0
        ):
            raise ValueError("gpu_layers must be 'all' or a non-negative integer")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive or None")


@dataclass(frozen=True)
class LocalReadResult:
    """A parsed Reader observation and its reproducible content fingerprint."""

    payload: dict[str, Any]
    inference_fingerprint: str
    fingerprint_manifest: dict[str, Any]
    stderr: str


def sha256_file(path: Path) -> str:
    """Hash a file without loading a model-sized artifact into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise BatchBriefError(f"batch brief must be finite JSON data: {error}") from error


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reject_constant(value: str) -> None:
    raise LocalReaderOutputError(f"non-standard JSON number is forbidden: {value}")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LocalReaderOutputError(f"duplicate JSON key is forbidden: {key!r}")
        result[key] = value
    return result


def _load_one_json_object(text: str, *, source: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except LocalReaderOutputError:
        raise
    except json.JSONDecodeError as error:
        raise LocalReaderOutputError(
            f"{source} must contain exactly one JSON object: {error.msg}"
        ) from error
    if not isinstance(value, dict):
        raise LocalReaderOutputError(f"{source} must be a JSON object, not {type(value).__name__}")
    return value


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _reader_completion_after_prompt_echo(stdout: str) -> str:
    """Discard llama.cpp chrome through its final physical ``> `` echo line."""

    normalized_stdout = _normalize_newlines(stdout)
    offset = 0
    final_echo_end: int | None = None
    for line in normalized_stdout.splitlines(keepends=True):
        if line.startswith("> "):
            final_echo_end = offset + len(line)
        offset += len(line)

    if final_echo_end is not None:
        return normalized_stdout[final_echo_end:]
    return normalized_stdout


def _strip_known_reader_trailer(text: str) -> str:
    """Remove only llama.cpp's terminal ``Exiting...`` chrome and surrounding whitespace."""

    without_trailing_whitespace = text.rstrip()
    if without_trailing_whitespace.endswith("Exiting..."):
        return without_trailing_whitespace[: -len("Exiting...")]
    return text


def _strip_complete_json_fence(text: str) -> str:
    """Strip one complete Markdown JSON fence while rejecting surrounding prose."""

    match = re.fullmatch(
        r"\s*```(?:json)?[ \t]*\n(?P<body>.*?)\n```[ \t]*\s*",
        text,
        flags=re.DOTALL,
    )
    return match.group("body") if match is not None else text


def _balanced_top_level_objects(text: str, *, source: str) -> list[tuple[int, int]]:
    """Return balanced top-level object spans using a JSON-string-aware scan."""

    objects: list[tuple[int, int]] = []
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False

    for index, character in enumerate(text):
        if start is None:
            if character == "{":
                start = index
                depth = 1
            elif character == "}":
                raise LocalReaderOutputError(
                    f"{source} contains an unmatched closing brace outside a JSON object"
                )
            elif character in "[]":
                raise LocalReaderOutputError(
                    f"{source} contains a top-level array; one JSON object is required"
                )
            continue

        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                objects.append((start, index + 1))
                start = None

    if start is not None:
        raise LocalReaderOutputError(f"{source} contains an unbalanced JSON object")
    return objects


def _load_reader_stdout(stdout: str) -> dict[str, Any]:
    """Extract exactly one completion object from llama.cpp stdout, failing closed."""

    completion = _reader_completion_after_prompt_echo(stdout)
    completion = _strip_known_reader_trailer(completion)
    completion = _strip_complete_json_fence(completion)
    objects = _balanced_top_level_objects(completion, source="Reader stdout")
    if len(objects) != 1:
        raise LocalReaderOutputError(
            "Reader stdout must contain exactly one balanced top-level JSON object "
            f"after the prompt echo; observed {len(objects)}"
        )
    start, end = objects[0]
    if completion[:start].strip() or completion[end:].strip():
        raise LocalReaderOutputError(
            "Reader stdout contains non-whitespace text outside its JSON object"
        )
    return _load_one_json_object(completion[start:end], source="Reader stdout JSON object")


def _contains_external_ref(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str) and not child.startswith("#"):
                return True
            if _contains_external_ref(child):
                return True
    elif isinstance(value, list):
        return any(_contains_external_ref(child) for child in value)
    return False


def _resolve_local_file(path: Path, *, role: str) -> Path:
    raw = os.fspath(path)
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise ArtifactValidationError(f"{role} must be a local file, not a URL or UNC path")
    if not path.is_absolute():
        raise ArtifactValidationError(f"{role} path must be absolute: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ArtifactValidationError(f"{role} is missing or inaccessible: {path}") from error
    if not resolved.is_file():
        raise ArtifactValidationError(f"{role} is not a file: {resolved}")
    if os.fspath(resolved).startswith(("\\\\", "//")):
        raise ArtifactValidationError(f"{role} resolved to a UNC path: {resolved}")
    return resolved


def _verify_pin(pin: PinnedArtifact, *, role: str) -> Path:
    resolved = _resolve_local_file(pin.path, role=role)
    actual = sha256_file(resolved)
    if actual != pin.sha256:
        raise ArtifactValidationError(
            f"{role} checksum mismatch: expected {pin.sha256}, observed {actual}"
        )
    return resolved


def _safe_subprocess_environment() -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if key.upper() in _SAFE_ENVIRONMENT_KEYS
    }
    environment.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "NO_PROXY": "*",
            "no_proxy": "*",
        }
    )
    return environment


def _validate_confidence_ceiling(payload: Mapping[str, Any]) -> None:
    observations = payload.get("observations")
    if not isinstance(observations, dict) or not observations:
        raise LocalReaderOutputError("Reader output requires a non-empty observations object")

    for field_path, evidence in observations.items():
        if not isinstance(evidence, dict):
            raise LocalReaderOutputError(f"observation {field_path!r} must be an object")
        if "confidence" not in evidence:
            raise LocalReaderOutputError(f"observation {field_path!r} has no confidence")
        confidence = evidence["confidence"]
        if confidence not in _CONFIDENCE_VALUES:
            raise LocalReaderOutputError(
                f"single-reader confidence for {field_path!r} cannot be {confidence!r}; "
                "only PROBABLE, UNCLEAR, or null are allowed"
            )
        state = evidence.get("observation_state")
        if state == "PRESENT" and confidence is None:
            raise LocalReaderOutputError(
                f"present observation {field_path!r} needs PROBABLE or UNCLEAR confidence"
            )
        if state != "PRESENT" and confidence is not None:
            raise LocalReaderOutputError(
                f"non-present observation {field_path!r} must use null confidence"
            )
        if confidence == "UNCLEAR":
            uncertain_value = evidence.get("value")
            alternatives = evidence.get("alternatives")
            if (
                not isinstance(uncertain_value, str)
                or not uncertain_value.startswith("[unclear: ")
                or not uncertain_value.endswith("]")
                or not isinstance(alternatives, list)
                or not alternatives
            ):
                raise LocalReaderOutputError(
                    f"UNCLEAR observation {field_path!r} must retain [unclear: X/Y] "
                    "and at least one alternative"
                )


class LocalReader:
    """The application's sole Reader: an offline llama.cpp CLI subprocess."""

    def __init__(self, config: LocalReaderConfig) -> None:
        self.config = config
        pins: dict[str, PinnedArtifact] = {
            "executable": config.executable,
            "model": config.model,
            "mmproj": config.mmproj,
            "prompt": config.prompt,
            "schema": config.schema,
            "model_schema": config.model_schema,
        }
        if config.lora is not None:
            pins["lora"] = config.lora

        self._paths = {role: _verify_pin(pin, role=role) for role, pin in pins.items()}
        self._artifact_hashes = {role: pin.sha256 for role, pin in pins.items()}

        schema_texts: dict[str, str] = {}
        for role in ("schema", "model_schema"):
            try:
                schema_text = self._paths[role].read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise ArtifactValidationError(
                    f"{role} is not readable UTF-8: {error}"
                ) from error
            try:
                schema = _load_one_json_object(schema_text, source=role)
            except LocalReaderOutputError as error:
                raise ArtifactValidationError(
                    f"{role} is not one strict JSON object: {error}"
                ) from error
            if _contains_external_ref(schema):
                raise ArtifactValidationError(
                    f"{role} contains an external $ref; local Reader accepts fragment refs only"
                )
            schema_texts[role] = schema_text

        try:
            self._prompt_text = self._paths["prompt"].read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ArtifactValidationError(f"prompt is not readable UTF-8: {error}") from error
        self._model_schema_text = schema_texts["model_schema"]

        self._runtime_manifest = {
            "contract_version": _CONTRACT_VERSION,
            "runtime": "llama.cpp-mtmd-cli",
            "artifacts": self._artifact_hashes,
            "generation": self._generation_manifest(),
        }
        self.runtime_fingerprint = _fingerprint(self._runtime_manifest)

    @property
    def artifact_hashes(self) -> dict[str, str]:
        """Return a copy of verified runtime content hashes."""

        return dict(self._artifact_hashes)

    def _generation_manifest(self) -> dict[str, Any]:
        return {
            "context_size": self.config.context_size,
            "gpu_layers": self.config.gpu_layers,
            "image_max_tokens": self.config.image_max_tokens,
            "max_output_tokens": self.config.max_output_tokens,
            "frontend": "mtmd-cli",
            "seed": self.config.seed,
            "temperature": 0,
            "top_k": 1,
            "repeat_penalty": None,
        }

    def _prepare_brief(
        self, batch_brief: Mapping[str, Any], *, image_sha256: str
    ) -> tuple[dict[str, Any], str]:
        if not isinstance(batch_brief, Mapping):
            raise BatchBriefError("batch_brief must be a mapping")
        brief_text = _canonical_json(dict(batch_brief))
        brief = _load_one_json_object(brief_text, source="batch brief")

        missing = _REQUIRED_BRIEF_KEYS - set(brief)
        if missing:
            raise BatchBriefError(f"batch brief is missing metadata keys: {sorted(missing)}")
        leaked = _OUTPUT_ONLY_BRIEF_KEYS & set(brief)
        if leaked:
            raise BatchBriefError(
                f"blind batch brief must not contain prior Reader output: {sorted(leaked)}"
            )

        reader = brief.get("reader")
        if (
            not isinstance(reader, dict)
            or reader.get("mode") != "local"
            or reader.get("other_reader_output_seen") is not False
        ):
            raise BatchBriefError(
                "batch brief must identify a local blind Reader with other_reader_output_seen=false"
            )

        prompt = brief.get("prompt")
        if not isinstance(prompt, dict) or prompt.get("sha256") != self.config.prompt.sha256:
            raise BatchBriefError("batch brief prompt SHA-256 does not match the pinned prompt")

        artifact = brief.get("artifact")
        if not isinstance(artifact, dict) or artifact.get("sha256") != image_sha256:
            raise BatchBriefError("batch brief artifact SHA-256 does not match the input image")
        artifact_path = artifact.get("path")
        if (
            not isinstance(artifact_path, str)
            or not artifact_path
            or "://" in artifact_path
            or artifact_path.startswith(("\\\\", "//"))
        ):
            raise BatchBriefError("batch brief artifact path must be a local path")

        return brief, brief_text

    @staticmethod
    def _target_check_request(brief: Mapping[str, Any]) -> dict[str, Any]:
        target = brief.get("target")
        if not isinstance(target, Mapping):
            raise BatchBriefError("batch brief target must be an object")
        keys = ("year", "act_type", "act_no", "language")
        return {key: target.get(key) for key in keys}

    def _command(self, image_path: Path, request_text: str) -> list[str]:
        gpu_layers = "99" if self.config.gpu_layers == "all" else str(self.config.gpu_layers)
        command = [
            os.fspath(self._paths["executable"]),
            "-m",
            os.fspath(self._paths["model"]),
            "-mm",
            os.fspath(self._paths["mmproj"]),
            "--image",
            os.fspath(image_path),
            "-sys",
            self._prompt_text,
            "--json-schema",
            self._model_schema_text,
            "-p",
            request_text,
            "-c",
            str(self.config.context_size),
            "-n",
            str(self.config.max_output_tokens),
            "--image-max-tokens",
            str(self.config.image_max_tokens),
            "-s",
            str(self.config.seed),
            "--temp",
            "0",
            "--top-k",
            "1",
            "-ngl",
            gpu_layers,
        ]
        if "lora" in self._paths:
            command.extend(["--lora", os.fspath(self._paths["lora"])])
        return command

    def _assemble_full_label(
        self,
        model_payload: Mapping[str, Any],
        brief: Mapping[str, Any],
    ) -> dict[str, Any]:
        expected_target = self._target_check_request(brief)
        target_check = model_payload.get("target_check")
        if not isinstance(target_check, Mapping):
            raise LocalReaderOutputError("model output requires a target_check object")
        for key, expected in expected_target.items():
            if target_check.get(key) != expected:
                raise LocalReaderOutputError(
                    f"Reader changed target-check field {key!r}: "
                    f"expected {expected!r}, observed {target_check.get(key)!r}"
                )

        artifact = brief.get("artifact")
        act_region = artifact.get("act_region") if isinstance(artifact, Mapping) else None
        if not isinstance(act_region, Mapping):
            raise BatchBriefError("batch brief artifact.act_region must be an object")

        model_observations = model_payload.get("observations")
        if not isinstance(model_observations, Mapping):
            raise LocalReaderOutputError("model output requires an observations object")
        stamped_observations: dict[str, dict[str, Any]] = {}
        for field_path, evidence in model_observations.items():
            if not isinstance(field_path, str) or not isinstance(evidence, Mapping):
                raise LocalReaderOutputError(
                    "model observations require string keys and object values"
                )
            stamped_observations[field_path] = {
                **dict(evidence),
                "source_span_ids": ["act-region"],
            }

        return {
            "$schema": "https://aktreader.org/schema/reader-label-1.0.0.json",
            "schema_version": "1.0.0",
            **brief,
            "source_spans": {
                "act-region": {
                    "bbox": dict(act_region),
                    "description": (
                        "Entire supplied act region; the local model did not emit "
                        "field-level bounding boxes."
                    ),
                }
            },
            "mentions": [],
            "transcription": model_payload["transcription"],
            "observations": stamped_observations,
            "compliance": {
                "restricted_sources_used": False,
                "privacy_decision": "ALLOW",
                "privacy_basis": "local batch privacy gate allowed this act before inference",
                "training_eligible": False,
                "training_basis": (
                    "single local-reader output requires consensus or human verification"
                ),
            },
            "authority_warning": "extraction is not authority — verify against the scan",
        }

    def _fingerprint_manifest(
        self, *, image_sha256: str, batch_brief_sha256: str
    ) -> dict[str, Any]:
        return {
            **self._runtime_manifest,
            "input": {
                "batch_brief_sha256": batch_brief_sha256,
                "image_sha256": image_sha256,
            },
        }

    def read(self, image_path: Path | str, *, batch_brief: Mapping[str, Any]) -> LocalReadResult:
        """Read one local image and return exactly one graded JSON label.

        ``batch_brief`` is metadata only.  Output-bearing keys are rejected so a blind pass
        cannot accidentally see another Reader's transcription or observations.
        """

        image = _resolve_local_file(Path(image_path), role="input image")
        image_sha256 = sha256_file(image)
        brief, _ = self._prepare_brief(batch_brief, image_sha256=image_sha256)
        target_request = self._target_check_request(brief)
        request_text = (
            "Read the supplied image as one blind AKTREADER pass. Return only the bounded "
            "model-facing schema. The application stamps identity and provenance after "
            "generation; do not emit hashes, paths, timestamps, IDs, compliance fields, or "
            "other mechanical metadata. Confirm the requested act in target_check and derive "
            "all transcription and observations from the image. Do not use any other Reader "
            "output. Requested target metadata:\n"
            f"{_canonical_json(target_request)}"
        )
        command = self._command(image, request_text)

        creation_flags = 0
        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                creationflags=creation_flags,
                encoding="utf-8",
                env=_safe_subprocess_environment(),
                errors="strict",
                shell=False,
                stdin=subprocess.DEVNULL,
                text=True,
                timeout=self.config.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout if isinstance(error.stdout, str) else ""
            stderr = error.stderr if isinstance(error.stderr, str) else ""
            raise LocalInferenceError(
                f"local inference exceeded {self.config.timeout_seconds} seconds",
                stdout=stdout,
                stderr=stderr,
            ) from error
        except (OSError, UnicodeError) as error:
            raise LocalInferenceError(f"failed to execute pinned local runtime: {error}") from error

        if completed.returncode != 0:
            stderr_tail = completed.stderr[-4000:].strip()
            raise LocalInferenceError(
                f"local runtime exited with code {completed.returncode}: {stderr_tail}",
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

        try:
            model_payload = _load_reader_stdout(completed.stdout)
            _validate_confidence_ceiling(model_payload)
            try:
                validate_instance(model_payload, self._paths["model_schema"])
            except ContractValidationError as error:
                raise LocalReaderOutputError(
                    f"Reader output violates the pinned model JSON schema: {error}"
                ) from error
            payload = self._assemble_full_label(model_payload, brief)
            try:
                validate_instance(payload, self._paths["schema"])
            except ContractValidationError as error:
                raise LocalReaderOutputError(
                    f"pipeline-stamped output violates the pinned label JSON schema: {error}"
                ) from error
        except LocalReaderError as error:
            error.stdout = completed.stdout
            error.stderr = completed.stderr
            raise

        manifest = self._fingerprint_manifest(
            image_sha256=image_sha256,
            batch_brief_sha256=_fingerprint(brief),
        )
        return LocalReadResult(
            payload=payload,
            inference_fingerprint=_fingerprint(manifest),
            fingerprint_manifest=manifest,
            stderr=completed.stderr,
        )


__all__ = [
    "ArtifactValidationError",
    "BatchBriefError",
    "LocalInferenceError",
    "LocalReadResult",
    "LocalReader",
    "LocalReaderConfig",
    "LocalReaderError",
    "LocalReaderOutputError",
    "PinnedArtifact",
    "sha256_file",
]
