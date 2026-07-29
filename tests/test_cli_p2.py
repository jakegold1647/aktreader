import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import aktreader.cli as cli_module
import aktreader.local_reader as local_reader_module
from aktreader.cli import main
from aktreader.checkpoint import CheckpointStore, JobStatus
from aktreader.local_reader import LocalInferenceError
from aktreader.cli_support import load_local_reader_config

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reader_config(tmp_path: Path) -> Path:
    contents = {
        "llama-mtmd-cli.exe": b"test executable",
        "model.gguf": b"test model",
        "mmproj.gguf": b"test projector",
        "reader_prompt.md": b"test prompt",
        "reader-label.schema.json": b'{"type":"object"}',
        "model-output.schema.json": b'{"type":"object"}',
    }
    paths = {}
    for name, content in contents.items():
        path = tmp_path / name
        path.write_bytes(content)
        paths[name] = path
    config = {
        "schema_version": "1.0.0",
        "artifacts": {
            "executable": {
                "path": "llama-mtmd-cli.exe",
                "sha256": _sha256(paths["llama-mtmd-cli.exe"]),
            },
            "model": {"path": "model.gguf", "sha256": _sha256(paths["model.gguf"])},
            "mmproj": {"path": "mmproj.gguf", "sha256": _sha256(paths["mmproj.gguf"])},
            "prompt": {
                "path": "reader_prompt.md",
                "sha256": _sha256(paths["reader_prompt.md"]),
            },
            "schema": {
                "path": "reader-label.schema.json",
                "sha256": _sha256(paths["reader-label.schema.json"]),
            },
            "model_schema": {
                "path": "model-output.schema.json",
                "sha256": _sha256(paths["model-output.schema.json"]),
            },
        },
        "generation": {"seed": 0, "gpu_layers": "all", "timeout_seconds": 60},
    }
    path = tmp_path / "reader-config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


class FakeLocalReader:
    reads: list[tuple[Path, dict[str, Any]]] = []
    failure: LocalInferenceError | None = None

    def __init__(self, config: Any) -> None:
        self.config = config
        self.runtime_fingerprint = "f" * 64
        pins = {
            "executable": config.executable,
            "model": config.model,
            "mmproj": config.mmproj,
            "prompt": config.prompt,
            "schema": config.schema,
            "model_schema": config.model_schema,
        }
        if config.lora is not None:
            pins["lora"] = config.lora
        self.artifact_hashes = {key: pin.sha256 for key, pin in pins.items()}

    def read(self, image_path: Path, *, batch_brief: dict[str, Any]) -> Any:
        self.reads.append((Path(image_path), batch_brief))
        if self.failure is not None:
            raise self.failure
        return SimpleNamespace(
            payload={
                "record_id": batch_brief.get("record_id", "test-record"),
                "observations": {},
            },
            inference_fingerprint="e" * 64,
            stderr="",
        )


@pytest.fixture(autouse=True)
def forbid_real_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeLocalReader.reads = []

    def forbidden_subprocess(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("CLI tests must never launch the local runtime")
    FakeLocalReader.failure = None

    monkeypatch.setattr(local_reader_module.subprocess, "run", forbidden_subprocess)


def test_config_loader_resolves_relative_pins_without_running_executable(tmp_path: Path) -> None:
    config_path = _reader_config(tmp_path)

    config = load_local_reader_config(config_path)

    assert config.executable.path == (tmp_path / "llama-mtmd-cli.exe").resolve()
    assert config.model.path == (tmp_path / "model.gguf").resolve()
    assert config.seed == 0
    assert config.gpu_layers == "all"


def test_example_reader_config_is_local_only_and_marks_every_digest_for_replacement() -> None:
    example = json.loads(
        (ROOT / "examples" / "local-reader.config.example.json").read_text(encoding="utf-8")
    )

    assert example["schema_version"] == "1.0.0"
    assert set(example["artifacts"]) == {
        "executable",
        "model",
        "mmproj",
        "prompt",
        "schema",
        "model_schema",
    }
    for artifact in example["artifacts"].values():
        assert "://" not in artifact["path"]
        assert not artifact["path"].startswith(("\\\\", "//"))
        assert re.fullmatch(r"[a-f0-9]{64}", artifact["sha256"])
        assert len(set(artifact["sha256"])) == 1


def test_reader_inspect_and_infer_use_injected_local_reader_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _reader_config(tmp_path)
    monkeypatch.setattr(cli_module, "LocalReader", FakeLocalReader)

    assert main(["reader-inspect", "--config", str(config)]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["reader"] == "LOCAL_OPEN_WEIGHTS_ONLY"
    assert inspection["network_required"] is False
    assert FakeLocalReader.reads == []

    scan = tmp_path / "scan.jpg"
    scan.write_bytes(b"pixels")
    brief = tmp_path / "brief.json"
    brief.write_text(json.dumps({"record_id": "one", "target": {}}), encoding="utf-8")
    output = tmp_path / "output.json"
    assert (
        main(
            [
                "reader-infer",
                "--config",
                str(config),
                "--scan",
                str(scan),
                "--brief",
                str(brief),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    inference = json.loads(capsys.readouterr().out)
    assert inference["status"] == "SUCCEEDED"
    assert json.loads(output.read_text(encoding="utf-8"))["record_id"] == "one"
    assert [item[0] for item in FakeLocalReader.reads] == [scan]


def test_consensus_merge_uses_only_two_explicit_labels_and_refuses_implicit_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_path = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    left = json.loads(json.dumps(source))
    right = json.loads(json.dumps(source))
    left["label_id"] = "synthetic.reader-claude"
    left["reader"].update(
        {
            "reader_id": "synthetic-claude",
            "reader_family": "claude",
            "reader_version": "test-claude",
        }
    )
    right["label_id"] = "synthetic.reader-gpt"
    right["reader"].update(
        {
            "reader_id": "synthetic-gpt",
            "reader_family": "gpt",
            "reader_version": "test-gpt",
        }
    )
    left_path = tmp_path / "left.json"
    right_path = tmp_path / "right.json"
    left_path.write_text(json.dumps(left, ensure_ascii=False), encoding="utf-8")
    right_path.write_text(json.dumps(right, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "consensus.json"
    command = [
        "consensus-merge",
        str(left_path),
        str(right_path),
        "--output",
        str(output),
    ]

    assert main(command) == 0
    summary = json.loads(capsys.readouterr().out)
    record = json.loads(output.read_text(encoding="utf-8"))
    assert summary["status"] == "SUCCEEDED"
    assert summary["source_label_ids"] == [
        "synthetic.reader-claude",
        "synthetic.reader-gpt",
    ]
    assert record["record_kind"] == "DUAL_READER_CONSENSUS"
    assert record["schema_version"] == "2.0.0"
    assert [
        item["label_id"] for item in record["derivation"]["source_labels"]
    ] == summary["source_label_ids"]

    before = output.read_bytes()
    assert main(command) == 2
    assert "already exists" in capsys.readouterr().err
    assert output.read_bytes() == before


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update({"api_key": "forbidden"}),
        lambda payload: payload.update({"openai_api_key": "forbidden"}),
        lambda payload: payload["generation"].update({"context_size": True}),
        lambda payload: payload["artifacts"]["model"].update(
            {"path": "https://example.invalid/model.gguf"}
        ),
    ],
)
def test_reader_config_rejects_credentials_and_urls_before_reader_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mutation: Any,
) -> None:
    config = _reader_config(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    mutation(payload)
    config.write_text(json.dumps(payload), encoding="utf-8")

    def forbidden_reader(config: Any) -> None:
        raise AssertionError("invalid config reached LocalReader")

    monkeypatch.setattr(cli_module, "LocalReader", forbidden_reader)
    assert main(["reader-inspect", "--config", str(config)]) == 2
    assert "aktreader: error:" in capsys.readouterr().err.lower()


def test_batch_run_resumes_without_rerunning_matching_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _reader_config(tmp_path)
    monkeypatch.setattr(cli_module, "LocalReader", FakeLocalReader)
    scan = tmp_path / "scan.jpg"
    scan.write_bytes(b"pixels")
    brief = {
        "record_id": "serock-1900-death-1",
        "target": {"act_type": "death", "year": 1900, "act_no": 1},
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "one",
                        "scan": "scan.jpg",
                        "act_type": "death",
                        "year": 1900,
                        "target": {"kind": "act", "act_no": 1},
                        "metadata": {"batch_brief": brief},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    checkpoint = tmp_path / "run.sqlite3"
    output_dir = tmp_path / "outputs"
    command = [
        "batch-run",
        "--config",
        str(config),
        "--manifest",
        str(manifest),
        "--checkpoint",
        str(checkpoint),
        "--output-dir",
        str(output_dir),
        "--as-of-year",
        "2026",
    ]

    assert main(command) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["progress"]["succeeded"] == 1
    assert len(FakeLocalReader.reads) == 1
    assert main(command) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["progress"]["succeeded"] == 1
    assert len(FakeLocalReader.reads) == 1
    assert json.loads((output_dir / "one.json").read_text(encoding="utf-8"))[
        "record_id"
    ] == "serock-1900-death-1"


def test_batch_rebind_opt_in_preserves_failed_retry_count_without_spending_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _reader_config(tmp_path)
    monkeypatch.setattr(cli_module, "LocalReader", FakeLocalReader)
    scan = tmp_path / "scan.jpg"
    scan.write_bytes(b"pixels")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "one",
                        "scan": "scan.jpg",
                        "act_type": "death",
                        "year": 1900,
                        "target": {"kind": "act", "act_no": 1},
                        "metadata": {
                            "batch_brief": {
                                "record_id": "serock-1900-death-1",
                                "target": {
                                    "act_type": "death",
                                    "year": 1900,
                                    "act_no": 1,
                                },
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    checkpoint = tmp_path / "run.sqlite3"
    output_dir = tmp_path / "outputs"
    store = CheckpointStore(checkpoint)
    store.upsert_job(
        job_id="one",
        fingerprint="pre-mtmd-fingerprint",
        scan_path=str(scan),
        output_path=str(output_dir / "one.json"),
        job_json="{}",
    )
    for attempt in range(3):
        assert store.claim_job("one", "pre-mtmd-fingerprint", max_retries=2)
        store.finish_running("one", JobStatus.FAILED, error=f"failed attempt {attempt + 1}")
    assert store.get_job("one").retry_count == 2

    result = main(
        [
            "batch-run",
            "--config",
            str(config),
            "--manifest",
            str(manifest),
            "--checkpoint",
            str(checkpoint),
            "--output-dir",
            str(output_dir),
            "--as-of-year",
            "2026",
            "--max-retries",
            "2",
            "--rebind-failed-fingerprints",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert result == 1
    assert report["failed_fingerprint_rebind"] == "enabled"
    rebound = CheckpointStore(checkpoint).get_job("one")
    assert rebound.status is JobStatus.FAILED
    assert rebound.retry_count == 2
    assert FakeLocalReader.reads == []
    events = CheckpointStore(checkpoint).list_fingerprint_rebind_events()
    assert len(events) == 1
    assert events[0].old_fingerprint == "pre-mtmd-fingerprint"
    assert events[0].new_fingerprint == rebound.fingerprint
    assert events[0].retry_count == 2


def test_batch_failure_persists_raw_runtime_streams_and_records_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _reader_config(tmp_path)
    monkeypatch.setattr(cli_module, "LocalReader", FakeLocalReader)
    FakeLocalReader.failure = LocalInferenceError(
        "sampler initialization failed",
        stdout="raw stdout including prompt chrome",
        stderr="Unexpected empty grammar stack",
    )
    scan = tmp_path / "scan.jpg"
    scan.write_bytes(b"pixels")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "one",
                        "scan": "scan.jpg",
                        "act_type": "death",
                        "year": 1900,
                        "target": {"kind": "act", "act_no": 1},
                        "metadata": {
                            "batch_brief": {
                                "record_id": "serock-1900-death-1",
                                "target": {
                                    "act_type": "death",
                                    "year": 1900,
                                    "act_no": 1,
                                },
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    checkpoint = tmp_path / "run.sqlite3"
    output_dir = tmp_path / "outputs"
    result = main(
        [
            "batch-run",
            "--config",
            str(config),
            "--manifest",
            str(manifest),
            "--checkpoint",
            str(checkpoint),
            "--output-dir",
            str(output_dir),
            "--as-of-year",
            "2026",
        ]
    )
    capsys.readouterr()

    assert result == 1
    stdout_path = output_dir / "one.failed.stdout.txt"
    stderr_path = output_dir / "one.failed.stderr.txt"
    assert stdout_path.read_text(encoding="utf-8") == "raw stdout including prompt chrome"
    assert stderr_path.read_text(encoding="utf-8") == "Unexpected empty grammar stack"
    error = CheckpointStore(checkpoint).get_job("one").error or ""
    assert f"raw_stdout={stdout_path}" in error
    assert f"raw_stderr={stderr_path}" in error


def test_eval_writes_real_holdout_guarded_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = Path(__file__).resolve().parents[1]
    first_path = sorted((root / "gold" / "acts").glob("*.json"))[0]
    first_gold = json.loads(first_path.read_text(encoding="utf-8"))
    prediction = tmp_path / "prediction.json"
    prediction.write_text(
        json.dumps({"record_id": first_gold["record_id"], "observations": {}}),
        encoding="utf-8",
    )
    output = tmp_path / "eval.json"

    assert main(["eval", "--predictions", str(prediction), "--output", str(output)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["benchmark"] == "SerockBench-v1"
    assert report["holdout_integrity"]["status"] == "PASS"
    assert json.loads(output.read_text(encoding="utf-8")) == report
