"""Local, content-addressed project storage for the AKT Reader workbench.

A project is a directory the owner chooses.  It contains only local files: a
small manifest, a SQLite index, imported immutable objects, and import
manifests.  It never opens a port, resolves a remote URI, or downloads a model.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import unicodedata
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aktreader.pagexml import import_pagexml

PROJECT_CONTRACT_NAME = "aktreader-project"
PROJECT_CONTRACT_VERSION = "1.0.0"
PROJECT_MANIFEST_NAME = "project.akt.json"
PROJECT_DATABASE_NAME = "project.sqlite3"
PROJECT_DATABASE_VERSION = 4


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



def _revision_text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    _migrate_database(database)
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
                PRAGMA user_version = 4;
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
                CREATE TABLE transcription_revisions (
                    manifest_sha256 TEXT NOT NULL,
                    source_span_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 1),
                    prior_text TEXT,
                    revised_text TEXT NOT NULL,
                    editor TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (manifest_sha256, source_span_id, revision),
                    FOREIGN KEY (manifest_sha256, source_span_id)
                        REFERENCES lines(manifest_sha256, source_span_id)
                );

                CREATE TABLE htr_runs (
                    manifest_sha256 TEXT NOT NULL REFERENCES pagexml_imports(manifest_sha256),
                    output_sha256 TEXT NOT NULL REFERENCES source_objects(sha256),
                    engine TEXT NOT NULL,
                    runtime_fingerprint TEXT NOT NULL,
                    output_relative_path TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    line_count INTEGER NOT NULL CHECK (line_count >= 0),
                    PRIMARY KEY (manifest_sha256, output_sha256)
                );
                CREATE TABLE htr_suggestions (
                    manifest_sha256 TEXT NOT NULL,
                    output_sha256 TEXT NOT NULL,
                    source_span_id TEXT NOT NULL,
                    suggested_text TEXT,
                    PRIMARY KEY (manifest_sha256, output_sha256, source_span_id),
                    FOREIGN KEY (manifest_sha256, output_sha256)
                        REFERENCES htr_runs(manifest_sha256, output_sha256),
                    FOREIGN KEY (manifest_sha256, source_span_id)
                        REFERENCES lines(manifest_sha256, source_span_id)
                );

                CREATE TABLE training_consent_grants (
                    consent_id TEXT PRIMARY KEY,
                    manifest_sha256 TEXT NOT NULL,
                    source_span_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 1),
                    revised_text_sha256 TEXT NOT NULL,
                    contributor TEXT NOT NULL,
                    granted_at TEXT NOT NULL,
                    UNIQUE (
                        manifest_sha256,
                        source_span_id,
                        revision,
                        revised_text_sha256,
                        contributor
                    ),
                    FOREIGN KEY (manifest_sha256, source_span_id)
                        REFERENCES lines(manifest_sha256, source_span_id)
                );
                CREATE TABLE training_consent_revocations (
                    grant_consent_id TEXT PRIMARY KEY
                        REFERENCES training_consent_grants(consent_id),
                    revoked_by TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    revoked_at TEXT NOT NULL
                );
                """
            )
    finally:
        connection.close()


def _migrate_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            raise ProjectStoreError("project database has no supported schema version")
        if version == 1:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE transcription_revisions (
                        manifest_sha256 TEXT NOT NULL,
                        source_span_id TEXT NOT NULL,
                        revision INTEGER NOT NULL CHECK (revision >= 1),
                        prior_text TEXT,
                        revised_text TEXT NOT NULL,
                        editor TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (manifest_sha256, source_span_id, revision),
                        FOREIGN KEY (manifest_sha256, source_span_id)
                            REFERENCES lines(manifest_sha256, source_span_id)
                    );
                    PRAGMA user_version = 2;
                    """
                )
            version = 2
        if version == 2:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE htr_runs (
                        manifest_sha256 TEXT NOT NULL REFERENCES pagexml_imports(manifest_sha256),
                        output_sha256 TEXT NOT NULL REFERENCES source_objects(sha256),
                        engine TEXT NOT NULL,
                        runtime_fingerprint TEXT NOT NULL,
                        output_relative_path TEXT NOT NULL,
                        imported_at TEXT NOT NULL,
                        line_count INTEGER NOT NULL CHECK (line_count >= 0),
                        PRIMARY KEY (manifest_sha256, output_sha256)
                    );
                    CREATE TABLE htr_suggestions (
                        manifest_sha256 TEXT NOT NULL,
                        output_sha256 TEXT NOT NULL,
                        source_span_id TEXT NOT NULL,
                        suggested_text TEXT,
                        PRIMARY KEY (manifest_sha256, output_sha256, source_span_id),
                        FOREIGN KEY (manifest_sha256, output_sha256)
                            REFERENCES htr_runs(manifest_sha256, output_sha256),
                        FOREIGN KEY (manifest_sha256, source_span_id)
                            REFERENCES lines(manifest_sha256, source_span_id)
                    );
                    PRAGMA user_version = 3;
                    """
                )
            version = 3

        if version == 3:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE training_consent_grants (
                        consent_id TEXT PRIMARY KEY,
                        manifest_sha256 TEXT NOT NULL,
                        source_span_id TEXT NOT NULL,
                        revision INTEGER NOT NULL CHECK (revision >= 1),
                        revised_text_sha256 TEXT NOT NULL,
                        contributor TEXT NOT NULL,
                        granted_at TEXT NOT NULL,
                        UNIQUE (
                            manifest_sha256,
                            source_span_id,
                            revision,
                            revised_text_sha256,
                            contributor
                        ),
                        FOREIGN KEY (manifest_sha256, source_span_id)
                            REFERENCES lines(manifest_sha256, source_span_id)
                    );
                    CREATE TABLE training_consent_revocations (
                        grant_consent_id TEXT PRIMARY KEY
                            REFERENCES training_consent_grants(consent_id),
                        revoked_by TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        revoked_at TEXT NOT NULL
                    );
                    PRAGMA user_version = 4;
                    """
                )
            version = 4

        if version != PROJECT_DATABASE_VERSION:
            raise ProjectStoreError(f"unsupported project database version: {version}")
    except sqlite3.Error as error:
        raise ProjectStoreError(f"project database migration failed: {error}") from error
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



def _atomic_write_bytes(path: Path, payload: bytes, *, replace_existing: bool) -> None:
    if path.exists() and not replace_existing:
        raise ProjectStoreError(
            f"export destination already exists; pass replace_existing=True: {path}"
        )
    descriptor, temporary_raw = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_raw)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
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
                            (
                                manifest_sha256,
                                page_index,
                                page_id,
                                image_sha256,
                                width_px,
                                height_px
                            )
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


def _require_sha256(value: str, *, role: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ProjectStoreError(f"{role} must be a lowercase SHA-256 string")
    try:
        int(value, 16)
    except ValueError as error:
        raise ProjectStoreError(f"{role} must be a lowercase SHA-256 string") from error
    if value != value.lower():
        raise ProjectStoreError(f"{role} must be a lowercase SHA-256 string")
    return value


def _htr_line_key(
    page_index: int,
    page_id: str,
    region_id: str | None,
    line_id: str,
) -> tuple[int, str, str | None, str]:
    return page_index, page_id, region_id, line_id


def import_htr_suggestions(
    project: Path | str,
    source: Path | str,
    *,
    manifest_sha256: str,
    engine: str,
    runtime_fingerprint: str,
    image_root: Path | str | None = None,
) -> dict[str, object]:
    """Persist aligned PAGE XML recognition text as separate local suggestions."""

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    runtime_fingerprint = _require_sha256(
        runtime_fingerprint,
        role="runtime_fingerprint",
    )
    if not isinstance(engine, str) or not engine or not engine.replace("-", "").isalnum():
        raise ProjectStoreError("engine must be a nonblank lowercase alphanumeric identifier")
    if engine != engine.lower():
        raise ProjectStoreError("engine must be a nonblank lowercase alphanumeric identifier")

    root = _required_project_root(project)
    imported = import_pagexml(source, image_root=image_root)
    source_info = imported["source"]
    output_sha256 = source_info["sha256"]
    if not isinstance(output_sha256, str):
        raise ProjectStoreError("PAGE XML importer returned an invalid result digest")
    output_sha256 = _require_sha256(output_sha256, role="result PAGE XML SHA-256")
    output_path = Path(source_info["path"])
    output_pages = imported["pages"]
    database = root / PROJECT_DATABASE_NAME
    connection = sqlite3.connect(database)
    try:
        target_import = connection.execute(
            "SELECT 1 FROM pagexml_imports WHERE manifest_sha256 = ?",
            (manifest_sha256,),
        ).fetchone()
        if target_import is None:
            raise ProjectStoreError("project PAGE XML import was not found")
        target_pages = {
            row[0]: (row[1], row[2], row[3], row[4])
            for row in connection.execute(
                """
                SELECT page_index, page_id, image_sha256, width_px, height_px
                FROM pages
                WHERE manifest_sha256 = ?
                """,
                (manifest_sha256,),
            )
        }
        target_lines = {
            _htr_line_key(row[0], row[1], row[2], row[3]): (row[4], row[5])
            for row in connection.execute(
                """
                SELECT page_index, page_id, region_id, line_id, source_span_id, bbox_json
                FROM lines
                WHERE manifest_sha256 = ?
                """,
                (manifest_sha256,),
            )
        }
        if len(output_pages) != len(target_pages):
            raise ProjectStoreError(
                "recognition PAGE XML page count does not match the project import"
            )

        suggestions: list[tuple[str, str | None]] = []
        observed_line_keys: set[tuple[int, str, str | None, str]] = set()
        for page in output_pages:
            page_index = page["page_index"]
            page_id = page["page_id"]
            image = page["image"]
            expected_page = target_pages.get(page_index)
            observed_page = (
                page_id,
                image["sha256"],
                image["width_px"],
                image["height_px"],
            )
            if expected_page != observed_page:
                raise ProjectStoreError(
                    "recognition PAGE XML page identity, image, or dimensions do not match "
                    "the project import"
                )
            for line in page["lines"]:
                locator = line["locator"]
                key = _htr_line_key(
                    page_index,
                    page_id,
                    locator["region_id"],
                    locator["line_id"],
                )
                target_line = target_lines.get(key)
                if target_line is None:
                    raise ProjectStoreError(
                        "recognition PAGE XML contains a line not present in the project import"
                    )
                if _canonical_json(line["bbox"]) != target_line[1]:
                    raise ProjectStoreError(
                        "recognition PAGE XML line geometry does not match the project import"
                    )
                observed_line_keys.add(key)
                suggested_text = line["text"]
                if suggested_text is not None and not isinstance(suggested_text, str):
                    raise ProjectStoreError("recognition PAGE XML returned a non-string line text")
                suggestions.append((target_line[0], suggested_text))
        if observed_line_keys != set(target_lines):
            raise ProjectStoreError(
                "recognition PAGE XML does not contain exactly the project import's lines"
            )
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot validate recognition PAGE XML: {error}") from error
    finally:
        connection.close()

    stored_output = _store_object(
        root,
        output_path,
        digest=output_sha256,
        object_kind=f"{engine}-pagexml-result",
    )
    imported_at = _timestamp()
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            _insert_object(
                connection,
                digest=output_sha256,
                object_kind=f"{engine}-pagexml-result",
                source=output_path,
                relative_path=stored_output,
                imported_at=imported_at,
            )
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO htr_runs
                    (manifest_sha256, output_sha256, engine, runtime_fingerprint,
                     output_relative_path, imported_at, line_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest_sha256,
                    output_sha256,
                    engine,
                    runtime_fingerprint,
                    stored_output,
                    imported_at,
                    len(suggestions),
                ),
            )
            already_imported = cursor.rowcount == 0
            if not already_imported:
                connection.executemany(
                    """
                    INSERT INTO htr_suggestions
                        (manifest_sha256, output_sha256, source_span_id, suggested_text)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (manifest_sha256, output_sha256, source_span_id, text)
                        for source_span_id, text in suggestions
                    ],
                )
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot store recognition suggestions: {error}") from error
    finally:
        connection.close()
    return {
        "status": "SUCCEEDED",
        "project": str(root),
        "manifest_sha256": manifest_sha256,
        "engine": engine,
        "runtime_fingerprint": runtime_fingerprint,
        "result_pagexml_sha256": output_sha256,
        "result_pagexml_object": stored_output,
        "already_imported": already_imported,
        "suggestion_count": len(suggestions),
        "network_required": False,
    }



_FORBIDDEN_PAGE_XML_DECLARATION = re.compile(
    br"<!\s*(?:DOCTYPE|ENTITY)\b",
    re.IGNORECASE,
)


def _xml_local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _xml_tag_like(element: ET.Element, local_name: str) -> str:
    if element.tag.startswith("{"):
        namespace = element.tag.split("}", 1)[0][1:]
        return f"{{{namespace}}}{local_name}"
    return local_name


def _selected_text_equiv(line: ET.Element) -> ET.Element | None:
    candidates: list[tuple[int, int, ET.Element]] = []
    for position, candidate in enumerate(line):
        if _xml_local_name(candidate) != "TextEquiv":
            continue
        raw_index = candidate.get("index")
        try:
            index = 0 if raw_index is None else int(raw_index)
        except ValueError as error:
            raise ProjectStoreError("stored PAGE XML has a non-integer TextEquiv index") from error
        candidates.append((index, position, candidate))
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item[0], item[1]))[2]


def _replace_text_equiv(line: ET.Element, text: str) -> None:
    selected = _selected_text_equiv(line)
    if selected is None:
        selected = ET.SubElement(line, _xml_tag_like(line, "TextEquiv"))
    unicode = next(
        (child for child in selected if _xml_local_name(child) == "Unicode"),
        None,
    )
    if unicode is None:
        unicode = ET.SubElement(selected, _xml_tag_like(selected, "Unicode"))
    for child in list(unicode):
        unicode.remove(child)
    unicode.text = text


def export_human_pagexml(
    project: Path | str,
    output: Path | str,
    *,
    manifest_sha256: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    """Export human revisions as a new local PAGE XML document.

    The content-addressed source XML, page images, HTR proposals, and revision
    history are unchanged.  The generated XML applies only the latest explicit
    human revision for each affected PAGE TextLine.
    """

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    if not isinstance(replace_existing, bool):
        raise ProjectStoreError("replace_existing must be a boolean")
    root = _required_project_root(project)
    output_path = _local_path(output, role="PAGE XML export", must_exist=False)
    if not output_path.parent.is_dir():
        raise ProjectStoreError(f"PAGE XML export parent does not exist: {output_path.parent}")
    if output_path == root or root in output_path.parents:
        raise ProjectStoreError(
            "PAGE XML export must be outside the project so project objects stay immutable"
        )

    database = root / PROJECT_DATABASE_NAME
    connection = sqlite3.connect(database)
    try:
        source = connection.execute(
            """
            SELECT pagexml_imports.pagexml_sha256, source_objects.relative_path
            FROM pagexml_imports
            JOIN source_objects ON source_objects.sha256 = pagexml_imports.pagexml_sha256
            WHERE pagexml_imports.manifest_sha256 = ?
            """,
            (manifest_sha256,),
        ).fetchone()
        if source is None:
            raise ProjectStoreError("project PAGE XML import was not found")
        revision_rows = connection.execute(
            """
            SELECT
                lines.source_span_id,
                lines.page_index,
                lines.page_id,
                lines.line_id,
                lines.locator_json,
                transcription_revisions.revised_text
            FROM lines
            JOIN transcription_revisions
                ON transcription_revisions.manifest_sha256 = lines.manifest_sha256
               AND transcription_revisions.source_span_id = lines.source_span_id
               AND transcription_revisions.revision = (
                    SELECT MAX(latest.revision)
                    FROM transcription_revisions AS latest
                    WHERE latest.manifest_sha256 = lines.manifest_sha256
                      AND latest.source_span_id = lines.source_span_id
               )
            WHERE lines.manifest_sha256 = ?
            ORDER BY lines.page_index, lines.rowid
            """,
            (manifest_sha256,),
        ).fetchall()
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot load project revisions for export: {error}") from error
    finally:
        connection.close()

    source_sha256, source_relative_path = source
    source_path = root / source_relative_path
    if not source_path.is_file() or _sha256_file(source_path) != source_sha256:
        raise ProjectStoreError("project PAGE XML source object is missing or checksum-mismatched")
    if output_path == source_path:
        raise ProjectStoreError("PAGE XML export must not overwrite its immutable source object")

    revisions: dict[tuple[int, str, str], str] = {}
    for source_span_id, page_index, page_id, line_id, locator_json, revised_text in revision_rows:
        try:
            locator = json.loads(locator_json)
        except (TypeError, json.JSONDecodeError) as error:
            raise ProjectStoreError(
                f"stored locator is unreadable for project line {source_span_id}"
            ) from error
        if (
            not isinstance(locator, dict)
            or locator.get("kind") != "PAGE_XML_TEXT_LINE"
            or locator.get("page_index") != page_index
            or locator.get("page_id") != page_id
            or locator.get("line_id") != line_id
            or not isinstance(revised_text, str)
        ):
            raise ProjectStoreError(f"stored locator is invalid for project line {source_span_id}")
        key = (page_index, page_id, line_id)
        if key in revisions:
            raise ProjectStoreError(f"project contains duplicate export locator {key!r}")
        revisions[key] = revised_text

    source_bytes = source_path.read_bytes()
    if _FORBIDDEN_PAGE_XML_DECLARATION.search(source_bytes):
        raise ProjectStoreError("stored PAGE XML contains a forbidden XML declaration")
    try:
        document = ET.fromstring(source_bytes)
    except ET.ParseError as error:
        raise ProjectStoreError("stored PAGE XML cannot be parsed for export") from error
    pages = [element for element in document.iter() if _xml_local_name(element) == "Page"]
    seen: set[tuple[int, str, str]] = set()
    for page_index, page in enumerate(pages):
        raw_page_id = page.get("id")
        page_id = raw_page_id.strip() if isinstance(raw_page_id, str) and raw_page_id.strip() else (
            f"page-index-{page_index}"
        )
        for line in page.iter():
            if _xml_local_name(line) != "TextLine":
                continue
            raw_line_id = line.get("id")
            if not isinstance(raw_line_id, str) or not raw_line_id.strip():
                continue
            key = (page_index, page_id, raw_line_id.strip())
            revised_text = revisions.get(key)
            if revised_text is None:
                continue
            _replace_text_equiv(line, revised_text)
            seen.add(key)
    missing = sorted(set(revisions) - seen)
    if missing:
        raise ProjectStoreError(
            "stored PAGE XML no longer matches the project's revision locators: "
            f"{missing[0]!r}"
        )

    rendered = ET.tostring(document, encoding="utf-8", xml_declaration=True)
    _atomic_write_bytes(output_path, rendered, replace_existing=replace_existing)
    return {
        "status": "SUCCEEDED",
        "project": str(root),
        "manifest_sha256": manifest_sha256,
        "source_pagexml_sha256": source_sha256,
        "output": str(output_path),
        "output_sha256": hashlib.sha256(rendered).hexdigest(),
        "human_revision_count": len(revisions),
        "network_required": False,
    }


def _levenshtein_distance(reference: Sequence[str], hypothesis: Sequence[str]) -> int:
    """Return the exact insertion/deletion/substitution distance for two sequences."""

    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for row_index, reference_item in enumerate(reference, start=1):
        current = [row_index]
        for column_index, hypothesis_item in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[column_index - 1] + 1,
                    previous[column_index] + 1,
                    previous[column_index - 1]
                    + (0 if reference_item == hypothesis_item else 1),
                )
            )
        previous = current
    return previous[-1]


def _normalize_htr_text(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def evaluate_htr_suggestions(
    project: Path | str,
    *,
    manifest_sha256: str,
    result_pagexml_sha256: str,
) -> dict[str, object]:
    """Compare one imported local HTR result with explicit human revisions only."""

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    result_pagexml_sha256 = _require_sha256(
        result_pagexml_sha256,
        role="result_pagexml_sha256",
    )
    root = _required_project_root(project)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        run = connection.execute(
            """
            SELECT engine, runtime_fingerprint, line_count
            FROM htr_runs
            WHERE manifest_sha256 = ? AND output_sha256 = ?
            """,
            (manifest_sha256, result_pagexml_sha256),
        ).fetchone()
        if run is None:
            raise ProjectStoreError("imported HTR result was not found for this project import")
        source_line_count = connection.execute(
            "SELECT COUNT(*) FROM lines WHERE manifest_sha256 = ?",
            (manifest_sha256,),
        ).fetchone()[0]
        rows = connection.execute(
            """
            SELECT htr_suggestions.suggested_text, transcription_revisions.revised_text
            FROM lines
            JOIN transcription_revisions
                ON transcription_revisions.manifest_sha256 = lines.manifest_sha256
               AND transcription_revisions.source_span_id = lines.source_span_id
               AND transcription_revisions.revision = (
                    SELECT MAX(latest.revision)
                    FROM transcription_revisions AS latest
                    WHERE latest.manifest_sha256 = lines.manifest_sha256
                      AND latest.source_span_id = lines.source_span_id
               )
            LEFT JOIN htr_suggestions
                ON htr_suggestions.manifest_sha256 = lines.manifest_sha256
               AND htr_suggestions.source_span_id = lines.source_span_id
               AND htr_suggestions.output_sha256 = ?
            WHERE lines.manifest_sha256 = ?
            ORDER BY lines.page_index, lines.rowid
            """,
            (result_pagexml_sha256, manifest_sha256),
        ).fetchall()
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot evaluate imported HTR suggestions: {error}") from error
    finally:
        connection.close()

    human_revision_count = len(rows)
    suggestion_count = sum(row[0] is not None for row in rows)
    evaluated_pairs: list[tuple[str, str]] = []
    for suggested_text, revised_text in rows:
        if suggested_text is None:
            continue
        if not isinstance(suggested_text, str) or not isinstance(revised_text, str):
            raise ProjectStoreError("stored HTR suggestion or human revision is invalid")
        evaluated_pairs.append(
            (_normalize_htr_text(revised_text), _normalize_htr_text(suggested_text))
        )

    reference_char_count = sum(len(reference) for reference, _ in evaluated_pairs)
    hypothesis_char_count = sum(len(hypothesis) for _, hypothesis in evaluated_pairs)
    char_edit_distance = sum(
        _levenshtein_distance(reference, hypothesis)
        for reference, hypothesis in evaluated_pairs
    )
    reference_word_count = sum(len(reference.split()) for reference, _ in evaluated_pairs)
    hypothesis_word_count = sum(len(hypothesis.split()) for _, hypothesis in evaluated_pairs)
    word_edit_distance = sum(
        _levenshtein_distance(reference.split(), hypothesis.split())
        for reference, hypothesis in evaluated_pairs
    )
    exact_line_match_count = sum(
        reference == hypothesis for reference, hypothesis in evaluated_pairs
    )
    evaluated_line_count = len(evaluated_pairs)
    return {
        "status": "SUCCEEDED" if evaluated_line_count else "NO_EVALUABLE_HUMAN_REVISIONS",
        "project": str(root),
        "manifest_sha256": manifest_sha256,
        "result_pagexml_sha256": result_pagexml_sha256,
        "engine": run[0],
        "runtime_fingerprint": run[1],
        "source_line_count": source_line_count,
        "run_line_count": run[2],
        "human_revision_count": human_revision_count,
        "suggestion_count_for_human_revisions": suggestion_count,
        "evaluated_line_count": evaluated_line_count,
        "normalization": "UNICODE_NFC_EXACT_WHITESPACE",
        "character_error_rate": (
            char_edit_distance / reference_char_count if reference_char_count else None
        ),
        "character_edit_distance": char_edit_distance,
        "reference_character_count": reference_char_count,
        "hypothesis_character_count": hypothesis_char_count,
        "word_error_rate": (
            word_edit_distance / reference_word_count if reference_word_count else None
        ),
        "word_edit_distance": word_edit_distance,
        "reference_word_count": reference_word_count,
        "hypothesis_word_count": hypothesis_word_count,
        "exact_line_match_rate": (
            exact_line_match_count / evaluated_line_count if evaluated_line_count else None
        ),
        "exact_line_match_count": exact_line_match_count,
        "network_required": False,
    }

def list_project_pages(path: Path | str) -> list[dict[str, object]]:
    """List every imported page in stable import and page order."""

    root = _required_project_root(path)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        rows = connection.execute(
            """
            SELECT
                pages.manifest_sha256,
                pages.page_index,
                pages.page_id,
                pages.image_sha256,
                pages.width_px,
                pages.height_px,
                source_objects.relative_path
            FROM pages
            JOIN pagexml_imports
                ON pagexml_imports.manifest_sha256 = pages.manifest_sha256
            JOIN source_objects ON source_objects.sha256 = pages.image_sha256
            ORDER BY pagexml_imports.imported_at, pages.manifest_sha256, pages.page_index
            """
        ).fetchall()
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot list project pages: {error}") from error
    finally:
        connection.close()
    return [
        {
            "manifest_sha256": row[0],
            "page_index": row[1],
            "page_id": row[2],
            "image_sha256": row[3],
            "width_px": row[4],
            "height_px": row[5],
            "image_path": str(root / row[6]),
        }
        for row in rows
    ]


def load_project_page(
    path: Path | str,
    *,
    manifest_sha256: str,
    page_index: int,
) -> dict[str, object]:
    """Load one image-backed page with effective, revision-aware line text."""

    if not isinstance(manifest_sha256, str) or len(manifest_sha256) != 64:
        raise ProjectStoreError("manifest_sha256 must be a SHA-256 string")
    if not isinstance(page_index, int) or page_index < 0:
        raise ProjectStoreError("page_index must be a non-negative integer")
    root = _required_project_root(path)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        page = connection.execute(
            """
            SELECT pages.page_id, pages.image_sha256, pages.width_px, pages.height_px,
                   source_objects.relative_path
            FROM pages
            JOIN source_objects ON source_objects.sha256 = pages.image_sha256
            WHERE pages.manifest_sha256 = ? AND pages.page_index = ?
            """,
            (manifest_sha256, page_index),
        ).fetchone()
        if page is None:
            raise ProjectStoreError("project page was not found")
        lines = connection.execute(
            """
            SELECT
                lines.source_span_id,
                lines.region_id,
                lines.line_id,
                lines.text_equiv,
                lines.bbox_json,
                lines.locator_json,
                COALESCE(MAX(transcription_revisions.revision), 0) AS revision,
                (
                    SELECT revised_text
                    FROM transcription_revisions AS latest
                    WHERE latest.manifest_sha256 = lines.manifest_sha256
                      AND latest.source_span_id = lines.source_span_id
                    ORDER BY latest.revision DESC
                    LIMIT 1
                ) AS revised_text
            FROM lines
            LEFT JOIN transcription_revisions
                ON transcription_revisions.manifest_sha256 = lines.manifest_sha256
               AND transcription_revisions.source_span_id = lines.source_span_id
            WHERE lines.manifest_sha256 = ? AND lines.page_index = ?
            GROUP BY
                lines.manifest_sha256,
                lines.source_span_id,
                lines.region_id,
                lines.line_id,
                lines.text_equiv,
                lines.bbox_json,
                lines.locator_json
            ORDER BY lines.rowid
            """,
            (manifest_sha256, page_index),
        ).fetchall()
        suggestion_rows = connection.execute(
            """
            SELECT
                htr_suggestions.source_span_id,
                htr_runs.engine,
                htr_runs.runtime_fingerprint,
                htr_runs.output_sha256,
                htr_suggestions.suggested_text,
                htr_runs.imported_at
            FROM htr_suggestions
            JOIN htr_runs
                ON htr_runs.manifest_sha256 = htr_suggestions.manifest_sha256
               AND htr_runs.output_sha256 = htr_suggestions.output_sha256
            WHERE htr_suggestions.manifest_sha256 = ?
            ORDER BY htr_runs.imported_at DESC, htr_suggestions.output_sha256
            """,
            (manifest_sha256,),
        ).fetchall()
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot load project page: {error}") from error
    finally:
        connection.close()
    suggestions_by_span: dict[str, list[dict[str, object]]] = {}
    for suggestion in suggestion_rows:
        suggestions_by_span.setdefault(suggestion[0], []).append(
            {
                "engine": suggestion[1],
                "runtime_fingerprint": suggestion[2],
                "result_pagexml_sha256": suggestion[3],
                "text": suggestion[4],
                "imported_at": suggestion[5],
            }
        )
    return {
        "manifest_sha256": manifest_sha256,
        "page_index": page_index,
        "page_id": page[0],
        "image_sha256": page[1],
        "width_px": page[2],
        "height_px": page[3],
        "image_path": str(root / page[4]),
        "lines": [
            {
                "source_span_id": row[0],
                "region_id": row[1],
                "line_id": row[2],
                "source_text": row[3],
                "text": row[7] if row[7] is not None else row[3],
                "revision": row[6],
                "bbox": json.loads(row[4]),
                "locator": json.loads(row[5]),
                "suggestions": suggestions_by_span.get(row[0], []),
            }
            for row in lines
        ],
    }


def revise_line_transcription(
    path: Path | str,
    *,
    manifest_sha256: str,
    source_span_id: str,
    text: str,
    editor: str = "local-user",
) -> dict[str, object]:
    """Append one human transcription revision without changing PAGE XML source text."""

    if not isinstance(manifest_sha256, str) or len(manifest_sha256) != 64:
        raise ProjectStoreError("manifest_sha256 must be a SHA-256 string")
    if not isinstance(source_span_id, str) or not source_span_id.strip():
        raise ProjectStoreError("source_span_id must be a nonblank string")
    if not isinstance(text, str):
        raise ProjectStoreError("transcription text must be a string")
    if not isinstance(editor, str) or not editor.strip():
        raise ProjectStoreError("editor must be a nonblank string")
    root = _required_project_root(path)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        with connection:
            row = connection.execute(
                """
                SELECT
                    lines.text_equiv,
                    COALESCE(MAX(transcription_revisions.revision), 0),
                    (
                        SELECT revised_text
                        FROM transcription_revisions AS latest
                        WHERE latest.manifest_sha256 = lines.manifest_sha256
                          AND latest.source_span_id = lines.source_span_id
                        ORDER BY latest.revision DESC
                        LIMIT 1
                    )
                FROM lines
                LEFT JOIN transcription_revisions
                    ON transcription_revisions.manifest_sha256 = lines.manifest_sha256
                   AND transcription_revisions.source_span_id = lines.source_span_id
                WHERE lines.manifest_sha256 = ? AND lines.source_span_id = ?
                GROUP BY lines.manifest_sha256, lines.source_span_id, lines.text_equiv
                """,
                (manifest_sha256, source_span_id),
            ).fetchone()
            if row is None:
                raise ProjectStoreError("project line was not found")
            current_text = row[2] if row[2] is not None else row[0]
            current_revision = row[1]
            if current_text == text:
                return {
                    "status": "UNCHANGED",
                    "project": str(root),
                    "manifest_sha256": manifest_sha256,
                    "source_span_id": source_span_id,
                    "revision": current_revision,
                    "network_required": False,
                }
            revision = current_revision + 1
            created_at = _timestamp()
            connection.execute(
                """
                INSERT INTO transcription_revisions
                    (manifest_sha256, source_span_id, revision, prior_text, revised_text, editor,
                     created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest_sha256,
                    source_span_id,
                    revision,
                    current_text,
                    text,
                    editor.strip(),
                    created_at,
                ),
            )
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot save transcription revision: {error}") from error
    finally:
        connection.close()
    return {
        "status": "SAVED",
        "project": str(root),
        "manifest_sha256": manifest_sha256,
        "source_span_id": source_span_id,
        "revision": revision,
        "editor": editor.strip(),
        "network_required": False,
    }


def _latest_human_revisions(
    connection: sqlite3.Connection,
    *,
    manifest_sha256: str,
) -> dict[str, tuple[int, str, str]]:
    rows = connection.execute(
        """
        SELECT
            lines.source_span_id,
            transcription_revisions.revision,
            transcription_revisions.revised_text,
            transcription_revisions.editor
        FROM lines
        JOIN transcription_revisions
            ON transcription_revisions.manifest_sha256 = lines.manifest_sha256
           AND transcription_revisions.source_span_id = lines.source_span_id
           AND transcription_revisions.revision = (
                SELECT MAX(latest.revision)
                FROM transcription_revisions AS latest
                WHERE latest.manifest_sha256 = lines.manifest_sha256
                  AND latest.source_span_id = lines.source_span_id
           )
        WHERE lines.manifest_sha256 = ?
        """,
        (manifest_sha256,),
    ).fetchall()
    return {row[0]: (row[1], row[2], row[3]) for row in rows}


def grant_training_consent(
    project: Path | str,
    *,
    manifest_sha256: str,
    contributor: str,
    source_span_ids: Sequence[str] | None = None,
    all_human_revised: bool = False,
) -> dict[str, object]:
    """Append consent for the contributor's current human revisions only."""

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    if not isinstance(contributor, str) or not contributor.strip():
        raise ProjectStoreError("contributor must be a nonblank string")
    if source_span_ids is None:
        requested_spans: list[str] = []
    elif isinstance(source_span_ids, str):
        raise ProjectStoreError("source_span_ids must be a sequence of nonblank strings")
    else:
        requested_spans = list(source_span_ids)
    if all_human_revised == bool(requested_spans):
        raise ProjectStoreError(
            "select one or more source_span_ids or set all_human_revised=True, but not both"
        )
    if any(not isinstance(span, str) or not span.strip() for span in requested_spans):
        raise ProjectStoreError("source_span_ids must contain only nonblank strings")
    requested_spans = [span.strip() for span in requested_spans]
    if len(requested_spans) != len(set(requested_spans)):
        raise ProjectStoreError("source_span_ids must not contain duplicates")

    root = _required_project_root(project)
    database = root / PROJECT_DATABASE_NAME
    contributor = contributor.strip()
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            imported = connection.execute(
                "SELECT 1 FROM pagexml_imports WHERE manifest_sha256 = ?",
                (manifest_sha256,),
            ).fetchone()
            if imported is None:
                raise ProjectStoreError("project PAGE XML import was not found")
            revisions = _latest_human_revisions(
                connection,
                manifest_sha256=manifest_sha256,
            )
            spans = sorted(revisions) if all_human_revised else requested_spans
            if not spans:
                raise ProjectStoreError(
                    "there are no human revisions available for training consent"
                )
            grants: list[dict[str, str | int | bool]] = []
            for source_span_id in spans:
                revision = revisions.get(source_span_id)
                if revision is None:
                    raise ProjectStoreError(
                        "training consent requires a current human revision for every selected line"
                    )
                revision_number, revised_text, revision_editor = revision
                if revision_editor != contributor:
                    raise ProjectStoreError(
                        "training consent contributor must match the editor of the current revision"
                    )
                revised_text_sha256 = _revision_text_sha256(revised_text)
                existing = connection.execute(
                    """
                    SELECT consent_id
                    FROM training_consent_grants
                    WHERE manifest_sha256 = ?
                      AND source_span_id = ?
                      AND revision = ?
                      AND revised_text_sha256 = ?
                      AND contributor = ?
                    """,
                    (
                        manifest_sha256,
                        source_span_id,
                        revision_number,
                        revised_text_sha256,
                        contributor,
                    ),
                ).fetchone()
                if existing is None:
                    consent_id = str(uuid.uuid4())
                    connection.execute(
                        """
                        INSERT INTO training_consent_grants
                            (
                                consent_id,
                                manifest_sha256,
                                source_span_id,
                                revision,
                                revised_text_sha256,
                                contributor,
                                granted_at
                            )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            consent_id,
                            manifest_sha256,
                            source_span_id,
                            revision_number,
                            revised_text_sha256,
                            contributor,
                            _timestamp(),
                        ),
                    )
                    already_granted = False
                else:
                    consent_id = existing[0]
                    already_granted = True
                grants.append(
                    {
                        "consent_id": consent_id,
                        "source_span_id": source_span_id,
                        "revision": revision_number,
                        "already_granted": already_granted,
                    }
                )
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot record training consent: {error}") from error
    finally:
        connection.close()
    return {
        "status": "GRANTED",
        "project": str(root),
        "manifest_sha256": manifest_sha256,
        "contributor": contributor,
        "grants": grants,
        "network_required": False,
    }


def revoke_training_consent(
    project: Path | str,
    *,
    grant_consent_id: str,
    contributor: str,
    reason: str,
) -> dict[str, object]:
    """Append one irrevocable withdrawal for a training-consent grant."""

    if not isinstance(grant_consent_id, str) or not grant_consent_id.strip():
        raise ProjectStoreError("grant_consent_id must be a nonblank string")
    if not isinstance(contributor, str) or not contributor.strip():
        raise ProjectStoreError("contributor must be a nonblank string")
    if not isinstance(reason, str) or not reason.strip():
        raise ProjectStoreError("reason must be a nonblank string")
    root = _required_project_root(project)
    database = root / PROJECT_DATABASE_NAME
    contributor = contributor.strip()
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            grant = connection.execute(
                """
                SELECT contributor
                FROM training_consent_grants
                WHERE consent_id = ?
                """,
                (grant_consent_id.strip(),),
            ).fetchone()
            if grant is None:
                raise ProjectStoreError("training-consent grant was not found")
            if grant[0] != contributor:
                raise ProjectStoreError(
                    "only the contributor who granted training consent may revoke it"
                )
            existing = connection.execute(
                """
                SELECT 1
                FROM training_consent_revocations
                WHERE grant_consent_id = ?
                """,
                (grant_consent_id.strip(),),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO training_consent_revocations
                        (grant_consent_id, revoked_by, reason, revoked_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        grant_consent_id.strip(),
                        contributor,
                        reason.strip(),
                        _timestamp(),
                    ),
                )
                already_revoked = False
            else:
                already_revoked = True
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot revoke training consent: {error}") from error
    finally:
        connection.close()
    return {
        "status": "REVOKED",
        "project": str(root),
        "grant_consent_id": grant_consent_id.strip(),
        "contributor": contributor,
        "already_revoked": already_revoked,
        "network_required": False,
    }


def training_readiness(
    project: Path | str,
    *,
    manifest_sha256: str,
) -> dict[str, object]:
    """Report whether every imported line has an eligible consented human revision."""

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    root = _required_project_root(project)
    database = root / PROJECT_DATABASE_NAME
    connection = sqlite3.connect(database)
    try:
        imported = connection.execute(
            "SELECT 1 FROM pagexml_imports WHERE manifest_sha256 = ?",
            (manifest_sha256,),
        ).fetchone()
        if imported is None:
            raise ProjectStoreError("project PAGE XML import was not found")
        line_rows = connection.execute(
            "SELECT source_span_id FROM lines WHERE manifest_sha256 = ? ORDER BY rowid",
            (manifest_sha256,),
        ).fetchall()
        revisions = _latest_human_revisions(
            connection,
            manifest_sha256=manifest_sha256,
        )
        active_grants = connection.execute(
            """
            SELECT
                training_consent_grants.source_span_id,
                training_consent_grants.revision,
                training_consent_grants.revised_text_sha256,
                training_consent_grants.consent_id
            FROM training_consent_grants
            LEFT JOIN training_consent_revocations
                ON training_consent_revocations.grant_consent_id
                 = training_consent_grants.consent_id
            WHERE training_consent_grants.manifest_sha256 = ?
              AND training_consent_revocations.grant_consent_id IS NULL
            """,
            (manifest_sha256,),
        ).fetchall()
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot inspect training readiness: {error}") from error
    finally:
        connection.close()

    active_by_revision = {
        (row[0], row[1], row[2]): row[3]
        for row in active_grants
    }
    unrevised: list[str] = []
    unconsented: list[str] = []
    eligible: list[str] = []
    for (source_span_id,) in line_rows:
        revision = revisions.get(source_span_id)
        if revision is None:
            unrevised.append(source_span_id)
            continue
        revision_number, revised_text, _editor = revision
        key = (source_span_id, revision_number, _revision_text_sha256(revised_text))
        if key in active_by_revision:
            eligible.append(source_span_id)
        else:
            unconsented.append(source_span_id)

    source_line_count = len(line_rows)
    if source_line_count == 0:
        status = "NO_SOURCE_LINES"
    elif unrevised:
        status = "BLOCKED_HUMAN_REVISIONS"
    elif unconsented:
        status = "BLOCKED_TRAINING_CONSENT"
    else:
        status = "READY_FOR_PAGEXML_TRAINING_EXPORT"
    return {
        "status": status,
        "project": str(root),
        "manifest_sha256": manifest_sha256,
        "source_line_count": source_line_count,
        "human_revision_count": len(revisions),
        "active_consent_grant_count": len(active_grants),
        "eligible_training_line_count": len(eligible),
        "unrevised_line_count": len(unrevised),
        "unconsented_human_revision_line_count": len(unconsented),
        "unrevised_source_span_ids": unrevised,
        "unconsented_source_span_ids": unconsented,
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
        revision_count = connection.execute(
            "SELECT COUNT(*) FROM transcription_revisions"
        ).fetchone()[0]
        htr_run_count = connection.execute("SELECT COUNT(*) FROM htr_runs").fetchone()[0]
        htr_suggestion_count = connection.execute(
            "SELECT COUNT(*) FROM htr_suggestions"
        ).fetchone()[0]
        training_consent_grant_count = connection.execute(
            "SELECT COUNT(*) FROM training_consent_grants"
        ).fetchone()[0]
        training_consent_revocation_count = connection.execute(
            "SELECT COUNT(*) FROM training_consent_revocations"
        ).fetchone()[0]
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
        "transcription_revision_count": revision_count,
        "htr_run_count": htr_run_count,
        "htr_suggestion_count": htr_suggestion_count,
        "training_consent_grant_count": training_consent_grant_count,
        "training_consent_revocation_count": training_consent_revocation_count,
        "network_required": False,
    }
