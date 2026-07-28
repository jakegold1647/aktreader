import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "examples" / "p2-baseline.artifacts.json"
HELPER = ROOT / "tools" / "fetch_p2_model.ps1"


def test_owner_fetch_helper_matches_frozen_model_pins() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    script = HELPER.read_text(encoding="utf-8")

    for role in ("model", "mmproj"):
        artifact = lock[role]
        assert artifact["source_url"] in script
        assert artifact["sha256"] in script
        assert str(artifact["size_bytes"]) in script


def test_owner_fetch_helper_is_fail_closed_and_not_an_inference_downloader() -> None:
    script = HELPER.read_text(encoding="utf-8")

    assert "ExecutionPolicy Bypass" not in script
    assert "--fail --location" in script
    assert '"$destination.partial"' in script
    assert "throw " in script
    assert "This is provisioning, not an AKTREADER inference path" in script
