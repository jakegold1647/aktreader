"""Render a checked-in field reference from the repository's versioned JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
OUTPUT = ROOT / "docs" / "schema-reference.md"


def _inline(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def _markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _summary(node: dict[str, Any]) -> str:
    parts: list[str] = []
    if "$ref" in node:
        parts.append(f"reference to \`{node['$ref']}\`")
    elif "const" in node:
        parts.append(f"constant \`{_inline(node['const'])}\`")
    elif "enum" in node:
        values = ", ".join(f"\`{_inline(value)}\`" for value in node['enum'])
        parts.append(f"one of {values}")
    elif "type" in node:
        node_type = node['type']
        if isinstance(node_type, list):
            parts.append(" or ".join(f"\`{value}\`" for value in node_type))
        else:
            parts.append(f"\`{node_type}\`")

    if "items" in node:
        parts.append(f"items: {_summary(node['items'])}")
    for keyword in ("oneOf", "anyOf", "allOf"):
        if keyword in node:
            options = " / ".join(_summary(option) for option in node[keyword])
            parts.append(f"{keyword}: {options}")

    return "; ".join(parts) if parts else "unconstrained"


def _constraints(node: dict[str, Any]) -> str:
    parts: list[str] = []
    for keyword in (
        "format",
        "pattern",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "minProperties",
        "maxProperties",
    ):
        if keyword in node:
            parts.append(f"{keyword}: \`{_inline(node[keyword])}\`")
    if node.get("uniqueItems") is True:
        parts.append("unique items")
    if node.get("additionalProperties") is False:
        parts.append("additional properties are not allowed")
    return "; ".join(parts)


def _field_table(properties: dict[str, Any], required: list[str]) -> list[str]:
    if not properties:
        return ["_No named properties._", ""]

    lines = [
        "| Field | Required | Type / structure | Description |",
        "| --- | --- | --- | --- |",
    ]
    required_names = set(required)
    for name in sorted(properties):
        node = properties[name]
        description = _markdown(str(node.get("description", "—")))
        summary = _markdown(_summary(node))
        constraints = _constraints(node)
        if constraints:
            summary = f"{summary}<br>{_markdown(constraints)}"
        lines.append(
            f"| \`{_markdown(name)}\` | {'yes' if name in required_names else 'no'} "
            f"| {summary} | {description} |"
        )
    lines.append("")
    return lines


def _section(name: str, node: dict[str, Any], required: list[str]) -> list[str]:
    lines = [f"#### \`{name}\`", "", f"Type: {_summary(node)}."]
    constraints = _constraints(node)
    if constraints:
        lines.extend(["", f"Constraints: {constraints}."])
    description = node.get("description")
    if description:
        lines.extend(["", _markdown(str(description))])
    lines.extend(["", *_field_table(node.get("properties", {}), required)])
    return lines


def _schema_reference(path: Path) -> list[str]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    title = _markdown(str(schema.get("title", path.stem)))
    relative = path.relative_to(ROOT).as_posix()
    lines = [
        f"## {title}",
        "",
        f"Source: [\`{relative}\`](../{relative})",
    ]
    if "$id" in schema:
        lines.extend(["", f"Schema ID: \`{_markdown(str(schema['$id']))}\`"])
    lines.extend(["", "### Field tree", "", *_section("root", schema, schema.get("required", []))])

    definitions = schema.get("$defs", {})
    if definitions:
        lines.extend(["### Reusable definitions", ""])
        for name in sorted(definitions):
            definition = definitions[name]
            lines.extend(_section(f"$defs.{name}", definition, definition.get("required", [])))
    return lines


def render_reference() -> str:
    """Return the deterministic Markdown reference for every versioned JSON Schema."""
    lines = [
        "# Schema reference",
        "",
        "This reference is generated from the versioned JSON Schemas in "
        "[\`schemas/\`](../schemas/) by "
        "[\`tools/build_schema_reference.py\`](../tools/build_schema_reference.py). "
        "Do not edit it by hand.",
        "",
        "It lists each schema's named object fields, required status, declared type or "
        "structure, and any description carried by the contract. References to "
        "\`$defs\` remain pointers to the reusable definition named below rather than being "
        "expanded repeatedly.",
        "",
        "## Schemas",
        "",
    ]
    paths = sorted(SCHEMA_DIR.glob("*.schema.json"))
    for path in paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        title = _markdown(str(schema.get("title", path.stem)))
        lines.append(f"- \`${path.name}\` — {title}")
    for path in paths:
        lines.extend(["", *_schema_reference(path)])
    return "\n".join(lines) + "\n"


def main() -> int:
    OUTPUT.write_text(render_reference(), encoding="utf-8", newline="\n")
    print(OUTPUT.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
