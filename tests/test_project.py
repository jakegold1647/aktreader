from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from PIL import Image

from aktreader.cli import main
from aktreader.pagexml import import_pagexml
from aktreader.project import (
    create_project,
    evaluate_htr_suggestions,
    export_human_pagexml,
    grant_training_consent,
    import_htr_suggestions,
    import_pagexml_into_project,
    inspect_project,
    list_project_pages,
    load_project_page,
    revise_line_transcription,
    revoke_training_consent,
    training_readiness,
)


def _write_image(path: Path) -> None:
    Image.new("L", (40, 30), color=255).save(path)


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


def test_project_migrates_v2_store_for_htr_suggestions(tmp_path: Path) -> None:
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock births")

    connection = sqlite3.connect(project / "project.sqlite3")
    try:
        with connection:
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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
    finally:
        connection.close()
