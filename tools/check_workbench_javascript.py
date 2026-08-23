"""Parse the browser workbench's rendered inline JavaScript with Node.js."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from aktreader.web_workbench import _INDEX_HTML


@dataclass(frozen=True)
class InlineScript:
    code: str
    module: bool = False


class _ExecutableInlineScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[InlineScript] = []
        self._parts: list[str] | None = None
        self._module = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "script":
            return
        attributes = {name.lower(): value for name, value in attrs}
        script_type = (attributes.get("type") or "").strip().lower()
        if "src" not in attributes and script_type in {
            "",
            "application/javascript",
            "module",
            "text/javascript",
        }:
            if self._parts is not None:
                raise ValueError("nested executable script elements are not supported")
            self._parts = []
            self._module = script_type == "module"

    def handle_data(self, data: str) -> None:
        if self._parts is not None:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._parts is not None:
            self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._parts is not None:
            self._parts.append(f"&#{name};")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._parts is not None:
            self.scripts.append(InlineScript("".join(self._parts), module=self._module))
            self._parts = None
            self._module = False

    def close(self) -> None:
        super().close()
        if self._parts is not None:
            raise ValueError("unterminated executable script element")


def executable_inline_scripts(html: str) -> list[InlineScript]:
    """Return classic and module scripts that a browser would execute inline."""

    parser = _ExecutableInlineScriptParser()
    parser.feed(html)
    parser.close()
    return parser.scripts


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def check_scripts(
    scripts: Sequence[InlineScript],
    *,
    node: str,
    run: RunCommand = subprocess.run,
) -> None:
    """Raise ``SyntaxError`` with Node's diagnostic if any script cannot parse."""

    if not scripts:
        raise ValueError("workbench HTML contains no executable inline JavaScript")
    with tempfile.TemporaryDirectory(prefix="aktreader-workbench-js-") as temporary:
        root = Path(temporary)
        for index, script in enumerate(scripts, start=1):
            suffix = ".mjs" if script.module else ".js"
            script_path = root / f"workbench-inline-{index}{suffix}"
            script_path.write_text(script.code, encoding="utf-8")
            result = run(
                [node, "--check", str(script_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            if result.returncode != 0:
                diagnostic = (result.stderr or result.stdout).strip()
                raise SyntaxError(
                    f"workbench inline script {index} is invalid JavaScript:\n{diagnostic}"
                )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse rendered aktreader workbench JavaScript with Node.js."
    )
    parser.add_argument(
        "--node",
        help="Node.js executable; defaults to the node command on PATH",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    node = args.node or shutil.which("node")
    if node is None:
        print(
            "Node.js is required to verify the browser workbench JavaScript.",
            file=sys.stderr,
        )
        return 2
    try:
        scripts = executable_inline_scripts(_INDEX_HTML)
        check_scripts(scripts, node=node)
    except (SyntaxError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"workbench JavaScript syntax: PASS ({len(scripts)} inline script)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
