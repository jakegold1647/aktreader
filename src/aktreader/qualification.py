"""Build blind, hash-pinned human qualification packets without label leakage."""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image

from aktreader.batch import atomic_write_json


class QualificationPacketError(ValueError):
    """Raised when a qualification packet cannot be built without provenance drift."""


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
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir()

    try:
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise QualificationPacketError("source manifest is not readable strict JSON") from error
    if not isinstance(source_manifest, Mapping):
        raise QualificationPacketError("source manifest must be an object")
    records = source_manifest.get("records")
    candidate_codes = source_manifest.get("candidate_codes")
    if not isinstance(records, list) or not records:
        raise QualificationPacketError("source manifest requires records")
    if not isinstance(candidate_codes, list) or len(candidate_codes) < 3:
        raise QualificationPacketError("qualification requires at least three candidates")

    public_records: list[dict[str, Any]] = []
    image_payloads: dict[str, bytes] = {}
    for entry in records:
        if not isinstance(entry, Mapping):
            raise QualificationPacketError("record entry must be an object")
        record_id = entry.get("record_id")
        source = entry.get("source")
        crop = entry.get("crop")
        if not isinstance(record_id, str) or not record_id:
            raise QualificationPacketError("record_id must be non-empty")
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

        destination = images_dir / f"{record_id}.png"
        with Image.open(source_path) as image:
            if x + width > image.width or y + height > image.height:
                raise QualificationPacketError(f"{record_id}: crop exceeds source image")
            image.crop((x, y, x + width, y + height)).save(destination, format="PNG")
        crop_sha = _sha256(destination)
        relative_image = f"images/{destination.name}"
        image_payloads[relative_image] = destination.read_bytes()
        public_records.append(
            {
                "record_id": record_id,
                "source_language": entry.get("source_language"),
                "artifact": {"path": relative_image, "sha256": crop_sha},
            }
        )

    readme = (
        b"Blind qualification packet. Do not use OCR or AI. Do not consult indexes or "
        b"other readers. Fill one JSON file per image, preserving original spelling and "
        b"line order. Use [illegible] and [unclear: candidate] rather than guessing.\n"
    )
    zip_receipts: list[dict[str, str]] = []
    for candidate_code in candidate_codes:
        if not isinstance(candidate_code, str) or not candidate_code:
            raise QualificationPacketError("candidate codes must be non-empty strings")
        assignment = {
            "schema_version": "1.0.0",
            "packet_id": source_manifest.get("packet_id"),
            "candidate_code": candidate_code,
            "purpose": "QUALIFICATION_ONLY_EXCLUDED_FROM_GOLD_AND_TRAINING",
            "records": public_records,
        }
        zip_path = output_dir / f"{source_manifest.get('packet_id')}-{candidate_code}.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            _zip_write(archive, "README.txt", readme)
            _zip_write(archive, "assignment.json", _json_bytes(assignment))
            for name, payload in sorted(image_payloads.items()):
                _zip_write(archive, name, payload)
            for record in public_records:
                submission = {
                    "$schema": "human-transcription-submission-1.0.0.schema.json",
                    "schema_version": "1.0.0",
                    "assignment_id": f"{source_manifest.get('packet_id')}-{candidate_code}",
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
        zip_receipts.append({"path": zip_path.name, "sha256": _sha256(zip_path)})

    receipt = {
        "schema_version": "1.0.0",
        "packet_id": source_manifest.get("packet_id"),
        "purpose": "QUALIFICATION_ONLY_EXCLUDED_FROM_GOLD_AND_TRAINING",
        "source_manifest": {
            "path": str(source_manifest_path),
            "sha256": _sha256(source_manifest_path),
        },
        "record_count": len(public_records),
        "candidate_count": len(candidate_codes),
        "records": public_records,
        "candidate_archives": zip_receipts,
        "machine_labels_included": False,
    }
    atomic_write_json(output_dir / "receipt.json", receipt)
    return receipt
