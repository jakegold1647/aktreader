"""Score a complete blind human qualification adjudication."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aktreader.batch import atomic_write_json
from aktreader.qualification_scoring import (
    QualificationScoringError,
    score_qualification_adjudication,
)

ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--intake",
        type=Path,
        default=ROOT / "training" / "qualification-0001" / "intake.json",
    )
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument(
        "--schema",
        type=Path,
        default=(ROOT / "schemas" / "human-qualification-adjudication-1.0.0.schema.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "training" / "qualification-0001" / "score.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"score output already exists: {args.output}")
    try:
        report = score_qualification_adjudication(
            intake_path=args.intake,
            adjudication_path=args.adjudication,
            adjudication_schema_path=args.schema,
        )
    except QualificationScoringError as error:
        parser.error(str(error))
    atomic_write_json(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "production_hiring_gate": report["production_hiring_gate"],
                "passing_candidates": report["passing_candidate_codes"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
