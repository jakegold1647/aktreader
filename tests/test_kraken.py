from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

import aktreader.kraken as kraken_module
from aktreader.kraken import (
    KrakenArtifactError,
    KrakenConfig,
    KrakenInferenceError,
    KrakenOutputError,
    LocalKraken,
)
from aktreader.local_reader import PinnedArtifact, sha256_file


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def _pin(path: Path) -> PinnedArtifact:
    return PinnedArtifact(path=path, sha256=sha256_file(path))


def _config(tmp_path: Path) -> KrakenConfig:
    executable = _write(tmp_path / "kraken.exe", b"pinned kraken executable")
    model = _write(tmp_path / "cyrillic.safetensors", b"pinned recognition model")
    return KrakenConfig(
        executable=_pin(executable),
        model=_pin(model),
        device="cuda:0",
        precision="bf16-mixed",
        batch_size=8,
        timeout_seconds=60,
    )


def _pagexml(text: str = "") -> bytes:
    return (
        "<PcGts><Page imageFilename=\"page.png\" imageWidth=\"40\" imageHeight=\"30\">"
        "<TextRegion id=\"region-1\"><TextLine id=\"line-1\">"
        f"<TextEquiv><Unicode>{text}</Unicode></TextEquiv>"
        "</TextLine></TextRegion></Page></PcGts>"
    ).encode("utf-8")


def _mock_success(monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        input_index = command.index("-i")
        output = Path(command[input_index + 2])
        output.write_bytes(_pagexml("Гольдштейн"))
        return subprocess.CompletedProcess(command, 0, "local stdout", "local stderr")

    monkeypatch.setattr(kraken_module.subprocess, "run", fake_run)


def test_recognition_uses_only_pinned_local_paths_and_atomic_pagexml_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    source = _write(tmp_path / "input.page.xml", _pagexml())
    output = tmp_path / "recognized.page.xml"
    captured: dict[str, Any] = {}
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-cross-process-boundary")
    _mock_success(monkeypatch, captured)

    result = LocalKraken(config).recognize_pagexml(source, output)

    command = captured["command"]
    kwargs = captured["kwargs"]
    assert command[0] == str(config.executable.path)
    assert command[command.index("-x")] == "-x"
    assert command[command.index("--device") + 1] == "cuda:0"
    assert command[command.index("--precision") + 1] == "bf16-mixed"
    assert command[command.index("-f") + 1] == "xml"
    assert command[command.index("-i") + 1] == str(source)
    assert command[command.index("ocr") + 1] == "-m"
    assert command[command.index("-m") + 1] == str(config.model.path)
    assert command[command.index("-B") + 1] == "8"
    assert all("http://" not in item and "https://" not in item for item in command)
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert "OPENAI_API_KEY" not in kwargs["env"]
    assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
    assert output.read_bytes() == _pagexml("Гольдштейн")
    assert result.source_sha256 == sha256_file(source)
    assert result.output_sha256 == sha256_file(output)
    assert result.runtime_fingerprint
    assert result.fingerprint_manifest["output_sha256"] == result.output_sha256


def test_recognition_refuses_changed_artifacts_and_existing_output(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.model.path.write_bytes(b"changed after checksum pin")

    with pytest.raises(KrakenArtifactError, match="model checksum mismatch"):
        LocalKraken(config)

    source = _write(tmp_path / "input.page.xml", _pagexml())
    output = _write(tmp_path / "recognized.page.xml", _pagexml())

    with pytest.raises(KrakenOutputError, match="already exists"):
        LocalKraken(
            KrakenConfig(executable=config.executable, model=_pin(config.model.path))
        ).recognize_pagexml(source, output)


def test_recognition_rejects_invalid_output_and_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    source = _write(tmp_path / "input.page.xml", _pagexml())
    output = tmp_path / "recognized.page.xml"

    def invalid_output(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        output_index = command.index("-i") + 2
        Path(command[output_index]).write_text("not XML", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(kraken_module.subprocess, "run", invalid_output)
    with pytest.raises(KrakenOutputError, match="not well-formed XML"):
        LocalKraken(config).recognize_pagexml(source, output)
    assert not output.exists()

    def timeout(*_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired("kraken", 60, output=b"partial", stderr=b"slow")

    monkeypatch.setattr(kraken_module.subprocess, "run", timeout)
    with pytest.raises(KrakenInferenceError, match="timed out"):
        LocalKraken(config).recognize_pagexml(source, output)


@pytest.mark.parametrize(
    ("device", "precision"),
    [("localhost", "32"), ("cuda:-1", "32"), ("cpu", "half")],
)
def test_config_rejects_unapproved_runtime_arguments(device: str, precision: str) -> None:
    pin = PinnedArtifact(Path("/tmp/kraken"), "0" * 64)

    with pytest.raises(ValueError):
        KrakenConfig(executable=pin, model=pin, device=device, precision=precision)
