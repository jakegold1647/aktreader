from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from PIL import Image

from aktreader.cli import main
from aktreader.collection import (
    add_project_to_collection,
    create_collection,
    inspect_collection,
    list_collection_documents,
    search_collection,
)
from aktreader.project import (
    create_project,
    import_pagexml_into_project,
    revise_line_transcription,
    update_project_document,
)


def _source(root: Path) -> Path:
    Image.new("L", (40, 30), color=255).save(root / "page.png")
    source = root / "page.xml"
    source.write_text(
        """<PcGts>
  <Page imageFilename="page.png" imageWidth="40" imageHeight="30">
    <TextRegion id="region-1">
      <Coords points="0,0 40,0 40,30 0,30"/>
      <TextLine id="line-1">
        <Coords points="2,2 38,2 38,12 2,12"/>
        <TextEquiv><Unicode>Alexander record</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )
    return source


def test_collection_indexes_and_refreshes_effective_project_text(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = _source(source_root)
    project = tmp_path / "register.aktproj"
    collection = tmp_path / "registers.aktcollection"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    create_collection(collection, name="Serock collection")

    indexed = add_project_to_collection(collection, project)
    found = search_collection(collection, "alexander")

    assert indexed["indexed_document_count"] == 1
    assert indexed["indexed_line_count"] == 1
    assert found["match_count"] == 1
    assert found["matches"][0]["document_title"] == "page"
    assert inspect_collection(collection)["document_count"] == 1

    revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=found["matches"][0]["source_span_id"],
        text="Aleksander corrected",
        editor="reviewer-1",
    )
    add_project_to_collection(collection, project)

    assert search_collection(collection, "alexander")["match_count"] == 0
    refreshed = search_collection(collection, "corrected")
    assert refreshed["matches"][0]["revision"] == 1


def test_collection_migrates_v1_without_losing_text_search(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = _source(source_root)
    project = tmp_path / "register.aktproj"
    collection = tmp_path / "registers.aktcollection"
    create_project(project, name="Serock births")
    import_pagexml_into_project(project, source)
    create_collection(collection, name="Serock collection")
    add_project_to_collection(collection, project)

    database = collection / "collection.sqlite3"
    connection = sqlite3.connect(database)
    try:
        with connection:
            connection.execute("DROP TABLE document_index")
            connection.execute("PRAGMA user_version = 1")
    finally:
        connection.close()

    migrated = search_collection(collection, "record")

    assert migrated["match_count"] == 1
    assert migrated["matches"][0]["document_id"] is None
    assert inspect_collection(collection)["document_count"] == 0


def test_collection_discovers_document_metadata(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = _source(source_root)
    project = tmp_path / "register.aktproj"
    collection = tmp_path / "registers.aktcollection"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    update_project_document(
        project,
        manifest_sha256=imported["manifest_sha256"],
        title="Serock birth register, 1831",
        tags=["births", "Serock"],
        notes="Registers from the Serock parish.",
    )
    create_collection(collection, name="Serock collection")

    add_project_to_collection(collection, project)
    discovered = list_collection_documents(collection, query="parish")

    assert discovered["match_count"] == 1
    assert discovered["documents"][0]["title"] == "Serock birth register, 1831"
    assert discovered["documents"][0]["tags"] == ["births", "Serock"]
    assert discovered["documents"][0]["page_count"] == 1
    assert discovered["documents"][0]["line_count"] == 1


def test_collection_cli_creates_indexes_and_searches(tmp_path: Path, capsys) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = _source(source_root)
    project = tmp_path / "register.aktproj"
    collection = tmp_path / "registers.aktcollection"
    create_project(project, name="Serock births")
    import_pagexml_into_project(project, source)

    assert main(["collection-create", str(collection), "--name", "Registers"]) == 0
    capsys.readouterr()
    assert main(["collection-add-project", str(collection), str(project)]) == 0
    capsys.readouterr()
    assert main(["collection-list-documents", str(collection), "--query", "page"]) == 0
    documents = json.loads(capsys.readouterr().out)
    assert documents["match_count"] == 1
    assert main(["collection-search", str(collection), "record"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["match_count"] == 1
