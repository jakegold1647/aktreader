from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDENDUM = ROOT / "docs" / "p2-baseline-addendum.md"


def test_p2_addendum_records_full_protocol_arc_and_caveats() -> None:
    text = ADDENDUM.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    required_facts = (
        "1/77 (1.30%)",
        "0/36 fully image-verified benchmark-eligible acts",
        "Phantom identities intercepted by blind disagreement",
        "The coordinator caused the pressure",
        "supervisory-protocol failure",
        "Read-only retro-audit: coverage paired with groundedness",
        "wave-001 Reader A",
        "wave-004 Reader B",
        "silver records",
        "Restructured verification protocol",
        "fresh, blind same-vendor session",
        "correlated blind spots remain",
        "act 26's nine weeks",
        "act 12's surname Goldberg",
    )
    for fact in required_facts:
        assert fact in normalized


def test_p2_addendum_does_not_overstate_research_derived_baseline() -> None:
    text = ADDENDUM.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "not publication-grade" in normalized
    assert "research-derived before-picture" in normalized
    assert "These are safety catches, not benchmark accuracy." in normalized
    assert "raw 0% transcription-support result for gold is void" in normalized
