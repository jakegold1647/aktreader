from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from PIL import Image

from aktreader.cli import main
from aktreader.project import create_project, import_pagexml_into_project, inspect_project


def _write_image(path: Path) -> None:
    Image.new("L", (40, 30), color=255).save(path)


def _write_pagexml(path: Path) -> None:
    path.write_text(
        """<PcGts>
  <Page imageFilename="page.png" imageWidth="40" imageHeight="30">
    <TextRegion id="region-1">
      <Coords points="0,0 40,0 40,30 0,30"/>
      <TextLine id="line-1">
        <Coords points="2,2 38,2 38,12 2,12"/>
        <Baseline points="2,10 38,10"/>
        <TextEquiv><Unicode>Александр</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )


def test_create_project_initializes_a_local_workbench_store(tmp_path: Path) -> None:
    project = tmp_path / "register.aktproj"

    report = create_project(project, name="Serock births")

    manifest = json.loads((project / "project.akt.json").read_text(encoding="utf-8"))
    assert report["status"] == "READY"
    assert report["project"] == str(project.resolve())
    assert report["name"] == "Serock births"
    assert report["object_count"] == 0
    assert report["pagexml_import_count"] == 0
    assert report["page_count"] == 0
    assert report["line_count"] == 0
    assert report["network_required"] is False
    assert manifest["contract"] == {"name": "aktreader-project", "version": "1.0.0"}
    assert manifest["storage"] == {
        "database": "project.sqlite3",
        "objects": "objects/sha256",
        "imports": "imports/pagexml",
    }
    assert (project / "project.sqlite3").is_file()


def test_project_import_copies_hashed_pagexml_images_and_lines(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    image = source_root / "page.png"
    source = source_root / "page.xml"
    _write_image(image)
    _write_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")

    report = import_pagexml_into_project(project, source)

    manifest = json.loads(Path(report["manifest"]).read_text(encoding="utf-8"))
    xml_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    image_digest = hashlib.sha256(image.read_bytes()).hexdigest()
    assert report["status"] == "SUCCEEDED"
    assert report["already_imported"] is False
    assert report["page_count"] == 1
    assert report["region_count"] == 1
    assert report["line_count"] == 1
    assert report["network_required"] is False
    assert manifest["source"]["stored_object"] == f"objects/sha256/{xml_digest[:2]}/{xml_digest}"
    assert manifest["pages"][0]["image"]["stored_object"] == (
        f"objects/sha256/{image_digest[:2]}/{image_digest}"
    )
    assert (project / manifest["source"]["stored_object"]).read_bytes() == source.read_bytes()
    assert (
        project / manifest["pages"][0]["image"]["stored_object"]
    ).read_bytes() == image.read_bytes()
    line = manifest["pages"][0]["lines"][0]
    assert line["locator"]["page_id"] == "page-index-0"
    assert line["locator"]["line_id"] == "line-1"
    assert line["text"] == "Александр"

    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        assert connection.execute("SELECT COUNT(*) FROM source_objects").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM pagexml_imports").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM lines").fetchone()[0] == 1
    finally:
        connection.close()

    repeated = import_pagexml_into_project(project, source)

    assert repeated["already_imported"] is True
    report_after_repeat = inspect_project(project)
    assert report_after_repeat["object_count"] == 2
    assert report_after_repeat["pagexml_import_count"] == 1
    assert report_after_repeat["page_count"] == 1
    assert report_after_repeat["line_count"] == 1


def test_project_cli_creates_and_inspects_an_offline_project(tmp_path: Path, capsys) -> None:
    project = tmp_path / "register.aktproj"

    create_exit = main(["project-create", str(project), "--name", "Serock births"])

    create_report = json.loads(capsys.readouterr().out)
    inspect_exit = main(["project-inspect", str(project)])
    inspect_report = json.loads(capsys.readouterr().out)
    assert create_exit == inspect_exit == 0
    assert create_report["status"] == "READY"
    assert create_report["project"] == str(project.resolve())
    assert inspect_report["project_id"] == create_report["project_id"]
    assert inspect_report["network_required"] is False
