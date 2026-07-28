from pathlib import Path

import pytest

from aktreader.prompt import PromptIntegrityError, verify_reader_prompt

ROOT = Path(__file__).resolve().parents[1]


def test_reader_prompt_contains_all_three_skills_verbatim() -> None:
    assert verify_reader_prompt(ROOT) == (
        "9e679f3a799e75bbfeb7bf077f55b868d7fa06b9ab1164bed443a6f51b0b9d09"
    )


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
        "9e679f3a799e75bbfeb7bf077f55b868d7fa06b9ab1164bed443a6f51b0b9d09",
        "0" * 64,
    )
    manifest_path.write_text(manifest, encoding="utf-8")

    with pytest.raises(PromptIntegrityError, match="manifest hash"):
        verify_reader_prompt(tmp_path)
