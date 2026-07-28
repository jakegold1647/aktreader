from pathlib import Path

import pytest

from aktreader.prompt import PromptIntegrityError, verify_reader_prompt

ROOT = Path(__file__).resolve().parents[1]


def test_reader_prompt_contains_all_three_skills_verbatim() -> None:
    assert verify_reader_prompt(ROOT) == (
        "ea0e83756698496414ba654de70805179829848f31acc644112b1e51f48e955f"
    )
    prompt = (ROOT / "prompts" / "reader_prompt.md").read_text(encoding="utf-8")
    assert "Line-break surname split" in prompt
    assert "Read «умеръ»/«умерла» first in death acts" in prompt
    assert "Clerk-specific «-фельдъ» written with в" in prompt


def test_prompt_check_detects_skill_drift(tmp_path: Path) -> None:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "skills").mkdir()
    for source in (ROOT / "prompts").iterdir():
        (tmp_path / "prompts" / source.name).write_bytes(source.read_bytes())
    for source in (ROOT / "skills").iterdir():
        (tmp_path / "skills" / source.name).write_bytes(source.read_bytes())
    target = tmp_path / "skills" / "uncertainty-grading.md"
    target.write_text(target.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")

    with pytest.raises(PromptIntegrityError, match="differs"):
        verify_reader_prompt(tmp_path)


def test_prompt_check_detects_manifest_drift(tmp_path: Path) -> None:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "skills").mkdir()
    for source in (ROOT / "prompts").iterdir():
        (tmp_path / "prompts" / source.name).write_bytes(source.read_bytes())
    for source in (ROOT / "skills").iterdir():
        (tmp_path / "skills" / source.name).write_bytes(source.read_bytes())
    manifest_path = tmp_path / "prompts" / "manifest.json"
    manifest = manifest_path.read_text(encoding="utf-8").replace(
        "ea0e83756698496414ba654de70805179829848f31acc644112b1e51f48e955f",
        "0" * 64,
    )
    manifest_path.write_text(manifest, encoding="utf-8")

    with pytest.raises(PromptIntegrityError, match="manifest hash"):
        verify_reader_prompt(tmp_path)
