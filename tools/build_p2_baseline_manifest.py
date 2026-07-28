"""Build the scan-backed P2 baseline job manifest from immutable gold metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOLD_ACTS = ROOT / "gold" / "acts"
PROMPT_MANIFEST = ROOT / "prompts" / "manifest.json"
DEFAULT_OUTPUT = ROOT / "examples" / "p2-baseline.jobs.json"
CREATED_AT = "2026-07-28T15:39:23-04:00"
AUTHORITY_WARNING = "extraction is not authority — verify against the scan"
JPEG_START_OF_FRAME = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _image_dimensions(path: Path) -> tuple[int, int]:
    """Read PNG/JPEG dimensions without adding an image-library dependency."""
    with path.open("rb") as stream:
        header = stream.read(24)
        if header.startswith(b"\x89PNG\r\n\x1a\n") and header[12:16] == b"IHDR":
            return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
        if not header.startswith(b"\xff\xd8"):
            raise ValueError(f"unsupported baseline image format: {path}")
        stream.seek(2)
        while True:
            prefix = stream.read(1)
            if not prefix:
                break
            if prefix != b"\xff":
                continue
            marker_byte = stream.read(1)
            while marker_byte == b"\xff":
                marker_byte = stream.read(1)
            if not marker_byte:
                break
            marker = marker_byte[0]
            if marker in {0x01, *range(0xD0, 0xD9)}:
                continue
            length_bytes = stream.read(2)
            if len(length_bytes) != 2:
                break
            segment_length = int.from_bytes(length_bytes, "big")
            if segment_length < 2:
                raise ValueError(f"invalid JPEG segment length: {path}")
            if marker in JPEG_START_OF_FRAME:
                frame = stream.read(5)
                if len(frame) != 5:
                    break
                height = int.from_bytes(frame[1:3], "big")
                width = int.from_bytes(frame[3:5], "big")
                if width > 0 and height > 0:
                    return width, height
                break
            stream.seek(segment_length - 2, 1)
    raise ValueError(f"could not read image dimensions: {path}")


def _batch_brief(record: dict[str, Any], *, width: int, height: int) -> dict[str, Any]:
    prompt_header = _load_json(PROMPT_MANIFEST)["prompt_header"]
    register = record["register"]
    artifact = record["artifact"]
    return {
        "$schema": "schemas/reader-label-1.0.0.schema.json",
        "schema_version": "1.0.0",
        "label_id": f"{record['record_id']}.local-qwen35-p2-baseline",
        "record_id": record["record_id"],
        "created_at": CREATED_AT,
        "reader": {
            "reader_id": "local-qwen3.5-9b-q5-k-m",
            "reader_family": "qwen",
            "reader_version": "qwen3.5-9b-q5_k_m@unsloth-9f870da",
            "mode": "local",
            "blind_group_id": "p2-scan-backed-baseline-v1.2",
            "other_reader_output_seen": False,
        },
        "prompt": {
            "version": prompt_header["prompt_version"],
            "sha256": prompt_header["prompt_sha256"],
            "path": "prompts/reader_prompt.md",
        },
        "clerk_year": register["clerk_year"],
        "artifact": {
            "path": artifact["path"],
            "sha256": artifact["sha256"],
            "width_px": width,
            "height_px": height,
            "page_index": 0,
            "act_region": {
                "x": 0,
                "y": 0,
                "width": width,
                "height": height,
                "coordinate_space": "source_pixels",
            },
        },
        "target": {
            "town": register["town"],
            "fond": register["fond"],
            "year": register["year"],
            "act_type": register["act_type"],
            "act_no": register["act_no"],
            "language": register["language"],
        },
        "compliance": {
            "restricted_sources_used": False,
            "privacy_decision": "ALLOW",
            "privacy_basis": record["privacy"]["basis"],
            "training_eligible": False,
            "training_basis": "SerockBench gold holdout is evaluation-only; consent absent.",
        },
        "authority_warning": AUTHORITY_WARNING,
    }


def build_manifest() -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    records = [_load_json(path) for path in sorted(GOLD_ACTS.glob("*.json"))]
    for record in records:
        artifact = record["artifact"]
        if artifact["status"] != "LOCAL":
            excluded.append(
                {
                    "record_id": record["record_id"],
                    "reason": "gold artifact is NOT_LOCALIZED",
                }
            )
            continue
        scan = Path(artifact["path"])
        if not scan.is_file():
            raise FileNotFoundError(f"localized gold scan is missing: {scan}")
        actual_hash = _sha256(scan)
        if actual_hash != artifact["sha256"]:
            raise ValueError(
                f"gold scan hash mismatch for {record['record_id']}: "
                f"expected {artifact['sha256']}, observed {actual_hash}"
            )
        width, height = _image_dimensions(scan)
        register = record["register"]
        jobs.append(
            {
                "id": record["record_id"],
                "scan": artifact["path"],
                "act_type": register["act_type"],
                "year": register["year"],
                "target": {"kind": "act", "act_no": register["act_no"]},
                "metadata": {"batch_brief": _batch_brief(record, width=width, height=height)},
            }
        )

    return {
        "schema_version": "1.0.0",
        "profile_id": "p2-qwen3.5-9b-q5_k_m-f16",
        "created_at": CREATED_AT,
        "scope": {
            "gold_records": len(records),
            "scan_backed_jobs": len(jobs),
            "not_localized_exclusions": len(excluded),
            "coverage_ceiling": f"{len(jobs)}/{len(records)}",
        },
        "excluded": excluded,
        "jobs": jobs,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
