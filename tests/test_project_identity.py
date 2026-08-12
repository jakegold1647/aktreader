from pathlib import Path

import tomllib

from aktreader import (
    COMMAND_NAME,
    DISTRIBUTION_NAME,
    PACKAGE_NAMESPACE,
    PROJECT_NAME,
    PROJECT_ROLE,
    REPOSITORY_URL,
    __version__,
)

ROOT = Path(__file__).resolve().parents[1]


def test_application_distribution_metadata_is_unambiguous() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["name"] == DISTRIBUTION_NAME == "aktreader-app"
    assert project["version"] == __version__
    assert project["scripts"] == {COMMAND_NAME: f"{PACKAGE_NAMESPACE}.cli:main"}
    assert project["urls"] == {
        "Homepage": REPOSITORY_URL,
        "Repository": REPOSITORY_URL,
        "Issues": f"{REPOSITORY_URL}/issues",
    }
    assert PROJECT_NAME == "AKT Reader - Application"
    assert PROJECT_ROLE == "application"


def test_lockfile_uses_the_application_distribution_name() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    editable_packages = [
        package for package in lock["package"] if package.get("source") == {"editable": "."}
    ]

    assert len(editable_packages) == 1
    assert editable_packages[0]["name"] == DISTRIBUTION_NAME
    assert editable_packages[0]["version"] == __version__
