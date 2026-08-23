from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import tools.check_workbench_javascript as workbench_javascript
from tools.check_workbench_javascript import (
    InlineScript,
    check_scripts,
    executable_inline_scripts,
)


def test_executable_inline_scripts_ignore_data_and_external_scripts() -> None:
    html = """<!doctype html>
<script type="application/ld+json">{"not": "code"}</script>
<script src="app.js"></script>
<script>const classic = 1 &lt; 2;</script>
<script type="module">export const moduleValue = 2;</script>
"""

    assert executable_inline_scripts(html) == [
        InlineScript("const classic = 1 &lt; 2;"),
        InlineScript("export const moduleValue = 2;", module=True),
    ]


def test_check_scripts_runs_node_check_for_each_rendered_script() -> None:
    seen: list[tuple[list[str], str]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        script = Path(command[-1]).read_text(encoding="utf-8")
        seen.append((command, script))
        assert kwargs == {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "check": False,
        }
        return subprocess.CompletedProcess(command, 0, "", "")

    check_scripts(
        [InlineScript("const one = 1;"), InlineScript("const two = 2;", module=True)],
        node="node-test",
        run=run,
    )

    assert [command[:2] for command, _script in seen] == [
        ["node-test", "--check"],
        ["node-test", "--check"],
    ]
    assert [script for _command, script in seen] == ["const one = 1;", "const two = 2;"]
    assert [Path(command[-1]).suffix for command, _script in seen] == [".js", ".mjs"]


def test_check_scripts_surfaces_node_syntax_diagnostic() -> None:
    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "SyntaxError: missing )")

    with pytest.raises(SyntaxError) as error:
        check_scripts([InlineScript("broken(")], node="node-test", run=run)
    assert "inline script 1" in str(error.value)
    assert "SyntaxError: missing )" in str(error.value)


def test_check_scripts_refuses_an_empty_workbench() -> None:
    with pytest.raises(ValueError, match="no executable inline JavaScript"):
        check_scripts([], node="node-test")


def test_command_explains_when_optional_local_node_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(workbench_javascript.shutil, "which", lambda _command: None)

    assert workbench_javascript.main([]) == 2
    assert "Node.js is required" in capsys.readouterr().err
