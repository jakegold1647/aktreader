import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from aktreader.qualification import (
    QualificationIntakeError,
    build_qualification_packet,
    intake_qualification_submissions,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "human-transcription-submission-1.0.0.schema.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _complete_return_matrix(tmp_path: Path) -> tuple[Path, list[Path]]:
    source = tmp_path / "source.png"
    Image.new("RGB", (20, 20), color=(240, 240, 240)).save(source)
    manifest = tmp_path / "source-manifest.json"
    _write_json(
        manifest,
        {
            "schema_version": "1.0.0",
            "packet_id": "qualification-test",
            "candidate_codes": ["H1", "H2", "H3"],
            "records": [
                {
                    "record_id": "synthetic-1890-death-1",
                    "source_language": "ru",
                    "source": {"path": str(source), "sha256": _sha256(source)},
                    "crop": {"x": 2, "y": 3, "width": 10, "height": 8},
                }
            ],
        },
    )
    packet_dir = tmp_path / "packet"
    receipt = build_qualification_packet(
        source_manifest_path=manifest,
        output_dir=packet_dir,
    )

    paths: list[Path] = []
    for archive_receipt in receipt["candidate_archives"]:
        candidate_code = archive_receipt["candidate_code"]
        archive_path = packet_dir / archive_receipt["path"]
        with zipfile.ZipFile(archive_path) as archive:
            payload = json.loads(archive.read("submissions/synthetic-1890-death-1.json"))
        payload["submitted_at"] = "2026-07-30T01:00:00Z"
        payload["transcription"]["original_script"] = "Строка"
        payload["transcription"]["line_count"] = 1
        destination = tmp_path / "returns" / candidate_code / "submission.json"
        _write_json(destination, payload)
        paths.append(destination)
    return packet_dir / "receipt.json", paths


def test_complete_qualification_return_matrix_is_content_addressed(tmp_path: Path) -> None:
    receipt_path, paths = _complete_return_matrix(tmp_path)

    report = intake_qualification_submissions(
        receipt_path=receipt_path,
        submission_schema_path=SCHEMA,
        submission_paths=paths,
    )

    assert report["status"] == "COMPLETE"
    assert report["matrix"] == {
        "candidate_codes": ["H1", "H2", "H3"],
        "record_ids": ["synthetic-1890-death-1"],
        "candidate_count": 3,
        "record_count": 1,
        "submission_count": 3,
    }
    assert [item["candidate_code"] for item in report["submissions"]] == [
        "H1",
        "H2",
        "H3",
    ]
    assert all(len(item["sha256"]) == 64 for item in report["submissions"])
    assert report["machine_assistance_detected"] is False


def test_incomplete_qualification_return_matrix_fails_closed(tmp_path: Path) -> None:
    receipt_path, paths = _complete_return_matrix(tmp_path)

    with pytest.raises(QualificationIntakeError, match="matrix is incomplete"):
        intake_qualification_submissions(
            receipt_path=receipt_path,
            submission_schema_path=SCHEMA,
            submission_paths=paths[:-1],
        )


def test_qualification_intake_rejects_artifact_pin_drift(tmp_path: Path) -> None:
    receipt_path, paths = _complete_return_matrix(tmp_path)
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    payload["artifact"]["sha256"] = "0" * 64
    _write_json(paths[0], payload)

    with pytest.raises(QualificationIntakeError, match="artifact pin mismatch"):
        intake_qualification_submissions(
            receipt_path=receipt_path,
            submission_schema_path=SCHEMA,
            submission_paths=paths,
        )


def test_qualification_intake_rejects_assignment_mismatch(tmp_path: Path) -> None:
    receipt_path, paths = _complete_return_matrix(tmp_path)
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    payload["assignment_id"] = "qualification-test-h9"
    _write_json(paths[0], payload)

    with pytest.raises(QualificationIntakeError, match="assignment ID mismatch"):
        intake_qualification_submissions(
            receipt_path=receipt_path,
            submission_schema_path=SCHEMA,
            submission_paths=paths,
        )


def test_qualification_intake_rejects_duplicate_worker_record(tmp_path: Path) -> None:
    receipt_path, paths = _complete_return_matrix(tmp_path)
    duplicate = tmp_path / "returns" / "duplicate.json"
    shutil.copyfile(paths[0], duplicate)

    with pytest.raises(QualificationIntakeError, match="duplicate candidate/record"):
        intake_qualification_submissions(
            receipt_path=receipt_path,
            submission_schema_path=SCHEMA,
            submission_paths=[*paths, duplicate],
        )
