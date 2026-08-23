from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image

import aktreader.kraken as kraken_module
from aktreader.cli import main
from aktreader.kraken import KrakenConfig, LocalKraken
from aktreader.local_reader import PinnedArtifact, sha256_file
from aktreader.pagexml import import_pagexml
from aktreader.project import (
    ProjectRevisionConflictError,
    ProjectStoreError,
    create_project,
    evaluate_htr_suggestions,
    export_consented_training_pagexml,
    export_human_alto,
    export_human_pagexml,
    export_human_pdf,
    export_human_transcript,
    export_human_transcriptions_csv,
    export_review_package,
    grant_training_consent,
    import_htr_suggestions,
    import_images_into_project,
    import_pagexml_into_project,
    import_pdf_into_project,
    import_review_package,
    inspect_project,
    list_htr_suggestion_evaluations,
    list_project_activity,
    list_project_documents,
    list_project_pages,
    load_project_page,
    load_project_page_layout,
    load_project_revision_history,
    recognize_project_with_kraken,
    resolve_review_proposal,
    restore_line_geometry,
    restore_line_transcription,
    restore_page_reading_order,
    restore_region_geometry,
    revise_line_geometry,
    revise_line_transcription,
    revise_page_reading_order,
    revise_region_geometry,
    revoke_training_consent,
    search_project_transcriptions,
    segment_project_with_kraken,
    training_readiness,
    undo_line_geometry,
    undo_page_reading_order,
    undo_region_geometry,
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


def _create_two_revision_streams(
    tmp_path: Path,
) -> tuple[Path, Path, str, str]:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_two_region_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    manifest_sha256 = imported["manifest_sha256"]
    line = load_project_page(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
    )["lines"][0]
    source_span_id = line["source_span_id"]

    revise_line_transcription(
        project,
        manifest_sha256=manifest_sha256,
        source_span_id=source_span_id,
        text="first draft",
        editor="reviewer",
        expected_revision=0,
    )
    revise_line_transcription(
        project,
        manifest_sha256=manifest_sha256,
        source_span_id=source_span_id,
        text="first approved",
        editor="reviewer",
        expected_revision=1,
    )
    revise_line_geometry(
        project,
        manifest_sha256=manifest_sha256,
        source_span_id=source_span_id,
        polygon=[[1, 1], [39, 1], [39, 11], [1, 11]],
        baseline=[[2, 9], [38, 9]],
        editor="reviewer",
        expected_revision=0,
    )
    revise_line_geometry(
        project,
        manifest_sha256=manifest_sha256,
        source_span_id=source_span_id,
        polygon=[[1, 2], [39, 2], [39, 12], [1, 12]],
        baseline=[[2, 10], [38, 10]],
        editor="reviewer",
        expected_revision=1,
    )
    revise_region_geometry(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
        region_id="region-2",
        polygon=[[1, 15], [39, 15], [39, 29], [1, 29]],
        editor="reviewer",
        expected_revision=0,
    )
    revise_region_geometry(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
        region_id="region-2",
        polygon=[[2, 15], [38, 15], [38, 29], [2, 29]],
        editor="reviewer",
        expected_revision=1,
    )
    revise_page_reading_order(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
        region_ids=["region-2", "region-1"],
        editor="reviewer",
        expected_revision=0,
    )
    revise_page_reading_order(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
        region_ids=["region-1", "region-2"],
        editor="reviewer",
        expected_revision=1,
    )
    return project, source, manifest_sha256, source_span_id


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


def test_project_searches_effective_transcriptions_by_field(tmp_path: Path, capsys) -> None:
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
    update_project_document(
        project,
        manifest_sha256=imported["manifest_sha256"],
        title="Serock birth index",
        tags=["Serock", "1890"],
    )
    revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="Aleksander Goldstein",
        editor="reviewer-1",
    )

    text_matches = search_project_transcriptions(
        project,
        query="gold",
        field="text",
    )
    title_matches = search_project_transcriptions(
        project,
        query="birth",
        field="title",
    )
    tag_matches = search_project_transcriptions(
        project,
        query="ser",
        field="tag",
    )

    assert text_matches["network_required"] is False
    assert text_matches["result_count"] == 1
    assert text_matches["truncated"] is False
    assert text_matches["results"] == [
        {
            "manifest_sha256": imported["manifest_sha256"],
            "document_id": text_matches["results"][0]["document_id"],
            "title": "Serock birth index",
            "tags": ["Serock", "1890"],
            "page_index": 0,
            "page_id": "page-index-0",
            "region_id": "region-1",
            "line_id": "line-1",
            "source_span_id": line["source_span_id"],
            "text": "Aleksander Goldstein",
            "revision": 1,
        }
    ]
    assert title_matches["result_count"] == tag_matches["result_count"] == 1
    assert title_matches["results"][0]["source_span_id"] == line["source_span_id"]
    assert tag_matches["results"][0]["source_span_id"] == line["source_span_id"]

    assert (
        main(
            [
                "project-search",
                str(project),
                "Serock",
                "--field",
                "tag",
                "--limit",
                "1",
            ]
        )
        == 0
    )
    cli_report = json.loads(capsys.readouterr().out)
    assert cli_report["field"] == "tag"
    assert cli_report["limit"] == 1
    assert cli_report["network_required"] is False
    assert cli_report["results"][0]["text"] == "Aleksander Goldstein"

    assert main(["project-search", str(project), "gold", "--limit", "0"]) == 2
    assert "search limit must be an integer from 1 to 100" in capsys.readouterr().err


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



def test_project_keeps_human_transcription_revisions_separate_from_source(
    tmp_path: Path,
    capsys,
) -> None:
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

    assert (
        main(
            [
                "project-revise-line-transcription",
                str(project),
                "--manifest-sha256",
                imported["manifest_sha256"],
                "--source-span-id",
                line["source_span_id"],
                "--text",
                "Александръ",
                "--editor",
                "reviewer-1",
                "--expected-revision",
                "0",
            ]
        )
        == 0
    )
    saved = json.loads(capsys.readouterr().out)

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

    assert (
        main(
            [
                "project-activity",
                str(project),
                "--manifest-sha256",
                imported["manifest_sha256"],
                "--limit",
                "1",
            ]
        )
        == 0
    )
    activity = json.loads(capsys.readouterr().out)
    assert activity["manifest_sha256"] == imported["manifest_sha256"]
    assert activity["network_required"] is False
    assert len(activity["events"]) == 1
    assert activity["events"][0]["kind"] == "TRANSCRIPTION"
    assert activity["events"][0]["source_span_id"] == line["source_span_id"]
    assert activity["events"][0]["editor"] == "reviewer-1"
    assert "prior_text" not in activity["events"][0]
    assert "revised_text" not in activity["events"][0]

    assert (
        main(
            [
                "project-activity",
                str(project),
                "--manifest-sha256",
                imported["manifest_sha256"],
                "--limit",
                "0",
            ]
        )
        == 2
    )
    assert "activity limit must be an integer from 1 to 500" in capsys.readouterr().err

    assert (
        main(
            [
                "project-undo-line-transcription",
                str(project),
                "--manifest-sha256",
                imported["manifest_sha256"],
                "--source-span-id",
                line["source_span_id"],
                "--editor",
                "reviewer-1",
                "--expected-revision",
                "1",
            ]
        )
        == 0
    )
    undone = json.loads(capsys.readouterr().out)
    assert undone["status"] == "UNDONE"
    assert undone["revision"] == 2
    assert undone["undone_revision"] == 1
    restored = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )["lines"][0]
    assert restored["source_text"] == restored["text"] == "Александр"
    assert restored["revision"] == 2
    assert inspect_project(project)["transcription_revision_count"] == 2
    assert source.read_text(encoding="utf-8").count("Александр") == 1

    assert (
        main(
            [
                "project-undo-line-transcription",
                str(project),
                "--manifest-sha256",
                imported["manifest_sha256"],
                "--source-span-id",
                line["source_span_id"],
                "--editor",
                "reviewer-1",
                "--expected-revision",
                "1",
            ]
        )
        == 2
    )
    assert "transcription revision conflict" in capsys.readouterr().err


def test_project_activity_filters_revision_streams_and_locators(
    tmp_path: Path,
    capsys,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_two_region_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    manifest_sha256 = imported["manifest_sha256"]
    lines = load_project_page(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
    )["lines"]
    first_line = next(line for line in lines if line["region_id"] == "region-1")

    revise_line_transcription(
        project,
        manifest_sha256=manifest_sha256,
        source_span_id=first_line["source_span_id"],
        text="first revised",
        editor="text-reviewer",
        expected_revision=0,
    )
    revise_line_geometry(
        project,
        manifest_sha256=manifest_sha256,
        source_span_id=first_line["source_span_id"],
        polygon=[[1, 1], [39, 1], [39, 11], [1, 11]],
        baseline=[[2, 9], [38, 9]],
        editor="layout-reviewer",
        expected_revision=0,
    )
    revise_region_geometry(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
        region_id="region-2",
        polygon=[[1, 15], [39, 15], [39, 29], [1, 29]],
        editor="layout-reviewer",
        expected_revision=0,
    )
    revise_page_reading_order(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
        region_ids=["region-2", "region-1"],
        editor="layout-reviewer",
        expected_revision=0,
    )

    activity = list_project_activity(
        project,
        manifest_sha256=manifest_sha256,
        limit=10,
    )
    assert activity["filters"] == {
        "kind": None,
        "page_index": None,
        "source_span_id": None,
        "region_id": None,
    }
    assert {event["kind"] for event in activity["events"]} == {
        "TRANSCRIPTION",
        "LINE_GEOMETRY",
        "REGION_GEOMETRY",
        "READING_ORDER",
    }
    assert all("prior_text" not in event for event in activity["events"])
    assert all("revised_text" not in event for event in activity["events"])

    by_kind = list_project_activity(
        project,
        manifest_sha256=manifest_sha256,
        kind="line_geometry",
    )
    assert by_kind["filters"]["kind"] == "LINE_GEOMETRY"
    assert [event["kind"] for event in by_kind["events"]] == ["LINE_GEOMETRY"]

    by_source_span = list_project_activity(
        project,
        manifest_sha256=manifest_sha256,
        source_span_id=first_line["source_span_id"],
    )
    assert {event["kind"] for event in by_source_span["events"]} == {
        "TRANSCRIPTION",
        "LINE_GEOMETRY",
    }
    assert all(
        event["source_span_id"] == first_line["source_span_id"]
        for event in by_source_span["events"]
    )

    by_region = list_project_activity(
        project,
        manifest_sha256=manifest_sha256,
        region_id="region-2",
    )
    assert [event["kind"] for event in by_region["events"]] == ["REGION_GEOMETRY"]
    assert by_region["events"][0]["region_id"] == "region-2"

    assert (
        list_project_activity(
            project,
            manifest_sha256=manifest_sha256,
            page_index=1,
        )["events"]
        == []
    )

    assert (
        main(
            [
                "project-activity",
                str(project),
                "--manifest-sha256",
                manifest_sha256,
                "--kind",
                "line_geometry",
                "--page-index",
                "0",
                "--source-span-id",
                first_line["source_span_id"],
                "--region-id",
                "region-1",
            ]
        )
        == 0
    )
    filtered = json.loads(capsys.readouterr().out)
    assert filtered["filters"] == {
        "kind": "LINE_GEOMETRY",
        "page_index": 0,
        "source_span_id": first_line["source_span_id"],
        "region_id": "region-1",
    }
    assert [event["kind"] for event in filtered["events"]] == ["LINE_GEOMETRY"]

    with pytest.raises(ProjectStoreError, match="supported revision kind"):
        list_project_activity(
            project,
            manifest_sha256=manifest_sha256,
            kind="OTHER",
        )
    with pytest.raises(ProjectStoreError, match="non-negative integer"):
        list_project_activity(
            project,
            manifest_sha256=manifest_sha256,
            page_index=True,
        )
    with pytest.raises(ProjectStoreError, match="nonblank exact string"):
        list_project_activity(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=" ",
        )
    with pytest.raises(ProjectStoreError, match="nonblank exact string"):
        list_project_activity(
            project,
            manifest_sha256=manifest_sha256,
            region_id=" ",
        )


def test_project_cli_inspects_effective_pages_and_layout(
    tmp_path: Path,
    capsys,
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
    revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="Александръ",
        editor="reviewer-1",
        expected_revision=0,
    )
    revised_polygon = [[1, 1], [39, 1], [39, 16], [1, 16]]
    revise_line_geometry(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        polygon=revised_polygon,
        baseline=[[2, 13], [38, 13]],
        editor="layout-reviewer",
        expected_revision=0,
    )

    assert main(["project-list-pages", str(project)]) == 0
    inventory = json.loads(capsys.readouterr().out)
    assert inventory["status"] == "READY"
    assert inventory["page_count"] == 1
    assert inventory["network_required"] is False
    assert inventory["pages"][0]["manifest_sha256"] == imported["manifest_sha256"]
    assert inventory["pages"][0]["page_index"] == 0
    assert Path(inventory["pages"][0]["image_path"]).is_file()

    assert (
        main(
            [
                "project-show-page",
                str(project),
                "--manifest-sha256",
                imported["manifest_sha256"],
                "--page-index",
                "0",
            ]
        )
        == 0
    )
    page = json.loads(capsys.readouterr().out)
    expected_page = load_project_page(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
    )
    assert page == {**expected_page, "network_required": False}
    assert page["network_required"] is False
    assert page["lines"][0]["source_text"] == "Александр"
    assert page["lines"][0]["text"] == "Александръ"
    assert page["lines"][0]["revision"] == 1

    assert (
        main(
            [
                "project-show-page-layout",
                str(project),
                "--manifest-sha256",
                imported["manifest_sha256"],
                "--page-index",
                "0",
            ]
        )
        == 0
    )
    layout = json.loads(capsys.readouterr().out)
    assert layout["network_required"] is False
    assert layout["reading_order"]["revision"] == 0
    assert layout["lines"][0]["source_span_id"] == line["source_span_id"]
    assert layout["lines"][0]["revision"] == 1
    assert layout["lines"][0]["polygon"] == revised_polygon

    assert (
        main(
            [
                "project-show-page",
                str(project),
                "--manifest-sha256",
                imported["manifest_sha256"],
                "--page-index",
                "-1",
            ]
        )
        == 2
    )
    assert "page_index must be a non-negative integer" in capsys.readouterr().err



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


def test_project_derives_editable_kraken_layout_without_mutating_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_root = tmp_path / "unsegmented-images"
    source_root.mkdir()
    _write_image(source_root / "folio-01.png")
    _write_image(source_root / "folio-02.png")
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_images_into_project(project, source_root, title="Raw folios")

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
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        source = Path(command[command.index("-i") + 1])
        output = Path(command[command.index("-i") + 2])
        index = int(source.stem.rsplit("-", 1)[-1])
        output.write_text(
            f"""<PcGts>
  <Page id="segmented-{index}" imageFilename="{source.name}" imageWidth="40" imageHeight="30">
    <TextRegion id="region-{index}">
      <Coords points="0,0 40,0 40,30 0,30"/>
      <TextLine id="line-{index}">
        <Coords points="2,2 38,2 38,12 2,12"/>
        <Baseline points="2,10 38,10"/>
        <TextEquiv><Unicode></Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "local stdout", "local stderr")

    monkeypatch.setattr(kraken_module.subprocess, "run", fake_run)

    report = segment_project_with_kraken(
        project,
        manifest_sha256=imported["manifest_sha256"],
        kraken=kraken,
    )

    assert report["status"] == "SUCCEEDED"
    assert report["source_manifest_sha256"] == imported["manifest_sha256"]
    assert report["manifest_sha256"] != imported["manifest_sha256"]
    assert report["page_count"] == 2
    assert report["region_count"] == 2
    assert report["line_count"] == 2
    assert report["runtime_fingerprint"] == kraken.runtime_fingerprint
    assert len(report["pages"]) == 2
    assert report["document"]["title"] == "Raw folios — Kraken layout"
    assert report["document"]["tags"] == ["kraken-layout"]
    assert imported["manifest_sha256"] in report["document"]["notes"]
    assert str(source_root) not in report["document"]["notes"]

    source_document = next(
        item
        for item in list_project_documents(project)
        if item["manifest_sha256"] == imported["manifest_sha256"]
    )
    assert source_document["line_count"] == 0
    derived_page = load_project_page(
        project,
        manifest_sha256=report["manifest_sha256"],
        page_index=1,
    )
    assert derived_page["page_id"] == "segmented-1"
    assert derived_page["lines"][0]["line_id"] == "line-1"
    assert derived_page["lines"][0]["suggestions"] == []
    assert len(commands) == 2
    for command in commands:
        assert command[command.index("segment") + 1] == "-bl"
        assert "-m" not in command
        assert all("http://" not in item and "https://" not in item for item in command)


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


def test_project_document_update_refuses_a_stale_metadata_timestamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "register.xml"
    _write_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    original = list_project_documents(project)[0]
    timestamps = iter(("2026-08-23T12:00:01Z", "2026-08-23T12:00:02Z"))
    monkeypatch.setattr("aktreader.project._timestamp", lambda: next(timestamps))

    updated = update_project_document(
        project,
        manifest_sha256=imported["manifest_sha256"],
        title="Serock register",
        expected_updated_at=original["updated_at"],
    )
    assert updated["updated_at"] == "2026-08-23T12:00:01Z"

    with pytest.raises(ProjectRevisionConflictError, match="document metadata conflict"):
        update_project_document(
            project,
            manifest_sha256=imported["manifest_sha256"],
            notes="stale tab should not win",
            expected_updated_at=original["updated_at"],
        )

    stored = list_project_documents(project)[0]
    assert stored["title"] == "Serock register"
    assert stored["notes"] == ""
    assert stored["updated_at"] == "2026-08-23T12:00:01Z"

    with pytest.raises(ProjectStoreError, match="nonblank exact string"):
        update_project_document(
            project,
            manifest_sha256=imported["manifest_sha256"],
            notes="invalid token",
            expected_updated_at="  ",
        )


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



def test_project_exports_effective_human_transcriptions_as_text_and_csv(
    tmp_path: Path,
    capsys,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    recognized = source_root / "page.kraken.xml"
    _write_pagexml(source, text="source transcript")
    _write_pagexml(recognized, text="machine-only suggestion")
    source_bytes = source.read_bytes()
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    import_htr_suggestions(
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
    transcript_path = tmp_path / "serock.txt"
    csv_path = tmp_path / "serock.csv"

    initial_transcript = export_human_transcript(
        project,
        transcript_path,
        manifest_sha256=imported["manifest_sha256"],
    )
    initial_csv = export_human_transcriptions_csv(
        project,
        csv_path,
        manifest_sha256=imported["manifest_sha256"],
    )

    assert initial_transcript["human_revision_count"] == 0
    assert transcript_path.read_text(encoding="utf-8") == "source transcript\n"
    initial_rows = list(
        csv.DictReader(csv_path.open(encoding="utf-8", newline=""))
    )
    assert initial_csv["columns"] == [
        "manifest_sha256",
        "page_index",
        "page_id",
        "region_id",
        "line_id",
        "source_span_id",
        "source_text",
        "text",
        "revision",
        "editor",
    ]
    assert initial_rows == [
        {
            "manifest_sha256": imported["manifest_sha256"],
            "page_index": "0",
            "page_id": "page-index-0",
            "region_id": "region-1",
            "line_id": "line-1",
            "source_span_id": line["source_span_id"],
            "source_text": "source transcript",
            "text": "source transcript",
            "revision": "0",
            "editor": "",
        }
    ]

    revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="first human correction",
        editor="reviewer-1",
    )
    revise_line_transcription(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        text="final human correction",
        editor="reviewer-2",
    )
    transcript = export_human_transcript(
        project,
        transcript_path,
        manifest_sha256=imported["manifest_sha256"],
        replace_existing=True,
    )
    exported_csv = export_human_transcriptions_csv(
        project,
        csv_path,
        manifest_sha256=imported["manifest_sha256"],
        replace_existing=True,
    )

    assert transcript["human_revision_count"] == exported_csv["human_revision_count"] == 1
    assert transcript_path.read_text(encoding="utf-8") == "final human correction\n"
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8", newline="")))
    assert rows[0]["text"] == "final human correction"
    assert rows[0]["revision"] == "2"
    assert rows[0]["editor"] == "reviewer-2"
    assert source.read_bytes() == source_bytes

    cli_transcript = tmp_path / "cli-transcript.txt"
    transcript_exit = main(
        [
            "project-export-transcript",
            str(project),
            "--manifest-sha256",
            imported["manifest_sha256"],
            "--output",
            str(cli_transcript),
        ]
    )
    transcript_report = json.loads(capsys.readouterr().out)
    cli_csv = tmp_path / "cli-transcriptions.csv"
    csv_exit = main(
        [
            "project-export-transcriptions-csv",
            str(project),
            "--manifest-sha256",
            imported["manifest_sha256"],
            "--output",
            str(cli_csv),
        ]
    )
    csv_report = json.loads(capsys.readouterr().out)

    assert transcript_exit == csv_exit == 0
    assert transcript_report["output"] == str(cli_transcript.resolve())
    assert csv_report["output"] == str(cli_csv.resolve())
    assert cli_transcript.read_text(encoding="utf-8") == "final human correction\n"
    assert list(csv.DictReader(cli_csv.open(encoding="utf-8", newline="")))[0]["text"] == (
        "final human correction"
    )


def test_project_exports_current_human_content_and_layout_as_alto(
    tmp_path: Path,
    capsys,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_pagexml(source, text="source line")
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
        text="final human correction",
        editor="reviewer-1",
    )
    revise_line_geometry(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        polygon=[[1, 1], [39, 1], [39, 14], [1, 14]],
        baseline=[[1, 12], [39, 12]],
        editor="reviewer-1",
    )
    revise_region_geometry(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
        region_id="region-1",
        polygon=[[0, 0], [40, 0], [40, 29], [0, 29]],
        editor="reviewer-1",
    )
    alto_path = tmp_path / "serock.alto.xml"

    report = export_human_alto(
        project,
        alto_path,
        manifest_sha256=imported["manifest_sha256"],
    )

    assert report["status"] == "SUCCEEDED"
    assert report["source_pagexml_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert report["output_sha256"] == hashlib.sha256(alto_path.read_bytes()).hexdigest()
    assert report["page_count"] == report["line_count"] == report["human_revision_count"] == 1
    assert report["network_required"] is False
    assert source.read_bytes() == source_bytes
    namespace = {"alto": "http://www.loc.gov/standards/alto/ns-v4#"}
    alto = ET.fromstring(alto_path.read_bytes())
    page = alto.find("./alto:Layout/alto:Page", namespace)
    block = alto.find("./alto:Layout/alto:Page/alto:PrintSpace/alto:TextBlock", namespace)
    text_line = alto.find(
        "./alto:Layout/alto:Page/alto:PrintSpace/alto:TextBlock/alto:TextLine",
        namespace,
    )
    text = alto.find(
        "./alto:Layout/alto:Page/alto:PrintSpace/alto:TextBlock/alto:TextLine/alto:String",
        namespace,
    )

    assert page is not None
    assert page.attrib["PHYSICAL_IMG_NR"] == "1"
    assert page.attrib["WIDTH"] == "40"
    assert page.attrib["HEIGHT"] == "30"
    assert block is not None
    assert block.attrib["HEIGHT"] == "29"
    assert text_line is not None
    assert {
        key: text_line.attrib[key]
        for key in ("HPOS", "VPOS", "WIDTH", "HEIGHT")
    } == {"HPOS": "1", "VPOS": "1", "WIDTH": "38", "HEIGHT": "13"}
    assert text is not None
    assert text.attrib["CONTENT"] == "final human correction"

    cli_path = tmp_path / "serock-cli.alto.xml"
    exit_code = main(
        [
            "project-export-alto",
            str(project),
            "--manifest-sha256",
            imported["manifest_sha256"],
            "--output",
            str(cli_path),
        ]
    )
    cli_report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert cli_report["output"] == str(cli_path.resolve())
    assert ET.fromstring(cli_path.read_bytes()).find(
        ".//alto:String",
        namespace,
    ).attrib["CONTENT"] == "final human correction"



def test_project_exports_current_human_content_as_image_only_pdf(
    tmp_path: Path,
    capsys,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    recognized = source_root / "page.kraken.xml"
    _write_pagexml(source, text="source transcript")
    _write_pagexml(recognized, text="machine-only suggestion")
    source_bytes = source.read_bytes()
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    import_htr_suggestions(
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
        text="final human correction",
        editor="reviewer-1",
    )
    revise_line_geometry(
        project,
        manifest_sha256=imported["manifest_sha256"],
        source_span_id=line["source_span_id"],
        polygon=[[1, 1], [39, 1], [39, 14], [1, 14]],
        baseline=[[1, 12], [39, 12]],
        editor="reviewer-1",
    )
    pdf_path = tmp_path / "serock-human.pdf"

    report = export_human_pdf(
        project,
        pdf_path,
        manifest_sha256=imported["manifest_sha256"],
    )

    pdf_bytes = pdf_path.read_bytes()
    assert report["status"] == "SUCCEEDED"
    assert report["source_pagexml_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert report["output_sha256"] == hashlib.sha256(pdf_bytes).hexdigest()
    assert report["format"] == "PDF"
    assert report["page_count"] == report["line_count"] == report["human_revision_count"] == 1
    assert report["text_layer"] is False
    assert report["source_scans_included"] is False
    assert report["font_sha256"] is not None
    assert report["network_required"] is False
    assert pdf_bytes.startswith(b"%PDF")
    assert b"source transcript" not in pdf_bytes
    assert b"machine-only suggestion" not in pdf_bytes
    assert str(source_root).encode() not in pdf_bytes
    assert source.read_bytes() == source_bytes

    with pdfium.PdfDocument(pdf_path) as document:
        assert len(document) == 1
        page = document[0]
        try:
            bitmap = page.render(scale=50)
            try:
                rendered = bitmap.to_pil().copy()
            finally:
                bitmap.close()
        finally:
            page.close()
    try:
        grayscale = rendered.convert("L")
        try:
            assert grayscale.getextrema()[0] < 255
        finally:
            grayscale.close()
    finally:
        rendered.close()

    cli_path = tmp_path / "serock-cli.pdf"
    exit_code = main(
        [
            "project-export-pdf",
            str(project),
            "--manifest-sha256",
            imported["manifest_sha256"],
            "--output",
            str(cli_path),
        ]
    )
    cli_report = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert cli_report["output"] == str(cli_path.resolve())
    assert cli_report["text_layer"] is False
    assert cli_path.read_bytes().startswith(b"%PDF")

def test_project_alto_export_uses_current_region_reading_order(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_two_region_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    revise_page_reading_order(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
        region_ids=["region-2", "region-1"],
        editor="layout-reviewer",
    )
    alto_path = tmp_path / "serock-reading-order.alto.xml"

    export_human_alto(
        project,
        alto_path,
        manifest_sha256=imported["manifest_sha256"],
    )

    namespace = {"alto": "http://www.loc.gov/standards/alto/ns-v4#"}
    alto = ET.fromstring(alto_path.read_bytes())
    assert [
        string.attrib["CONTENT"]
        for string in alto.findall(
            "./alto:Layout/alto:Page/alto:PrintSpace/alto:TextBlock/alto:TextLine/alto:String",
            namespace,
        )
    ] == ["second", "first"]


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


def test_project_evaluates_one_htr_result_against_human_revisions(
    tmp_path: Path,
    capsys,
) -> None:
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

    assert (
        main(
            [
                "project-list-htr-evaluations",
                str(project),
                "--manifest-sha256",
                imported["manifest_sha256"],
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == []

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
    assert len(report["human_revision_set_sha256"]) == 64
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

    evaluations = list_htr_suggestion_evaluations(
        project,
        manifest_sha256=imported["manifest_sha256"],
    )
    assert len(evaluations) == 1
    assert evaluations[0]["result_pagexml_sha256"] == htr["result_pagexml_sha256"]
    assert evaluations[0]["engine"] == "kraken"
    assert evaluations[0]["character_error_rate"] == 1 / 3
    assert evaluations[0]["human_revision_set_sha256"] == report["human_revision_set_sha256"]
    assert isinstance(evaluations[0]["imported_at"], str)

    assert (
        main(
            [
                "project-list-htr-evaluations",
                str(project),
                "--manifest-sha256",
                imported["manifest_sha256"],
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == evaluations



def test_project_htr_evaluation_keeps_missing_suggestions_out_of_coverage(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    recognized = source_root / "page.kraken.xml"
    _write_pagexml(source, text="source text")
    _write_pagexml(recognized, text="")
    recognized.write_text(
        recognized.read_text(encoding="utf-8").replace(
            "<TextEquiv><Unicode></Unicode></TextEquiv>",
            "",
        ),
        encoding="utf-8",
    )
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    htr = import_htr_suggestions(
        project,
        recognized,
        manifest_sha256=imported["manifest_sha256"],
        engine="kraken",
        runtime_fingerprint="b" * 64,
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
        text="reviewed text",
        editor="reviewer-1",
    )

    report = evaluate_htr_suggestions(
        project,
        manifest_sha256=imported["manifest_sha256"],
        result_pagexml_sha256=htr["result_pagexml_sha256"],
    )

    assert report["status"] == "NO_EVALUABLE_HUMAN_REVISIONS"
    assert report["human_revision_count"] == 1
    assert report["suggestion_count_for_human_revisions"] == 0
    assert report["evaluated_line_count"] == 0


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
            "--expected-revision",
            "0",
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
            "--expected-revision",
            "0",
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


def test_project_cli_revises_line_geometry_with_revision_precondition(
    tmp_path: Path,
    capsys,
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
    geometry = tmp_path / "line-geometry.json"
    geometry.write_text(
        json.dumps(
            {
                "polygon": [[1, 1], [39, 1], [39, 16], [1, 16]],
                "baseline": [[2, 13], [38, 13]],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "project-revise-line-geometry",
            str(project),
            "--manifest-sha256",
            imported["manifest_sha256"],
            "--source-span-id",
            line["source_span_id"],
            "--geometry",
            str(geometry),
            "--editor",
            "layout-reviewer",
            "--expected-revision",
            "0",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["status"] == "SAVED"
    assert report["source_span_id"] == line["source_span_id"]
    assert report["revision"] == 1
    assert report["network_required"] is False


def test_project_layout_cli_rejects_stale_revision_preconditions(
    tmp_path: Path,
    capsys,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_two_region_pagexml(source)
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
        polygon=[[1, 1], [39, 1], [39, 14], [1, 14]],
        baseline=[[2, 12], [38, 12]],
        editor="first-reviewer",
        expected_revision=0,
    )
    revise_region_geometry(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
        region_id="region-2",
        polygon=[[1, 15], [39, 15], [39, 29], [1, 29]],
        editor="first-reviewer",
        expected_revision=0,
    )
    revise_page_reading_order(
        project,
        manifest_sha256=imported["manifest_sha256"],
        page_index=0,
        region_ids=["region-2", "region-1"],
        editor="first-reviewer",
        expected_revision=0,
    )

    line_geometry = tmp_path / "stale-line-geometry.json"
    line_geometry.write_text(
        json.dumps(
            {
                "polygon": [[2, 2], [38, 2], [38, 15], [2, 15]],
                "baseline": [[3, 13], [37, 13]],
            }
        ),
        encoding="utf-8",
    )
    region_geometry = tmp_path / "stale-region-geometry.json"
    region_geometry.write_text(
        json.dumps({"polygon": [[2, 16], [38, 16], [38, 28], [2, 28]]}),
        encoding="utf-8",
    )
    reading_order = tmp_path / "stale-reading-order.json"
    reading_order.write_text(
        json.dumps({"region_ids": ["region-1", "region-2"]}),
        encoding="utf-8",
    )

    cases = [
        (
            [
                "project-revise-line-geometry",
                str(project),
                "--manifest-sha256",
                imported["manifest_sha256"],
                "--source-span-id",
                line["source_span_id"],
                "--geometry",
                str(line_geometry),
                "--editor",
                "stale-reviewer",
                "--expected-revision",
                "0",
            ],
            "line geometry revision conflict",
        ),
        (
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
                str(region_geometry),
                "--editor",
                "stale-reviewer",
                "--expected-revision",
                "0",
            ],
            "region geometry revision conflict",
        ),
        (
            [
                "project-revise-page-reading-order",
                str(project),
                "--manifest-sha256",
                imported["manifest_sha256"],
                "--page-index",
                "0",
                "--region-order",
                str(reading_order),
                "--editor",
                "stale-reviewer",
                "--expected-revision",
                "0",
            ],
            "reading-order revision conflict",
        ),
    ]

    for command, conflict in cases:
        assert main(command) == 2
        assert conflict in capsys.readouterr().err

    summary = inspect_project(project)
    assert summary["line_geometry_revision_count"] == 1
    assert summary["region_geometry_revision_count"] == 1
    assert summary["page_reading_order_revision_count"] == 1


def test_project_undoes_layout_revisions_by_appending_restorations(
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
    manifest_sha256 = imported["manifest_sha256"]
    line = load_project_page(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
    )["lines"][0]
    source_span_id = line["source_span_id"]

    unavailable = [
        undo_line_geometry(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=source_span_id,
            expected_revision=0,
        ),
        undo_region_geometry(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            region_id="region-2",
            expected_revision=0,
        ),
        undo_page_reading_order(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            expected_revision=0,
        ),
    ]
    assert [item["status"] for item in unavailable] == [
        "UNDO_UNAVAILABLE",
        "UNDO_UNAVAILABLE",
        "UNDO_UNAVAILABLE",
    ]

    revise_line_geometry(
        project,
        manifest_sha256=manifest_sha256,
        source_span_id=source_span_id,
        polygon=[[1, 1], [39, 1], [39, 11], [1, 11]],
        baseline=[[2, 9], [38, 9]],
        editor="layout-reviewer",
        expected_revision=0,
    )
    revise_region_geometry(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
        region_id="region-2",
        polygon=[[1, 15], [39, 15], [39, 29], [1, 29]],
        editor="layout-reviewer",
        expected_revision=0,
    )
    revise_page_reading_order(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
        region_ids=["region-2", "region-1"],
        editor="layout-reviewer",
        expected_revision=0,
    )

    undone = [
        undo_line_geometry(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=source_span_id,
            editor="layout-reviewer",
            expected_revision=1,
        ),
        undo_region_geometry(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            region_id="region-2",
            editor="layout-reviewer",
            expected_revision=1,
        ),
        undo_page_reading_order(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            editor="layout-reviewer",
            expected_revision=1,
        ),
    ]

    assert [item["status"] for item in undone] == ["UNDONE", "UNDONE", "UNDONE"]
    assert [item["revision"] for item in undone] == [2, 2, 2]
    assert [item["undone_revision"] for item in undone] == [1, 1, 1]
    assert all(item["network_required"] is False for item in undone)
    layout = load_project_page_layout(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
    )
    restored_line = next(
        item for item in layout["lines"] if item["source_span_id"] == source_span_id
    )
    restored_region = next(
        item for item in layout["regions"] if item["region_id"] == "region-2"
    )
    assert restored_line["polygon"] == [[2, 2], [38, 2], [38, 10], [2, 10]]
    assert restored_line["baseline"] is None
    assert restored_line["revision"] == 2
    assert restored_region["polygon"] == [[0, 15], [40, 15], [40, 30], [0, 30]]
    assert restored_region["revision"] == 2
    assert layout["reading_order"] == {
        "revision": 2,
        "region_ids": ["region-1", "region-2"],
    }
    assert source.read_bytes() == source_bytes
    summary = inspect_project(project)
    assert summary["line_geometry_revision_count"] == 2
    assert summary["region_geometry_revision_count"] == 2
    assert summary["page_reading_order_revision_count"] == 2

    with pytest.raises(ProjectRevisionConflictError, match="line geometry revision conflict"):
        undo_line_geometry(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=source_span_id,
            expected_revision=1,
        )
    with pytest.raises(ProjectRevisionConflictError, match="region geometry revision conflict"):
        undo_region_geometry(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            region_id="region-2",
            expected_revision=1,
        )
    with pytest.raises(ProjectRevisionConflictError, match="reading-order revision conflict"):
        undo_page_reading_order(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            expected_revision=1,
        )


def test_project_layout_undo_cli_restores_all_three_revision_streams(
    tmp_path: Path,
    capsys,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_two_region_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    manifest_sha256 = imported["manifest_sha256"]
    line = load_project_page(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
    )["lines"][0]
    source_span_id = line["source_span_id"]

    revise_line_geometry(
        project,
        manifest_sha256=manifest_sha256,
        source_span_id=source_span_id,
        polygon=[[1, 1], [39, 1], [39, 11], [1, 11]],
        baseline=[[2, 9], [38, 9]],
        editor="layout-reviewer",
        expected_revision=0,
    )
    revise_region_geometry(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
        region_id="region-2",
        polygon=[[1, 15], [39, 15], [39, 29], [1, 29]],
        editor="layout-reviewer",
        expected_revision=0,
    )
    revise_page_reading_order(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
        region_ids=["region-2", "region-1"],
        editor="layout-reviewer",
        expected_revision=0,
    )

    commands = [
        [
            "project-undo-line-geometry",
            str(project),
            "--manifest-sha256",
            manifest_sha256,
            "--source-span-id",
            source_span_id,
            "--editor",
            "layout-reviewer",
            "--expected-revision",
            "1",
        ],
        [
            "project-undo-region-geometry",
            str(project),
            "--manifest-sha256",
            manifest_sha256,
            "--page-index",
            "0",
            "--region-id",
            "region-2",
            "--editor",
            "layout-reviewer",
            "--expected-revision",
            "1",
        ],
        [
            "project-undo-page-reading-order",
            str(project),
            "--manifest-sha256",
            manifest_sha256,
            "--page-index",
            "0",
            "--editor",
            "layout-reviewer",
            "--expected-revision",
            "1",
        ],
    ]

    reports = []
    for command in commands:
        assert main(command) == 0
        reports.append(json.loads(capsys.readouterr().out))

    assert [report["status"] for report in reports] == ["UNDONE", "UNDONE", "UNDONE"]
    assert [report["revision"] for report in reports] == [2, 2, 2]
    assert [report["undone_revision"] for report in reports] == [1, 1, 1]
    assert all(report["network_required"] is False for report in reports)
    layout = load_project_page_layout(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
    )
    assert layout["reading_order"]["region_ids"] == ["region-1", "region-2"]
    assert next(
        item["revision"] for item in layout["regions"] if item["region_id"] == "region-2"
    ) == 2
    assert next(
        item["revision"]
        for item in layout["lines"]
        if item["source_span_id"] == source_span_id
    ) == 2


def test_project_restores_any_prior_revision_by_appending_new_revisions(
    tmp_path: Path,
) -> None:
    project, source, manifest_sha256, source_span_id = _create_two_revision_streams(
        tmp_path
    )
    source_bytes = source.read_bytes()

    restored_revision = [
        restore_line_transcription(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=source_span_id,
            target_revision=1,
            editor="reviewer",
            expected_revision=2,
        ),
        restore_line_geometry(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=source_span_id,
            target_revision=1,
            editor="reviewer",
            expected_revision=2,
        ),
        restore_region_geometry(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            region_id="region-2",
            target_revision=1,
            editor="reviewer",
            expected_revision=2,
        ),
        restore_page_reading_order(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            target_revision=1,
            editor="reviewer",
            expected_revision=2,
        ),
    ]

    assert [item["status"] for item in restored_revision] == [
        "RESTORED",
        "RESTORED",
        "RESTORED",
        "RESTORED",
    ]
    assert [item["revision"] for item in restored_revision] == [3, 3, 3, 3]
    assert [item["target_revision"] for item in restored_revision] == [1, 1, 1, 1]
    assert all(item["network_required"] is False for item in restored_revision)
    restored_line = load_project_page(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
    )["lines"][0]
    restored_layout = load_project_page_layout(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
    )
    restored_line_layout = next(
        item
        for item in restored_layout["lines"]
        if item["source_span_id"] == source_span_id
    )
    restored_region = next(
        item
        for item in restored_layout["regions"]
        if item["region_id"] == "region-2"
    )
    assert restored_line["text"] == "first draft"
    assert restored_line["revision"] == 3
    assert restored_line_layout["polygon"] == [
        [1, 1],
        [39, 1],
        [39, 11],
        [1, 11],
    ]
    assert restored_line_layout["baseline"] == [[2, 9], [38, 9]]
    assert restored_line_layout["revision"] == 3
    assert restored_region["polygon"] == [
        [1, 15],
        [39, 15],
        [39, 29],
        [1, 29],
    ]
    assert restored_region["revision"] == 3
    assert restored_layout["reading_order"] == {
        "revision": 3,
        "region_ids": ["region-2", "region-1"],
    }

    restored_source = [
        restore_line_transcription(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=source_span_id,
            target_revision=0,
            editor="reviewer",
            expected_revision=3,
        ),
        restore_line_geometry(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=source_span_id,
            target_revision=0,
            editor="reviewer",
            expected_revision=3,
        ),
        restore_region_geometry(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            region_id="region-2",
            target_revision=0,
            editor="reviewer",
            expected_revision=3,
        ),
        restore_page_reading_order(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            target_revision=0,
            editor="reviewer",
            expected_revision=3,
        ),
    ]

    assert [item["status"] for item in restored_source] == [
        "RESTORED",
        "RESTORED",
        "RESTORED",
        "RESTORED",
    ]
    assert [item["revision"] for item in restored_source] == [4, 4, 4, 4]
    assert [item["target_revision"] for item in restored_source] == [0, 0, 0, 0]
    source_line = load_project_page(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
    )["lines"][0]
    source_layout = load_project_page_layout(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
    )
    source_line_layout = next(
        item
        for item in source_layout["lines"]
        if item["source_span_id"] == source_span_id
    )
    source_region = next(
        item for item in source_layout["regions"] if item["region_id"] == "region-2"
    )
    assert source_line["source_text"] == source_line["text"] == "first"
    assert source_line["revision"] == 4
    assert source_line_layout["polygon"] == [
        [2, 2],
        [38, 2],
        [38, 10],
        [2, 10],
    ]
    assert source_line_layout["baseline"] is None
    assert source_line_layout["revision"] == 4
    assert source_region["polygon"] == [
        [0, 15],
        [40, 15],
        [40, 30],
        [0, 30],
    ]
    assert source_region["revision"] == 4
    assert source_layout["reading_order"] == {
        "revision": 4,
        "region_ids": ["region-1", "region-2"],
    }
    assert source.read_bytes() == source_bytes
    summary = inspect_project(project)
    assert summary["transcription_revision_count"] == 4
    assert summary["line_geometry_revision_count"] == 4
    assert summary["region_geometry_revision_count"] == 4
    assert summary["page_reading_order_revision_count"] == 4

    unchanged = [
        restore_line_transcription(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=source_span_id,
            target_revision=0,
            expected_revision=4,
        ),
        restore_line_geometry(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=source_span_id,
            target_revision=0,
            expected_revision=4,
        ),
        restore_region_geometry(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            region_id="region-2",
            target_revision=0,
            expected_revision=4,
        ),
        restore_page_reading_order(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            target_revision=0,
            expected_revision=4,
        ),
    ]
    assert [item["status"] for item in unchanged] == [
        "UNCHANGED",
        "UNCHANGED",
        "UNCHANGED",
        "UNCHANGED",
    ]
    assert [item["revision"] for item in unchanged] == [4, 4, 4, 4]
    assert [item["target_revision"] for item in unchanged] == [0, 0, 0, 0]
    unchanged_summary = inspect_project(project)
    assert unchanged_summary["transcription_revision_count"] == 4
    assert unchanged_summary["line_geometry_revision_count"] == 4
    assert unchanged_summary["region_geometry_revision_count"] == 4
    assert unchanged_summary["page_reading_order_revision_count"] == 4

    with pytest.raises(ProjectRevisionConflictError, match="transcription revision conflict"):
        restore_line_transcription(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=source_span_id,
            target_revision=1,
            expected_revision=3,
        )
    with pytest.raises(ProjectRevisionConflictError, match="line geometry revision conflict"):
        restore_line_geometry(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=source_span_id,
            target_revision=1,
            expected_revision=3,
        )
    with pytest.raises(ProjectRevisionConflictError, match="region geometry revision conflict"):
        restore_region_geometry(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            region_id="region-2",
            target_revision=1,
            expected_revision=3,
        )
    with pytest.raises(ProjectRevisionConflictError, match="reading-order revision conflict"):
        restore_page_reading_order(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            target_revision=1,
            expected_revision=3,
        )
    with pytest.raises(ProjectStoreError, match="must be earlier"):
        restore_line_transcription(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=source_span_id,
            target_revision=4,
            expected_revision=4,
        )
    with pytest.raises(ProjectStoreError, match="non-negative integer"):
        restore_line_geometry(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=source_span_id,
            target_revision=True,
            expected_revision=4,
        )
    with pytest.raises(ProjectStoreError, match="non-negative integer"):
        restore_region_geometry(
            project,
            manifest_sha256=manifest_sha256,
            page_index=0,
            region_id="region-2",
            target_revision=-1,
            expected_revision=4,
        )


def test_project_restore_cli_covers_all_four_revision_streams(
    tmp_path: Path,
    capsys,
) -> None:
    project, _, manifest_sha256, source_span_id = _create_two_revision_streams(
        tmp_path
    )
    commands = [
        [
            "project-restore-line-transcription",
            str(project),
            "--manifest-sha256",
            manifest_sha256,
            "--source-span-id",
            source_span_id,
            "--target-revision",
            "1",
            "--editor",
            "reviewer",
            "--expected-revision",
            "2",
        ],
        [
            "project-restore-line-geometry",
            str(project),
            "--manifest-sha256",
            manifest_sha256,
            "--source-span-id",
            source_span_id,
            "--target-revision",
            "1",
            "--editor",
            "reviewer",
            "--expected-revision",
            "2",
        ],
        [
            "project-restore-region-geometry",
            str(project),
            "--manifest-sha256",
            manifest_sha256,
            "--page-index",
            "0",
            "--region-id",
            "region-2",
            "--target-revision",
            "1",
            "--editor",
            "reviewer",
            "--expected-revision",
            "2",
        ],
        [
            "project-restore-page-reading-order",
            str(project),
            "--manifest-sha256",
            manifest_sha256,
            "--page-index",
            "0",
            "--target-revision",
            "1",
            "--editor",
            "reviewer",
            "--expected-revision",
            "2",
        ],
    ]

    reports = []
    for command in commands:
        assert main(command) == 0
        reports.append(json.loads(capsys.readouterr().out))

    assert [report["status"] for report in reports] == [
        "RESTORED",
        "RESTORED",
        "RESTORED",
        "RESTORED",
    ]
    assert [report["revision"] for report in reports] == [3, 3, 3, 3]
    assert [report["target_revision"] for report in reports] == [1, 1, 1, 1]
    assert all(report["network_required"] is False for report in reports)
    page = load_project_page(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
    )
    layout = load_project_page_layout(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
    )
    assert page["lines"][0]["text"] == "first draft"
    assert layout["reading_order"]["region_ids"] == ["region-2", "region-1"]
    assert next(
        item["revision"]
        for item in layout["lines"]
        if item["source_span_id"] == source_span_id
    ) == 3
    assert next(
        item["revision"]
        for item in layout["regions"]
        if item["region_id"] == "region-2"
    ) == 3


def test_project_loads_targeted_contentful_revision_history_without_writes(
    tmp_path: Path,
) -> None:
    project, source, manifest_sha256, source_span_id = _create_two_revision_streams(
        tmp_path
    )
    source_bytes = source.read_bytes()
    summary_before = inspect_project(project)

    transcription = load_project_revision_history(
        project,
        manifest_sha256=manifest_sha256,
        kind="transcription",
        source_span_id=source_span_id,
    )
    line_geometry = load_project_revision_history(
        project,
        manifest_sha256=manifest_sha256,
        kind="LINE_GEOMETRY",
        source_span_id=source_span_id,
    )
    region_geometry = load_project_revision_history(
        project,
        manifest_sha256=manifest_sha256,
        kind="REGION_GEOMETRY",
        page_index=0,
        region_id="region-2",
    )
    reading_order = load_project_revision_history(
        project,
        manifest_sha256=manifest_sha256,
        kind="READING_ORDER",
        page_index=0,
    )

    assert transcription["kind"] == "TRANSCRIPTION"
    assert transcription["locator"] == {
        "page_index": 0,
        "page_id": "page-1",
        "region_id": "region-1",
        "line_id": "line-1",
        "source_span_id": source_span_id,
    }
    assert transcription["imported_state"] == {"text": "first"}
    assert transcription["current_revision"] == 2
    assert [item["revision"] for item in transcription["revisions"]] == [2, 1]
    assert transcription["revisions"][0]["prior_state"] == {"text": "first draft"}
    assert transcription["revisions"][0]["revised_state"] == {
        "text": "first approved"
    }
    assert transcription["revisions"][1]["prior_state"] == {"text": "first"}
    assert transcription["revisions"][1]["revised_state"] == {"text": "first draft"}
    assert transcription["contains_human_text"] is True
    assert transcription["content_included"] is True
    assert transcription["network_required"] is False

    assert line_geometry["locator"] == transcription["locator"]
    assert line_geometry["imported_state"] == {
        "polygon": [[2, 2], [38, 2], [38, 10], [2, 10]],
        "baseline": None,
    }
    assert line_geometry["current_revision"] == 2
    assert [item["revision"] for item in line_geometry["revisions"]] == [2, 1]
    assert line_geometry["revisions"][0]["prior_state"] == {
        "polygon": [[1, 1], [39, 1], [39, 11], [1, 11]],
        "baseline": [[2, 9], [38, 9]],
    }
    assert line_geometry["revisions"][0]["revised_state"] == {
        "polygon": [[1, 2], [39, 2], [39, 12], [1, 12]],
        "baseline": [[2, 10], [38, 10]],
    }
    assert line_geometry["contains_human_text"] is False

    assert region_geometry["locator"] == {
        "page_index": 0,
        "page_id": "page-1",
        "region_id": "region-2",
    }
    assert region_geometry["imported_state"] == {
        "polygon": [[0, 15], [40, 15], [40, 30], [0, 30]]
    }
    assert region_geometry["current_revision"] == 2
    assert [item["revision"] for item in region_geometry["revisions"]] == [2, 1]
    assert region_geometry["revisions"][0]["prior_state"] == {
        "polygon": [[1, 15], [39, 15], [39, 29], [1, 29]]
    }
    assert region_geometry["revisions"][0]["revised_state"] == {
        "polygon": [[2, 15], [38, 15], [38, 29], [2, 29]]
    }

    assert reading_order["locator"] == {"page_index": 0, "page_id": "page-1"}
    assert reading_order["imported_state"] == {
        "region_ids": ["region-1", "region-2"]
    }
    assert reading_order["current_revision"] == 2
    assert [item["revision"] for item in reading_order["revisions"]] == [2, 1]
    assert reading_order["revisions"][0]["prior_state"] == {
        "region_ids": ["region-2", "region-1"]
    }
    assert reading_order["revisions"][0]["revised_state"] == {
        "region_ids": ["region-1", "region-2"]
    }

    newest = load_project_revision_history(
        project,
        manifest_sha256=manifest_sha256,
        kind="TRANSCRIPTION",
        source_span_id=source_span_id,
        limit=1,
    )
    older = load_project_revision_history(
        project,
        manifest_sha256=manifest_sha256,
        kind="TRANSCRIPTION",
        source_span_id=source_span_id,
        limit=1,
        before_revision=2,
    )
    exhausted = load_project_revision_history(
        project,
        manifest_sha256=manifest_sha256,
        kind="TRANSCRIPTION",
        source_span_id=source_span_id,
        limit=1,
        before_revision=1,
    )
    assert [item["revision"] for item in newest["revisions"]] == [2]
    assert newest["pagination"] == {
        "limit": 1,
        "before_revision": None,
        "has_more": True,
        "next_before_revision": 2,
    }
    assert [item["revision"] for item in older["revisions"]] == [1]
    assert older["pagination"] == {
        "limit": 1,
        "before_revision": 2,
        "has_more": False,
        "next_before_revision": None,
    }
    assert exhausted["revisions"] == []
    assert exhausted["current_revision"] == 2

    activity = list_project_activity(
        project,
        manifest_sha256=manifest_sha256,
        source_span_id=source_span_id,
    )
    assert all(
        not ({"prior_state", "revised_state", "imported_state"} & set(event))
        for event in activity["events"]
    )
    assert source.read_bytes() == source_bytes
    assert inspect_project(project) == summary_before


def test_project_revision_history_reports_imported_state_before_any_edits(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    _write_image(source_root / "page.png")
    source = source_root / "page.xml"
    _write_two_region_pagexml(source)
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")
    imported = import_pagexml_into_project(project, source)
    manifest_sha256 = imported["manifest_sha256"]
    source_span_id = load_project_page(
        project,
        manifest_sha256=manifest_sha256,
        page_index=0,
    )["lines"][0]["source_span_id"]

    histories = [
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="TRANSCRIPTION",
            source_span_id=source_span_id,
        ),
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="LINE_GEOMETRY",
            source_span_id=source_span_id,
        ),
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="REGION_GEOMETRY",
            page_index=0,
            region_id="region-2",
        ),
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="READING_ORDER",
            page_index=0,
        ),
    ]

    assert [history["current_revision"] for history in histories] == [0, 0, 0, 0]
    assert [history["revisions"] for history in histories] == [[], [], [], []]
    assert all(history["pagination"]["has_more"] is False for history in histories)
    assert histories[0]["imported_state"] == {"text": "first"}
    assert histories[1]["imported_state"] == {
        "polygon": [[2, 2], [38, 2], [38, 10], [2, 10]],
        "baseline": None,
    }
    assert histories[2]["imported_state"] == {
        "polygon": [[0, 15], [40, 15], [40, 30], [0, 30]]
    }
    assert histories[3]["imported_state"] == {
        "region_ids": ["region-1", "region-2"]
    }


def test_project_revision_history_validates_exact_stream_locators(
    tmp_path: Path,
) -> None:
    project, _, manifest_sha256, source_span_id = _create_two_revision_streams(
        tmp_path
    )

    with pytest.raises(ProjectStoreError, match="supported revision kind"):
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="OTHER",
            source_span_id=source_span_id,
        )
    with pytest.raises(ProjectStoreError, match="requires one exact source_span_id"):
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="TRANSCRIPTION",
        )
    with pytest.raises(ProjectStoreError, match="accepts source_span_id only"):
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="LINE_GEOMETRY",
            source_span_id=source_span_id,
            page_index=0,
        )
    with pytest.raises(ProjectStoreError, match="requires a non-negative page_index"):
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="READING_ORDER",
        )
    with pytest.raises(ProjectStoreError, match="accepts page_index only"):
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="READING_ORDER",
            page_index=0,
            region_id="region-2",
        )
    with pytest.raises(ProjectStoreError, match="requires one exact region_id"):
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="REGION_GEOMETRY",
            page_index=0,
        )
    with pytest.raises(ProjectStoreError, match="accepts page_index and region_id only"):
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="REGION_GEOMETRY",
            page_index=0,
            region_id="region-2",
            source_span_id=source_span_id,
        )
    with pytest.raises(ProjectStoreError, match="limit must be an integer from 1 to 500"):
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="TRANSCRIPTION",
            source_span_id=source_span_id,
            limit=0,
        )
    with pytest.raises(ProjectStoreError, match="before_revision must be a positive integer"):
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="TRANSCRIPTION",
            source_span_id=source_span_id,
            before_revision=0,
        )
    with pytest.raises(ProjectStoreError, match="project line was not found"):
        load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind="TRANSCRIPTION",
            source_span_id="pagexml-missing",
        )


def test_project_revision_history_cli_covers_all_four_streams(
    tmp_path: Path,
    capsys,
) -> None:
    project, _, manifest_sha256, source_span_id = _create_two_revision_streams(
        tmp_path
    )
    commands = [
        [
            "project-show-revision-history",
            str(project),
            "--manifest-sha256",
            manifest_sha256,
            "--kind",
            "TRANSCRIPTION",
            "--source-span-id",
            source_span_id,
            "--limit",
            "1",
        ],
        [
            "project-show-revision-history",
            str(project),
            "--manifest-sha256",
            manifest_sha256,
            "--kind",
            "LINE_GEOMETRY",
            "--source-span-id",
            source_span_id,
            "--limit",
            "1",
        ],
        [
            "project-show-revision-history",
            str(project),
            "--manifest-sha256",
            manifest_sha256,
            "--kind",
            "REGION_GEOMETRY",
            "--page-index",
            "0",
            "--region-id",
            "region-2",
            "--limit",
            "1",
        ],
        [
            "project-show-revision-history",
            str(project),
            "--manifest-sha256",
            manifest_sha256,
            "--kind",
            "READING_ORDER",
            "--page-index",
            "0",
            "--limit",
            "1",
        ],
    ]

    reports = []
    for command in commands:
        assert main(command) == 0
        reports.append(json.loads(capsys.readouterr().out))

    assert [report["kind"] for report in reports] == [
        "TRANSCRIPTION",
        "LINE_GEOMETRY",
        "REGION_GEOMETRY",
        "READING_ORDER",
    ]
    assert [report["current_revision"] for report in reports] == [2, 2, 2, 2]
    assert [report["revisions"][0]["revision"] for report in reports] == [2, 2, 2, 2]
    assert all(report["pagination"]["has_more"] is True for report in reports)
    assert reports[0]["revisions"][0]["revised_state"] == {
        "text": "first approved"
    }
    assert reports[1]["revisions"][0]["revised_state"]["baseline"] == [
        [2, 10],
        [38, 10],
    ]
    assert reports[2]["revisions"][0]["revised_state"]["polygon"] == [
        [2, 15],
        [38, 15],
        [38, 29],
        [2, 29],
    ]
    assert reports[3]["revisions"][0]["revised_state"] == {
        "region_ids": ["region-1", "region-2"]
    }
