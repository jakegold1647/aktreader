"""Read-only retro-audit of coverage and groundedness across frozen label sets."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aktreader.grounding import CYRILLIC_RE
from aktreader.labels import (
    AUTHORITY_WARNING,
    LabelValidationError,
    ReaderLabel,
    load_reader_label,
    parse_legacy_reader_a,
)

SPACE_RE = re.compile(r"\s+")
AUDIT_VERSION = "1.0.0"


@dataclass(frozen=True)
class AuditRecord:
    record_id: str
    language: str
    transcription: str
    observations: Mapping[str, Mapping[str, Any]]
    source_path: Path


@dataclass(frozen=True)
class AuditGroup:
    group_id: str
    source_kind: str
    paths: tuple[Path, ...]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalized_text(value: str) -> str:
    return SPACE_RE.sub(" ", unicodedata.normalize("NFC", value)).strip().casefold()


def _legacy_index_record(path: Path, payload: Mapping[str, Any]) -> AuditRecord:
    register = payload.get("register")
    entries = payload.get("entries")
    if not isinstance(register, Mapping) or not isinstance(entries, list):
        raise ValueError(f"{path}: invalid legacy index label shape")
    observations: dict[str, Mapping[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            continue
        confidence = entry.get("confidence", "PROBABLE")
        for key in ("surname_as_written", "given_name", "act_no"):
            value = entry.get(key)
            if value is None:
                continue
            original = value if key != "act_no" and isinstance(value, str) else None
            observations[f"entries.{index}.{key}"] = {
                "value": value,
                "original_script": original,
                "confidence": confidence,
                "observation_state": "PRESENT",
            }
    return AuditRecord(
        record_id=path.stem,
        language=str(register.get("language", "ru")),
        transcription="",
        observations=observations,
        source_path=path,
    )

def _reader_record(path: Path) -> AuditRecord:
    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    if raw_payload.get("schema_version") is None and "entries" in raw_payload:
        return _legacy_index_record(path, raw_payload)
    try:
        label: ReaderLabel = load_reader_label(path)
    except LabelValidationError as error:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload.get("schema_version") is None
            and "authority_warning" in str(error)
        ):
            adapted = copy.deepcopy(payload)
            adapted["authority_warning"] = AUTHORITY_WARNING
            label = parse_legacy_reader_a(adapted, source_path=str(path))
        else:
            raise ValueError(f"{path}: {error}") from error
    transcription = label.raw.get("transcription")
    original = transcription.get("original_script") if isinstance(transcription, Mapping) else ""
    return AuditRecord(
        record_id=label.record_id,
        language=str(label.target.get("language", "")),
        transcription=original if isinstance(original, str) else "",
        observations=label.observations,
        source_path=path,
    )


def _silver_record(path: Path) -> AuditRecord:
    payload = json.loads(path.read_text(encoding="utf-8"))
    target = payload.get("target")
    observations = payload.get("observations")
    if not isinstance(target, Mapping) or not isinstance(observations, Mapping):
        raise ValueError(f"{path}: invalid silver record shape")
    return AuditRecord(
        record_id=str(payload.get("record_id", path.stem)),
        language=str(target.get("language", "")),
        transcription="",
        observations={
            str(field_path): evidence
            for field_path, evidence in observations.items()
            if isinstance(evidence, Mapping)
        },
        source_path=path,
    )


def _walk_gold_fields(
    value: Any,
    path: str,
    output: dict[str, Mapping[str, Any]],
) -> None:
    if isinstance(value, Mapping) and {
        "value",
        "original_script",
        "observation_state",
    }.issubset(value):
        output[path] = value
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            _walk_gold_fields(child, child_path, output)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}.{index}" if path else str(index)
            _walk_gold_fields(child, child_path, output)


def _gold_record(path: Path) -> AuditRecord:
    payload = json.loads(path.read_text(encoding="utf-8"))
    register = payload.get("register")
    fields = payload.get("fields")
    if not isinstance(register, Mapping) or not isinstance(fields, Mapping):
        raise ValueError(f"{path}: invalid gold record shape")
    observations: dict[str, Mapping[str, Any]] = {}
    _walk_gold_fields(fields, "", observations)
    return AuditRecord(
        record_id=str(payload.get("record_id", path.stem)),
        language=str(register.get("language", "")),
        transcription="",
        observations=observations,
        source_path=path,
    )


def _load_record(path: Path, source_kind: str) -> AuditRecord:
    if source_kind == "reader":
        return _reader_record(path)
    if source_kind == "silver":
        return _silver_record(path)
    if source_kind == "gold":
        return _gold_record(path)
    raise ValueError(f"unknown source kind {source_kind!r}")


def _audit_records(records: Sequence[AuditRecord]) -> dict[str, Any]:
    reported = 0
    present = 0
    cyrillic_applicable = 0
    cyrillic_supported = 0
    transcription_supported = 0
    fully_grounded = 0
    violation_codes: Counter[str] = Counter()
    affected_records: set[str] = set()

    for record in records:
        transcription = _normalized_text(record.transcription)
        requires_cyrillic = record.language.casefold() == "ru"
        for evidence in record.observations.values():
            reported += 1
            if evidence.get("observation_state") != "PRESENT":
                continue
            present += 1
            original = evidence.get("original_script")
            original_text = original if isinstance(original, str) else ""
            cyrillic_ok = not requires_cyrillic or bool(CYRILLIC_RE.search(original_text))
            if requires_cyrillic:
                cyrillic_applicable += 1
                cyrillic_supported += int(cyrillic_ok)
                if not cyrillic_ok:
                    violation_codes["PRESENT_RU_ORIGINAL_SCRIPT_HAS_NO_CYRILLIC"] += 1
                    affected_records.add(record.record_id)
            normalized_original = _normalized_text(original_text)
            transcription_ok = bool(
                normalized_original
                and transcription
                and normalized_original in transcription
            )
            transcription_supported += int(transcription_ok)
            if not transcription_ok:
                violation_codes["PRESENT_ORIGINAL_SCRIPT_NOT_IN_TRANSCRIPTION"] += 1
                affected_records.add(record.record_id)
            fully_grounded += int(cyrillic_ok and transcription_ok)

    def rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 6) if denominator else 1.0

    return {
        "status": "FAIL" if violation_codes else "PASS",
        "quality_metrics": {
            "coverage": {
                "record_count": len(records),
                "reported_observation_count": reported,
                "present_observation_count": present,
                "non_present_observation_count": reported - present,
                "present_rate": rate(present, reported),
            },
            "groundedness": {
                "present_observation_count": present,
                "cyrillic_applicable_count": cyrillic_applicable,
                "cyrillic_supported_count": cyrillic_supported,
                "transcription_supported_count": transcription_supported,
                "fully_grounded_count": fully_grounded,
                "violation_count": sum(violation_codes.values()),
                "affected_record_count": len(affected_records),
                "groundedness_rate": rate(fully_grounded, present),
            },
        },
        "violation_codes": dict(sorted(violation_codes.items())),
    }


def inventory(root: Path) -> tuple[AuditGroup, ...]:
    reader_a = root / "labels" / "readerA"
    reader_b = root / "labels" / "readerB"

    def deaths(base: Path, act_numbers: Sequence[int]) -> tuple[Path, ...]:
        return tuple(base / f"serock-1890-death-{number}.json" for number in act_numbers)

    groups = (
        AuditGroup("wave-001-reader-a", "reader", deaths(reader_a, range(1, 3))),
        AuditGroup("wave-001-reader-b", "reader", deaths(reader_b, range(1, 3))),
        AuditGroup("wave-002-reader-a", "reader", deaths(reader_a, range(3, 7))),
        AuditGroup("wave-002-reader-b", "reader", deaths(reader_b, range(3, 7))),
        AuditGroup("wave-003-reader-a", "reader", deaths(reader_a, range(30, 41))),
        AuditGroup("wave-003-reader-b", "reader", deaths(reader_b, range(30, 41))),
        AuditGroup(
            "wave-004-reader-a",
            "reader",
            deaths(reader_a, range(41, 50)) + (reader_a / "serock-1890-skz-index.json",),
        ),
        AuditGroup(
            "wave-004-reader-b",
            "reader",
            deaths(reader_b, range(41, 50)) + (reader_b / "serock-1890-skz-index.json",),
        ),
        AuditGroup(
            "silver-records",
            "silver",
            tuple(sorted((root / "labels" / "silver" / "records").glob("*.json"))),
        ),
        AuditGroup(
            "gold-acts",
            "gold",
            tuple(sorted((root / "gold" / "acts").glob("*.json"))),
        ),
    )
    for group in groups:
        if not group.paths:
            raise FileNotFoundError(f"{group.group_id}: no files")
        missing = [path for path in group.paths if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                f"{group.group_id}: missing {', '.join(str(path) for path in missing)}"
            )
    return groups


def build_report(root: Path) -> dict[str, Any]:
    root = root.resolve()
    group_reports: list[dict[str, Any]] = []
    for group in inventory(root):
        records = tuple(_load_record(path, group.source_kind) for path in group.paths)
        audit = _audit_records(records)
        group_reports.append(
            {
                "group_id": group.group_id,
                "source_kind": group.source_kind,
                "files": [
                    {
                        "path": path.relative_to(root).as_posix(),
                        "sha256": _sha256_file(path),
                    }
                    for path in group.paths
                ],
                **audit,
            }
        )
    return {
        "audit_version": AUDIT_VERSION,
        "policy": {
            "coverage": "PRESENT observations / all reported evidence leaves",
            "groundedness": (
                "PRESENT observations satisfying applicable Cyrillic presence and "
                "continuous-transcription substring support"
            ),
            "labels_modified": False,
        },
        "groups": group_reports,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Groundedness retro-audit — 2026-07-29",
        "",
        "This is a read-only audit. No label was modified. Coverage and groundedness are",
        "reported together; groundedness requires both applicable Cyrillic presence and",
        "continuous-transcription substring support for every PRESENT assertion.",
        "",
        "| Label set | Records | Reported | PRESENT | Coverage | Cyrillic | Transcript | "
        "Fully grounded | Groundedness | Violations |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group in report["groups"]:
        quality = group["quality_metrics"]
        coverage = quality["coverage"]
        grounding = quality["groundedness"]
        lines.append(
            f"| {group['group_id']} | {coverage['record_count']} | "
            f"{coverage['reported_observation_count']} | "
            f"{coverage['present_observation_count']} | "
            f"{coverage['present_rate']:.1%} | "
            f"{grounding['cyrillic_supported_count']}/"
            f"{grounding['cyrillic_applicable_count']} | "
            f"{grounding['transcription_supported_count']}/"
            f"{grounding['present_observation_count']} | "
            f"{grounding['fully_grounded_count']} | "
            f"{grounding['groundedness_rate']:.1%} | "
            f"{grounding['violation_count']} |"
        )
    lines.extend(
        [
            "",
            "A zero transcription-support score means the stored format has no continuous",
            "transcription or no PRESENT excerpt occurs in it. The audit does not synthesize",
            "a transcription from field claims and does not infer that unsupported claims are",
            "factually wrong; it records that their evidence is insufficient for guarded ingest.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_report(args.root)
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.json_output:
        _atomic_write(args.json_output, serialized)
    if args.markdown_output:
        _atomic_write(args.markdown_output, render_markdown(report))
    if not args.json_output and not args.markdown_output:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
