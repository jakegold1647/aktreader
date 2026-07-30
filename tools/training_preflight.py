"""Write a deterministic training-readiness report and fail closed when blocked."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aktreader.batch import atomic_write_json
from aktreader.training import build_training_readiness

ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "training" / "plan-0001.json")
    parser.add_argument("--output", type=Path, default=ROOT / "training" / "readiness-0001.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_training_readiness(workspace_root=ROOT, plan_path=args.plan)
    atomic_write_json(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "paid_training_launch_allowed": report["paid_training_launch_allowed"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
