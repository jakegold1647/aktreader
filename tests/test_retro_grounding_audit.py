import hashlib
from pathlib import Path

from tools.retro_audit_grounding import build_report, inventory, render_markdown

ROOT = Path(__file__).resolve().parents[1]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_retro_audit_is_read_only_and_pairs_quality_metrics() -> None:
    groups = inventory(ROOT)
    paths = tuple(path for group in groups for path in group.paths)
    before = {path: _digest(path) for path in paths}

    report = build_report(ROOT)

    assert {group["group_id"] for group in report["groups"]} == {
        "wave-001-reader-a",
        "wave-001-reader-b",
        "wave-002-reader-a",
        "wave-002-reader-b",
        "wave-003-reader-a",
        "wave-003-reader-b",
        "wave-004-reader-a",
        "wave-004-reader-b",
        "silver-records",
        "gold-acts",
    }
    for group in report["groups"]:
        assert set(group["quality_metrics"]) == {"coverage", "groundedness"}
        assert group["status"] in {"PASS", "FAIL"}
    assert {path: _digest(path) for path in paths} == before


def test_retro_audit_inventory_and_rendered_table_are_stable() -> None:
    report = build_report(ROOT)
    groups = {group["group_id"]: group for group in report["groups"]}

    assert groups["wave-001-reader-a"]["quality_metrics"]["coverage"]["record_count"] == 2
    assert groups["wave-004-reader-b"]["quality_metrics"]["coverage"]["record_count"] == 10
    assert groups["silver-records"]["quality_metrics"]["coverage"]["record_count"] == 5
    assert groups["gold-acts"]["quality_metrics"]["coverage"]["record_count"] == 36
    markdown = render_markdown(report)
    assert "Coverage" in markdown
    assert "Groundedness" in markdown
    assert "No label was modified" in markdown
