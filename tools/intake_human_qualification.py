"""Verify a complete blind human-qualification return matrix for adjudication."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aktreader.batch import atomic_write_json
from aktreader.qualification import (
    QualificationIntakeError,
    intake_qualification_submissions,
)

ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--receipt",
        type=Path,
        default=ROOT / "training" / "qualification-0001" / "receipt.json",
    )
    parser.add_argument(
        "--submission-schema",
        type=Path,
        default=ROOT / "schemas" / "human-transcription-submission-1.0.0.schema.json",
    )
    parser.add_argument("--submissions-dir", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "training" / "qualification-0001" / "intake.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"intake output already exists: {args.output}")
    if not args.submissions_dir.is_dir():
        parser.error(f"submissions directory does not exist: {args.submissions_dir}")
    paths = sorted(path for path in args.submissions_dir.rglob("*.json") if path.is_file())
    try:
        report = intake_qualification_submissions(
            receipt_path=args.receipt,
            submission_schema_path=args.submission_schema,
            submission_paths=paths,
        )
    except QualificationIntakeError as error:
        parser.error(str(error))
    atomic_write_json(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "submissions": report["matrix"]["submission_count"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
