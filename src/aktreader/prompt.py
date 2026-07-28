"""Integrity checks for the one shared subscription/local Reader prompt."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

VERBATIM_SKILLS = (
    "napoleonic-act-formula.md",
    "cyrillic-paleography.md",
    "uncertainty-grading.md",
)
PROMPT_VERSION = "1.2.0"


class PromptIntegrityError(ValueError):
    """Raised when the frozen Reader prompt diverges from its source skills or checksum."""


def sha256_path(path: Path) -> str:
    """Hash a prompt or model artifact as bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_reader_prompt(root: Path) -> str:
    """Require each domain skill byte-for-byte between stable prompt delimiters."""
    prompt_path = root / "prompts" / "reader_prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    if f"Prompt version: {PROMPT_VERSION}\n" not in prompt:
        raise PromptIntegrityError(f"reader prompt is not version {PROMPT_VERSION}")
    for filename in VERBATIM_SKILLS:
        begin = f"<!-- BEGIN VERBATIM: skills/{filename} -->\n"
        end = f"\n<!-- END VERBATIM: skills/{filename} -->"
        if begin not in prompt or end not in prompt:
            raise PromptIntegrityError(f"missing prompt delimiters for {filename}")
        section = prompt.split(begin, 1)[1].split(end, 1)[0]
        expected = (root / "skills" / filename).read_text(encoding="utf-8")
        if section != expected:
            raise PromptIntegrityError(f"verbatim prompt section differs from skills/{filename}")

    digest = sha256_path(prompt_path)
    checksum_line = (root / "prompts" / "reader_prompt.sha256").read_text(
        encoding="utf-8"
    ).strip()
    expected_digest, separator, expected_name = checksum_line.partition("  ")
    if not separator or expected_name != "reader_prompt.md" or expected_digest != digest:
        raise PromptIntegrityError("reader_prompt.sha256 does not match reader_prompt.md")

    manifest = json.loads(
        (root / "prompts" / "manifest.json").read_text(encoding="utf-8")
    )
    header = manifest.get("prompt_header")
    if not isinstance(header, dict):
        raise PromptIntegrityError("prompt manifest has no prompt_header")
    if header.get("prompt_version") != PROMPT_VERSION:
        raise PromptIntegrityError("prompt manifest version does not match reader prompt")
    if header.get("prompt_sha256") != digest:
        raise PromptIntegrityError("prompt manifest hash does not match reader prompt")
    return digest
