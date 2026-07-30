"""Build the blind human qualification packet from pinned source images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aktreader.qualification import build_qualification_packet

ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=ROOT / "training" / "qualification-source-0001.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "training" / "qualification-0001",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    receipt = build_qualification_packet(
        source_manifest_path=args.source_manifest,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "records": receipt["record_count"],
                "candidates": receipt["candidate_count"],
                "output": str(args.output_dir),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
