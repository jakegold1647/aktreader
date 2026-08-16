"""Regression checks for the repository's CI hardening invariants."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ROOT / ".github" / "workflows" / "ci.yml",
    ROOT / ".github" / "workflows" / "commit-hygiene.yml",
)
ACTION_REFERENCE = re.compile(r"^\s*-?\s*uses:\s+[^\s@]+@(?P<ref>[^\s#]+)", re.MULTILINE)
FULL_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")


def test_external_actions_are_pinned_to_full_commit_shas() -> None:
    for workflow in WORKFLOWS:
        content = workflow.read_text(encoding="utf-8")
        references = ACTION_REFERENCE.findall(content)

        assert references, f"{workflow.relative_to(ROOT)} has no action references"
        unpinned = [
            reference
            for reference in references
            if not FULL_COMMIT_SHA.fullmatch(reference)
        ]
        assert unpinned == [], (
            f"{workflow.relative_to(ROOT)} uses mutable action references: {', '.join(unpinned)}"
        )


def test_workflows_default_to_read_only_contents_permission() -> None:
    for workflow in WORKFLOWS:
        content = workflow.read_text(encoding="utf-8")

        assert "permissions:\n  contents: read\n" in content, (
            f"{workflow.relative_to(ROOT)} must explicitly default to contents: read"
        )
