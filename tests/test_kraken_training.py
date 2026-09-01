from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import aktreader.kraken_training as training


def _write_config(tmp_path: Path) -> tuple[Path, Path]:
    executable = tmp_path / "ketos"
    executable.write_bytes(b"pinned local ketos")
    config = tmp_path / "training.json"
    config.write_text(
        json.dumps(
            {
                "contract": {
                    "name": "aktreader-local-kraken-training",
                    "version": "1.0.0",
                },
                "ketos": {
                    "path": str(executable),
                    "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                },
                "runtime": {
                    "device": "cpu",
                    "precision": "32-true",
                    "workers": 0,
                    "threads": 1,
                    "seed": 7,
                    "deterministic": True,
                    "timeout_seconds": 60,
                },
                "train": {
                    "architecture": {
                        "kind": "ppocrv6",
                        "variant": "tiny",
                        "height": 96,
                        "max_width": 2560,
                    },
                    "weights_format": "safetensors",
                    "normalization": "NFC",
                    "normalize_whitespace": True,
                    "quit": "fixed",
                    "epochs": 1,
                    "lag": 1,
                    "lrate": 0.001,
                    "schedule": "constant",
                    "warmup": 0,
                    "augment": False,
                    "batch_size": 1,
                    "accumulate_grad_batches": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    return executable, config


def test_training_uses_pinned_local_ketos_and_writes_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    executable, config = _write_config(tmp_path)
    plan = tmp_path / "plan.json"
    plan.write_text("{}", encoding="utf-8")
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    output = tmp_path / "run"
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        training,
        "inspect_consented_training_corpus",
        lambda _plan, _corpus: {
            "corpus_manifest_sha256": "a" * 64,
            "source_plan_sha256": "b" * 64,
        },
    )

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        experiment = Path(command[2])
        checkpoint_line = next(
            line for line in experiment.read_text(encoding="utf-8").splitlines()
            if line.startswith("  checkpoint_path: ")
        )
        checkpoints = Path(json.loads(checkpoint_line.split(": ", 1)[1]))
        checkpoints.mkdir()
        (checkpoints / "a.safetensors").write_bytes(b"lower")
        (checkpoints / "B.safetensors").write_bytes(b"upper")
        return subprocess.CompletedProcess(command, 0, "trained", "")

    monkeypatch.setattr(training.subprocess, "run", fake_run)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-cross-process-boundary")

    report = training.run_kraken_training(config, plan, corpus, output)

    receipt = json.loads((output / "training-run.aktreader.json").read_text(encoding="utf-8"))
    assert report["status"] == "SUCCEEDED"
    assert captured["command"][0] == str(executable)
    assert captured["command"][1:] == ["--config", captured["command"][2], "train"]
    assert captured["kwargs"]["cwd"] == corpus
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
    assert "OPENAI_API_KEY" not in captured["kwargs"]["env"]
    assert captured["kwargs"]["env"]["HF_HUB_OFFLINE"] == "1"
    assert receipt["ketos_executable_sha256"] == hashlib.sha256(executable.read_bytes()).hexdigest()
    assert receipt["corpus_manifest_sha256"] == "a" * 64
    assert receipt["outputs"] == [
        {
            "path": "checkpoints/B.safetensors",
            "sha256": hashlib.sha256(b"upper").hexdigest(),
            "size_bytes": 5,
        },
        {
            "path": "checkpoints/a.safetensors",
            "sha256": hashlib.sha256(b"lower").hexdigest(),
            "size_bytes": 5,
        },
    ]
