from pathlib import Path

from tools.build_schema_reference import OUTPUT, SCHEMA_DIR, render_reference

ROOT = Path(__file__).resolve().parents[1]


def test_schema_reference_is_current() -> None:
    assert OUTPUT == ROOT / "docs" / "schema-reference.md"
    assert OUTPUT.read_text(encoding="utf-8") == render_reference()


def test_schema_reference_lists_each_versioned_contract() -> None:
    reference = render_reference()
    for schema in sorted(SCHEMA_DIR.glob("*.schema.json")):
        assert f"\`{schema.name}\`" in reference
        assert f"Source: [\`schemas/{schema.name}\`]" in reference
