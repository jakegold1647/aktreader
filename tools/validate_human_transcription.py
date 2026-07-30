"""Validate one paid human transcription before adjudication or payment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aktreader.human_gold import validate_human_transcription

ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=ROOT / "schemas" / "human-transcription-submission-1.0.0.schema.json",
    )
    parser.add_argument("--qualification", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = json.loads(args.submission.read_text(encoding="utf-8"))
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validate_human_transcription(payload, schema, qualification=args.qualification)
    print(json.dumps({"status": "PASS", "submission": str(args.submission)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
