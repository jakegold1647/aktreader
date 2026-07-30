"""Write a provider-neutral JSONL training export after hard leakage validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aktreader.batch import atomic_write_json, atomic_write_text
from aktreader.training import build_training_export

ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--silver-manifest",
        type=Path,
        default=ROOT / "labels" / "silver" / "manifest.json",
    )
    parser.add_argument("--evaluation-holdout", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest-output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    examples, manifest = build_training_export(
        workspace_root=ROOT,
        silver_manifest_path=args.silver_manifest,
        evaluation_holdout_path=args.evaluation_holdout,
    )
    jsonl = "".join(
        json.dumps(example, ensure_ascii=False, sort_keys=True) + "\n" for example in examples
    )
    atomic_write_text(args.output, jsonl)
    atomic_write_json(args.manifest_output, manifest)
    print(
        json.dumps(
            {
                "status": "PASS",
                "examples": len(examples),
                "output": str(args.output),
                "manifest": str(args.manifest_output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
