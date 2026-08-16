"""Local multi-project collection indexing and document discovery."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aktreader.project import (
    inspect_project,
    list_project_documents,
    list_project_pages,
    load_project_page,
)

COLLECTION_CONTRACT = {"name": "aktreader-collection", "version": "1.0.0"}
COLLECTION_MANIFEST_NAME = "collection.akt.json"
COLLECTION_DATABASE_NAME = "collection.sqlite3"
COLLECTION_DATABASE_VERSION = 2


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


def _create_document_index(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE document_index (
            project_id TEXT NOT NULL REFERENCES projects(project_id),
            manifest_sha256 TEXT NOT NULL,
            document_id TEXT NOT NULL,
            title TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            notes TEXT NOT NULL,
            page_count INTEGER NOT NULL CHECK (page_count >= 0),
            region_count INTEGER NOT NULL CHECK (region_count >= 0),
            line_count INTEGER NOT NULL CHECK (line_count >= 0),
            source_pagexml_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (project_id, manifest_sha256),
            UNIQUE (project_id, document_id)
        );
        CREATE INDEX document_index_project_title
            ON document_index(project_id, title);
        """
    )


def _migrate_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        application_id = connection.execute("PRAGMA application_id").fetchone()[0]
        if application_id != 1095459671:
            raise CollectionError("collection database has an unsupported application ID")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        with connection:
            if version == 1:
                _create_document_index(connection)
                connection.execute(f"PRAGMA user_version = {COLLECTION_DATABASE_VERSION}")
            elif version != COLLECTION_DATABASE_VERSION:
                raise CollectionError(
                    f"collection database has unsupported schema version {version}"
                )
    except sqlite3.Error as error:
        raise CollectionError(f"collection database is unreadable: {error}") from error
    finally:
        connection.close()


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
    _migrate_database(database_path)
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
                f"""
                PRAGMA application_id = 1095459671;
                PRAGMA user_version = {COLLECTION_DATABASE_VERSION};
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
            _create_document_index(connection)
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


def _document_index_rows(
    report: dict[str, object],
    project: Path,
) -> list[tuple[object, ...]]:
    project_id = report["project_id"]
    if not isinstance(project_id, str):
        raise CollectionError("project inspection returned an invalid identity")
    rows: list[tuple[object, ...]] = []
    for document in list_project_documents(project):
        required_strings = (
            "manifest_sha256",
            "document_id",
            "title",
            "notes",
            "source_pagexml_sha256",
            "created_at",
            "updated_at",
        )
        if not all(isinstance(document.get(name), str) for name in required_strings):
            raise CollectionError("project document metadata is invalid")
        tags = document.get("tags")
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise CollectionError("project document tags are invalid")
        counts = ("page_count", "region_count", "line_count")
        if not all(isinstance(document.get(name), int) for name in counts):
            raise CollectionError("project document counts are invalid")
        rows.append(
            (
                project_id,
                document["manifest_sha256"],
                document["document_id"],
                document["title"],
                json.dumps(document["tags"], ensure_ascii=False, separators=(",", ":")),
                document["notes"],
                document["page_count"],
                document["region_count"],
                document["line_count"],
                document["source_pagexml_sha256"],
                document["created_at"],
                document["updated_at"],
            )
        )
    return rows


def _project_index_rows(
    project: Path,
) -> tuple[dict[str, object], list[tuple[object, ...]], list[tuple[object, ...]]]:
    report = inspect_project(project)
    document_rows = _document_index_rows(report, project)
    text_rows: list[tuple[object, ...]] = []
    for page in list_project_pages(project):
        loaded = load_project_page(
            project,
            manifest_sha256=str(page["manifest_sha256"]),
            page_index=int(page["page_index"]),
        )
        for line in loaded["lines"]:
            text = line["text"]
            if isinstance(text, str) and text:
                text_rows.append(
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
    return report, document_rows, text_rows


def add_project_to_collection(
    collection: Path | str,
    project: Path | str,
) -> dict[str, object]:
    """Add or refresh one verified local project in a collection index."""

    root = _required_collection_root(collection)
    project_path = _local_path(project, role="project", must_exist=True)
    if not project_path.is_dir():
        raise CollectionError(f"project is not a directory: {project_path}")
    try:
        report, document_rows, text_rows = _project_index_rows(project_path)
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
                raise CollectionError(
                    "collection path belongs to a different local project identity"
                )
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
            connection.execute(
                "DELETE FROM document_index WHERE project_id = ?",
                (project_id,),
            )
            connection.executemany(
                """
                INSERT INTO document_index (
                    project_id, manifest_sha256, document_id, title, tags_json, notes,
                    page_count, region_count, line_count, source_pagexml_sha256,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                document_rows,
            )
            connection.executemany(
                """
                INSERT INTO text_index (
                    project_id, manifest_sha256, page_index, page_id, source_span_id,
                    region_id, line_id, text, revision
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                text_rows,
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
        "indexed_document_count": len(document_rows),
        "indexed_line_count": len(text_rows),
        "network_required": False,
    }


def inspect_collection(path: Path | str) -> dict[str, object]:
    """Return stable local collection counts without touching member projects."""

    root = _required_collection_root(path)
    manifest = _read_manifest(root)
    connection = sqlite3.connect(root / COLLECTION_DATABASE_NAME)
    try:
        project_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        document_count = connection.execute("SELECT COUNT(*) FROM document_index").fetchone()[0]
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


def _decode_tags(raw: object) -> list[str]:
    if not isinstance(raw, str):
        raise CollectionError("collection document tags are invalid")
    try:
        tags = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CollectionError("collection document tags are invalid") from error
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise CollectionError("collection document tags are invalid")
    return tags


def list_collection_documents(
    collection: Path | str,
    *,
    query: str | None = None,
    limit: int = 100,
) -> dict[str, object]:
    """List locally indexed documents and optionally filter their metadata."""

    if query is not None and (not isinstance(query, str) or not query.strip()):
        raise CollectionError("document query must be a nonblank string")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise CollectionError("document limit must be an integer from 1 to 1000")
    root = _required_collection_root(collection)
    needle = query.casefold() if query is not None else None
    connection = sqlite3.connect(root / COLLECTION_DATABASE_NAME)
    try:
        rows = connection.execute(
            """
            SELECT
                document_index.project_id, projects.project_name, projects.project_path,
                document_index.manifest_sha256, document_index.document_id,
                document_index.title, document_index.tags_json, document_index.notes,
                document_index.page_count, document_index.region_count,
                document_index.line_count, document_index.source_pagexml_sha256,
                document_index.created_at, document_index.updated_at
            FROM document_index
            JOIN projects ON projects.project_id = document_index.project_id
            ORDER BY projects.project_name, document_index.title,
                     document_index.manifest_sha256
            """
        ).fetchall()
    finally:
        connection.close()
    documents = [
        {
            "project_id": row[0],
            "project_name": row[1],
            "project_path": row[2],
            "manifest_sha256": row[3],
            "document_id": row[4],
            "title": row[5],
            "tags": _decode_tags(row[6]),
            "notes": row[7],
            "page_count": row[8],
            "region_count": row[9],
            "line_count": row[10],
            "source_pagexml_sha256": row[11],
            "created_at": row[12],
            "updated_at": row[13],
        }
        for row in rows
    ]
    if needle is not None:
        documents = [
            document
            for document in documents
            if needle
            in " ".join(
                [
                    document["title"],
                    *document["tags"],
                    document["notes"],
                ]
            ).casefold()
        ]
    return {
        "status": "READY",
        "collection": str(root),
        "query": query,
        "match_count": len(documents),
        "returned_count": min(len(documents), limit),
        "documents": documents[:limit],
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
                text_index.region_id, text_index.line_id, text_index.text,
                text_index.revision, document_index.document_id, document_index.title,
                document_index.tags_json
            FROM text_index
            JOIN projects ON projects.project_id = text_index.project_id
            LEFT JOIN document_index
                ON document_index.project_id = text_index.project_id
                AND document_index.manifest_sha256 = text_index.manifest_sha256
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
            "document_id": row[10],
            "document_title": row[11],
            "document_tags": _decode_tags(row[12]) if row[12] is not None else [],
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
