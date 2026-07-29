"""Report coverage and groundedness together for an explicit label set."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from aktreader.grounding import (
    grounding_findings,
    paired_quality_metrics,
    validate_cross_reader_grounding,
)
from aktreader.labels import load_reader_label


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--label",
        action="append",
        required=True,
        type=Path,
        help="Reader label to include; repeat for a wave.",
    )
    parser.add_argument(
        "--pair-consecutive",
        action="store_true",
        help="Treat labels as left/right consecutive pairs and run impossibility checks.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    labels = tuple(load_reader_label(path) for path in args.label)
    findings = tuple(finding for label in labels for finding in grounding_findings(label))
    incidents = ()
    if args.pair_consecutive:
        if len(labels) % 2:
            raise SystemExit("--pair-consecutive requires an even label count")
        incidents = tuple(
            finding
            for index in range(0, len(labels), 2)
            for finding in validate_cross_reader_grounding(labels[index], labels[index + 1])
        )
    print(
        json.dumps(
            {
                "status": "PASS" if not findings else "FAIL",
                "quality_metrics": paired_quality_metrics(labels),
                "grounding_violation_codes": dict(
                    sorted(Counter(finding.code for finding in findings).items())
                ),
                "affected_record_count": len(
                    {record_id for finding in findings for record_id in finding.record_ids}
                ),
                "groundedness_incident_count": len(incidents),
                "groundedness_incident_record_ids": sorted(
                    {record_id for finding in incidents for record_id in finding.record_ids}
                ),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not findings and not incidents else 1


if __name__ == "__main__":
    raise SystemExit(main())
