"""Pinned local Kraken PAGE XML recognition and layout backend.

AKT Reader does not package, download, or invoke a Kraken server. The owner
supplies a checksum-pinned local executable and recognition model. The backend
can segment local page images into PAGE XML and recognize pre-segmented local
PAGE XML in a subprocess, atomically publishing only validated local output.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from aktreader.local_reader import PinnedArtifact, sha256_file

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_DEVICE = re.compile(r"^(?:cpu|mps|cuda:[0-9]+)$")
_PRECISIONS = frozenset({"32", "16", "16-mixed", "bf16", "bf16-mixed"})
_TEXT_DIRECTIONS = frozenset(
    {"horizontal-lr", "horizontal-rl", "vertical-lr", "vertical-rl"}
)
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
_CONTRACT_VERSION = "aktreader-local-kraken-1.0.0"


class KrakenError(RuntimeError):
    """Base error raised by the fully local Kraken adapter."""

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


class KrakenArtifactError(KrakenError):
    """A configured executable or recognition model is not safely pinned."""


class KrakenInferenceError(KrakenError):
    """The local Kraken subprocess failed or timed out."""


class KrakenOutputError(KrakenError):
    """Kraken did not produce a valid local PAGE XML result."""


@dataclass(frozen=True)
class KrakenConfig:
    """Pinned runtime assets and explicit deterministic local inference settings."""

    executable: PinnedArtifact
    model: PinnedArtifact
    device: str = "cpu"
    precision: str = "32"
    batch_size: int = 1
    text_direction: str = "horizontal-lr"
    timeout_seconds: float | None = 1_800.0

    def __post_init__(self) -> None:
        if not _DEVICE.fullmatch(self.device):
            raise ValueError("device must be cpu, mps, or cuda:<non-negative index>")
        if self.precision not in _PRECISIONS:
            raise ValueError(
                "precision must be one of 32, 16, 16-mixed, bf16, or bf16-mixed"
            )
        if isinstance(self.batch_size, bool) or not isinstance(self.batch_size, int):
            raise TypeError("batch_size must be an integer")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.text_direction not in _TEXT_DIRECTIONS:
            raise ValueError(
                "text_direction must be horizontal-lr, horizontal-rl, vertical-lr, or vertical-rl"
            )
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive or None")


@dataclass(frozen=True)
class KrakenSegmentationResult:
    """Immutable evidence about one local image-to-PAGE XML layout run."""

    source_sha256: str
    output_sha256: str
    output_path: Path
    runtime_fingerprint: str
    fingerprint_manifest: dict[str, Any]
    stdout: str
    stderr: str


@dataclass(frozen=True)
class KrakenRecognitionResult:
    """Immutable evidence about one local PAGE XML recognition run."""

    source_sha256: str
    output_sha256: str
    output_path: Path
    runtime_fingerprint: str
    fingerprint_manifest: dict[str, Any]
    stdout: str
    stderr: str


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


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


def _resolve_local_file(path: Path | str, *, role: str) -> Path:
    raw = os.fspath(path)
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise KrakenArtifactError(f"{role} must be a local file, not a URL or UNC path")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise KrakenArtifactError(f"{role} path must be absolute: {candidate}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise KrakenArtifactError(f"{role} is missing or inaccessible: {candidate}") from error
    if not resolved.is_file():
        raise KrakenArtifactError(f"{role} is not a file: {resolved}")
    if os.fspath(resolved).startswith(("\\\\", "//")):
        raise KrakenArtifactError(f"{role} resolved to a UNC path: {resolved}")
    return resolved


def _resolve_local_output(path: Path | str) -> Path:
    raw = os.fspath(path)
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise KrakenOutputError("PAGE XML output must be a local path, not a URL or UNC path")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise KrakenOutputError(f"PAGE XML output path must be absolute: {candidate}")
    resolved = candidate.resolve()
    if os.fspath(resolved).startswith(("\\\\", "//")):
        raise KrakenOutputError("PAGE XML output resolved to a UNC path")
    parent = resolved.parent
    if not parent.is_dir():
        raise KrakenOutputError(f"PAGE XML output directory is missing: {parent}")
    return resolved


def _verify_pin(pin: PinnedArtifact, *, role: str) -> Path:
    if not _SHA256.fullmatch(pin.sha256):
        raise KrakenArtifactError(
            f"invalid SHA-256 pin for {role}: expected 64 lowercase hex characters"
        )
    resolved = _resolve_local_file(pin.path, role=role)
    actual = sha256_file(resolved)
    if actual != pin.sha256:
        raise KrakenArtifactError(
            f"{role} checksum mismatch: expected {pin.sha256}, observed {actual}"
        )
    return resolved


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _validate_image(path: Path, *, role: str) -> None:
    try:
        with Image.open(path) as opened:
            width, height = opened.size
            opened.verify()
    except (OSError, UnidentifiedImageError) as error:
        raise KrakenOutputError(f"{role} is not a readable image: {path}") from error
    if width < 1 or height < 1:
        raise KrakenOutputError(f"{role} has invalid dimensions")


def _validate_pagexml(path: Path, *, role: str) -> None:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise KrakenOutputError(f"{role} is not readable: {path}") from error
    marker = raw.upper()
    if b"<!DOCTYPE" in marker or b"<!ENTITY" in marker:
        raise KrakenOutputError(f"{role} must not contain DTD or entity declarations")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise KrakenOutputError(f"{role} is not well-formed XML: {error}") from error
    if _local_name(root.tag) != "PcGts":
        raise KrakenOutputError(f"{role} root element must be PcGts")
    if not any(_local_name(element.tag) == "Page" for element in root.iter()):
        raise KrakenOutputError(f"{role} contains no Page element")


class LocalKraken:
    """Run checksum-pinned Kraken against pre-segmented local PAGE XML."""

    def __init__(self, config: KrakenConfig) -> None:
        self.config = config
        pins = {"executable": config.executable, "model": config.model}
        self._paths = {role: _verify_pin(pin, role=role) for role, pin in pins.items()}
        self._artifact_hashes = {role: pin.sha256 for role, pin in pins.items()}
        self._runtime_manifest = {
            "contract_version": _CONTRACT_VERSION,
            "runtime": "kraken-cli",
            "artifacts": self._artifact_hashes,
            "inference": self.inference_settings,
        }
        self.runtime_fingerprint = _fingerprint(self._runtime_manifest)

    @property
    def artifact_hashes(self) -> dict[str, str]:
        """Return copies of verified executable and model hashes."""

        return dict(self._artifact_hashes)

    @property
    def inference_settings(self) -> dict[str, Any]:
        """Return the explicit local Kraken settings in the run fingerprint."""

        return {
            "batch_size": self.config.batch_size,
            "device": self.config.device,
            "text_direction": self.config.text_direction,
            "precision": self.config.precision,
            "timeout_seconds": self.config.timeout_seconds,
        }

    def _command(self, source: Path, destination: Path) -> list[str]:
        return [
            os.fspath(self._paths["executable"]),
            "-x",
            "--device",
            self.config.device,
            "--precision",
            self.config.precision,
            "-f",
            "xml",
            "-i",
            os.fspath(source),
            os.fspath(destination),
            "ocr",
            "-m",
            os.fspath(self._paths["model"]),
            "-B",
            str(self.config.batch_size),
        ]

    def _segment_command(self, source: Path, destination: Path) -> list[str]:
        return [
            os.fspath(self._paths["executable"]),
            "-x",
            "--device",
            self.config.device,
            "--precision",
            self.config.precision,
            "-i",
            os.fspath(source),
            os.fspath(destination),
            "segment",
            "-bl",
            "-d",
            self.config.text_direction,
        ]

    def segment_image(
        self,
        source: Path | str,
        output: Path | str,
        *,
        replace_existing: bool = False,
    ) -> KrakenSegmentationResult:
        """Segment one local image into validated PAGE XML with Kraken's baseline model."""

        source_path = _resolve_local_file(source, role="input image")
        _validate_image(source_path, role="input image")
        output_path = _resolve_local_output(output)
        if source_path == output_path:
            raise KrakenOutputError("PAGE XML output must not overwrite the input image")
        if output_path.exists() and not replace_existing:
            raise KrakenOutputError(
                "PAGE XML output already exists; pass --replace-existing to replace it"
            )
        source_sha256 = sha256_file(source_path)

        with tempfile.TemporaryDirectory(
            prefix=".aktreader-kraken-", dir=os.fspath(output_path.parent)
        ) as temporary_directory:
            temporary_output = Path(temporary_directory) / "segmented.page.xml"
            command = self._segment_command(source_path, temporary_output)
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    cwd=temporary_directory,
                    env=_safe_subprocess_environment(),
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=False,
                    timeout=self.config.timeout_seconds,
                )
            except subprocess.TimeoutExpired as error:
                raise KrakenInferenceError(
                    f"local Kraken timed out after {self.config.timeout_seconds} seconds",
                    stdout=_stream_text(error.stdout),
                    stderr=_stream_text(error.stderr),
                ) from error
            if completed.returncode != 0:
                raise KrakenInferenceError(
                    f"local Kraken exited with code {completed.returncode}",
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            if not temporary_output.is_file():
                raise KrakenOutputError(
                    "local Kraken exited successfully but did not create PAGE XML output",
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            _validate_pagexml(temporary_output, role="Kraken PAGE XML layout output")
            output_sha256 = sha256_file(temporary_output)
            os.replace(temporary_output, output_path)

        manifest = {
            "runtime_fingerprint": self.runtime_fingerprint,
            "source_sha256": source_sha256,
            "output_sha256": output_sha256,
        }
        return KrakenSegmentationResult(
            source_sha256=source_sha256,
            output_sha256=output_sha256,
            output_path=output_path,
            runtime_fingerprint=self.runtime_fingerprint,
            fingerprint_manifest=manifest,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def recognize_pagexml(
        self,
        source: Path | str,
        output: Path | str,
        *,
        replace_existing: bool = False,
    ) -> KrakenRecognitionResult:
        """Recognize existing PAGE XML and atomically publish a new PAGE XML result."""

        source_path = _resolve_local_file(source, role="input PAGE XML")
        _validate_pagexml(source_path, role="input PAGE XML")
        output_path = _resolve_local_output(output)
        if source_path == output_path:
            raise KrakenOutputError("PAGE XML output must not overwrite the input PAGE XML")
        if output_path.exists() and not replace_existing:
            raise KrakenOutputError(
                "PAGE XML output already exists; pass --replace-existing to replace it"
            )
        source_sha256 = sha256_file(source_path)

        with tempfile.TemporaryDirectory(
            prefix=".aktreader-kraken-",
            dir=os.fspath(output_path.parent),
        ) as temporary_directory:
            temporary_output = Path(temporary_directory) / "recognized.page.xml"
            command = self._command(source_path, temporary_output)
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    cwd=temporary_directory,
                    env=_safe_subprocess_environment(),
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=False,
                    timeout=self.config.timeout_seconds,
                )
            except subprocess.TimeoutExpired as error:
                raise KrakenInferenceError(
                    f"local Kraken timed out after {self.config.timeout_seconds} seconds",
                    stdout=_stream_text(error.stdout),
                    stderr=_stream_text(error.stderr),
                ) from error
            if completed.returncode != 0:
                raise KrakenInferenceError(
                    f"local Kraken exited with code {completed.returncode}",
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            if not temporary_output.is_file():
                raise KrakenOutputError(
                    "local Kraken exited successfully but did not create PAGE XML output",
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            _validate_pagexml(temporary_output, role="Kraken PAGE XML output")
            output_sha256 = sha256_file(temporary_output)
            os.replace(temporary_output, output_path)

        manifest = {
            "runtime_fingerprint": self.runtime_fingerprint,
            "source_sha256": source_sha256,
            "output_sha256": output_sha256,
        }
        return KrakenRecognitionResult(
            source_sha256=source_sha256,
            output_sha256=output_sha256,
            output_path=output_path,
            runtime_fingerprint=self.runtime_fingerprint,
            fingerprint_manifest=manifest,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def _stream_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
