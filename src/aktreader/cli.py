"""Command-line scaffold for AKTREADER."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Sequence

from aktreader import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser without causing import-time side effects."""
    parser = argparse.ArgumentParser(
        prog="aktreader",
        description="Evidence-first civil-register extraction (P1 gold corpus).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")
    doctor = subparsers.add_parser("doctor", help="report the local development environment")
    doctor.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def environment_report() -> dict[str, object]:
    """Return deterministic environment facts useful at phase gates."""
    supported = sys.version_info >= (3, 10)
    return {
        "aktreader_version": __version__,
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_supported": supported,
        "phase": "P1",
        "pipeline_available": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the pre-pipeline CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "doctor":
        parser.print_help()
        return 0

    report = environment_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"AKTREADER {report['aktreader_version']} ({report['phase']} review gate)")
        print(f"Python {report['python_version']} ({report['implementation']})")
        print(f"Python >= 3.10: {'yes' if report['python_supported'] else 'no'}")
        print("Pipeline available: no")
    return 0 if report["python_supported"] else 1
