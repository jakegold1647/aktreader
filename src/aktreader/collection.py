"""Local multi-project collection indexing and text search."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aktreader.project import inspect_project, list_project_pages, load_project_page

COLLECTION_CONTRACT = {"name": "aktreader-collection", "version": "1.0.0"}
COLLECTION_MANIFEST_NAME = "collection.akt.json"
COLLECTION_DATABASE_NAME = "collection.sqlite3"


class CollectionError(ValueError):
    """Raised when a local collection cannot be created, indexed, or searched."""


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _local_path(path: Path | str, *, role: str, must_exist: bool) -> Path:
    raw = os.fspath(path)
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise CollectionError(f"{role} must be a local path, not a URL or UNC path")
    candidate = Path(raw)
    try:
        return candidate.resolve(strict=must_exist)
    except OSError as error:
        raise CollectionError(f"{role} is missing or inaccessible: {raw}") from error


def _atomic_write_json(path: Path, payload: object) -> None:
    descriptor, temporary_raw = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _required_collection_root(path: Path | str) -> Path:
    root = _local_path(path, role="collection", must_exist=True)
    if not root.is_dir():
        raise CollectionError(f"collection is not a directory: {root}")
    manifest_path = root / COLLECTION_MANIFEST_NAME
    database_path = root / COLLECTION_DATABASE_NAME
    if not manifest_path.is_file() or not database_path.is_file():
        raise CollectionError("collection is missing its manifest or database")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CollectionError("collection manifest is unreadable") from error
    if not isinstance(manifest, dict) or manifest.get("contract") != COLLECTION_CONTRACT:
        raise CollectionError("collection manifest has an unsupported contract")
    return root


def _read_manifest(root: Path) -> dict[str, Any]:
    try:
        payload = json.loads((root / COLLECTION_MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CollectionError("collection manifest is unreadable") from error
    if not isinstance(payload, dict):
        raise CollectionError("collection manifest is invalid")
    return payload


def _initialize_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.executescript(
                """
                PRAGMA application_id = 1095459671;
                PRAGMA user_version = 1;
                CREATE TABLE projects (
                    project_id TEXT PRIMARY KEY,
                    project_path TEXT NOT NULL UNIQUE,
                    project_name TEXT NOT NULL,
                    indexed_at TEXT NOT NULL
                );
                CREATE TABLE text_index (
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    manifest_sha256 TEXT NOT NULL,
                    page_index INTEGER NOT NULL CHECK (page_index >= 0),
                    page_id TEXT NOT NULL,
                    source_span_id TEXT NOT NULL,
                    region_id TEXT,
                    line_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 0),
                    PRIMARY KEY (project_id, manifest_sha256, source_span_id)
                );
                CREATE INDEX text_index_project_page
                    ON text_index(project_id, manifest_sha256, page_index);
                """
            )
    finally:
        connection.close()


def create_collection(path: Path | str, *, name: str) -> dict[str, object]:
    """Create one empty, local-only collection."""

    if not isinstance(name, str) or not name.strip():
        raise CollectionError("collection name must be a nonblank string")
    destination = _local_path(path, role="collection destination", must_exist=False)
    if destination.exists():
        raise CollectionError(f"collection destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise CollectionError(f"collection destination parent does not exist: {destination.parent}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        _atomic_write_json(
            temporary / COLLECTION_MANIFEST_NAME,
            {
                "contract": COLLECTION_CONTRACT,
                "collection_id": str(uuid.uuid4()),
                "name": name.strip(),
                "created_at": _timestamp(),
                "network_required": False,
            },
        )
        _initialize_database(temporary / COLLECTION_DATABASE_NAME)
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists():
            for item in temporary.iterdir():
                item.unlink()
            temporary.rmdir()
        raise
    return inspect_collection(destination)


def _project_index_rows(project: Path) -> tuple[dict[str, object], list[tuple[object, ...]]]:
    report = inspect_project(project)
    rows: list[tuple[object, ...]] = []
    for page in list_project_pages(project):
        loaded = load_project_page(
            project,
            manifest_sha256=str(page["manifest_sha256"]),
            page_index=int(page["page_index"]),
        )
        for line in loaded["lines"]:
            text = line["text"]
            if isinstance(text, str) and text:
                rows.append(
                    (
                        report["project_id"],
                        page["manifest_sha256"],
                        page["page_index"],
                        loaded["page_id"],
                        line["source_span_id"],
                        line["region_id"],
                        line["line_id"],
                        text,
                        line["revision"],
                    )
                )
    return report, rows


def add_project_to_collection(
    collection: Path | str,
    project: Path | str,
) -> dict[str, object]:
    """Add or refresh one verified local project in a collection text index."""

    root = _required_collection_root(collection)
    project_path = _local_path(project, role="project", must_exist=True)
    if not project_path.is_dir():
        raise CollectionError(f"project is not a directory: {project_path}")
    try:
        report, rows = _project_index_rows(project_path)
    except ValueError as error:
        raise CollectionError(f"cannot index project: {error}") from error
    project_id = report["project_id"]
    if not isinstance(project_id, str) or not isinstance(report["name"], str):
        raise CollectionError("project inspection returned an invalid identity")
    connection = sqlite3.connect(root / COLLECTION_DATABASE_NAME)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            conflicting = connection.execute(
                "SELECT project_id FROM projects WHERE project_path = ?",
                (str(project_path),),
            ).fetchone()
            if conflicting is not None and conflicting[0] != project_id:
                raise CollectionError(\n                    "collection path belongs to a different local project identity"\n                )
            connection.execute(
                """
                INSERT INTO projects (project_id, project_path, project_name, indexed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    project_path = excluded.project_path,
                    project_name = excluded.project_name,
                    indexed_at = excluded.indexed_at
                """,
                (project_id, str(project_path), report["name"], _timestamp()),
            )
            connection.execute("DELETE FROM text_index WHERE project_id = ?", (project_id,))
            connection.executemany(
                """
                INSERT INTO text_index (
                    project_id, manifest_sha256, page_index, page_id, source_span_id,
                    region_id, line_id, text, revision
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
    except sqlite3.Error as error:
        raise CollectionError(f"cannot update collection index: {error}") from error
    finally:
        connection.close()
    return {
        "status": "INDEXED",
        "collection": str(root),
        "project": str(project_path),
        "project_id": project_id,
        "project_name": report["name"],
        "indexed_line_count": len(rows),
        "network_required": False,
    }


def inspect_collection(path: Path | str) -> dict[str, object]:
    """Return stable local collection counts without touching member projects."""

    root = _required_collection_root(path)
    manifest = _read_manifest(root)
    connection = sqlite3.connect(root / COLLECTION_DATABASE_NAME)
    try:
        project_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        document_count = connection.execute(
            "SELECT COUNT(DISTINCT project_id || ':' || manifest_sha256) FROM text_index"
        ).fetchone()[0]
        indexed_line_count = connection.execute("SELECT COUNT(*) FROM text_index").fetchone()[0]
    finally:
        connection.close()
    return {
        "status": "READY",
        "collection": str(root),
        "collection_id": manifest["collection_id"],
        "name": manifest["name"],
        "contract": manifest["contract"],
        "project_count": project_count,
        "document_count": document_count,
        "indexed_line_count": indexed_line_count,
        "network_required": False,
    }


def search_collection(
    collection: Path | str,
    query: str,
    *,
    limit: int = 100,
) -> dict[str, object]:
    """Search the collection's refreshable, locally stored effective text index."""

    if not isinstance(query, str) or not query.strip():
        raise CollectionError("search query must be a nonblank string")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise CollectionError("search limit must be an integer from 1 to 1000")
    root = _required_collection_root(collection)
    needle = query.casefold()
    connection = sqlite3.connect(root / COLLECTION_DATABASE_NAME)
    try:
        rows = connection.execute(
            """
            SELECT
                text_index.project_id, projects.project_name, text_index.manifest_sha256,
                text_index.page_index, text_index.page_id, text_index.source_span_id,
                text_index.region_id, text_index.line_id, text_index.text, text_index.revision
            FROM text_index
            JOIN projects ON projects.project_id = text_index.project_id
            ORDER BY projects.project_name, text_index.manifest_sha256,
                     text_index.page_index, text_index.source_span_id
            """
        ).fetchall()
    finally:
        connection.close()
    matches = [
        {
            "project_id": row[0],
            "project_name": row[1],
            "manifest_sha256": row[2],
            "page_index": row[3],
            "page_id": row[4],
            "source_span_id": row[5],
            "region_id": row[6],
            "line_id": row[7],
            "text": row[8],
            "revision": row[9],
        }
        for row in rows
        if needle in row[8].casefold()
    ]
    return {
        "status": "READY",
        "collection": str(root),
        "query": query,
        "match_count": len(matches),
        "returned_count": min(len(matches), limit),
        "matches": matches[:limit],
        "network_required": False,
    }
