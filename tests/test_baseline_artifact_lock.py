import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "examples" / "p2-baseline.artifacts.json"
CONFIG_PATH = ROOT / "examples" / "p2-baseline.local-reader.json"
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:\\")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_baseline_lock_uses_revision_pinned_owner_fetches() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    revision = lock["prebuilt_gguf"]["revision"]

    assert lock["state"] == "MTMD_REDUCED_SCHEMA_FROZEN_PROBE_PENDING"
    assert lock["application_downloads_artifacts"] is False
    assert lock["inference_network_allowed"] is False
    assert len(revision) == 40
    for role in ("model", "mmproj"):
        artifact = lock[role]
        assert artifact["size_bytes"] > 0
        assert SHA256_RE.fullmatch(artifact["sha256"])
        assert f"/resolve/{revision}/" in artifact["source_url"]
        assert "/main/" not in artifact["source_url"]
        assert WINDOWS_ABSOLUTE_RE.match(artifact["local_path"])


def test_runnable_config_contains_only_local_paths_and_matches_lock() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    artifacts = config["artifacts"]

    expected = {
        "executable": lock["runtime"],
        "model": lock["model"],
        "mmproj": lock["mmproj"],
        "model_schema": lock["model_schema"],
        "prompt": lock["prompt"],
        "schema": lock["schema"],
    }
    for role, pin in artifacts.items():
        assert WINDOWS_ABSOLUTE_RE.match(pin["path"])
        assert "://" not in pin["path"]
        assert pin["sha256"] == expected[role]["sha256"]

    assert _sha256(ROOT / "prompts" / "reader_prompt-v1.2.0.md") == artifacts["prompt"]["sha256"]
    assert (
        _sha256(ROOT / "schemas" / "reader-label-1.0.0-v1.2.schema.json")
        == artifacts["schema"]["sha256"]
    )
    assert (
        _sha256(ROOT / "schemas" / "model-output-1.0.0.schema.json")
        == artifacts["model_schema"]["sha256"]
    )
