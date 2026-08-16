from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from aktreader.htr_corpus import (
    HtrCorpusError,
    assemble_consented_training_corpus,
    inspect_consented_training_corpus,
)
from aktreader.pagexml import import_pagexml
from aktreader.project import (
    create_project,
    grant_training_consent,
    import_pagexml_into_project,
    inspect_project,
    load_project_page,
    revise_line_transcription,
)


def _write_source(source_root: Path, *, text: str) -> Path:
    source_root.mkdir(parents=True)
    image = source_root / "page.png"
    Image.new("L", (40, 30), color=255).save(image)
    source = source_root / "page.xml"
    source.write_text(
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
    return source


def _ready_project(tmp_path: Path, *, name: str, text: str) -> tuple[Path, str]:
    source = _write_source(tmp_path / f"{name}-source", text=text)
    project = tmp_path / f"{name}.aktproj"
    create_project(project, name=name)
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
        text=f"{text} reviewed",
        editor="reviewer-1",
    )
    grant_training_consent(
        project,
        manifest_sha256=imported["manifest_sha256"],
        contributor="reviewer-1",
        all_human_revised=True,
    )
    return project, imported["manifest_sha256"]


def _write_plan(
    path: Path,
    *,
    train_project: Path,
    train_manifest: str,
    validation_project: Path,
    validation_manifest: str,
) -> None:
    path.write_text(
        json.dumps(
            {
                "contract": {
                    "name": "aktreader-local-htr-corpus-plan",
                    "version": "1.0.0",
                },
                "inputs": [
                    {
                        "project": str(train_project.relative_to(path.parent)),
                        "manifest_sha256": train_manifest,
                        "split": "train",
                    },
                    {
                        "project": str(validation_project.relative_to(path.parent)),
                        "manifest_sha256": validation_manifest,
                        "split": "validation",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_assembles_current_consent_projects_into_explicit_kraken_corpus(tmp_path: Path) -> None:
    train_project, train_manifest = _ready_project(
        tmp_path,
        name="train",
        text="Александр",
    )
    validation_project, validation_manifest = _ready_project(
        tmp_path,
        name="validation",
        text="Екатерина",
    )
    plan = tmp_path / "corpus-plan.json"
    _write_plan(
        plan,
        train_project=train_project,
        train_manifest=train_manifest,
        validation_project=validation_project,
        validation_manifest=validation_manifest,
    )
    corpus = tmp_path / "corpus"

    report = assemble_consented_training_corpus(plan, corpus)

    manifest = json.loads((corpus / "corpus.aktreader.json").read_text(encoding="utf-8"))
    train_path = f"data/{train_manifest}/document.page.xml"
    validation_path = f"data/{validation_manifest}/document.page.xml"
    assert report["status"] == "SUCCEEDED"
    assert report["network_required"] is False
    assert report["split_pagexml_counts"] == {"train": 1, "validation": 1}
    assert manifest["contract"] == {
        "name": "aktreader-consented-pagexml-training-corpus",
        "version": "1.0.0",
    }
    assert manifest["source_plan_sha256"] == hashlib.sha256(plan.read_bytes()).hexdigest()
    assert manifest["splits"] == {
        "train": {"manifest": "train.lst", "pagexml_count": 1},
        "validation": {"manifest": "validation.lst", "pagexml_count": 1},
    }
    assert manifest["kraken"]["automatic_partitioning"] is False
    assert manifest["kraken"]["train_command"] == [
        "ketos",
        "train",
        "-f",
        "xml",
        "-t",
        "train.lst",
        "-e",
        "validation.lst",
    ]
    assert (corpus / "train.lst").read_text(encoding="utf-8") == f"{train_path}\n"
    assert (corpus / "validation.lst").read_text(encoding="utf-8") == f"{validation_path}\n"
    assert not (corpus / "bundles").exists()
    assert str(tmp_path) not in (corpus / "corpus.aktreader.json").read_text(encoding="utf-8")
    train_pagexml = import_pagexml(
        corpus / train_path,
        image_root=corpus / "data" / train_manifest,
    )
    assert train_pagexml["pages"][0]["lines"][0]["text"] == "Александр reviewed"
    inspected = inspect_consented_training_corpus(plan, corpus)

    assert inspected["status"] == "READY_FOR_LOCAL_KRAKEN_TRAINING"
    assert inspected["corpus_manifest_sha256"] == report["corpus_manifest_sha256"]
    assert inspected["network_required"] is False
    assert inspect_project(train_project)["training_split_assignment_count"] == 1
    assert inspect_project(validation_project)["training_split_assignment_count"] == 1


def test_corpus_rechecks_current_consent_before_writing_output(tmp_path: Path) -> None:
    train_project, train_manifest = _ready_project(
        tmp_path,
        name="train",
        text="Александр",
    )
    validation_project, validation_manifest = _ready_project(
        tmp_path,
        name="validation",
        text="Екатерина",
    )
    line = load_project_page(
        train_project,
        manifest_sha256=train_manifest,
        page_index=0,
    )["lines"][0]
    revise_line_transcription(
        train_project,
        manifest_sha256=train_manifest,
        source_span_id=line["source_span_id"],
        text="new revision without consent",
        editor="reviewer-1",
    )
    plan = tmp_path / "corpus-plan.json"
    _write_plan(
        plan,
        train_project=train_project,
        train_manifest=train_manifest,
        validation_project=validation_project,
        validation_manifest=validation_manifest,
    )
    corpus = tmp_path / "corpus"

    with pytest.raises(HtrCorpusError, match="not currently eligible for training export"):
        assemble_consented_training_corpus(plan, corpus)

    assert not corpus.exists()
    assert inspect_project(train_project)["training_split_assignment_count"] == 0


def test_corpus_rejects_one_source_pagexml_across_multiple_splits(tmp_path: Path) -> None:
    shared_source = _write_source(tmp_path / "shared-source", text="Александр")
    projects: list[tuple[Path, str]] = []
    for name in ("first", "second"):
        project = tmp_path / f"{name}.aktproj"
        create_project(project, name=name)
        imported = import_pagexml_into_project(project, shared_source)
        line = load_project_page(
            project,
            manifest_sha256=imported["manifest_sha256"],
            page_index=0,
        )["lines"][0]
        revise_line_transcription(
            project,
            manifest_sha256=imported["manifest_sha256"],
            source_span_id=line["source_span_id"],
            text="Александр reviewed",
            editor="reviewer-1",
        )
        grant_training_consent(
            project,
            manifest_sha256=imported["manifest_sha256"],
            contributor="reviewer-1",
            all_human_revised=True,
        )
        projects.append((project, imported["manifest_sha256"]))

    plan = tmp_path / "corpus-plan.json"
    _write_plan(
        plan,
        train_project=projects[0][0],
        train_manifest=projects[0][1],
        validation_project=projects[1][0],
        validation_manifest=projects[1][1],
    )

    with pytest.raises(HtrCorpusError, match="repeats a source PAGE XML"):
        assemble_consented_training_corpus(plan, tmp_path / "corpus")

    assert inspect_project(projects[0][0])["training_split_assignment_count"] == 0
    assert inspect_project(projects[1][0])["training_split_assignment_count"] == 0


def test_corpus_inspection_rejects_tampered_image_bytes(tmp_path: Path) -> None:
    train_project, train_manifest = _ready_project(
        tmp_path,
        name="train",
        text="Александр",
    )
    validation_project, validation_manifest = _ready_project(
        tmp_path,
        name="validation",
        text="Екатерина",
    )
    plan = tmp_path / "corpus-plan.json"
    _write_plan(
        plan,
        train_project=train_project,
        train_manifest=train_manifest,
        validation_project=validation_project,
        validation_manifest=validation_manifest,
    )
    corpus = tmp_path / "corpus"
    assemble_consented_training_corpus(plan, corpus)
    image = next((corpus / "data" / train_manifest / "images").iterdir())
    image.write_bytes(b"tampered training image")

    with pytest.raises(HtrCorpusError, match="image checksum mismatch"):
        inspect_consented_training_corpus(plan, corpus)
