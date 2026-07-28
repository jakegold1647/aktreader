import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import aktreader.local_reader as local_reader_module
from aktreader.local_reader import (
    ArtifactValidationError,
    BatchBriefError,
    LocalInferenceError,
    LocalReader,
    LocalReaderConfig,
    LocalReaderOutputError,
    PinnedArtifact,
    sha256_file,
)


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def _pin(path: Path) -> PinnedArtifact:
    return PinnedArtifact(path=path, sha256=sha256_file(path))


def _reader_config(tmp_path: Path, *, with_lora: bool = False) -> LocalReaderConfig:
    executable = _write(tmp_path / "llama-cli.exe", b"pinned llama.cpp executable")
    model = _write(tmp_path / "model.gguf", b"pinned quantized model")
    mmproj = _write(tmp_path / "mmproj.gguf", b"pinned vision projector")
    prompt = _write(tmp_path / "reader_prompt.md", b"pinned reader prompt")
    schema = _write(tmp_path / "reader-label.schema.json", b'{"type":"object"}')
    lora = _write(tmp_path / "aktreader-lora.gguf", b"pinned LoRA") if with_lora else None
    return LocalReaderConfig(
        executable=_pin(executable),
        model=_pin(model),
        mmproj=_pin(mmproj),
        prompt=_pin(prompt),
        schema=_pin(schema),
        lora=_pin(lora) if lora else None,
        timeout_seconds=60,
    )


def _brief(config: LocalReaderConfig, image: Path) -> dict[str, Any]:
    return {
        "label_id": "serock-1888-d31.local-baseline",
        "record_id": "serock-1888-death-31",
        "created_at": "2026-07-28T12:00:00Z",
        "reader": {
            "reader_id": "local-qwen",
            "reader_family": "Qwen3.5-VL",
            "reader_version": "9B-Q5",
            "mode": "local",
            "blind_group_id": "serock-pilot-001",
            "other_reader_output_seen": False,
        },
        "prompt": {
            "version": "1.0.0",
            "sha256": config.prompt.sha256,
            "path": "prompts/reader_prompt.md",
        },
        "clerk_year": {
            "id": "serock-1888",
            "basis": "REGISTER_YEAR_PROXY",
            "clerk_id": None,
        },
        "artifact": {
            "path": "Decode_Package/01_Cyrillic_Serock/scan.jpg",
            "sha256": sha256_file(image),
            "width_px": 1000,
            "height_px": 1500,
            "page_index": 0,
            "act_region": {
                "x": 0,
                "y": 0,
                "width": 1000,
                "height": 1500,
                "coordinate_space": "source_pixels",
            },
        },
        "target": {
            "town": "Serock",
            "fond": "73/826/0",
            "year": 1888,
            "act_type": "death",
            "act_no": 31,
            "language": "ru",
        },
    }


def _payload(brief: dict[str, Any], *, confidence: str | None = "PROBABLE") -> dict[str, Any]:
    if confidence is None:
        observation = {
            "value": None,
            "original_script": None,
            "confidence": None,
            "observation_state": "BLANK",
            "alternatives": [],
            "source_span_ids": ["span-1"],
            "notes": [],
        }
    elif confidence == "UNCLEAR":
        observation = {
            "value": "[unclear: Goldsztejn/Goldfarb]",
            "original_script": "[unclear: Гольдштейнъ/Гольдфарбъ]",
            "confidence": "UNCLEAR",
            "observation_state": "PRESENT",
            "alternatives": [
                {"value": "Goldsztejn", "original_script": "Гольдштейнъ"},
                {"value": "Goldfarb", "original_script": "Гольдфарбъ"},
            ],
            "source_span_ids": ["span-1"],
            "notes": [],
        }
    else:
        observation = {
            "value": "Goldsztejn",
            "original_script": "Гольдштейнъ",
            "confidence": confidence,
            "observation_state": "PRESENT",
            "alternatives": [],
            "source_span_ids": ["span-1"],
            "notes": [],
        }

    return {
        "$schema": "https://aktreader.org/schema/reader-label-1.0.0.json",
        "schema_version": "1.0.0",
        **brief,
        "source_spans": {
            "span-1": {
                "bbox": {
                    "x": 10,
                    "y": 20,
                    "width": 30,
                    "height": 40,
                    "coordinate_space": "source_pixels",
                },
                "description": "surname",
            }
        },
        "mentions": [],
        "transcription": {
            "original_script": "Гольдштейнъ",
            "translation": "Goldsztejn",
        },
        "observations": {"principal.name": observation},
        "compliance": {
            "restricted_sources_used": False,
            "privacy_decision": "ALLOW",
            "privacy_basis": "death act older than 80 years",
            "training_eligible": False,
            "training_basis": "consent not recorded",
        },
        "authority_warning": "extraction is not authority — verify against the scan",
    }


def _mock_success(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    captured: dict[str, Any] | None = None,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if captured is not None:
            captured["command"] = command
            captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr="local diagnostics",
        )

    monkeypatch.setattr(local_reader_module.subprocess, "run", fake_run)


def _mock_chromed_stdout(
    monkeypatch: pytest.MonkeyPatch,
    completion: str,
    *,
    banner: str = "",
    line_ending: str = "\n",
) -> None:
    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        request = command[command.index("--prompt") + 1]
        echoed_request = request.replace("\n", line_ending)
        normalized_banner = banner.replace("\n", line_ending)
        stdout = (
            normalized_banner
            + f"> {echoed_request}{line_ending}"
            + completion
            + line_ending
            + "Exiting..."
            + line_ending
        )
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(local_reader_module.subprocess, "run", fake_run)


def _mock_stdout(monkeypatch: pytest.MonkeyPatch, stdout: str) -> None:
    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(local_reader_module.subprocess, "run", fake_run)


def test_constructor_fails_closed_on_missing_or_changed_artifact(tmp_path: Path) -> None:
    config = _reader_config(tmp_path)
    config.model.path.write_bytes(b"changed after checksum pin")

    with pytest.raises(ArtifactValidationError, match="model checksum mismatch"):
        LocalReader(config)

    relative_config = LocalReaderConfig(
        executable=PinnedArtifact(Path("llama-cli.exe"), "0" * 64),
        model=config.model,
        mmproj=config.mmproj,
        prompt=config.prompt,
        schema=config.schema,
    )
    with pytest.raises(ArtifactValidationError, match="path must be absolute"):
        LocalReader(relative_config)


def test_constructor_rejects_external_schema_refs(tmp_path: Path) -> None:
    config = _reader_config(tmp_path)
    schema_path = config.schema.path
    schema_path.write_text(
        '{"type":"object","properties":{"x":{"$ref":"https://example.invalid/schema"}}}',
        encoding="utf-8",
    )
    config = LocalReaderConfig(
        executable=config.executable,
        model=config.model,
        mmproj=config.mmproj,
        prompt=config.prompt,
        schema=_pin(schema_path),
    )

    with pytest.raises(ArtifactValidationError, match=r"external \$ref"):
        LocalReader(config)


def test_local_command_is_deterministic_keyless_and_path_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _reader_config(tmp_path)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    payload = _payload(brief)
    captured: dict[str, Any] = {}
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-cross-process-boundary")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-cross-process-boundary")
    _mock_success(monkeypatch, payload, captured)

    result = LocalReader(config).read(image, batch_brief=brief)

    command = captured["command"]
    kwargs = captured["kwargs"]
    assert command[0] == str(config.executable.path)
    assert command[command.index("-m") + 1] == str(config.model.path)
    assert command[command.index("-mm") + 1] == str(config.mmproj.path)
    assert command[command.index("--image") + 1] == str(image)
    assert command[command.index("--temp") + 1] == "0"
    assert command[command.index("--top-k") + 1] == "1"
    assert command[command.index("--reasoning") + 1] == "off"
    assert "-hf" not in command
    assert "--model-url" not in command
    assert all("http://" not in item and "https://" not in item for item in command)
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert "OPENAI_API_KEY" not in kwargs["env"]
    assert "ANTHROPIC_API_KEY" not in kwargs["env"]
    assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
    assert result.payload == payload
    assert result.stderr == "local diagnostics"


@pytest.mark.parametrize("confidence", ["PROBABLE", "UNCLEAR", None])
def test_single_reader_accepts_only_honest_confidence_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, confidence: str | None
) -> None:
    config = _reader_config(tmp_path)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    _mock_success(monkeypatch, _payload(brief, confidence=confidence))

    result = LocalReader(config).read(image, batch_brief=brief)

    assert result.payload["observations"]["principal.name"]["confidence"] == confidence


def test_single_reader_rejects_confident_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _reader_config(tmp_path)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    _mock_success(monkeypatch, _payload(brief, confidence="CONFIDENT"))

    with pytest.raises(LocalReaderOutputError, match="cannot be 'CONFIDENT'"):
        LocalReader(config).read(image, batch_brief=brief)


def test_reader_output_must_validate_against_the_pinned_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _reader_config(tmp_path)
    schema_path = config.schema.path
    schema_path.write_text(
        '{"type":"object","required":["schema-only-sentinel"]}',
        encoding="utf-8",
    )
    config = LocalReaderConfig(
        executable=config.executable,
        model=config.model,
        mmproj=config.mmproj,
        prompt=config.prompt,
        schema=_pin(schema_path),
    )
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    _mock_success(monkeypatch, _payload(brief))

    with pytest.raises(LocalReaderOutputError, match="pinned JSON schema"):
        LocalReader(config).read(image, batch_brief=brief)


@pytest.mark.parametrize(
    "stdout",
    [
        '{"observations": {}} trailing prose',
        '[{"observations": {}}]',
        '{"observations":{},"observations":{}}',
        '{"observations":{},"value":NaN}',
    ],
)
def test_reader_requires_exactly_one_strict_json_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stdout: str
) -> None:
    config = _reader_config(tmp_path)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(local_reader_module.subprocess, "run", fake_run)

    with pytest.raises(LocalReaderOutputError):
        LocalReader(config).read(image, batch_brief=brief)


def test_reader_extracts_json_after_exact_multiline_prompt_echo_and_runtime_chrome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _reader_config(tmp_path)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    payload = _payload(brief)
    _mock_chromed_stdout(
        monkeypatch,
        json.dumps(payload, ensure_ascii=False),
        banner=(
            "llama.cpp build 10167\n"
            '{"banner_diagnostic":{"cuda":true}}\n'
            "available commands: /exit\n"
        ),
        line_ending="\r\n",
    )

    result = LocalReader(config).read(image, batch_brief=brief)

    assert result.payload == payload


def test_reader_stdout_scan_is_string_and_escape_aware(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _reader_config(tmp_path)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    payload = _payload(brief)
    payload["transcription"]["translation"] = (
        'literal braces { and }, an escaped quote " and a backslash \\'
    )
    _mock_chromed_stdout(monkeypatch, json.dumps(payload, ensure_ascii=False))

    result = LocalReader(config).read(image, batch_brief=brief)

    assert result.payload == payload


@pytest.mark.parametrize("position", ["before", "after"])
def test_reader_stdout_rejects_model_prose_outside_the_json_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    position: str,
) -> None:
    config = _reader_config(tmp_path)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    payload = json.dumps(_payload(brief), ensure_ascii=False)
    completion = f"model preface\n{payload}" if position == "before" else f"{payload}\ncommentary"
    _mock_chromed_stdout(monkeypatch, completion)

    with pytest.raises(LocalReaderOutputError, match="non-whitespace text outside"):
        LocalReader(config).read(image, batch_brief=brief)


def test_reader_stdout_accepts_only_whitespace_around_json_and_known_trailer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _reader_config(tmp_path)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    payload = _payload(brief)
    completion = f"\n \t{json.dumps(payload, ensure_ascii=False)}\n  "
    _mock_chromed_stdout(monkeypatch, completion)

    assert LocalReader(config).read(image, batch_brief=brief).payload == payload


@pytest.mark.parametrize(
    ("completion", "observed"),
    [
        ("ordinary prose only", 0),
        ('{}\n{"second":true}', 2),
    ],
)
def test_reader_stdout_rejects_zero_or_multiple_post_echo_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    completion: str,
    observed: int,
) -> None:
    config = _reader_config(tmp_path)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    _mock_chromed_stdout(monkeypatch, completion)

    with pytest.raises(
        LocalReaderOutputError,
        match=rf"exactly one balanced top-level JSON object.*observed {observed}",
    ):
        LocalReader(config).read(image, batch_brief=brief)


@pytest.mark.parametrize(
    ("completion", "message"),
    [
        ('{"broken": tru}', "exactly one JSON object"),
        ('{"broken":{"nested":true}', "unbalanced JSON object"),
        ('{"broken":{"nested":true}]}', "exactly one JSON object"),
        ("unexpected }", "unmatched closing brace"),
        ('[{"looks":"object-like"}]', "top-level array"),
        ('{"duplicate":1,"duplicate":2}', "duplicate JSON key"),
        ('{"value":NaN}', "non-standard JSON number"),
    ],
)
def test_reader_stdout_rejects_malformed_non_object_or_unbalanced_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    completion: str,
    message: str,
) -> None:
    config = _reader_config(tmp_path)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    _mock_chromed_stdout(monkeypatch, completion)

    with pytest.raises(LocalReaderOutputError, match=message):
        LocalReader(config).read(image, batch_brief=brief)


def test_reader_stdout_rejects_a_nonmatching_prompt_echo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _reader_config(tmp_path)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    payload = json.dumps(_payload(brief), ensure_ascii=False)
    _mock_stdout(monkeypatch, f"> a different request\n{payload}\nExiting...\n")

    with pytest.raises(LocalReaderOutputError, match="does not exactly match"):
        LocalReader(config).read(image, batch_brief=brief)


def test_reader_preserves_direct_json_stdout_compatibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _reader_config(tmp_path)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    payload = _payload(brief)
    _mock_stdout(monkeypatch, f" \n{json.dumps(payload, ensure_ascii=False)}\n\t")

    assert LocalReader(config).read(image, batch_brief=brief).payload == payload


def test_blind_brief_rejects_reader_output_and_wrong_hashes(tmp_path: Path) -> None:
    config = _reader_config(tmp_path)
    reader = LocalReader(config)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    brief["observations"] = {"father.name": "leaked prior output"}

    with pytest.raises(BatchBriefError, match="prior Reader output"):
        reader.read(image, batch_brief=brief)

    brief = _brief(config, image)
    brief["artifact"]["sha256"] = "0" * 64
    with pytest.raises(BatchBriefError, match="artifact SHA-256"):
        reader.read(image, batch_brief=brief)


def test_runtime_failure_surfaces_bounded_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _reader_config(tmp_path)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 7, "", "CUDA allocation failed")

    monkeypatch.setattr(local_reader_module.subprocess, "run", fake_run)

    with pytest.raises(LocalInferenceError, match="code 7: CUDA allocation failed"):
        LocalReader(config).read(image, batch_brief=brief)


def test_fingerprint_is_stable_content_based_and_includes_optional_lora(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _reader_config(tmp_path, with_lora=True)
    image = _write(tmp_path / "scan.jpg", b"scan pixels")
    brief = _brief(config, image)
    payload = _payload(brief)
    captured: dict[str, Any] = {}
    _mock_success(monkeypatch, payload, captured)
    reader = LocalReader(config)

    first = reader.read(image, batch_brief=copy.deepcopy(brief))
    second = reader.read(image, batch_brief=copy.deepcopy(brief))

    assert first.inference_fingerprint == second.inference_fingerprint
    assert first.fingerprint_manifest == second.fingerprint_manifest
    assert first.fingerprint_manifest["artifacts"]["lora"] == config.lora.sha256
    assert captured["command"][captured["command"].index("--lora") + 1] == str(config.lora.path)
    assert len(reader.runtime_fingerprint) == 64
    assert len(first.inference_fingerprint) == 64
