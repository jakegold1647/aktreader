"""Generate paired blind Reader briefs from a local wave specification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aktreader.batch import atomic_write_json
from aktreader.briefs import build_reader_briefs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--accept-coordinator-pins",
        action="store_true",
        help=(
            "do not open source images; stamp hashes as coordinator-relayed rather than reverified"
        ),
    )
    args = parser.parse_args(argv)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError("wave specification must be a JSON object")
    result = build_reader_briefs(spec, verify_artifacts=not args.accept_coordinator_pins)
    atomic_write_json(args.output, result)
    print(
        json.dumps(
            {
                "status": "PASS",
                "blind_group_id": result["blind_group_id"],
                "briefs_per_reader": len(result["reader_a"]),
                "artifact_verification": result["artifact_verification"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
