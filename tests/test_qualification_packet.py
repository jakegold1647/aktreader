import hashlib
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from aktreader.human_gold import validate_human_transcription
from aktreader.qualification import QualificationPacketError, build_qualification_packet


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_manifest(tmp_path: Path, source: Path) -> Path:
    manifest = {
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
    }
    path = tmp_path / "source-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _manifest_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_builds_deterministic_blind_candidate_archives(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (20, 20), color=(240, 240, 240)).save(source)
    manifest = _source_manifest(tmp_path, source)

    first = build_qualification_packet(
        source_manifest_path=manifest,
        output_dir=tmp_path / "packet-one",
    )
    second = build_qualification_packet(
        source_manifest_path=manifest,
        output_dir=tmp_path / "packet-two",
    )

    assert first["machine_labels_included"] is False
    assert first["record_count"] == 1
    assert first["candidate_count"] == 3
    assert [item["sha256"] for item in first["candidate_archives"]] == [
        item["sha256"] for item in second["candidate_archives"]
    ]
    archive_path = tmp_path / "packet-one" / first["candidate_archives"][0]["path"]
    with zipfile.ZipFile(archive_path) as archive:
        assert set(archive.namelist()) == {
            "README.txt",
            "assignment.json",
            "images/synthetic-1890-death-1.png",
            "submissions/synthetic-1890-death-1.json",
        }
        assignment = json.loads(archive.read("assignment.json"))
        assert set(assignment["records"][0]) == {
            "record_id",
            "source_language",
            "artifact",
        }
        assert b"observations" not in archive.read("assignment.json")
        submission = json.loads(archive.read("submissions/synthetic-1890-death-1.json"))
        submission["submitted_at"] = "2026-07-30T00:00:00Z"
        submission["transcription"]["original_script"] = "Строка"
        submission["transcription"]["line_count"] = 1
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schemas/human-transcription-submission-1.0.0.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validate_human_transcription(submission, schema, qualification=True)


def test_refuses_bulkdata_source_even_when_hash_matches(tmp_path: Path) -> None:
    restricted = tmp_path / "BulkData"
    restricted.mkdir()
    source = restricted / "source.png"
    Image.new("RGB", (20, 20)).save(source)
    manifest = _source_manifest(tmp_path, source)

    with pytest.raises(QualificationPacketError, match="must not enter BulkData"):
        build_qualification_packet(
            source_manifest_path=manifest,
            output_dir=tmp_path / "packet",
        )


@pytest.mark.parametrize(
    ("field", "unsafe_value", "message"),
    [
        ("packet_id", "../escaped", "packet_id is not a portable identifier"),
        ("candidate_code", "../escaped", "candidate code is not a portable identifier"),
        ("record_id", "../../escaped", "record_id is not a portable identifier"),
        ("record_id", "con", "record_id is not a portable filename segment"),
    ],
)
def test_rejects_archive_unsafe_identifiers_before_writing_output(
    tmp_path: Path,
    field: str,
    unsafe_value: str,
    message: str,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (20, 20)).save(source)
    manifest = _source_manifest(tmp_path, source)
    payload = _manifest_payload(manifest)
    if field == "candidate_code":
        payload["candidate_codes"][1] = unsafe_value
    elif field == "record_id":
        payload["records"][0]["record_id"] = unsafe_value
    else:
        payload[field] = unsafe_value
    _write_manifest(manifest, payload)
    output = tmp_path / "packet"

    with pytest.raises(QualificationPacketError, match=message):
        build_qualification_packet(source_manifest_path=manifest, output_dir=output)

    assert not output.exists()
    assert not (tmp_path.parent / "escaped.png").exists()
    assert not (tmp_path.parent / "escaped.zip").exists()


def test_rejects_case_colliding_candidate_codes_before_writing_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (20, 20)).save(source)
    manifest = _source_manifest(tmp_path, source)
    payload = _manifest_payload(manifest)
    payload["candidate_codes"] = ["H1", "h1", "H3"]
    _write_manifest(manifest, payload)
    output = tmp_path / "packet"

    with pytest.raises(QualificationPacketError, match="case-insensitively unique"):
        build_qualification_packet(source_manifest_path=manifest, output_dir=output)

    assert not output.exists()


def test_rejects_duplicate_record_ids_before_writing_output(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (20, 20)).save(source)
    manifest = _source_manifest(tmp_path, source)
    payload = _manifest_payload(manifest)
    payload["records"].append(deepcopy(payload["records"][0]))
    _write_manifest(manifest, payload)
    output = tmp_path / "packet"

    with pytest.raises(
        QualificationPacketError,
        match="record IDs must be case-insensitively unique",
    ):
        build_qualification_packet(source_manifest_path=manifest, output_dir=output)

    assert not output.exists()
