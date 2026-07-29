"""Build canonical consensus JSON only for complete Reader A/Reader B filename pairs."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from aktreader.consensus import ConsensusResult, merge_labels
from aktreader.consensus_record import build_consensus_record, write_consensus_record
from aktreader.grounding import (
    load_grounded_reader_label,
    paired_quality_metrics,
    validate_cross_reader_grounding,
)
from aktreader.labels import ReaderLabel
from aktreader.validators.corpus import validate_corpus
from aktreader.validators.dates import validate_dates
from aktreader.validators.formula import validate_formula_positions
from aktreader.validators.models import ValidationFinding

ROOT = Path(__file__).resolve().parents[1]
READER_A_DIR = ROOT / "labels" / "readerA"
READER_B_DIR = ROOT / "labels" / "readerB"
OUTPUT_DIR = ROOT / "labels" / "consensus"
SCHEMA_PATH = ROOT / "schemas" / "act-record-2.0.0.schema.json"
RECORD_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]+$")


def _source_findings(
    findings: tuple[ValidationFinding, ...],
    label: ReaderLabel,
) -> tuple[ValidationFinding, ...]:
    return tuple(
        replace(
            finding,
            evidence={
                **dict(finding.evidence),
                "source_label_id": label.label_id,
            },
        )
        for finding in findings
    )


def _complete_pair_paths() -> list[tuple[Path, Path]]:
    reader_a = {path.name: path for path in READER_A_DIR.glob("*.json")}
    reader_b = {path.name: path for path in READER_B_DIR.glob("*.json")}
    return [(reader_a[name], reader_b[name]) for name in sorted(reader_a.keys() & reader_b)]


def _selected_pair_paths(record_ids: Sequence[str]) -> list[tuple[Path, Path]]:
    requested = sorted(set(record_ids))
    if len(requested) != len(record_ids):
        raise ValueError("duplicate --record-id values are not allowed")
    invalid = [record_id for record_id in requested if not RECORD_ID_RE.fullmatch(record_id)]
    if invalid:
        raise ValueError(f"invalid record IDs: {invalid}")
    available = {
        reader_a.stem: (reader_a, reader_b) for reader_a, reader_b in _complete_pair_paths()
    }
    missing = [record_id for record_id in requested if record_id not in available]
    if missing:
        raise ValueError(f"no complete Reader A/Reader B pair for: {missing}")
    return [available[record_id] for record_id in requested]


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build canonical consensus JSON for explicitly named complete blind-reader pairs."
        )
    )
    parser.add_argument(
        "--record-id",
        action="append",
        required=True,
        help="Exact record ID to build; repeat for multiple records. There is no all-records mode.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    pairs = _selected_pair_paths(args.record_id)

    merged: list[tuple[ReaderLabel, ReaderLabel, ConsensusResult]] = []
    findings_by_record: dict[str, list[ValidationFinding]] = {}
    all_source_labels: list[ReaderLabel] = []
    for reader_a_path, reader_b_path in pairs:
        reader_a = load_grounded_reader_label(reader_a_path)
        reader_b = load_grounded_reader_label(reader_b_path)
        result = merge_labels(reader_a, reader_b)
        merged.append((reader_a, reader_b, result))
        all_source_labels.extend((reader_a, reader_b))
        findings_by_record[result.record_id] = list(validate_dates(result))
        findings_by_record[result.record_id].extend(
            validate_cross_reader_grounding(reader_a, reader_b)
        )
        for label in (reader_a, reader_b):
            source_checks = validate_dates(label) + validate_formula_positions(label)
            findings_by_record[result.record_id].extend(_source_findings(source_checks, label))

    corpus_findings = validate_corpus(
        tuple(result for _, _, result in merged) + tuple(all_source_labels)
    )
    for finding in corpus_findings:
        for record_id in finding.record_ids:
            if record_id in findings_by_record:
                findings_by_record[record_id].append(finding)

    written = []
    for reader_a, reader_b, result in merged:
        record = build_consensus_record(
            result,
            reader_a,
            reader_b,
            findings=findings_by_record[result.record_id],
            workspace_root=ROOT,
        )
        output = OUTPUT_DIR / f"{result.record_id}.consensus.json"
        write_consensus_record(output, record, schema_path=SCHEMA_PATH)
        written.append(output.relative_to(ROOT).as_posix())

    unpaired_reader_a = sorted(
        path.name
        for path in READER_A_DIR.glob("*.json")
        if not (READER_B_DIR / path.name).is_file()
    )
    print(
        json.dumps(
            {
                "written": written,
                "selected_pair_count": len(written),
                "unpaired_reader_a": unpaired_reader_a,
                "groundedness_incident_count": sum(
                    finding.severity == "GROUNDEDNESS_INCIDENT"
                    for findings in findings_by_record.values()
                    for finding in findings
                ),
                "quality_metrics": paired_quality_metrics(all_source_labels),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
