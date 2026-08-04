"""Fail closed when declared packages are absent from the reviewed license inventory."""

from __future__ import annotations

import json
import re
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "dependency-licenses.json"
PYPROJECT = ROOT / "pyproject.toml"
NAME = re.compile(r"^[A-Za-z0-9_.-]+")


def _package_name(requirement: str) -> str:
    match = NAME.match(requirement.strip())
    if match is None:
        raise ValueError(f"cannot parse dependency requirement: {requirement!r}")
    return match.group(0).lower().replace("_", "-")


def check_dependency_licenses() -> dict[str, object]:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    declared = {
        "runtime": sorted(
            _package_name(item) for item in project["project"].get("dependencies", [])
        ),
        "development": sorted(
            _package_name(item)
            for item in project["project"].get("optional-dependencies", {}).get("dev", [])
        ),
        "build": sorted(
            _package_name(item) for item in project["build-system"].get("requires", [])
        ),
    }
    expected = {
        group: sorted(name.lower().replace("_", "-") for name in names)
        for group, names in inventory["declared_dependencies"].items()
    }
    if declared != expected:
        raise ValueError(
            f"declared dependency set changed; current={declared}, reviewed={expected}"
        )

    reviewed = inventory["reviewed_packages"]
    names = [package["name"].lower().replace("_", "-") for package in reviewed]
    if len(names) != len(set(names)):
        raise ValueError("dependency license inventory contains duplicate packages")
    missing = sorted({name for group in declared.values() for name in group} - set(names))
    if missing:
        raise ValueError(f"declared dependencies lack license review: {missing}")

    allowed = set(inventory["policy"]["allowed_spdx"])
    rejected = sorted(
        package["name"] for package in reviewed if package["spdx"] not in allowed
    )
    if rejected:
        raise ValueError(f"dependency licenses are not approved: {rejected}")
    if inventory.get("decision") != "PASS":
        raise ValueError("dependency license inventory is not marked PASS")
    return {
        "status": "PASS",
        "declared_dependency_count": sum(len(group) for group in declared.values()),
        "reviewed_package_count": len(reviewed),
        "allowed_spdx": sorted(allowed),
    }


def main() -> int:
    print(json.dumps(check_dependency_licenses(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
