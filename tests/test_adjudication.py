import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from aktreader.adjudication import (
    CANT_TELL_CHOICE,
    AdjudicationError,
    generate_packet,
    ingest_answers,
    mine_lineup,
    select_questions,
)
from aktreader.cli import PROJECT_ROOT, main


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(image_path: Path, digest: str, x: int) -> dict[str, object]:
    return {
        "path": image_path.name,
        "sha256": digest,
        "bbox": {
            "x": x,
            "y": 0,
            "width": 12,
            "height": 12,
            "coordinate_space": "source_pixels",
        },
        "character_index": 0,
    }


def _wave_spec(tmp_path: Path) -> Path:
    image_path = tmp_path / "scan.png"
    Image.new("RGB", (120, 20), (240, 232, 214)).save(image_path)
    digest = _digest(image_path)
    candidates = [
        {
            "candidate_id": "candidate-b",
            "label": "Cyrillic б",
            "value": "Бобекъ",
            "glyph": "б",
            "consequence": "record the б reading as human-attested",
        },
        {
            "candidate_id": "candidate-d",
            "label": "Cyrillic д",
            "value": "Бодекъ",
            "glyph": "д",
            "consequence": "record the д reading as human-attested",
        },
    ]
    question = {
        "question_id": "q-act40-surname",
        "record_id": "serock-1890-death-40",
        "record_sha256": "a" * 64,
        "field_path": "principal.name",
        "clerk_year_id": "serock-1890-clerk",
        "selection_reason": "MACHINE_DEADLOCK",
        "claim": "The machines split evenly between two surname readings.",
        "question": "Does the disputed third letter match б or д?",
        "artifact": {
            **_artifact(image_path, digest, 0),
            "glyph_bbox": {
                "x": 3,
                "y": 1,
                "width": 5,
                "height": 10,
                "coordinate_space": "source_pixels",
            },
        },
        "magnification": 6,
        "candidates": candidates,
        "bilingual_anchors": [
            {
                "label": "Latin signature",
                "plain_text": "Josek Rubin...",
                "artifact": _artifact(image_path, digest, 96),
            }
        ],
        "structural_checks": [
            {
                "label": "Index cross-check",
                "result": "NEUTRAL",
                "interpretation": "The index is also ambiguous.",
            }
        ],
        "neither_consequence": "preserve unclear and route a third shape to expert review",
        "cant_tell_consequence": "preserve unclear and route to expert review",
    }
    exemplars = []
    for glyph, offset in (("б", 20), ("д", 56)):
        for index in range(3):
            exemplars.append(
                {
                    "exemplar_id": f"{ord(glyph)}-{index}",
                    "clerk_year_id": "serock-1890-clerk",
                    "glyph": glyph,
                    "label": f"reference word {index}",
                    "text": f"{glyph}word",
                    "confidence": "UNCONTESTED",
                    "artifact": _artifact(image_path, digest, offset + index * 12),
                }
            )
    exemplars.append(
        {
            "exemplar_id": "wrong-clerk",
            "clerk_year_id": "other-clerk",
            "glyph": "б",
            "label": "wrong clerk",
            "text": "бword",
            "confidence": "UNCONTESTED",
            "artifact": _artifact(image_path, digest, 8),
        }
    )
    payload = {
        "$schema": str(PROJECT_ROOT / "schemas" / "adjudication-wave-1.0.0.schema.json"),
        "schema_version": "1.0.0",
        "wave_id": "003",
        "title": "Wave 003 adjudication",
        "questions": [question],
        "exemplar_catalog": exemplars,
    }
    spec_path = tmp_path / "wave-003.json"
    spec_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return spec_path


def _completed_answers(packet_dir: Path, *, choice_id: str) -> dict[str, object]:
    template = json.loads((packet_dir / "answers.template.json").read_text(encoding="utf-8"))
    template["verifier"] = {
        "verifier_id": "owner",
        "script_expertise": "NON_READER",
        "correction_consent": {
            "status": "NOT_RECORDED",
            "training_eligible": False,
        },
    }
    template["answered_at"] = "2026-07-29T20:00:00-04:00"
    template["answers"][0] = {
        "question_id": "q-act40-surname",
        "choice_id": choice_id,
        "verbatim_answer": "the flag curls up and right",
        "interpretation": "the shape matches the б lineup",
        "methods": ["LETTERFORM_LINEUP"],
    }
    return template


def test_selection_keeps_mandatory_questions_and_excludes_transcription_queue() -> None:
    questions = [
        {"question_id": "optional", "selection_reason": "GOLD_SINGLE_COVERAGE"},
        {"question_id": "identity", "selection_reason": "IDENTITY_FORK"},
        {"question_id": "deadlock", "selection_reason": "MACHINE_DEADLOCK"},
        {"question_id": "queue", "selection_reason": "EXCLUDE_TRANSCRIPTION_QUEUE"},
    ]

    selected = select_questions(questions, max_questions=1)

    assert [item["question_id"] for item in selected] == ["identity", "deadlock"]


def test_lineup_miner_requires_same_clerk_uncontested_examples(tmp_path: Path) -> None:
    spec = json.loads(_wave_spec(tmp_path).read_text(encoding="utf-8"))

    lineup = mine_lineup(spec["questions"][0], spec["exemplar_catalog"])

    assert set(lineup) == {"candidate-b", "candidate-d"}
    assert all(len(items) == 3 for items in lineup.values())
    assert all(
        item["clerk_year_id"] == "serock-1890-clerk" for items in lineup.values() for item in items
    )


def test_generate_and_ingest_packet_are_offline_self_contained_and_immutable(
    tmp_path: Path,
) -> None:
    spec_path = _wave_spec(tmp_path)
    packet_dir = tmp_path / "packet"

    generated = generate_packet(
        project_root=PROJECT_ROOT,
        spec_path=spec_path,
        output_dir=packet_dir,
        wave_id="003",
    )

    packet = (packet_dir / "packet.html").read_text(encoding="utf-8")
    assert generated["status"] == "GENERATED"
    assert generated["network_required"] is False
    assert "data:image/png;base64," in packet
    assert "Neither / something else" in packet
    assert "Can't tell" in packet
    assert "proportional character segmentation" in packet
    questions = json.loads((packet_dir / "questions.json").read_text(encoding="utf-8"))
    assert questions["questions"][0]["lineup_exemplar_ids"] == {
        "candidate-b": ["1073-0", "1073-1", "1073-2"],
        "candidate-d": ["1076-0", "1076-1", "1076-2"],
    }

    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps(_completed_answers(packet_dir, choice_id="candidate-b"), ensure_ascii=False),
        encoding="utf-8",
    )
    original_packet = (packet_dir / "packet.html").read_bytes()
    (packet_dir / "packet.html").write_bytes(original_packet + b"<!-- tampered -->")
    with pytest.raises(AdjudicationError, match="packet HTML digest"):
        ingest_answers(
            project_root=PROJECT_ROOT,
            packet_dir=packet_dir,
            answers_path=answers_path,
        )
    (packet_dir / "packet.html").write_bytes(original_packet)
    ingested = ingest_answers(
        project_root=PROJECT_ROOT,
        packet_dir=packet_dir,
        answers_path=answers_path,
    )

    result_dir = Path(ingested["result_dir"])
    assert ingested["definitive_answer_count"] == 1
    assert ingested["expert_review_count"] == 0
    assert ingested["training_eligible_correction_count"] == 0
    assert ingested["label_mutations_performed"] is False
    attestation = json.loads(
        (result_dir / "gold-attestation-events.json").read_text(encoding="utf-8")
    )
    assert attestation["events"][0]["evidence_class"] == "VERIFIED_FROM_IMAGE"
    assert attestation["events"][0]["field_path"] == "principal.name"
    with pytest.raises(AdjudicationError, match="already ingested"):
        ingest_answers(
            project_root=PROJECT_ROOT,
            packet_dir=packet_dir,
            answers_path=answers_path,
        )


def test_cant_tell_routes_to_expert_without_correction(tmp_path: Path) -> None:
    spec_path = _wave_spec(tmp_path)
    packet_dir = tmp_path / "packet"
    generate_packet(
        project_root=PROJECT_ROOT,
        spec_path=spec_path,
        output_dir=packet_dir,
        wave_id="003",
    )
    answers_path = tmp_path / "cant-tell.json"
    answers_path.write_text(
        json.dumps(_completed_answers(packet_dir, choice_id=CANT_TELL_CHOICE)),
        encoding="utf-8",
    )

    report = ingest_answers(
        project_root=PROJECT_ROOT,
        packet_dir=packet_dir,
        answers_path=answers_path,
    )

    result_dir = Path(report["result_dir"])
    assert report["definitive_answer_count"] == 0
    assert report["expert_review_count"] == 1
    assert (result_dir / "correction-flywheel.jsonl").read_text(encoding="utf-8") == ""


def test_cli_generates_packet_and_refuses_unpinned_artifact(tmp_path: Path, capsys) -> None:
    spec_path = _wave_spec(tmp_path)
    output_dir = tmp_path / "cli-packet"

    exit_code = main(
        [
            "adjudicate",
            "--wave",
            "003",
            "--spec",
            str(spec_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["status"] == "GENERATED"
    tampered = json.loads(spec_path.read_text(encoding="utf-8"))
    tampered["questions"][0]["artifact"]["sha256"] = "0" * 64
    spec_path.write_text(json.dumps(tampered), encoding="utf-8")
    failure = main(
        [
            "adjudicate",
            "--wave",
            "003",
            "--spec",
            str(spec_path),
            "--output-dir",
            str(tmp_path / "bad-packet"),
        ]
    )
    assert failure == 2
    assert "sha256 mismatch" in capsys.readouterr().err
