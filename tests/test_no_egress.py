"""No-egress guard: "local-only" as an executable assertion, not a promise.

Static half: every module under ``src/aktreader`` is parsed and its imports are
checked against a blocklist of networking-capable modules. The one reviewed
exception is the explicitly started, loopback-only browser workbench; its exact
imports are scoped to its one module below. The declared runtime dependency set
is pinned, so an egress-capable client cannot arrive without this file changing
in the same review.

Runtime half: representative CLI paths run with socket creation forcibly
disabled at the ``socket`` module level. The static half proves the package
never imports ``socket`` itself, so patching the module attributes closes the
remaining stdlib-indirection routes; any attempt to open a socket fails the
test rather than the promise.
"""

from __future__ import annotations

import ast
import hashlib
import json
import socket
from pathlib import Path

import pytest
import tomllib
from PIL import Image

from aktreader.cli import main
from aktreader.project import (
    grant_training_consent,
    load_project_page,
    revise_line_transcription,
)

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

# The browser workbench creates a loopback listener only after the explicit
# `serve` command. Keep these networking imports scoped to that module: no
# other package module may import them, and socket-level local-only tests still
# cover every regular CLI path.
LOOPBACK_ONLY_IMPORTS: dict[str, frozenset[str]] = {
    "src/aktreader/web_workbench.py": frozenset(
        {
            "http",
            "http.server",
            "urllib.parse",
        }
    )
}

# The reviewed local-only runtime dependency set (see dependency-licenses.json
# for the full transitive license inventory). None of these packages opens sockets.
REVIEWED_RUNTIME_DEPENDENCIES = ["jsonschema", "pillow", "pypdfium2"]


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
        relative = source.relative_to(ROOT)
        allowed_for_source = LOOPBACK_ONLY_IMPORTS.get(relative.as_posix(), frozenset())
        for lineno, name in _imported_names(tree):
            if name in allowed_for_source:
                continue
            if name.split(".")[0] in BLOCKED_TOP_LEVEL:
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


def test_checkout_verify_runs_with_sockets_disabled(sockets_disabled: None, capsys) -> None:
    exit_code = main(["checkout-verify", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["network_required"] is False


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


def test_compare_runs_with_sockets_disabled(
    sockets_disabled: None, tmp_path: Path, capsys
) -> None:
    output = tmp_path / "comparison.json"
    csv = tmp_path / "comparison.csv"

    exit_code = main(
        [
            "compare",
            str(ROOT / "labels" / "readerA"),
            str(ROOT / "labels" / "readerB"),
            "--output",
            str(output),
            "--csv",
            str(csv),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["network_used"] is False
    assert payload["output"] == str(output)
    assert payload["csv_output"] == str(csv)
    assert output.is_file()
    assert csv.is_file()


def test_pagexml_import_runs_with_sockets_disabled(
    sockets_disabled: None,
    tmp_path: Path,
    capsys,
) -> None:
    image = tmp_path / "page.png"
    Image.new("L", (20, 20), color=255).save(image)
    source = tmp_path / "page.xml"
    source.write_text(
        """<PcGts>
  <Page id="page-1" imageFilename="page.png" imageWidth="20" imageHeight="20">
    <TextRegion id="region-1">
      <Coords points="0,0 20,0 20,20 0,20"/>
      <TextLine id="line-1">
        <Coords points="1,1 19,1 19,10 1,10"/>
        <TextEquiv><Unicode>test</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )
    output = tmp_path / "manifest.json"

    exit_code = main(["pagexml-import", str(source), "--output", str(output)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["network_required"] is False
    assert output.is_file()


def test_project_create_runs_with_sockets_disabled(
    sockets_disabled: None,
    tmp_path: Path,
    capsys,
) -> None:
    project = tmp_path / "register.aktproj"

    exit_code = main(["project-create", str(project), "--name", "Serock births"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["network_required"] is False
    assert (project / "project.akt.json").is_file()


def test_kraken_inspect_runs_with_sockets_disabled(
    sockets_disabled: None,
    tmp_path: Path,
    capsys,
) -> None:
    executable = tmp_path / "kraken.exe"
    model = tmp_path / "register.safetensors"
    executable.write_bytes(b"local kraken executable")
    model.write_bytes(b"local recognition model")
    config = tmp_path / "kraken.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "artifacts": {
                    "executable": {
                        "path": str(executable),
                        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                    },
                    "model": {
                        "path": str(model),
                        "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                    },
                },
                "inference": {"device": "cpu", "precision": "32", "batch_size": 1},
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["kraken-inspect", "--config", str(config)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "READY"
    assert payload["reader"] == "LOCAL_KRAKEN_PAGEXML"
    assert payload["network_required"] is False


def test_project_htr_suggestion_import_runs_with_sockets_disabled(
    sockets_disabled: None,
    tmp_path: Path,
    capsys,
) -> None:
    image = tmp_path / "page.png"
    Image.new("L", (20, 20), color=255).save(image)
    source = tmp_path / "page.xml"
    recognized = tmp_path / "page.kraken.xml"
    source.write_text(
        """<PcGts>
  <Page id="page-1" imageFilename="page.png" imageWidth="20" imageHeight="20">
    <TextRegion id="region-1">
      <Coords points="0,0 20,0 20,20 0,20"/>
      <TextLine id="line-1">
        <Coords points="1,1 19,1 19,10 1,10"/>
        <TextEquiv><Unicode>source text</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )
    recognized.write_text(
        source.read_text(encoding="utf-8").replace("source text", "recognized text"),
        encoding="utf-8",
    )
    project = tmp_path / "register.aktproj"

    assert main(["project-create", str(project), "--name", "Serock births"]) == 0
    capsys.readouterr()
    assert main(["project-import-pagexml", str(project), str(source)]) == 0
    imported = json.loads(capsys.readouterr().out)
    exit_code = main(
        [
            "project-import-htr-suggestions",
            str(project),
            str(recognized),
            "--manifest-sha256",
            imported["manifest_sha256"],
            "--runtime-fingerprint",
            "a" * 64,
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["suggestion_count"] == 1
    assert payload["network_required"] is False


def test_project_pagexml_export_runs_with_sockets_disabled(
    sockets_disabled: None,
    tmp_path: Path,
    capsys,
) -> None:
    image = tmp_path / "page.png"
    Image.new("L", (20, 20), color=255).save(image)
    source = tmp_path / "page.xml"
    source.write_text(
        """<PcGts>
  <Page id="page-1" imageFilename="page.png" imageWidth="20" imageHeight="20">
    <TextRegion id="region-1">
      <Coords points="0,0 20,0 20,20 0,20"/>
      <TextLine id="line-1">
        <Coords points="1,1 19,1 19,10 1,10"/>
        <TextEquiv><Unicode>source text</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )
    project = tmp_path / "register.aktproj"
    exported = tmp_path / "human.page.xml"

    assert main(["project-create", str(project), "--name", "Serock births"]) == 0
    capsys.readouterr()
    assert main(["project-import-pagexml", str(project), str(source)]) == 0
    imported = json.loads(capsys.readouterr().out)
    exit_code = main(
        [
            "project-export-pagexml",
            str(project),
            "--manifest-sha256",
            imported["manifest_sha256"],
            "--output",
            str(exported),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["human_revision_count"] == 0
    assert payload["network_required"] is False
    assert exported.is_file()


def test_project_htr_evaluation_runs_with_sockets_disabled(
    sockets_disabled: None,
    tmp_path: Path,
    capsys,
) -> None:
    image = tmp_path / "page.png"
    Image.new("L", (20, 20), color=255).save(image)
    source = tmp_path / "page.xml"
    recognized = tmp_path / "page.kraken.xml"
    source.write_text(
        """<PcGts>
  <Page id="page-1" imageFilename="page.png" imageWidth="20" imageHeight="20">
    <TextRegion id="region-1">
      <Coords points="0,0 20,0 20,20 0,20"/>
      <TextLine id="line-1">
        <Coords points="1,1 19,1 19,10 1,10"/>
        <TextEquiv><Unicode>source text</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )
    recognized.write_text(
        source.read_text(encoding="utf-8").replace("source text", "recognized text"),
        encoding="utf-8",
    )
    project = tmp_path / "register.aktproj"
    report_path = tmp_path / "htr-evaluation.json"

    assert main(["project-create", str(project), "--name", "Serock births"]) == 0
    capsys.readouterr()
    assert main(["project-import-pagexml", str(project), str(source)]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert (
        main(
            [
                "project-import-htr-suggestions",
                str(project),
                str(recognized),
                "--manifest-sha256",
                imported["manifest_sha256"],
                "--runtime-fingerprint",
                "a" * 64,
            ]
        )
        == 0
    )
    htr = json.loads(capsys.readouterr().out)
    exit_code = main(
        [
            "project-evaluate-htr",
            str(project),
            "--manifest-sha256",
            imported["manifest_sha256"],
            "--result-pagexml-sha256",
            htr["result_pagexml_sha256"],
            "--output",
            str(report_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "NO_EVALUABLE_HUMAN_REVISIONS"
    assert payload["network_required"] is False
    assert report_path.is_file()


def test_project_training_readiness_runs_with_sockets_disabled(
    sockets_disabled: None,
    tmp_path: Path,
    capsys,
) -> None:
    image = tmp_path / "page.png"
    Image.new("L", (20, 20), color=255).save(image)
    source = tmp_path / "page.xml"
    source.write_text(
        """<PcGts>
  <Page id="page-1" imageFilename="page.png" imageWidth="20" imageHeight="20">
    <TextRegion id="region-1">
      <Coords points="0,0 20,0 20,20 0,20"/>
      <TextLine id="line-1">
        <Coords points="1,1 19,1 19,10 1,10"/>
        <TextEquiv><Unicode>source text</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )
    project = tmp_path / "register.aktproj"
    report_path = tmp_path / "training-readiness.json"

    assert main(["project-create", str(project), "--name", "Serock births"]) == 0
    capsys.readouterr()
    assert main(["project-import-pagexml", str(project), str(source)]) == 0
    imported = json.loads(capsys.readouterr().out)
    exit_code = main(
        [
            "project-training-readiness",
            str(project),
            "--manifest-sha256",
            imported["manifest_sha256"],
            "--output",
            str(report_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "BLOCKED_HUMAN_REVISIONS"
    assert payload["network_required"] is False
    assert report_path.is_file()


def test_consented_training_bundle_export_runs_with_sockets_disabled(
    sockets_disabled: None,
    tmp_path: Path,
    capsys,
) -> None:
    image = tmp_path / "page.png"
    Image.new("L", (20, 20), color=255).save(image)
    source = tmp_path / "page.xml"
    source.write_text(
        """<PcGts>
  <Page id="page-1" imageFilename="page.png" imageWidth="20" imageHeight="20">
    <TextRegion id="region-1">
      <Coords points="0,0 20,0 20,20 0,20"/>
      <TextLine id="line-1">
        <Coords points="1,1 19,1 19,10 1,10"/>
        <TextEquiv><Unicode>source text</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )
    project = tmp_path / "register.aktproj"
    bundle = tmp_path / "training-bundle"

    assert main(["project-create", str(project), "--name", "Serock births"]) == 0
    capsys.readouterr()
    assert main(["project-import-pagexml", str(project), str(source)]) == 0
    imported = json.loads(capsys.readouterr().out)
    line = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="reviewed text",
        editor="local-user",
    )
    grant_training_consent(
        project,
        manifest_sha256=imported["manifest_sha256"],
        contributor="local-user",
        all_human_revised=True,
    )
    exit_code = main(
        [
            "project-export-consented-training-pagexml",
            str(project),
            "--manifest-sha256",
            imported["manifest_sha256"],
            "--split",
            "train",
            "--output-directory",
            str(bundle),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "SUCCEEDED"
    assert payload["network_required"] is False
    assert (bundle / "bundle.aktreader.json").is_file()


def test_htr_corpus_assembly_runs_with_sockets_disabled(
    sockets_disabled: None,
    tmp_path: Path,
    capsys,
) -> None:
    def ready_project(name: str, text: str) -> tuple[Path, str]:
        source_root = tmp_path / f"{name}-source"
        source_root.mkdir()
        image = source_root / "page.png"
        Image.new("L", (20, 20), color=255).save(image)
        source = source_root / "page.xml"
        source.write_text(
            f"""<PcGts>
  <Page id="page-1" imageFilename="page.png" imageWidth="20" imageHeight="20">
    <TextRegion id="region-1">
      <Coords points="0,0 20,0 20,20 0,20"/>
      <TextLine id="line-1">
        <Coords points="1,1 19,1 19,10 1,10"/>
        <TextEquiv><Unicode>{text}</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
            encoding="utf-8",
        )
        project = tmp_path / f"{name}.aktproj"
        assert main(["project-create", str(project), "--name", name]) == 0
        capsys.readouterr()
        assert main(["project-import-pagexml", str(project), str(source)]) == 0
        imported = json.loads(capsys.readouterr().out)
        line = load_project_page(
            project,
            manifest_sha256=imported["manifest_sha256"],
            page_index=0,
        )["lines"][0]
        revise_line_transcription(
            project,
            manifest_sha256=imported["manifest_sha256"],
            source_span_id=line["source_span_id"],
            text=f"{text} reviewed",
            editor="local-user",
        )
        grant_training_consent(
            project,
            manifest_sha256=imported["manifest_sha256"],
            contributor="local-user",
            all_human_revised=True,
        )
        return project, imported["manifest_sha256"]

    train_project, train_manifest = ready_project("train", "Александр")
    validation_project, validation_manifest = ready_project("validation", "Екатерина")
    plan = tmp_path / "corpus-plan.json"
    plan.write_text(
        json.dumps(
            {
                "contract": {
                    "name": "aktreader-local-htr-corpus-plan",
                    "version": "1.0.0",
                },
                "inputs": [
                    {
                        "project": str(train_project),
                        "manifest_sha256": train_manifest,
                        "split": "train",
                    },
                    {
                        "project": str(validation_project),
                        "manifest_sha256": validation_manifest,
                        "split": "validation",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    corpus = tmp_path / "corpus"

    exit_code = main(
        [
            "htr-build-corpus",
            "--plan",
            str(plan),
            "--output-directory",
            str(corpus),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "SUCCEEDED"
    assert payload["network_required"] is False
    assert (corpus / "train.lst").is_file()
    assert (corpus / "validation.lst").is_file()

    inspect_exit_code = main(
        [
            "htr-inspect-corpus",
            "--plan",
            str(plan),
            "--corpus-directory",
            str(corpus),
        ]
    )

    inspected = json.loads(capsys.readouterr().out)
    assert inspect_exit_code == 0
    assert inspected["status"] == "READY_FOR_LOCAL_KRAKEN_TRAINING"
    assert inspected["network_required"] is False
