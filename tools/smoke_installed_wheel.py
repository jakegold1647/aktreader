"""Build and exercise the Application wheel outside its source checkout."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _run_raw(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="backslashreplace",
        check=False,
    )


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    result = _run_raw(command, cwd=cwd, env=env)
    if result.returncode != 0:
        rendered = " ".join(command)
        raise RuntimeError(
            f"command failed ({result.returncode}): {rendered}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _json_command(
    python: Path,
    arguments: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    result = _run([str(python), "-m", "aktreader", *arguments], cwd=cwd, env=env)
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError(f"command returned a non-object JSON payload: {arguments}")
    return payload


def _venv_python(environment: Path) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_reader_fixture(root: Path) -> Path:
    artifact_dir = root / "reader-artifacts"
    artifact_dir.mkdir()
    contents = {
        "llama-mtmd-cli.exe": b"wheel-smoke executable",
        "model.gguf": b"wheel-smoke model",
        "mmproj.gguf": b"wheel-smoke projector",
        "reader_prompt.md": b"wheel-smoke prompt",
        "reader-label.schema.json": b'{"type":"object"}',
        "model-output.schema.json": b'{"type":"object"}',
    }
    paths: dict[str, Path] = {}
    for name, content in contents.items():
        path = artifact_dir / name
        path.write_bytes(content)
        paths[name] = path
    config = {
        "schema_version": "1.0.0",
        "artifacts": {
            "executable": {
                "path": str(paths["llama-mtmd-cli.exe"]),
                "sha256": _sha256(paths["llama-mtmd-cli.exe"]),
            },
            "model": {
                "path": str(paths["model.gguf"]),
                "sha256": _sha256(paths["model.gguf"]),
            },
            "mmproj": {
                "path": str(paths["mmproj.gguf"]),
                "sha256": _sha256(paths["mmproj.gguf"]),
            },
            "prompt": {
                "path": str(paths["reader_prompt.md"]),
                "sha256": _sha256(paths["reader_prompt.md"]),
            },
            "schema": {
                "path": str(paths["reader-label.schema.json"]),
                "sha256": _sha256(paths["reader-label.schema.json"]),
            },
            "model_schema": {
                "path": str(paths["model-output.schema.json"]),
                "sha256": _sha256(paths["model-output.schema.json"]),
            },
        },
        "generation": {"seed": 0, "gpu_layers": "all", "timeout_seconds": 60},
    }
    config_path = artifact_dir / "reader-config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


def _write_consensus_fixture(root: Path) -> tuple[Path, Path]:
    source = json.loads(
        (ROOT / "labels" / "readerB" / "serock-1890-death-1.json").read_text(
            encoding="utf-8"
        )
    )
    source["observations"] = {"principal.age": source["observations"]["principal.age"]}
    left = json.loads(json.dumps(source))
    right = json.loads(json.dumps(source))
    left["label_id"] = "wheel-smoke.reader-left"
    left["reader"].update(
        {
            "reader_id": "wheel-smoke-left",
            "reader_family": "wheel-smoke-family-left",
            "reader_version": "test-left",
        }
    )
    right["label_id"] = "wheel-smoke.reader-right"
    right["reader"].update(
        {
            "reader_id": "wheel-smoke-right",
            "reader_family": "wheel-smoke-family-right",
            "reader_version": "test-right",
        }
    )
    left_path = root / "left-label.json"
    right_path = root / "right-label.json"
    left_path.write_text(json.dumps(left, ensure_ascii=False), encoding="utf-8")
    right_path.write_text(json.dumps(right, ensure_ascii=False), encoding="utf-8")
    return left_path, right_path


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aktreader-app-wheel-") as raw_temp:
        temp = Path(raw_temp)
        wheel_dir = temp / "wheel"
        wheel_dir.mkdir()
        clean_env = os.environ.copy()
        clean_env.pop("PYTHONPATH", None)

        explicit_inputs = temp / "explicit-inputs"
        explicit_inputs.mkdir()
        gold_dir = explicit_inputs / "gold"
        shutil.copytree(ROOT / "gold" / "acts", gold_dir)
        holdout = explicit_inputs / "clerk-year-holdout.json"
        shutil.copy2(ROOT / "gold" / "clerk_year_holdout.json", holdout)
        first_gold_path = sorted(gold_dir.glob("*.json"))[0]
        first_gold = json.loads(first_gold_path.read_text(encoding="utf-8"))
        prediction = explicit_inputs / "prediction.json"
        prediction.write_text(
            json.dumps({"record_id": first_gold["record_id"], "observations": {}}),
            encoding="utf-8",
        )
        reader_config = _write_reader_fixture(explicit_inputs)
        left_label, right_label = _write_consensus_fixture(explicit_inputs)

        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--disable-pip-version-check",
                "--no-deps",
                "--wheel-dir",
                str(wheel_dir),
                str(ROOT),
            ],
            cwd=temp,
            env=clean_env,
        )
        wheels = list(wheel_dir.glob("aktreader_app-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected one Application wheel, found {len(wheels)}")
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
        expected_runtime_assets = {
            "aktreader/assets/schemas/act-record-2.0.0.schema.json",
            "aktreader/assets/schemas/model-output-1.0.0.schema.json",
            "aktreader/assets/schemas/model-output-to-gold-map-1.0.0.json",
        }
        packaged_runtime_assets = {
            name
            for name in names
            if name.startswith("aktreader/assets/schemas/") and name.endswith(".json")
        }
        if packaged_runtime_assets != expected_runtime_assets:
            raise RuntimeError(
                "wheel runtime assets differ from the explicit package boundary: "
                f"{sorted(packaged_runtime_assets)}"
            )
        forbidden_segments = (
            "/gold/",
            "/labels/",
            "/prompts/",
            "/skills/",
            "/models/",
            "/runtime/",
            "/examples/",
        )
        unexpected = sorted(
            name for name in names if any(segment in f"/{name}" for segment in forbidden_segments)
        )
        if unexpected:
            raise RuntimeError(f"wheel contains excluded project material: {unexpected}")

        environment = temp / "venv"
        _run([sys.executable, "-m", "venv", str(environment)], cwd=temp, env=clean_env)
        python = _venv_python(environment)
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                str(wheel),
            ],
            cwd=temp,
            env=clean_env,
        )

        import_result = _run(
            [
                str(python),
                "-c",
                "import json, aktreader; print(json.dumps({'module_path': aktreader.__file__}))",
            ],
            cwd=temp,
            env=clean_env,
        )
        installed_module = Path(json.loads(import_result.stdout)["module_path"]).resolve()
        if environment.resolve() not in installed_module.parents:
            raise RuntimeError(f"wheel smoke imported outside its fresh venv: {installed_module}")
        if ROOT.resolve() in installed_module.parents:
            raise RuntimeError(f"wheel smoke imported the source checkout: {installed_module}")

        doctor = _json_command(python, ["doctor", "--json"], cwd=temp, env=clean_env)
        if doctor.get("runtime_mode") != "installed-distribution":
            raise RuntimeError(f"doctor did not recognize the wheel install: {doctor}")
        if doctor.get("available_runtime_asset_count") != 3:
            raise RuntimeError(f"doctor did not find all packaged runtime assets: {doctor}")
        if doctor.get("standalone_distribution_ready") is not True:
            raise RuntimeError(f"doctor did not mark the Application wheel ready: {doctor}")
        if doctor.get("source_checkout_verification_available") is not False:
            raise RuntimeError(f"doctor claimed checkout verification from a wheel: {doctor}")

        reader = _json_command(
            python,
            ["reader-inspect", "--config", str(reader_config)],
            cwd=temp,
            env=clean_env,
        )
        if reader.get("reader") != "LOCAL_OPEN_WEIGHTS_ONLY":
            raise RuntimeError(f"installed reader did not inspect explicit artifacts: {reader}")

        consensus_path = temp / "consensus.json"
        consensus = _json_command(
            python,
            [
                "consensus-merge",
                str(left_label),
                str(right_label),
                "--output",
                str(consensus_path),
            ],
            cwd=temp,
            env=clean_env,
        )
        if consensus.get("status") != "SUCCEEDED" or not consensus_path.is_file():
            raise RuntimeError(f"packaged consensus schema was not usable: {consensus}")

        missing_defaults = _run_raw(
            [str(python), "-m", "aktreader", "eval", "--predictions", str(prediction)],
            cwd=temp,
            env=clean_env,
        )
        if missing_defaults.returncode != 2 or (
            "requires --gold-dir and --holdout" not in missing_defaults.stderr
        ):
            raise RuntimeError(
                "installed eval did not require explicit corpus paths:\n"
                f"stdout:\n{missing_defaults.stdout}\nstderr:\n{missing_defaults.stderr}"
            )

        evaluation_path = temp / "evaluation.json"
        evaluation = _json_command(
            python,
            [
                "eval",
                "--predictions",
                str(prediction),
                "--gold-dir",
                str(gold_dir),
                "--holdout",
                str(holdout),
                "--output",
                str(evaluation_path),
            ],
            cwd=temp,
            env=clean_env,
        )
        if evaluation.get("benchmark") != "SerockBench-v1" or not evaluation_path.is_file():
            raise RuntimeError(f"installed evaluation did not use explicit inputs: {evaluation}")

        print(
            json.dumps(
                {
                    "status": "PASS",
                    "wheel": wheel.name,
                    "installed_module": str(installed_module),
                    "runtime_assets": "3/3",
                    "wheel_runtime_asset_entries": len(packaged_runtime_assets),
                    "reader_inspect": reader["reader"],
                    "consensus": consensus["status"],
                    "evaluation": evaluation["benchmark"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
