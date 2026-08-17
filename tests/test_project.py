from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

import aktreader.kraken as kraken_module
from aktreader.cli import main
from aktreader.kraken import KrakenConfig, LocalKraken
from aktreader.local_reader import PinnedArtifact, sha256_file
from aktreader.pagexml import import_pagexml
from aktreader.project import (
    ProjectStoreError,
    create_project,
    evaluate_htr_suggestions,
    export_consented_training_pagexml,
    export_human_pagexml,
    export_review_package,
    grant_training_consent,
    import_htr_suggestions,
    import_images_into_project,
    import_pagexml_into_project,
    import_pdf_into_project,
    import_review_package,
    inspect_project,
    list_project_documents,
    list_project_pages,
    load_project_page,
    resolve_review_proposal,
    recognize_project_with_kraken,
    revise_line_geometry,
    revise_line_transcription,
    revise_page_reading_order,
    revise_region_geometry,
    revoke_training_consent,
    training_readiness,
    update_project_document,
)


def _write_image(path: Path) -> None:
    Image.new("L", (40, 30), color=255).save(path)


def _write_pdf(path: Path) -> None:
    first = Image.new("L", (40, 30), color=255)
    second = Image.new("L", (20, 10), color=230)
    try:
        first.save(path, "PDF", resolution=72, save_all=True, append_images=[second])
    finally:
        first.close()
        second.close()


def _write_pagexml(path: Path, *, text: str = "Александр") -> None:
    path.write_text(
        f"""<PcGts>
  <Page imageFilename="page.png" imageWidth="40" imageHeight="30">
    <TextRegion id="region-1">
      <Coords points="0,0 40,0 40,30 0,30"/>
      <TextLine id="line-1">
        <Coords points="2,2 38,2 38,12 2,12"/>
        <Baseline points="2,10 38,10"/>
        <TextEquiv><Unicode>{text}</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )


def _write_two_region_pagexml(path: Path) -> None:
    path.write_text(
        """<PcGts>
  <Page id="page-1" imageFilename="page.png" imageWidth="40" imageHeight="30">
    <ReadingOrder>
      <OrderedGroup id="source-order">
        <RegionRefIndexed index="0" regionRef="region-1"/>
        <RegionRefIndexed index="1" regionRef="region-2"/>
      </OrderedGroup>
    </ReadingOrder>
    <TextRegion id="region-1">
      <Coords points="0,0 40,0 40,14 0,14"/>
      <TextLine id="line-1">
        <Coords points="2,2 38,2 38,10 2,10"/>
        <TextEquiv><Unicode>first</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
    <TextRegion id="region-2">
      <Coords points="0,15 40,15 40,30 0,30"/>
      <TextLine id="line-2">
        <Coords points="2,18 38,18 38,27 2,27"/>
        <TextEquiv><Unicode>second</Unicode></TextEquiv>
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


def test_project_imports_an_image_directory_as_editable_pagexml(tmp_path: Path) -> None:
    source_directory = tmp_path / "scans"
    source_directory.mkdir()
    _write_image(source_directory / "001.png")
    Image.new("L", (20, 10), color=240).save(source_directory / "002.png")
    (source_directory / "readme.txt").write_text("not an image", encoding="utf-8")
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")

    imported = import_images_into_project(
        project,
        source_directory,
        title="Serock birth register",
    )

    manifest = json.loads(Path(imported["manifest"]).read_text(encoding="utf-8"))
    pages = list_project_pages(project)
    document = list_project_documents(project)[0]
    first_page = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )

    assert imported["status"] == "SUCCEEDED"
    assert imported["source_kind"] == "IMAGE_DIRECTORY"
    assert imported["input_image_count"] == 2
    assert imported["page_count"] == 2
    assert imported["region_count"] == 2
    assert imported["line_count"] == 0
    assert Path(imported["generated_pagexml"]).is_file()
    assert Path(imported["generated_pagexml"]).is_relative_to(project)
    assert manifest["source"]["path"] == imported["generated_pagexml"]
    assert [page["page_id"] for page in manifest["pages"]] == [
        "image-0001",
        "image-0002",
    ]
    assert manifest["pages"][0]["regions"][0]["polygon"] == [
        [0, 0],
        [40, 0],
        [40, 30],
        [0, 30],
    ]
    assert manifest["pages"][1]["regions"][0]["polygon"] == [
        [0, 0],
        [20, 0],
        [20, 10],
        [0, 10],
    ]
    assert len(pages) == 2
    assert document["title"] == "Serock birth register"
    assert first_page["lines"] == []

    repeated = import_images_into_project(project, source_directory)

    assert repeated["already_imported"] is True
    assert list_project_documents(project)[0]["title"] == "Serock birth register"


def test_project_image_import_cli_creates_a_document(tmp_path: Path, capsys) -> None:
    source_directory = tmp_path / "scans"
    source_directory.mkdir()
    _write_image(source_directory / "page.png")
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")

    exit_code = main(
        [
            "project-import-images",
            str(project),
            str(source_directory),
            "--title",
            "Imported scans",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert report["source_kind"] == "IMAGE_DIRECTORY"
    assert report["page_count"] == 1
    assert list_project_documents(project)[0]["title"] == "Imported scans"


def test_project_imports_a_pdf_as_editable_pagexml_with_a_source_receipt(
    tmp_path: Path,
) -> None:
    source = tmp_path / "serock-births.pdf"
    _write_pdf(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")

    imported = import_pdf_into_project(project, source, dpi=144)

    manifest = json.loads(Path(imported["manifest"]).read_text(encoding="utf-8"))
    receipt = json.loads(Path(imported["pdf_receipt"]).read_text(encoding="utf-8"))
    stored_pdf = project / imported["source_pdf_stored_object"]
    document = list_project_documents(project)[0]
    first_page = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )

    assert imported["status"] == "SUCCEEDED"
    assert imported["source_kind"] == "PDF"
    assert imported["page_count"] == 2
    assert imported["region_count"] == 2
    assert imported["line_count"] == 0
    assert imported["renderer"]["dpi"] == 144
    assert stored_pdf.read_bytes() == source.read_bytes()
    assert receipt["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert receipt["source"]["stored_object"] == imported["source_pdf_stored_object"]
    assert receipt["renderer"] == imported["renderer"]
    assert len(receipt["pages"]) == 2
    assert Path(receipt["render_directory"]).is_dir()
    assert len(manifest["pages"]) == 2
    assert all(page["regions"][0]["region_id"] == "region-0001" for page in manifest["pages"])
    assert first_page["lines"] == []
    assert document["title"] == "serock-births"

    repeated = import_pdf_into_project(project, source, dpi=144)

    assert repeated["already_imported"] is True
    assert repeated["pdf_receipt"] == imported["pdf_receipt"]


def test_project_pdf_import_cli_creates_a_page_document(tmp_path: Path, capsys) -> None:
    source = tmp_path / "scans.pdf"
    _write_pdf(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")

    exit_code = main(
        [
            "project-import-pdf",
            str(project),
            str(source),
            "--dpi",
            "144",
            "--title",
            "Serock PDF scans",
        ]
    )
    report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert report["source_kind"] == "PDF"
    assert report["page_count"] == 2
    assert list_project_documents(project)[0]["title"] == "Serock PDF scans"



def test_project_keeps_human_transcription_revisions_separate_from_source(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)

    pages = list_project_pages(project)

    assert len(pages) == 1
    assert pages[0]["manifest_sha256"] == imported["manifest_sha256"]
    page = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )
    line = page["lines"][0]
    assert line["source_text"] == line["text"] == "Александр"
    assert line["revision"] == 0

    saved = revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="Александръ",
        editor="reviewer-1",
    )

    assert saved["status"] == "SAVED"
    assert saved["revision"] == 1
    updated = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    assert updated["source_text"] == "Александр"
    assert updated["text"] == "Александръ"
    assert updated["revision"] == 1
    assert source.read_text(encoding="utf-8").count("Александр") == 1

    unchanged = revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="Александръ",
    )

    assert unchanged["status"] == "UNCHANGED"
    assert unchanged["revision"] == 1
    assert inspect_project(project)["transcription_revision_count"] == 1



def test_project_imports_htr_suggestions_with_effective_line_geometry(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    line = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    revise_line_geometry(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        polygon=[[1, 1], [39, 1], [39, 13], [1, 13]],
        baseline=[[1, 11], [39, 11]],
        editor="reviewer-1",
    )
    recognized = tmp_path / "recognized.page.xml"
    export_human_pagexml(
        project,
        recognized,
        manifest_sha256=imported["manifest_sha256"],
    )

    report = import_htr_suggestions(
        project,
        recognized,
        manifest_sha256=imported["manifest_sha256"],
        engine="kraken",
        runtime_fingerprint="a" * 64,
        image_root=source_root,
    )

    assert report["status"] == "SUCCEEDED"
    assert report["suggestion_count"] == 1


def test_project_runs_pinned_kraken_from_its_own_materialized_images(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    shutil.rmtree(source_root)

    executable = tmp_path / "kraken.exe"
    model = tmp_path / "register.safetensors"
    executable.write_bytes(b"pinned local kraken executable")
    model.write_bytes(b"pinned local recognition model")
    kraken = LocalKraken(
        KrakenConfig(
            executable=PinnedArtifact(executable, sha256_file(executable)),
            model=PinnedArtifact(model, sha256_file(model)),
            timeout_seconds=60,
        )
    )
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        source_path = Path(command[command.index("-i") + 1])
        output_path = Path(command[command.index("-i") + 2])
        document = ET.parse(source_path)
        page = next(element for element in document.iter() if element.tag == "Page")
        assert page.get("imageFilename") == "page-0000.png"
        assert (source_path.parent / "page-0000.png").is_file()
        text = next(element for element in document.iter() if element.tag == "Unicode")
        text.text = "Александръ"
        document.write(output_path, encoding="utf-8", xml_declaration=True)
        return subprocess.CompletedProcess(command, 0, "local stdout", "local stderr")

    monkeypatch.setattr(kraken_module.subprocess, "run", fake_run)

    report = recognize_project_with_kraken(
        project,
        manifest_sha256=imported["manifest_sha256"],
        kraken=kraken,
    )

    assert report["status"] == "SUCCEEDED"
    assert report["engine"] == "kraken"
    assert report["suggestion_count"] == 1
    assert report["runtime_fingerprint"] == kraken.runtime_fingerprint
    assert all("source" not in item for item in report)
    command = captured["command"]
    assert isinstance(command, list)
    assert command[command.index("-f") + 1] == "xml"
    assert command[command.index("-x")] == "-x"
    suggestion = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )["lines"][0]["suggestions"][0]
    assert suggestion["text"] == "Александръ"


def test_project_keeps_htr_suggestions_separate_from_human_revisions(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    recognized = source_root / "page.kraken.xml"
    _write_pagexml(source)
    _write_pagexml(recognized, text="Александръ")
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)

    stored = import_htr_suggestions(
        project,
        recognized,
        manifest_sha256=imported["manifest_sha256"],
        engine="kraken",
        runtime_fingerprint="a" * 64,
    )

    assert stored["status"] == "SUCCEEDED"
    assert stored["already_imported"] is False
    assert stored["suggestion_count"] == 1
    page = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )
    line = page["lines"][0]
    assert line["source_text"] == line["text"] == "Александр"
    assert len(line["suggestions"]) == 1
    suggestion = line["suggestions"][0]
    assert suggestion["engine"] == "kraken"
    assert suggestion["runtime_fingerprint"] == "a" * 64
    assert suggestion["result_pagexml_sha256"] == hashlib.sha256(
        recognized.read_bytes()
    ).hexdigest()
    assert suggestion["text"] == "Александръ"
    assert isinstance(suggestion["imported_at"], str)
    revised = revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="Александръ?",
        editor="reviewer-1",
    )
    assert revised["status"] == "SAVED"
    after_revision = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    assert after_revision["text"] == "Александръ?"
    assert after_revision["suggestions"][0]["text"] == "Александръ"

    repeated = import_htr_suggestions(
        project,
        recognized,
        manifest_sha256=imported["manifest_sha256"],
        engine="kraken",
        runtime_fingerprint="a" * 64,
    )
    assert repeated["already_imported"] is True
    report = inspect_project(project)
    assert report["htr_run_count"] == 1
    assert report["htr_suggestion_count"] == 1



def test_project_documents_keep_metadata_separate_from_imported_pagexml(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "register.xml"
    _write_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)

    documents = list_project_documents(project)
    updated = update_project_document(
        project,
        manifest_sha256=imported["manifest_sha256"],
        title="Serock civil register, 1890",
        tags=["Serock", "births"],
        notes="Reviewed from the bound volume.",
    )
    repeated = import_pagexml_into_project(project, source)
    pages = list_project_pages(project)

    assert len(documents) == 1
    assert documents[0]["document_id"] == imported["document_id"]
    assert documents[0]["title"] == "register"
    assert updated["document_id"] == imported["document_id"]
    assert updated["tags"] == ["Serock", "births"]
    assert repeated["already_imported"] is True
    assert list_project_documents(project)[0]["notes"] == "Reviewed from the bound volume."
    assert pages[0]["document_id"] == imported["document_id"]
    assert inspect_project(project)["document_count"] == 1


def test_project_document_cli_updates_strict_metadata(tmp_path: Path, capsys) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "register.xml"
    _write_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    metadata = tmp_path / "document.json"
    metadata.write_text(
        json.dumps({"title": "Serock register", "tags": ["1890"], "notes": ""}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "project-update-document",
            str(project),
            "--manifest-sha256",
            imported["manifest_sha256"],
            "--metadata",
            str(metadata),
        ]
    )
    updated = json.loads(capsys.readouterr().out)
    list_exit = main(["project-list-documents", str(project)])
    listed = json.loads(capsys.readouterr().out)

    assert exit_code == list_exit == 0
    assert updated["title"] == "Serock register"
    assert listed["documents"][0]["tags"] == ["1890"]


def test_project_migrates_v2_store_for_htr_suggestions(tmp_path: Path) -> None:
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")

    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        with connection:
            connection.execute("DROP TABLE documents")
            connection.execute("DROP TABLE region_geometry_revisions")
            connection.execute("DROP TABLE page_reading_order_revisions")
            connection.execute("DROP TABLE line_geometry_revisions")
            connection.execute("DROP TABLE review_proposals")
            connection.execute("DROP TABLE training_split_assignments")
            connection.execute("DROP TABLE training_consent_revocations")
            connection.execute("DROP TABLE training_consent_grants")
            connection.execute("DROP TABLE htr_suggestions")
            connection.execute("DROP TABLE htr_runs")
            connection.execute("PRAGMA user_version = 2")
    finally:
        connection.close()

    report = inspect_project(project)

    assert report["htr_run_count"] == 0
    assert report["htr_suggestion_count"] == 0
    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 10
    finally:
        connection.close()

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


def test_project_exports_human_revisions_as_derivative_pagexml(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_pagexml(source)
    source_bytes = source.read_bytes()
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    line = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="Александръ?",
        editor="reviewer-1",
    )
    exported_path = tmp_path / "serock-human.page.xml"

    report = export_human_pagexml(
        project,
        exported_path,
        manifest_sha256=imported["manifest_sha256"],
    )

    assert report["status"] == "SUCCEEDED"
    assert report["source_pagexml_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert report["output_sha256"] == hashlib.sha256(exported_path.read_bytes()).hexdigest()
    assert report["human_revision_count"] == 1
    assert source.read_bytes() == source_bytes
    exported = import_pagexml(exported_path, image_root=source_root)
    assert exported["pages"][0]["lines"][0]["text"] == "Александръ?"

    revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="Александръ!?",
        editor="reviewer-2",
    )
    repeated = export_human_pagexml(
        project,
        exported_path,
        manifest_sha256=imported["manifest_sha256"],
        replace_existing=True,
    )

    assert repeated["human_revision_count"] == 1
    assert import_pagexml(exported_path, image_root=source_root)["pages"][0]["lines"][0][
        "text"
    ] == "Александръ!?"


def test_project_export_can_add_text_equiv_for_previously_blank_line(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "blank.xml"
    source.write_text(
        """<PcGts>
  <Page id="page-1" imageFilename="page.png" imageWidth="40" imageHeight="30">
    <TextRegion id="region-1">
      <Coords points="0,0 40,0 40,30 0,30"/>
      <TextLine id="line-1">
        <Coords points="2,2 38,2 38,12 2,12"/>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    line = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    exported_path = tmp_path / "blank-human.page.xml"
    revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="рукописный текст",
    )

    report = export_human_pagexml(
        project,
        exported_path,
        manifest_sha256=imported["manifest_sha256"],
    )

    assert report["human_revision_count"] == 1
    assert import_pagexml(exported_path, image_root=source_root)["pages"][0]["lines"][0][
        "text"
    ] == "рукописный текст"


def test_project_evaluates_one_htr_result_against_human_revisions(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    recognized = source_root / "page.kraken.xml"
    _write_pagexml(source, text="act.")
    _write_pagexml(recognized, text="akt")
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    htr = import_htr_suggestions(
        project,
        recognized,
        manifest_sha256=imported["manifest_sha256"],
        engine="kraken",
        runtime_fingerprint="a" * 64,
    )
    line = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="act",
        editor="reviewer-1",
    )

    report = evaluate_htr_suggestions(
        project,
        manifest_sha256=imported["manifest_sha256"],
        result_pagexml_sha256=htr["result_pagexml_sha256"],
    )

    assert report["status"] == "SUCCEEDED"
    assert report["engine"] == "kraken"
    assert report["source_line_count"] == report["run_line_count"] == 1
    assert report["human_revision_count"] == report["evaluated_line_count"] == 1
    assert report["suggestion_count_for_human_revisions"] == 1
    assert report["normalization"] == "UNICODE_NFC_EXACT_WHITESPACE"
    assert report["reference_character_count"] == report["hypothesis_character_count"] == 3
    assert report["character_edit_distance"] == 1
    assert report["character_error_rate"] == 1 / 3
    assert report["reference_word_count"] == report["hypothesis_word_count"] == 1
    assert report["word_edit_distance"] == 1
    assert report["word_error_rate"] == 1
    assert report["exact_line_match_count"] == 0
    assert report["exact_line_match_rate"] == 0
    assert report["network_required"] is False


def test_project_training_consent_tracks_the_current_human_revision(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_pagexml(source, text="Александр")
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    line = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="Александръ",
        editor="reviewer-1",
    )

    before = training_readiness(
        project,
        manifest_sha256=imported["manifest_sha256"],
    )
    granted = grant_training_consent(
        project,
        manifest_sha256=imported["manifest_sha256"],
        contributor="reviewer-1",
        source_span_ids=[line["source_span_id"]],
    )
    ready = training_readiness(
        project,
        manifest_sha256=imported["manifest_sha256"],
    )

    assert before["status"] == "BLOCKED_TRAINING_CONSENT"
    assert before["human_revision_count"] == 1
    assert before["eligible_training_line_count"] == 0
    assert granted["status"] == "GRANTED"
    assert granted["grants"][0]["already_granted"] is False
    assert ready["status"] == "READY_FOR_PAGEXML_TRAINING_EXPORT"
    assert ready["eligible_training_line_count"] == 1

    revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="Александръ?",
        editor="reviewer-1",
    )
    stale = training_readiness(
        project,
        manifest_sha256=imported["manifest_sha256"],
    )
    refreshed = grant_training_consent(
        project,
        manifest_sha256=imported["manifest_sha256"],
        contributor="reviewer-1",
        source_span_ids=[line["source_span_id"]],
    )
    revoked = revoke_training_consent(
        project,
        grant_consent_id=refreshed["grants"][0]["consent_id"],
        contributor="reviewer-1",
        reason="withdrew local training permission",
    )
    after_revocation = training_readiness(
        project,
        manifest_sha256=imported["manifest_sha256"],
    )

    assert stale["status"] == "BLOCKED_TRAINING_CONSENT"
    assert refreshed["grants"][0]["already_granted"] is False
    assert revoked["status"] == "REVOKED"
    assert after_revocation["status"] == "BLOCKED_TRAINING_CONSENT"
    report = inspect_project(project)
    assert report["training_consent_grant_count"] == 2
    assert report["training_consent_revocation_count"] == 1


def test_project_migrates_v3_store_for_training_consent(tmp_path: Path) -> None:
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")

    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        with connection:
            connection.execute("DROP TABLE documents")
            connection.execute("DROP TABLE region_geometry_revisions")
            connection.execute("DROP TABLE page_reading_order_revisions")
            connection.execute("DROP TABLE line_geometry_revisions")
            connection.execute("DROP TABLE review_proposals")
            connection.execute("DROP TABLE training_split_assignments")
            connection.execute("DROP TABLE training_consent_revocations")
            connection.execute("DROP TABLE training_consent_grants")
            connection.execute("PRAGMA user_version = 3")
    finally:
        connection.close()

    report = inspect_project(project)

    assert report["training_consent_grant_count"] == 0
    assert report["training_consent_revocation_count"] == 0
    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 10
    finally:
        connection.close()


def test_project_exports_a_consented_htr_training_bundle(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    image = source_root / "page.png"
    _write_image(image)
    source = source_root / "page.xml"
    _write_pagexml(source, text="Александр")
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    line = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="Александръ",
        editor="reviewer-1",
    )
    grant_training_consent(
        project,
        manifest_sha256=imported["manifest_sha256"],
        contributor="reviewer-1",
        all_human_revised=True,
    )
    bundle = tmp_path / "serock-train"

    report = export_consented_training_pagexml(
        project,
        bundle,
        manifest_sha256=imported["manifest_sha256"],
        split="train",
    )

    image_sha256 = hashlib.sha256(image.read_bytes()).hexdigest()
    bundle_manifest = json.loads(
        (bundle / "bundle.aktreader.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "SUCCEEDED"
    assert report["split"] == "train"
    assert report["eligible_training_line_count"] == 1
    assert (bundle / "train.lst").read_text(encoding="utf-8") == "document.page.xml\n"
    assert (bundle / "images" / f"{image_sha256}.png").is_file()
    assert bundle_manifest["contract"] == {
        "name": "aktreader-consented-pagexml-training-bundle",
        "version": "1.0.0",
    }
    assert bundle_manifest["source_import"]["manifest_sha256"] == imported["manifest_sha256"]
    assert bundle_manifest["split"] == "train"
    assert bundle_manifest["network_required"] is False
    exported = import_pagexml(bundle / "document.page.xml", image_root=bundle)
    assert exported["pages"][0]["lines"][0]["text"] == "Александръ"
    assert inspect_project(project)["training_split_assignment_count"] == 1

    try:
        export_consented_training_pagexml(
            project,
            tmp_path / "serock-validation",
            manifest_sha256=imported["manifest_sha256"],
            split="validation",
        )
    except ProjectStoreError as error:
        assert "different immutable training split assignment" in str(error)
    else:
        raise AssertionError("a source import must not be assigned to two training splits")


def test_project_migrates_v4_store_for_training_split_assignments(tmp_path: Path) -> None:
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")

    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        with connection:
            connection.execute("DROP TABLE documents")
            connection.execute("DROP TABLE region_geometry_revisions")
            connection.execute("DROP TABLE page_reading_order_revisions")
            connection.execute("DROP TABLE line_geometry_revisions")
            connection.execute("DROP TABLE review_proposals")
            connection.execute("DROP TABLE training_split_assignments")
            connection.execute("PRAGMA user_version = 4")
    finally:
        connection.close()

    report = inspect_project(project)

    assert report["training_split_assignment_count"] == 0
    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 10
    finally:
        connection.close()



def test_project_migrates_v7_store_for_page_reading_order_revisions(
    tmp_path: Path,
) -> None:
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")

    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        with connection:
            connection.execute("DROP TABLE documents")
            connection.execute("DROP TABLE region_geometry_revisions")
            connection.execute("DROP TABLE page_reading_order_revisions")
            connection.execute("PRAGMA user_version = 7")
    finally:
        connection.close()

    report = inspect_project(project)

    assert report["page_reading_order_revision_count"] == 0
    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 10
    finally:
        connection.close()



def test_project_migrates_v8_store_for_region_geometry_revisions(
    tmp_path: Path,
) -> None:
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")

    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        with connection:
            connection.execute("DROP TABLE documents")
            connection.execute("DROP TABLE region_geometry_revisions")
            connection.execute("PRAGMA user_version = 8")
    finally:
        connection.close()

    report = inspect_project(project)

    assert report["region_geometry_revision_count"] == 0
    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 10
    finally:
        connection.close()



def test_project_migrates_v9_store_for_documents(tmp_path: Path) -> None:
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")

    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        with connection:
            connection.execute("DROP TABLE documents")
            connection.execute("PRAGMA user_version = 9")
    finally:
        connection.close()

    report = inspect_project(project)

    assert report["document_count"] == 0
    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 10
    finally:
        connection.close()


def test_offline_review_package_queues_and_requires_explicit_acceptance(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_pagexml(source)

    reviewer = tmp_path / "reviewer.aktproj"
    owner = tmp_path / "owner.aktproj"
    create_project(reviewer, name="Reviewer copy")
    create_project(owner, name="Owner copy")
    reviewer_import = import_pagexml_into_project(reviewer, source)
    owner_import = import_pagexml_into_project(owner, source)
    reviewer_line = load_project_page(
        reviewer,
        manifest_sha256=reviewer_import["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    revise_line_transcription(
        reviewer,
        manifest_sha256=reviewer_import["manifest_sha256"],
        source_span_id=reviewer_line["source_span_id"],
        text="Александръ",
        editor="reviewer-1",
    )
    package = tmp_path / "reviewer.aktreview.json"

    exported = export_review_package(
        reviewer,
        package,
        manifest_sha256=reviewer_import["manifest_sha256"],
        contributor="reviewer-1",
    )
    queued = import_review_package(owner, package)

    assert exported["status"] == "EXPORTED"
    assert queued["status"] == "QUEUED"
    assert queued["pending_count"] == 1
    assert queued["conflict_count"] == 0
    assert len(queued["proposal_sha256s"]) == 1
    owner_line = load_project_page(
        owner,
        manifest_sha256=owner_import["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    assert owner_line["text"] == "Александр"
    assert owner_line["review_proposals"] == [
        {
            "proposal_sha256": queued["proposal_sha256s"][0],
            "contributor": "reviewer-1",
            "text": "Александръ",
            "state": "PENDING",
            "revised_at": owner_line["review_proposals"][0]["revised_at"],
        }
    ]

    resolved = resolve_review_proposal(
        owner,
        proposal_sha256=queued["proposal_sha256s"][0],
        decision="accept",
        editor="owner-1",
    )

    accepted = load_project_page(
        owner,
        manifest_sha256=owner_import["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    assert resolved["status"] == "ACCEPTED"
    assert resolved["editor"] == "owner-1"
    assert accepted["text"] == "Александръ"
    assert accepted["revision"] == 1
    assert accepted["review_proposals"] == []
    assert inspect_project(owner)["review_proposal_count"] == 1
    assert inspect_project(owner)["training_consent_grant_count"] == 0


def test_offline_review_package_detects_a_stale_base_without_applying_text(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_pagexml(source)

    reviewer = tmp_path / "reviewer.aktproj"
    owner = tmp_path / "owner.aktproj"
    create_project(reviewer, name="Reviewer copy")
    create_project(owner, name="Owner copy")
    reviewer_import = import_pagexml_into_project(reviewer, source)
    owner_import = import_pagexml_into_project(owner, source)
    reviewer_line = load_project_page(
        reviewer,
        manifest_sha256=reviewer_import["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    owner_line = load_project_page(
        owner,
        manifest_sha256=owner_import["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    revise_line_transcription(
        reviewer,
        manifest_sha256=reviewer_import["manifest_sha256"],
        source_span_id=reviewer_line["source_span_id"],
        text="Александръ",
        editor="reviewer-1",
    )
    revise_line_transcription(
        owner,
        manifest_sha256=owner_import["manifest_sha256"],
        source_span_id=owner_line["source_span_id"],
        text="Owner correction",
        editor="owner-1",
    )
    package = tmp_path / "reviewer.aktreview.json"
    export_review_package(
        reviewer,
        package,
        manifest_sha256=reviewer_import["manifest_sha256"],
        contributor="reviewer-1",
    )

    queued = import_review_package(owner, package)
    resolved = resolve_review_proposal(
        owner,
        proposal_sha256=queued["proposal_sha256s"][0],
        decision="accept",
        editor="owner-1",
    )

    assert queued["pending_count"] == 0
    assert queued["conflict_count"] == 1
    assert resolved["status"] == "CONFLICT"
    current = load_project_page(
        owner,
        manifest_sha256=owner_import["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    assert current["text"] == "Owner correction"
    assert current["revision"] == 1


def test_review_package_cli_queues_then_resolves_a_proposal(
    tmp_path: Path,
    capsys,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_pagexml(source)
    reviewer = tmp_path / "reviewer.aktproj"
    owner = tmp_path / "owner.aktproj"
    create_project(reviewer, name="Reviewer copy")
    create_project(owner, name="Owner copy")
    reviewer_import = import_pagexml_into_project(reviewer, source)
    import_pagexml_into_project(owner, source)
    reviewer_line = load_project_page(
        reviewer,
        manifest_sha256=reviewer_import["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    revise_line_transcription(
        reviewer,
        manifest_sha256=reviewer_import["manifest_sha256"],
        source_span_id=reviewer_line["source_span_id"],
        text="Александръ",
        editor="reviewer-1",
    )
    package = tmp_path / "reviewer.aktreview.json"
    export_review_package(
        reviewer,
        package,
        manifest_sha256=reviewer_import["manifest_sha256"],
        contributor="reviewer-1",
    )

    imported_exit = main(["project-import-review-package", str(owner), str(package)])
    imported = json.loads(capsys.readouterr().out)
    resolved_exit = main(
        [
            "project-resolve-review-proposal",
            str(owner),
            "--proposal-sha256",
            imported["proposal_sha256s"][0],
            "--decision",
            "reject",
            "--editor",
            "owner-1",
        ]
    )
    resolved = json.loads(capsys.readouterr().out)

    assert imported_exit == resolved_exit == 0
    assert imported["status"] == "QUEUED"
    assert resolved["status"] == "REJECTED"



def test_project_keeps_page_reading_order_revisions_separate_and_exports_them(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_two_region_pagexml(source)
    source_bytes = source.read_bytes()
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)

    revision = revise_page_reading_order(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
        region_ids=["region-2", "region-1"],
        editor="layout-reviewer",
    )
    try:
        revise_page_reading_order(
            project,
            manifest_sha256=imported["manifest_sha256"],
            page_index=0,
            region_ids=["region-2", "region-2"],
            editor="layout-reviewer",
        )
    except ProjectStoreError as error:
        assert "exact permutation" in str(error)
    else:
        raise AssertionError("duplicate region IDs must be rejected")
    output = tmp_path / "reading-order-revised.page.xml"
    exported = export_human_pagexml(
        project,
        output,
        manifest_sha256=imported["manifest_sha256"],
    )
    unchanged = revise_page_reading_order(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
        region_ids=["region-2", "region-1"],
        editor="layout-reviewer",
    )

    assert revision["status"] == "SAVED"
    assert revision["revision"] == 1
    assert revision["prior_region_ids"] == ["region-1", "region-2"]
    assert exported["human_revision_count"] == 0
    assert exported["page_reading_order_revision_count"] == 1
    assert source.read_bytes() == source_bytes
    rendered = import_pagexml(output, image_root=source_root)
    assert rendered["pages"][0]["reading_order"]["region_ids"] == ["region-2", "region-1"]
    assert unchanged["status"] == "UNCHANGED"
    assert unchanged["revision"] == 1
    assert inspect_project(project)["page_reading_order_revision_count"] == 1


def test_project_cli_revises_page_reading_order(tmp_path: Path, capsys) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_two_region_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    order = tmp_path / "order.json"
    order.write_text(
        json.dumps({"region_ids": ["region-2", "region-1"]}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "project-revise-page-reading-order",
            str(project),
            "--manifest-sha256",
            imported["manifest_sha256"],
            "--page-index",
            "0",
            "--region-order",
            str(order),
            "--editor",
            "layout-reviewer",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["status"] == "SAVED"
    assert report["region_ids"] == ["region-2", "region-1"]



def test_project_keeps_region_geometry_revisions_separate_and_exports_them(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_two_region_pagexml(source)
    source_bytes = source.read_bytes()
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)

    revision = revise_region_geometry(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
        region_id="region-2",
        polygon=[[1, 15], [39, 15], [39, 29], [1, 29]],
        editor="layout-reviewer",
    )
    try:
        revise_region_geometry(
            project,
            manifest_sha256=imported["manifest_sha256"],
            page_index=0,
            region_id="region-2",
            polygon=[[1, 15], [41, 15], [39, 29], [1, 29]],
            editor="layout-reviewer",
        )
    except ProjectStoreError as error:
        assert "outside source image" in str(error)
    else:
        raise AssertionError("out-of-bounds region geometry must be rejected")
    output = tmp_path / "region-geometry-revised.page.xml"
    exported = export_human_pagexml(
        project,
        output,
        manifest_sha256=imported["manifest_sha256"],
    )
    unchanged = revise_region_geometry(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
        region_id="region-2",
        polygon=[[1, 15], [39, 15], [39, 29], [1, 29]],
        editor="layout-reviewer",
    )

    assert revision["status"] == "SAVED"
    assert revision["prior_polygon"] == [[0, 15], [40, 15], [40, 30], [0, 30]]
    assert exported["region_geometry_revision_count"] == 1
    assert source.read_bytes() == source_bytes
    rendered = import_pagexml(output, image_root=source_root)
    region = next(
        item for item in rendered["pages"][0]["regions"] if item["region_id"] == "region-2"
    )
    assert region["polygon"] == [[1, 15], [39, 15], [39, 29], [1, 29]]
    assert unchanged["status"] == "UNCHANGED"
    assert unchanged["revision"] == 1
    assert inspect_project(project)["region_geometry_revision_count"] == 1


def test_project_cli_revises_region_geometry(tmp_path: Path, capsys) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_two_region_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    geometry = tmp_path / "region-geometry.json"
    geometry.write_text(
        json.dumps({"polygon": [[1, 15], [39, 15], [39, 29], [1, 29]]}),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "project-revise-region-geometry",
            str(project),
            "--manifest-sha256",
            imported["manifest_sha256"],
            "--page-index",
            "0",
            "--region-id",
            "region-2",
            "--geometry",
            str(geometry),
            "--editor",
            "layout-reviewer",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["status"] == "SAVED"
    assert report["region_id"] == "region-2"


def test_project_keeps_line_geometry_revisions_separate_and_exports_them(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_pagexml(source)
    source_bytes = source.read_bytes()
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    line = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )["lines"][0]

    revision = revise_line_geometry(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        polygon=[[1, 1], [39, 1], [39, 16], [1, 16]],
        baseline=[[2, 13], [38, 13]],
        editor="layout-reviewer",
    )
    output = tmp_path / "layout-revised.page.xml"
    exported = export_human_pagexml(
        project,
        output,
        manifest_sha256=imported["manifest_sha256"],
    )

    assert revision["status"] == "SAVED"
    assert revision["revision"] == 1
    assert exported["human_revision_count"] == 0
    assert exported["line_geometry_revision_count"] == 1
    assert source.read_bytes() == source_bytes
    rendered = import_pagexml(output, image_root=source_root)
    locator = rendered["pages"][0]["lines"][0]["locator"]
    assert locator["polygon"] == [[1, 1], [39, 1], [39, 16], [1, 16]]
    assert locator["baseline"] == [[2, 13], [38, 13]]
