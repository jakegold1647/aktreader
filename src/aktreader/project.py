"""Local, content-addressed project storage for the AKT Reader workbench.

A project is a directory the owner chooses.  It contains only local files: a
small manifest, a SQLite index, imported immutable objects, and import
manifests.  It never opens a port, resolves a remote URI, or downloads a model.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aktreader.pagexml import import_pagexml

PROJECT_CONTRACT_NAME = "aktreader-project"
PROJECT_CONTRACT_VERSION = "1.0.0"
PROJECT_MANIFEST_NAME = "project.akt.json"
PROJECT_DATABASE_NAME = "project.sqlite3"


class ProjectStoreError(ValueError):
    """Raised when a local project cannot be created, opened, or updated."""


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _local_path(path: Path | str, *, role: str, must_exist: bool) -> Path:
    raw = os.fspath(path)
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise ProjectStoreError(f"{role} must be a local path, not a URL or UNC path")
    candidate = Path(raw)
    try:
        return candidate.resolve(strict=must_exist)
    except OSError as error:
        raise ProjectStoreError(f"{role} is missing or inaccessible: {raw}") from error


def _required_project_root(path: Path | str) -> Path:
    root = _local_path(path, role="project", must_exist=True)
    if not root.is_dir():
        raise ProjectStoreError(f"project is not a directory: {root}")
    manifest_path = root / PROJECT_MANIFEST_NAME
    if not manifest_path.is_file():
        raise ProjectStoreError(f"project is missing {PROJECT_MANIFEST_NAME}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectStoreError(f"project manifest is unreadable: {manifest_path}") from error
    if not isinstance(manifest, dict):
        raise ProjectStoreError("project manifest must be a JSON object")
    contract = manifest.get("contract")
    if contract != {"name": PROJECT_CONTRACT_NAME, "version": PROJECT_CONTRACT_VERSION}:
        raise ProjectStoreError("project manifest has an unsupported contract")
    database = root / PROJECT_DATABASE_NAME
    if not database.is_file():
        raise ProjectStoreError(f"project is missing {PROJECT_DATABASE_NAME}")
    return root


def _read_project_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / PROJECT_MANIFEST_NAME
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectStoreError(f"project manifest is unreadable: {manifest_path}") from error
    if not isinstance(payload, dict):
        raise ProjectStoreError("project manifest must be a JSON object")
    return payload


def _initialize_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.executescript(
                """
                PRAGMA application_id = 1095459668;
                PRAGMA user_version = 1;
                CREATE TABLE source_objects (
                    sha256 TEXT PRIMARY KEY,
                    object_kind TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                    relative_path TEXT NOT NULL UNIQUE,
                    imported_at TEXT NOT NULL
                );
                CREATE TABLE pagexml_imports (
                    manifest_sha256 TEXT PRIMARY KEY,
                    pagexml_sha256 TEXT NOT NULL,
                    manifest_relative_path TEXT NOT NULL UNIQUE,
                    imported_at TEXT NOT NULL,
                    page_count INTEGER NOT NULL CHECK (page_count >= 1),
                    region_count INTEGER NOT NULL CHECK (region_count >= 0),
                    line_count INTEGER NOT NULL CHECK (line_count >= 0)
                );
                CREATE TABLE pages (
                    manifest_sha256 TEXT NOT NULL REFERENCES pagexml_imports(manifest_sha256),
                    page_index INTEGER NOT NULL CHECK (page_index >= 0),
                    page_id TEXT NOT NULL,
                    image_sha256 TEXT NOT NULL REFERENCES source_objects(sha256),
                    width_px INTEGER NOT NULL CHECK (width_px >= 1),
                    height_px INTEGER NOT NULL CHECK (height_px >= 1),
                    PRIMARY KEY (manifest_sha256, page_index)
                );
                CREATE TABLE lines (
                    manifest_sha256 TEXT NOT NULL REFERENCES pagexml_imports(manifest_sha256),
                    source_span_id TEXT NOT NULL,
                    page_index INTEGER NOT NULL CHECK (page_index >= 0),
                    page_id TEXT NOT NULL,
                    region_id TEXT,
                    line_id TEXT NOT NULL,
                    text_equiv TEXT,
                    bbox_json TEXT NOT NULL,
                    locator_json TEXT NOT NULL,
                    PRIMARY KEY (manifest_sha256, source_span_id)
                );
                """
            )
    finally:
        connection.close()


def _object_relative_path(digest: str) -> Path:
    return Path("objects") / "sha256" / digest[:2] / digest


def _store_object(root: Path, source: Path, *, digest: str, object_kind: str) -> str:
    if _sha256_file(source) != digest:
        raise ProjectStoreError(f"{object_kind} changed while it was being imported: {source}")
    relative = _object_relative_path(digest)
    destination = root / relative
    if destination.exists():
        if not destination.is_file() or _sha256_file(destination) != digest:
            raise ProjectStoreError(f"project object collision for SHA-256 {digest}")
        return relative.as_posix()

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_raw = tempfile.mkstemp(
        prefix=f".{digest[:12]}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temporary = Path(temporary_raw)
    try:
        with os.fdopen(descriptor, "wb") as target, source.open("rb") as origin:
            shutil.copyfileobj(origin, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        if _sha256_file(temporary) != digest:
            raise ProjectStoreError(f"{object_kind} copy failed checksum verification: {source}")
        try:
            os.replace(temporary, destination)
        except OSError:
            if not destination.is_file() or _sha256_file(destination) != digest:
                raise
    finally:
        if temporary.exists():
            temporary.unlink()
    return relative.as_posix()


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_raw = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def create_project(path: Path | str, *, name: str) -> dict[str, object]:
    """Create a new local workbench project atomically."""

    if not isinstance(name, str) or not name.strip():
        raise ProjectStoreError("project name must be a nonblank string")
    destination = _local_path(path, role="project destination", must_exist=False)
    if destination.exists():
        raise ProjectStoreError(f"project destination already exists: {destination}")
    parent = destination.parent
    if not parent.is_dir():
        raise ProjectStoreError(f"project destination parent does not exist: {parent}")

    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent))
    project_id = str(uuid.uuid4())
    manifest = {
        "contract": {"name": PROJECT_CONTRACT_NAME, "version": PROJECT_CONTRACT_VERSION},
        "project_id": project_id,
        "name": name.strip(),
        "created_at": _timestamp(),
        "storage": {
            "database": PROJECT_DATABASE_NAME,
            "objects": "objects/sha256",
            "imports": "imports/pagexml",
        },
        "network_required": False,
    }
    try:
        _atomic_write_json(temporary / PROJECT_MANIFEST_NAME, manifest)
        _initialize_database(temporary / PROJECT_DATABASE_NAME)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return inspect_project(destination)


def _insert_object(
    connection: sqlite3.Connection,
    *,
    digest: str,
    object_kind: str,
    source: Path,
    relative_path: str,
    imported_at: str,
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO source_objects
            (sha256, object_kind, size_bytes, relative_path, imported_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (digest, object_kind, source.stat().st_size, relative_path, imported_at),
    )


def import_pagexml_into_project(
    project: Path | str,
    source: Path | str,
    *,
    image_root: Path | str | None = None,
) -> dict[str, object]:
    """Copy one local PAGE XML import and its page images into a local project."""

    root = _required_project_root(project)
    imported = import_pagexml(source, image_root=image_root)
    source_info = imported["source"]
    source_path = Path(source_info["path"])
    pagexml_sha256 = source_info["sha256"]
    if not isinstance(pagexml_sha256, str):
        raise ProjectStoreError("PAGE XML importer returned an invalid source digest")
    stored_source = _store_object(
        root,
        source_path,
        digest=pagexml_sha256,
        object_kind="pagexml",
    )

    stored_pages: list[dict[str, object]] = []
    stored_objects: list[tuple[str, str, Path, str]] = [
        (pagexml_sha256, "pagexml", source_path, stored_source)
    ]
    for page in imported["pages"]:
        image = page["image"]
        image_path = Path(image["path"])
        image_sha256 = image["sha256"]
        if not isinstance(image_sha256, str):
            raise ProjectStoreError("PAGE XML importer returned an invalid image digest")
        stored_image = _store_object(
            root,
            image_path,
            digest=image_sha256,
            object_kind="image",
        )
        stored_objects.append((image_sha256, "image", image_path, stored_image))
        stored_pages.append({**page, "image": {**image, "stored_object": stored_image}})

    persisted = {
        **imported,
        "source": {**source_info, "stored_object": stored_source},
        "pages": stored_pages,
    }
    manifest_serialized = _canonical_json(persisted).encode()
    manifest_sha256 = hashlib.sha256(manifest_serialized).hexdigest()
    manifest_relative = Path("imports") / "pagexml" / f"{manifest_sha256}.json"
    manifest_path = root / manifest_relative
    if not manifest_path.exists():
        _atomic_write_json(manifest_path, persisted)

    summary = persisted["summary"]
    imported_at = _timestamp()
    database = root / PROJECT_DATABASE_NAME
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            for digest, object_kind, object_path, relative_path in stored_objects:
                _insert_object(
                    connection,
                    digest=digest,
                    object_kind=object_kind,
                    source=object_path,
                    relative_path=relative_path,
                    imported_at=imported_at,
                )
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO pagexml_imports
                    (manifest_sha256, pagexml_sha256, manifest_relative_path, imported_at,
                     page_count, region_count, line_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest_sha256,
                    pagexml_sha256,
                    manifest_relative.as_posix(),
                    imported_at,
                    summary["page_count"],
                    summary["region_count"],
                    summary["line_count"],
                ),
            )
            already_imported = cursor.rowcount == 0
            if not already_imported:
                for page in stored_pages:
                    image = page["image"]
                    connection.execute(
                        """
                        INSERT INTO pages
                            (manifest_sha256, page_index, page_id, image_sha256, width_px, height_px)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            manifest_sha256,
                            page["page_index"],
                            page["page_id"],
                            image["sha256"],
                            image["width_px"],
                            image["height_px"],
                        ),
                    )
                    for line in page["lines"]:
                        locator = line["locator"]
                        connection.execute(
                            """
                            INSERT INTO lines
                                (manifest_sha256, source_span_id, page_index, page_id, region_id,
                                 line_id, text_equiv, bbox_json, locator_json)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                manifest_sha256,
                                line["source_span_id"],
                                page["page_index"],
                                page["page_id"],
                                locator["region_id"],
                                locator["line_id"],
                                line["text"],
                                _canonical_json(line["bbox"]),
                                _canonical_json(locator),
                            ),
                        )
    finally:
        connection.close()

    return {
        "status": "SUCCEEDED",
        "project": str(root),
        "manifest_sha256": manifest_sha256,
        "manifest": str(manifest_path),
        "already_imported": already_imported,
        "page_count": summary["page_count"],
        "region_count": summary["region_count"],
        "line_count": summary["line_count"],
        "network_required": False,
    }


def inspect_project(path: Path | str) -> dict[str, object]:
    """Return the local project identity and durable-content counts."""

    root = _required_project_root(path)
    manifest = _read_project_manifest(root)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        object_count = connection.execute("SELECT COUNT(*) FROM source_objects").fetchone()[0]
        import_count = connection.execute("SELECT COUNT(*) FROM pagexml_imports").fetchone()[0]
        page_count = connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        line_count = connection.execute("SELECT COUNT(*) FROM lines").fetchone()[0]
    finally:
        connection.close()
    return {
        "status": "READY",
        "project": str(root),
        "project_id": manifest["project_id"],
        "name": manifest["name"],
        "contract": manifest["contract"],
        "object_count": object_count,
        "pagexml_import_count": import_count,
        "page_count": page_count,
        "line_count": line_count,
        "network_required": False,
    }
