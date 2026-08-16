"""Run one checksum-pinned local Kraken training job with an auditable receipt."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aktreader.htr_corpus import inspect_consented_training_corpus

_CONTRACT = {"name": "aktreader-local-kraken-training", "version": "1.0.0"}
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_DEVICE = re.compile(r"^(?:auto|cpu|mps|cuda(?::[0-9]+)?)$")
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
    "WINDIR",
}


class KrakenTrainingError(RuntimeError):
    """Raised when a local Kraken training run is unsafe or fails."""


@dataclass(frozen=True)
class KrakenTrainingConfig:
    """Explicit pinned runtime and trainer settings for one fresh local run."""

    executable: Path
    executable_sha256: str
    runtime: dict[str, object]
    train: dict[str, object]
    config_sha256: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_sha256(value: object, *, role: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise KrakenTrainingError(f"{role} must be a lowercase SHA-256 string")
    return value


def _resolve_local_path(path: Path | str, *, role: str, must_exist: bool) -> Path:
    raw = os.fspath(path)
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise KrakenTrainingError(f"{role} must be a local path, not a URL or UNC path")
    candidate = Path(raw)
    try:
        resolved = candidate.resolve(strict=must_exist)
    except OSError as error:
        raise KrakenTrainingError(f"{role} is missing or inaccessible: {raw}") from error
    if os.fspath(resolved).startswith(("\\\\", "//")):
        raise KrakenTrainingError(f"{role} must not resolve to a UNC path")
    return resolved


def _read_json(path: Path, *, role: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise KrakenTrainingError(f"{role} is not readable strict JSON: {path}") from error
    if not isinstance(payload, dict):
        raise KrakenTrainingError(f"{role} must be a JSON object: {path}")
    return payload


def _require_keys(payload: dict[str, Any], *, required: set[str], role: str) -> None:
    if set(payload) != required:
        missing = sorted(required - set(payload))
        extra = sorted(set(payload) - required)
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if extra:
            details.append(f"unexpected {', '.join(extra)}")
        raise KrakenTrainingError(f"{role} has invalid keys: {'; '.join(details)}")


def _positive_int(value: object, *, role: str, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise KrakenTrainingError(f"{role} must be an integer")
    if value < 0 or (value == 0 and not allow_zero):
        raise KrakenTrainingError(f"{role} must be {'non-negative' if allow_zero else 'positive'}")
    return value


def _positive_float(value: object, *, role: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise KrakenTrainingError(f"{role} must be a positive number")
    return float(value)


def _load_runtime(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise KrakenTrainingError("training runtime must be an object")
    _require_keys(
        value,
        required={"device", "precision", "workers", "threads", "seed", "deterministic", "timeout_seconds"},
        role="training runtime",
    )
    device = value["device"]
    if not isinstance(device, str) or not _DEVICE.fullmatch(device):
        raise KrakenTrainingError("training runtime device must be auto, cpu, mps, cuda, or cuda:<index>")
    precision = value["precision"]
    if precision not in {"32-true", "16-mixed", "bf16-mixed"}:
        raise KrakenTrainingError("training runtime precision is unsupported")
    deterministic = value["deterministic"]
    if deterministic is not True:
        raise KrakenTrainingError("training runtime deterministic must be true")
    return {
        "device": device,
        "precision": precision,
        "workers": _positive_int(value["workers"], role="training runtime workers", allow_zero=True),
        "threads": _positive_int(value["threads"], role="training runtime threads"),
        "seed": _positive_int(value["seed"], role="training runtime seed", allow_zero=True),
        "deterministic": deterministic,
        "timeout_seconds": _positive_float(
            value["timeout_seconds"],
            role="training runtime timeout_seconds",
        ),
    }


def _load_train(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise KrakenTrainingError("training settings must be an object")
    _require_keys(
        value,
        required={
            "architecture",
            "weights_format",
            "normalization",
            "normalize_whitespace",
            "quit",
            "epochs",
            "lag",
            "lrate",
            "schedule",
            "warmup",
            "augment",
            "batch_size",
            "accumulate_grad_batches",
        },
        role="training settings",
    )
    architecture = value["architecture"]
    if not isinstance(architecture, dict) or "kind" not in architecture:
        raise KrakenTrainingError("training architecture must be an object with kind")
    kind = architecture["kind"]
    if kind == "vgsl":
        _require_keys(architecture, required={"kind", "spec"}, role="VGSL architecture")
        spec = architecture["spec"]
        if not isinstance(spec, str) or not spec.strip():
            raise KrakenTrainingError("VGSL architecture spec must be a non-empty string")
        normalized_architecture: dict[str, object] = {"kind": kind, "spec": spec}
    elif kind == "ppocrv6":
        _require_keys(
            architecture,
            required={"kind", "variant", "height", "max_width"},
            role="PP-OCRv6 architecture",
        )
        variant = architecture["variant"]
        if variant not in {"tiny", "small", "medium"}:
            raise KrakenTrainingError("PP-OCRv6 variant must be tiny, small, or medium")
        normalized_architecture = {
            "kind": kind,
            "variant": variant,
            "height": _positive_int(architecture["height"], role="PP-OCRv6 height"),
            "max_width": _positive_int(
                architecture["max_width"],
                role="PP-OCRv6 max_width",
            ),
        }
    else:
        raise KrakenTrainingError("training architecture kind must be vgsl or ppocrv6")

    weights_format = value["weights_format"]
    if weights_format != "safetensors":
        raise KrakenTrainingError("training weights_format must be safetensors")
    normalization = value["normalization"]
    if normalization not in {"NFC", "NFD", "NFKC", "NFKD"}:
        raise KrakenTrainingError("training normalization is unsupported")
    if not isinstance(value["normalize_whitespace"], bool):
        raise KrakenTrainingError("training normalize_whitespace must be a boolean")
    if value["quit"] not in {"early", "fixed"}:
        raise KrakenTrainingError("training quit must be early or fixed")
    if value["schedule"] not in {"constant", "1cycle", "cosine", "reduceonplateau"}:
        raise KrakenTrainingError("training schedule is unsupported")
    if not isinstance(value["augment"], bool):
        raise KrakenTrainingError("training augment must be a boolean")
    return {
        "architecture": normalized_architecture,
        "weights_format": weights_format,
        "normalization": normalization,
        "normalize_whitespace": value["normalize_whitespace"],
        "quit": value["quit"],
        "epochs": _positive_int(value["epochs"], role="training epochs"),
        "lag": _positive_int(value["lag"], role="training lag"),
        "lrate": _positive_float(value["lrate"], role="training lrate"),
        "schedule": value["schedule"],
        "warmup": _positive_int(value["warmup"], role="training warmup", allow_zero=True),
        "augment": value["augment"],
        "batch_size": _positive_int(value["batch_size"], role="training batch_size"),
        "accumulate_grad_batches": _positive_int(
            value["accumulate_grad_batches"],
            role="training accumulate_grad_batches",
        ),
    }


def load_kraken_training_config(path: Path | str) -> KrakenTrainingConfig:
    """Load an explicit, pinned local Kraken training configuration."""

    config_path = _resolve_local_path(path, role="Kraken training configuration", must_exist=True)
    if not config_path.is_file():
        raise KrakenTrainingError(f"Kraken training configuration is not a file: {config_path}")
    payload = _read_json(config_path, role="Kraken training configuration")
    _require_keys(
        payload,
        required={"contract", "ketos", "runtime", "train"},
        role="Kraken training configuration",
    )
    if payload["contract"] != _CONTRACT:
        raise KrakenTrainingError("Kraken training configuration has an unsupported contract")
    ketos = payload["ketos"]
    if not isinstance(ketos, dict):
        raise KrakenTrainingError("Kraken training ketos pin must be an object")
    _require_keys(ketos, required={"path", "sha256"}, role="Kraken training ketos pin")
    executable = _resolve_local_path(ketos["path"], role="pinned ketos executable", must_exist=True)
    if not executable.is_file():
        raise KrakenTrainingError(f"pinned ketos executable is not a file: {executable}")
    executable_sha256 = _require_sha256(ketos["sha256"], role="pinned ketos executable SHA-256")
    if _sha256_file(executable) != executable_sha256:
        raise KrakenTrainingError("pinned ketos executable checksum mismatch")
    return KrakenTrainingConfig(
        executable=executable,
        executable_sha256=executable_sha256,
        runtime=_load_runtime(payload["runtime"]),
        train=_load_train(payload["train"]),
        config_sha256=_sha256_file(config_path),
    )


def _yaml_scalar(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _experiment_yaml(
    config: KrakenTrainingConfig,
    *,
    corpus: Path,
    checkpoint_directory: Path,
) -> str:
    runtime = config.runtime
    train = config.train
    architecture = train["architecture"]
    assert isinstance(architecture, dict)
    lines = [
        f"precision: {_yaml_scalar(runtime['precision'])}",
        f"device: {_yaml_scalar(runtime['device'])}",
        f"num_workers: {runtime['workers']}",
        f"num_threads: {runtime['threads']}",
        f"seed: {runtime['seed']}",
        "deterministic: true",
        "train:",
        f"  training_data:",
        f"    - {_yaml_scalar(str(corpus / 'train.lst'))}",
        f"  evaluation_data:",
        f"    - {_yaml_scalar(str(corpus / 'validation.lst'))}",
        '  format_type: "xml"',
        f"  checkpoint_path: {_yaml_scalar(str(checkpoint_directory))}",
        '  weights_format: "safetensors"',
        f"  normalization: {_yaml_scalar(train['normalization'])}",
        f"  normalize_whitespace: {str(train['normalize_whitespace']).lower()}",
        f"  quit: {_yaml_scalar(train['quit'])}",
        f"  epochs: {train['epochs']}",
        f"  lag: {train['lag']}",
        f"  lrate: {train['lrate']}",
        f"  schedule: {_yaml_scalar(train['schedule'])}",
        f"  warmup: {train['warmup']}",
        f"  augment: {str(train['augment']).lower()}",
        f"  batch_size: {train['batch_size']}",
        f"  accumulate_grad_batches: {train['accumulate_grad_batches']}",
    ]
    if architecture["kind"] == "vgsl":
        lines.append(f"  spec: {_yaml_scalar(architecture['spec'])}")
    else:
        lines.extend(
            [
                '  arch: "ppocrv6"',
                f"  variant: {_yaml_scalar(architecture['variant'])}",
                f"  height: {architecture['height']}",
                f"  max_width: {architecture['max_width']}",
            ]
        )
    return "\n".join(lines) + "\n"


def _safe_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in _SAFE_ENVIRONMENT_KEYS
    }
    environment.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "NO_PROXY": "*",
            "WANDB_DISABLED": "true",
            "no_proxy": "*",
        }
    )
    return environment


def _write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def run_kraken_training(
    config_path: Path | str,
    plan: Path | str,
    corpus_directory: Path | str,
    output_directory: Path | str,
) -> dict[str, object]:
    """Run a fresh local Kraken job against a currently inspected corpus."""

    config = load_kraken_training_config(config_path)
    inspected = inspect_consented_training_corpus(plan, corpus_directory)
    corpus = _resolve_local_path(
        corpus_directory,
        role="HTR training corpus directory",
        must_exist=True,
    )
    destination = _resolve_local_path(
        output_directory,
        role="Kraken training output directory",
        must_exist=False,
    )
    if not destination.parent.is_dir():
        raise KrakenTrainingError(
            f"Kraken training output parent does not exist: {destination.parent}"
        )
    if destination.exists():
        raise KrakenTrainingError(
            f"Kraken training output directory already exists: {destination}"
        )
    if destination == corpus or corpus in destination.parents:
        raise KrakenTrainingError("Kraken training output must be outside the inspected corpus")

    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    moved = False
    try:
        checkpoints = temporary / "checkpoints"
        experiment = temporary / "experiment.yml"
        _write_text(
            experiment,
            _experiment_yaml(config, corpus=corpus, checkpoint_directory=checkpoints),
        )
        command = [str(config.executable), "--config", str(experiment), "train"]
        try:
            completed = subprocess.run(
                command,
                cwd=corpus,
                env=_safe_environment(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=config.runtime["timeout_seconds"],
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise KrakenTrainingError("local Kraken training timed out") from error
        _write_text(temporary / "stdout.log", completed.stdout)
        _write_text(temporary / "stderr.log", completed.stderr)
        if completed.returncode != 0:
            raise KrakenTrainingError(
                f"local Kraken training failed with exit code {completed.returncode}"
            )
        artifacts = (
            [
                path
                for path in sorted(checkpoints.rglob("*.safetensors"))
                if path.is_file()
            ]
            if checkpoints.is_dir()
            else []
        )
        if not artifacts:
            raise KrakenTrainingError(
                "local Kraken training completed without a safetensors weights artifact"
            )
        artifact_receipts = [
            {
                "path": path.relative_to(temporary).as_posix(),
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in artifacts
        ]
        receipt = {
            "contract": {"name": "aktreader-local-kraken-training-run", "version": "1.0.0"},
            "config_sha256": config.config_sha256,
            "ketos_executable_sha256": config.executable_sha256,
            "runtime": config.runtime,
            "train": config.train,
            "corpus_manifest_sha256": inspected["corpus_manifest_sha256"],
            "source_plan_sha256": inspected["source_plan_sha256"],
            "command": ["ketos", "--config", "experiment.yml", "train"],
            "outputs": artifact_receipts,
            "stdout_sha256": _sha256_file(temporary / "stdout.log"),
            "stderr_sha256": _sha256_file(temporary / "stderr.log"),
            "network_required": False,
        }
        _write_text(
            temporary / "training-run.aktreader.json",
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        )
        receipt_sha256 = _sha256_file(temporary / "training-run.aktreader.json")
        os.replace(temporary, destination)
        moved = True
    finally:
        if not moved and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)

    return {
        "status": "SUCCEEDED",
        "output": str(destination),
        "receipt": str(destination / "training-run.aktreader.json"),
        "receipt_sha256": receipt_sha256,
        "weights": [
            str(destination / artifact["path"])
            for artifact in artifact_receipts
        ],
        "network_required": False,
    }
