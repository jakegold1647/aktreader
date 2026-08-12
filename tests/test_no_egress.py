"""No-egress guard: "local-only" as an executable assertion, not a promise.

Static half: every module under ``src/aktreader`` is parsed and its imports are
checked against a blocklist of networking-capable modules, and the declared
runtime dependency set is pinned, so a network client cannot arrive - directly
or transitively - without this file changing in the same review.

Runtime half: representative CLI paths run with socket creation forcibly
disabled at the ``socket`` module level. The static half proves the package
never imports ``socket`` itself, so patching the module attributes closes the
remaining stdlib-indirection routes; any attempt to open a socket fails the
test rather than the promise.
"""

from __future__ import annotations

import ast
import json
import socket
from pathlib import Path

import pytest
import tomllib

from aktreader.cli import main

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "aktreader"

# Top-level modules that can perform or enable network egress. Additions to
# the allowlist below require an explicit review note in the same commit.
BLOCKED_TOP_LEVEL = frozenset(
    {
        "aiohttp",
        "asyncio",
        "boto3",
        "botocore",
        "certifi",
        "ftplib",
        "http",
        "httpx",
        "imaplib",
        "nntplib",
        "paramiko",
        "poplib",
        "pycurl",
        "requests",
        "smtplib",
        "socket",
        "socketserver",
        "ssl",
        "telnetlib",
        "urllib",
        "urllib3",
        "webbrowser",
        "websocket",
        "websockets",
        "wsgiref",
        "xmlrpc",
    }
)

# Exact dotted imports permitted despite a blocked top level (none today;
# e.g. "urllib.parse" would belong here if a module ever needs URL parsing).
ALLOWED_EXACT: frozenset[str] = frozenset()

# The reviewed local-only runtime dependency set (see dependency-licenses.json
# for the full transitive license inventory). Neither package opens sockets.
REVIEWED_RUNTIME_DEPENDENCIES = ["jsonschema", "pillow"]


def _imported_names(tree: ast.Module) -> list[tuple[int, str]]:
    names: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append((node.lineno, node.module))
    return names


def test_package_imports_no_networking_modules() -> None:
    violations: list[str] = []
    for source in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for lineno, name in _imported_names(tree):
            if name in ALLOWED_EXACT:
                continue
            if name.split(".")[0] in BLOCKED_TOP_LEVEL:
                relative = source.relative_to(ROOT)
                violations.append(f"{relative}:{lineno}: imports {name}")

    assert violations == []


def test_runtime_dependencies_are_the_reviewed_local_only_set() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    declared = sorted(
        requirement.partition(">")[0].partition("<")[0].partition("=")[0].strip().lower()
        for requirement in project["project"]["dependencies"]
    )

    assert declared == REVIEWED_RUNTIME_DEPENDENCIES
    assert set(project["project"].get("optional-dependencies", {})) <= {"dev"}


@pytest.fixture
def sockets_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("network egress attempted during a local-only path")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)


def test_doctor_runs_with_sockets_disabled(sockets_disabled: None, capsys) -> None:
    exit_code = main(["doctor", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["network_required"] is False


def test_prompt_verify_runs_with_sockets_disabled(sockets_disabled: None, capsys) -> None:
    exit_code = main(["prompt-verify", "--root", str(ROOT)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"


def test_eval_runs_with_sockets_disabled(
    sockets_disabled: None, tmp_path: Path, capsys
) -> None:
    first_gold = json.loads(
        sorted((ROOT / "gold" / "acts").glob("*.json"))[0].read_text(encoding="utf-8")
    )
    prediction = tmp_path / "prediction.json"
    prediction.write_text(
        json.dumps({"record_id": first_gold["record_id"], "observations": {}}),
        encoding="utf-8",
    )
    output = tmp_path / "eval.json"
    table = tmp_path / "eval-strata.md"

    exit_code = main(
        [
            "eval",
            "--predictions",
            str(prediction),
            "--output",
            str(output),
            "--strata-table",
            str(table),
        ]
    )

    capsys.readouterr()
    assert exit_code == 0
    assert output.exists()
    assert table.exists()
