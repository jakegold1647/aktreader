from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import aktreader.kraken_training as training


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_evaluation_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    executable = tmp_path / "ketos"
    executable.write_bytes(b"pinned local ketos")
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "test.lst").write_text("data/test/document.page.xml\n", encoding="utf-8")

    training_run = tmp_path / "training-run"
    model = training_run / "checkpoints" / "model.safetensors"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"trained weights")
    (training_run / "training-run.aktreader.json").write_text(
        json.dumps(
            {
                "contract": {
                    "name": "aktreader-local-kraken-training-run",
                    "version": "1.0.0",
                },
                "config_sha256": "c" * 64,
                "ketos_executable_sha256": _sha256(executable),
                "runtime": {},
                "train": {},
                "corpus_manifest_sha256": "a" * 64,
                "source_plan_sha256": "b" * 64,
                "command": ["ketos", "--config", "experiment.yml", "train"],
                "outputs": [
                    {
                        "path": "checkpoints/model.safetensors",
                        "sha256": _sha256(model),
                        "size_bytes": model.stat().st_size,
                    }
                ],
                "stdout_sha256": "d" * 64,
                "stderr_sha256": "e" * 64,
                "network_required": False,
            }
        ),
        encoding="utf-8",
    )
    config = tmp_path / "evaluation.json"
    config.write_text(
        json.dumps(
            {
                "contract": {
                    "name": "aktreader-local-kraken-evaluation",
                    "version": "1.0.0",
                },
                "ketos": {"path": str(executable), "sha256": _sha256(executable)},
                "model": {"path": str(model), "sha256": _sha256(model)},
                "runtime": {"timeout_seconds": 60},
                "test": {
                    "format_type": "xml",
                    "batch_size": 1,
                    "normalization": "NFC",
                    "normalize_whitespace": True,
                },
            }
        ),
        encoding="utf-8",
    )
    plan = tmp_path / "plan.json"
    plan.write_text("{}", encoding="utf-8")
    return executable, config, plan, corpus, training_run


def test_evaluation_uses_receipted_model_and_writes_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable, config, plan, corpus, training_run = _write_evaluation_inputs(tmp_path)
    output = tmp_path / "evaluation-run"
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        training,
        "inspect_consented_training_corpus",
        lambda _plan, _corpus: {
            "corpus_manifest_sha256": "a" * 64,
            "source_plan_sha256": "b" * 64,
            "split_pagexml_counts": {"train": 1, "validation": 1, "test": 1},
        },
    )

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "CER: 0.25\n", "")

    monkeypatch.setattr(training.subprocess, "run", fake_run)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-cross-process-boundary")

    report = training.run_kraken_evaluation(
        config,
        plan,
        corpus,
        training_run,
        output,
    )

    receipt = json.loads(
        (output / "evaluation-run.aktreader.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "SUCCEEDED"
    assert captured["command"][0] == str(executable)
    assert captured["command"][1:5] == ["test", "-f", "xml", "-e"]
    assert captured["command"][5] == str(corpus / "test.lst")
    assert captured["command"][6:8] == ["-m", str(training_run / "checkpoints" / "model.safetensors")]
    assert captured["kwargs"]["cwd"] == corpus
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL
    assert "OPENAI_API_KEY" not in captured["kwargs"]["env"]
    assert captured["kwargs"]["env"]["HF_HUB_OFFLINE"] == "1"
    assert receipt["model"]["path"] == "checkpoints/model.safetensors"
    assert receipt["test_pagexml_count"] == 1
    assert receipt["command"][-1] == "--normalize-whitespace"
    assert receipt["network_required"] is False
    assert (output / "stdout.log").read_text(encoding="utf-8") == "CER: 0.25\n"


def test_evaluation_requires_a_held_out_test_split(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, config, plan, corpus, training_run = _write_evaluation_inputs(tmp_path)

    monkeypatch.setattr(
        training,
        "inspect_consented_training_corpus",
        lambda _plan, _corpus: {
            "corpus_manifest_sha256": "a" * 64,
            "source_plan_sha256": "b" * 64,
            "split_pagexml_counts": {"train": 1, "validation": 1},
        },
    )

    with pytest.raises(training.KrakenEvaluationError, match="non-empty test split"):
        training.run_kraken_evaluation(
            config,
            plan,
            corpus,
            training_run,
            tmp_path / "evaluation-run",
        )
