"""Build blind, hash-pinned human qualification packets without label leakage."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections.abc import Iterable, Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from aktreader.batch import atomic_write_json
from aktreader.human_gold import HumanGoldSubmissionError, validate_human_transcription


class QualificationPacketError(ValueError):
    """Raised when a qualification packet cannot be built without provenance drift."""


class QualificationIntakeError(ValueError):
    """Raised when returned qualification work cannot enter adjudication."""


_PACKET_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]+")
_CANDIDATE_CODE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_RECORD_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]+")
_WINDOWS_DEVICE_NAMES = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def _zip_write(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, payload)


def _source_path(raw: Any, *, base: Path) -> Path:
    if not isinstance(raw, str) or not raw:
        raise QualificationPacketError("source path must be a non-empty string")
    path = Path(raw)
    resolved = path.resolve() if path.is_absolute() else (base / path).resolve()
    if any(part.casefold() == "bulkdata" for part in resolved.parts):
        raise QualificationPacketError("qualification sources must not enter BulkData")
    return resolved


def _portable_identifier(raw: Any, *, role: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(raw, str) or pattern.fullmatch(raw) is None:
        raise QualificationPacketError(f"{role} is not a portable identifier")
    if raw.split(".", 1)[0].casefold() in _WINDOWS_DEVICE_NAMES:
        raise QualificationPacketError(f"{role} is not a portable filename segment")
    return raw


def _require_casefold_unique(values: Iterable[str], *, role: str) -> None:
    seen: set[str] = set()
    for value in values:
        folded = value.casefold()
        if folded in seen:
            raise QualificationPacketError(f"{role} must be case-insensitively unique")
        seen.add(folded)


def build_qualification_packet(
    *,
    source_manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Crop verified source images and build one deterministic blind ZIP per candidate."""
    source_manifest_path = source_manifest_path.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise QualificationPacketError(f"output directory is not empty: {output_dir}")

    try:
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise QualificationPacketError("source manifest is not readable strict JSON") from error
    if not isinstance(source_manifest, Mapping):
        raise QualificationPacketError("source manifest must be an object")
    packet_id = _portable_identifier(
        source_manifest.get("packet_id"),
        role="packet_id",
        pattern=_PACKET_ID_PATTERN,
    )
    records = source_manifest.get("records")
    raw_candidate_codes = source_manifest.get("candidate_codes")
    if not isinstance(records, list) or not records:
        raise QualificationPacketError("source manifest requires records")
    if not isinstance(raw_candidate_codes, list) or len(raw_candidate_codes) < 3:
        raise QualificationPacketError("qualification requires at least three candidates")
    candidate_codes = [
        _portable_identifier(
            candidate_code,
            role="candidate code",
            pattern=_CANDIDATE_CODE_PATTERN,
        )
        for candidate_code in raw_candidate_codes
    ]
    _require_casefold_unique(candidate_codes, role="candidate codes")

    public_records: list[dict[str, Any]] = []
    image_payloads: dict[str, bytes] = {}
    record_ids: list[str] = []
    for entry in records:
        if not isinstance(entry, Mapping):
            raise QualificationPacketError("record entry must be an object")
        record_id = _portable_identifier(
            entry.get("record_id"),
            role="record_id",
            pattern=_RECORD_ID_PATTERN,
        )
        record_ids.append(record_id)
        source = entry.get("source")
        crop = entry.get("crop")
        if not isinstance(source, Mapping) or not isinstance(crop, Mapping):
            raise QualificationPacketError(f"{record_id}: source and crop must be objects")
        source_path = _source_path(source.get("path"), base=source_manifest_path.parent)
        if _sha256(source_path) != source.get("sha256"):
            raise QualificationPacketError(f"{record_id}: source SHA-256 mismatch")
        try:
            x = int(crop["x"])
            y = int(crop["y"])
            width = int(crop["width"])
            height = int(crop["height"])
        except (KeyError, TypeError, ValueError) as error:
            raise QualificationPacketError(f"{record_id}: invalid crop") from error
        if min(x, y) < 0 or min(width, height) <= 0:
            raise QualificationPacketError(f"{record_id}: invalid crop bounds")

        with Image.open(source_path) as image:
            if x + width > image.width or y + height > image.height:
                raise QualificationPacketError(f"{record_id}: crop exceeds source image")
            image_buffer = BytesIO()
            image.crop((x, y, x + width, y + height)).save(image_buffer, format="PNG")
        image_payload = image_buffer.getvalue()
        crop_sha = hashlib.sha256(image_payload).hexdigest()
        relative_image = f"images/{record_id}.png"
        image_payloads[relative_image] = image_payload
        public_records.append(
            {
                "record_id": record_id,
                "source_language": entry.get("source_language"),
                "artifact": {"path": relative_image, "sha256": crop_sha},
            }
        )
    _require_casefold_unique(record_ids, role="record IDs")

    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir()
    for name, payload in image_payloads.items():
        (output_dir / name).write_bytes(payload)

    readme = (
        b"Blind qualification packet. Do not use OCR or AI. Do not consult indexes or "
        b"other readers. Fill one JSON file per image, preserving original spelling and "
        b"line order. Use [illegible] and [unclear: candidate] rather than guessing.\n"
    )
    zip_receipts: list[dict[str, str]] = []
    for candidate_code in candidate_codes:
        assignment_id = f"{packet_id}-{candidate_code.casefold()}"
        assignment = {
            "schema_version": "1.0.0",
            "packet_id": packet_id,
            "candidate_code": candidate_code,
            "purpose": "QUALIFICATION_ONLY_EXCLUDED_FROM_GOLD_AND_TRAINING",
            "records": public_records,
        }
        zip_path = output_dir / f"{packet_id}-{candidate_code}.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            _zip_write(archive, "README.txt", readme)
            _zip_write(archive, "assignment.json", _json_bytes(assignment))
            for name, payload in sorted(image_payloads.items()):
                _zip_write(archive, name, payload)
            for record in public_records:
                submission = {
                    "$schema": "human-transcription-submission-1.0.0.schema.json",
                    "schema_version": "1.0.0",
                    "assignment_id": assignment_id,
                    "record_id": record["record_id"],
                    "artifact": record["artifact"],
                    "source_language": record["source_language"],
                    "worker": {
                        "worker_code": candidate_code,
                        "marketplace": "OTHER",
                        "independence_attested": True,
                        "machine_assistance_used": False,
                        "machine_assistance_detail": None,
                    },
                    "submitted_at": "REPLACE_WITH_ISO_8601_UTC",
                    "transcription": {
                        "original_script": "",
                        "line_count": 0,
                        "uncertainties": [],
                        "notes": [],
                    },
                    "authority_warning": ("extraction is not authority — verify against the scan"),
                }
                _zip_write(
                    archive,
                    f"submissions/{record['record_id']}.json",
                    _json_bytes(submission),
                )
        zip_receipts.append(
            {
                "candidate_code": candidate_code,
                "path": zip_path.name,
                "sha256": _sha256(zip_path),
            }
        )

    receipt = {
        "schema_version": "1.0.0",
        "packet_id": packet_id,
        "purpose": "QUALIFICATION_ONLY_EXCLUDED_FROM_GOLD_AND_TRAINING",
        "source_manifest": {
            "path": str(source_manifest_path),
            "sha256": _sha256(source_manifest_path),
        },
        "record_count": len(public_records),
        "candidate_count": len(candidate_codes),
        "records": public_records,
        "candidate_archives": zip_receipts,
        "candidate_codes": candidate_codes,
        "machine_labels_included": False,
    }
    atomic_write_json(output_dir / "receipt.json", receipt)
    return receipt


def _load_intake_object(path: Path, *, role: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise QualificationIntakeError(f"{role} is not readable strict JSON: {path}") from error
    if not isinstance(payload, dict):
        raise QualificationIntakeError(f"{role} must be a JSON object: {path}")
    return payload


def intake_qualification_submissions(
    *,
    receipt_path: Path,
    submission_schema_path: Path,
    submission_paths: Iterable[Path],
) -> dict[str, Any]:
    """Verify a complete blind qualification return matrix for adjudication."""
    receipt_path = receipt_path.resolve()
    submission_schema_path = submission_schema_path.resolve()
    receipt = _load_intake_object(receipt_path, role="qualification receipt")
    schema = _load_intake_object(submission_schema_path, role="submission schema")

    packet_id = receipt.get("packet_id")
    candidate_codes = receipt.get("candidate_codes")
    candidate_count = receipt.get("candidate_count")
    records = receipt.get("records")
    archives = receipt.get("candidate_archives")
    if not isinstance(packet_id, str) or not packet_id:
        raise QualificationIntakeError("qualification receipt requires packet_id")
    if (
        not isinstance(candidate_codes, list)
        or not candidate_codes
        or not all(isinstance(code, str) and code for code in candidate_codes)
        or len(candidate_codes) != len(set(candidate_codes))
    ):
        raise QualificationIntakeError("qualification receipt has invalid candidate_codes")
    if candidate_count != len(candidate_codes):
        raise QualificationIntakeError("qualification receipt candidate count mismatch")
    if not isinstance(archives, list) or len(archives) != len(candidate_codes):
        raise QualificationIntakeError("qualification receipt archive count mismatch")
    archive_codes = [
        archive.get("candidate_code") if isinstance(archive, Mapping) else None
        for archive in archives
    ]
    if archive_codes != candidate_codes:
        raise QualificationIntakeError("qualification receipt archive candidate pins mismatch")
    if not isinstance(records, list) or not records:
        raise QualificationIntakeError("qualification receipt requires records")
    if receipt.get("record_count") != len(records):
        raise QualificationIntakeError("qualification receipt record count mismatch")

    expected_records: dict[str, dict[str, Any]] = {}
    for raw_record in records:
        if not isinstance(raw_record, dict):
            raise QualificationIntakeError("qualification receipt record must be an object")
        record_id = raw_record.get("record_id")
        artifact = raw_record.get("artifact")
        source_language = raw_record.get("source_language")
        if not isinstance(record_id, str) or not record_id:
            raise QualificationIntakeError("qualification receipt record_id is invalid")
        if record_id in expected_records:
            raise QualificationIntakeError(f"duplicate receipt record: {record_id}")
        if not isinstance(artifact, dict) or source_language not in {"pl", "ru"}:
            raise QualificationIntakeError(f"{record_id}: invalid receipt artifact or language")
        expected_records[record_id] = raw_record

    expected_pairs = {
        (candidate_code, record_id)
        for candidate_code in candidate_codes
        for record_id in expected_records
    }
    observed_pairs: set[tuple[str, str]] = set()
    observed_paths: set[Path] = set()
    accepted: list[dict[str, Any]] = []
    for raw_path in submission_paths:
        path = Path(raw_path).resolve()
        if path in observed_paths:
            raise QualificationIntakeError(f"duplicate submission path: {path}")
        observed_paths.add(path)
        payload = _load_intake_object(path, role="qualification submission")
        try:
            validate_human_transcription(payload, schema, qualification=True)
        except HumanGoldSubmissionError as error:
            raise QualificationIntakeError(f"invalid submission {path}: {error}") from error

        worker = payload["worker"]
        candidate_code = worker["worker_code"]
        record_id = payload["record_id"]
        pair = (candidate_code, record_id)
        if candidate_code not in candidate_codes:
            raise QualificationIntakeError(f"unexpected candidate code: {candidate_code}")
        if record_id not in expected_records:
            raise QualificationIntakeError(f"unexpected record ID: {record_id}")
        expected_assignment = f"{packet_id}-{candidate_code.casefold()}"
        if payload["assignment_id"] != expected_assignment:
            raise QualificationIntakeError(f"{candidate_code}/{record_id}: assignment ID mismatch")
        expected_record = expected_records[record_id]
        if payload["artifact"] != expected_record["artifact"]:
            raise QualificationIntakeError(f"{candidate_code}/{record_id}: artifact pin mismatch")
        if payload["source_language"] != expected_record["source_language"]:
            raise QualificationIntakeError(
                f"{candidate_code}/{record_id}: source language mismatch"
            )
        if pair in observed_pairs:
            raise QualificationIntakeError(
                f"duplicate candidate/record submission: {candidate_code}/{record_id}"
            )
        observed_pairs.add(pair)
        accepted.append(
            {
                "candidate_code": candidate_code,
                "record_id": record_id,
                "assignment_id": payload["assignment_id"],
                "submitted_at": payload["submitted_at"],
                "path": str(path),
                "sha256": _sha256(path),
            }
        )

    missing = sorted(expected_pairs - observed_pairs)
    if missing:
        missing_text = ", ".join(f"{code}/{record_id}" for code, record_id in missing)
        raise QualificationIntakeError(f"qualification return matrix is incomplete: {missing_text}")
    extra = observed_pairs - expected_pairs
    if extra:
        extra_text = ", ".join(f"{code}/{record_id}" for code, record_id in sorted(extra))
        raise QualificationIntakeError(f"qualification return matrix has extras: {extra_text}")

    accepted.sort(key=lambda item: (item["candidate_code"], item["record_id"]))
    return {
        "schema_version": "1.0.0",
        "intake_id": f"{packet_id}-intake",
        "packet_id": packet_id,
        "purpose": "QUALIFICATION_RETURNS_READY_FOR_BLIND_ADJUDICATION",
        "status": "COMPLETE",
        "receipt": {"path": str(receipt_path), "sha256": _sha256(receipt_path)},
        "submission_schema": {
            "path": str(submission_schema_path),
            "sha256": _sha256(submission_schema_path),
        },
        "matrix": {
            "candidate_codes": candidate_codes,
            "record_ids": sorted(expected_records),
            "candidate_count": len(candidate_codes),
            "record_count": len(expected_records),
            "submission_count": len(accepted),
        },
        "submissions": accepted,
        "machine_assistance_detected": False,
        "machine_labels_included": False,
    }
