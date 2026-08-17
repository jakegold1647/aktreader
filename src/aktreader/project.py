"""Local, content-addressed project storage for the AKT Reader workbench.

A project is a directory the owner chooses.  It contains only local files: a
small manifest, a SQLite index, imported immutable objects, and import
manifests.  It never opens a port, resolves a remote URI, or downloads a model.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
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

import pypdfium2 as pdfium
from PIL import Image, UnidentifiedImageError

from aktreader.kraken import LocalKraken
from aktreader.pagexml import import_pagexml

PROJECT_CONTRACT_NAME = "aktreader-project"
PROJECT_CONTRACT_VERSION = "1.0.0"
PROJECT_MANIFEST_NAME = "project.akt.json"
PROJECT_DATABASE_NAME = "project.sqlite3"
PROJECT_DATABASE_VERSION = 10


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
                PRAGMA user_version = 10;
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

                CREATE TABLE training_split_assignments (
                    manifest_sha256 TEXT PRIMARY KEY
                        REFERENCES pagexml_imports(manifest_sha256),
                    split TEXT NOT NULL CHECK (split IN ('train', 'validation', 'test')),
                    bundle_manifest_sha256 TEXT NOT NULL,
                    exported_at TEXT NOT NULL
                );
                CREATE TABLE review_proposals (
                    proposal_sha256 TEXT PRIMARY KEY,
                    package_sha256 TEXT NOT NULL,
                    manifest_sha256 TEXT NOT NULL
                        REFERENCES pagexml_imports(manifest_sha256),
                    source_pagexml_sha256 TEXT NOT NULL,
                    source_span_id TEXT NOT NULL,
                    contributor TEXT NOT NULL,
                    base_text_sha256 TEXT,
                    proposed_text TEXT NOT NULL,
                    proposed_text_sha256 TEXT NOT NULL,
                    revised_at TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (
                        state IN ('PENDING', 'CONFLICT', 'ACCEPTED', 'REJECTED')
                    ),
                    imported_at TEXT NOT NULL,
                    decided_by TEXT,
                    decided_at TEXT,
                    FOREIGN KEY (manifest_sha256, source_span_id)
                        REFERENCES lines(manifest_sha256, source_span_id)
                );
                CREATE TABLE line_geometry_revisions (
                    manifest_sha256 TEXT NOT NULL,
                    source_span_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 1),
                    prior_polygon_json TEXT NOT NULL,
                    prior_baseline_json TEXT,
                    polygon_json TEXT NOT NULL,
                    baseline_json TEXT,
                    editor TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (manifest_sha256, source_span_id, revision),
                    FOREIGN KEY (manifest_sha256, source_span_id)
                        REFERENCES lines(manifest_sha256, source_span_id)
                );
                CREATE TABLE page_reading_order_revisions (
                    manifest_sha256 TEXT NOT NULL REFERENCES pagexml_imports(manifest_sha256),
                    page_index INTEGER NOT NULL CHECK (page_index >= 0),
                    revision INTEGER NOT NULL CHECK (revision >= 1),
                    prior_region_ids_json TEXT NOT NULL,
                    region_ids_json TEXT NOT NULL,
                    editor TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (manifest_sha256, page_index, revision),
                    FOREIGN KEY (manifest_sha256, page_index)
                        REFERENCES pages(manifest_sha256, page_index)
                );
                CREATE TABLE region_geometry_revisions (
                    manifest_sha256 TEXT NOT NULL REFERENCES pagexml_imports(manifest_sha256),
                    page_index INTEGER NOT NULL CHECK (page_index >= 0),
                    region_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 1),
                    prior_polygon_json TEXT NOT NULL,
                    polygon_json TEXT NOT NULL,
                    editor TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (manifest_sha256, page_index, region_id, revision),
                    FOREIGN KEY (manifest_sha256, page_index)
                        REFERENCES pages(manifest_sha256, page_index)
                );
                CREATE TABLE documents (
                    manifest_sha256 TEXT PRIMARY KEY
                        REFERENCES pagexml_imports(manifest_sha256),
                    document_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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


        if version == 4:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE training_split_assignments (
                        manifest_sha256 TEXT PRIMARY KEY
                            REFERENCES pagexml_imports(manifest_sha256),
                        split TEXT NOT NULL CHECK (split IN ('train', 'validation', 'test')),
                        bundle_manifest_sha256 TEXT NOT NULL,
                        exported_at TEXT NOT NULL
                    );
                    PRAGMA user_version = 5;
                    """
                )
            version = 5

        if version == 5:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE review_proposals (
                        proposal_sha256 TEXT PRIMARY KEY,
                        package_sha256 TEXT NOT NULL,
                        manifest_sha256 TEXT NOT NULL
                            REFERENCES pagexml_imports(manifest_sha256),
                        source_pagexml_sha256 TEXT NOT NULL,
                        source_span_id TEXT NOT NULL,
                        contributor TEXT NOT NULL,
                        base_text_sha256 TEXT,
                        proposed_text TEXT NOT NULL,
                        proposed_text_sha256 TEXT NOT NULL,
                        revised_at TEXT NOT NULL,
                        state TEXT NOT NULL CHECK (
                            state IN ('PENDING', 'CONFLICT', 'ACCEPTED', 'REJECTED')
                        ),
                        imported_at TEXT NOT NULL,
                        decided_by TEXT,
                        decided_at TEXT,
                        FOREIGN KEY (manifest_sha256, source_span_id)
                            REFERENCES lines(manifest_sha256, source_span_id)
                    );
                    PRAGMA user_version = 6;
                    """
                )
            version = 6

        if version == 6:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE line_geometry_revisions (
                        manifest_sha256 TEXT NOT NULL,
                        source_span_id TEXT NOT NULL,
                        revision INTEGER NOT NULL CHECK (revision >= 1),
                        prior_polygon_json TEXT NOT NULL,
                        prior_baseline_json TEXT,
                        polygon_json TEXT NOT NULL,
                        baseline_json TEXT,
                        editor TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (manifest_sha256, source_span_id, revision),
                        FOREIGN KEY (manifest_sha256, source_span_id)
                            REFERENCES lines(manifest_sha256, source_span_id)
                    );
                    PRAGMA user_version = 7;
                    """
                )
            version = 7

        if version == 7:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE page_reading_order_revisions (
                        manifest_sha256 TEXT NOT NULL
                            REFERENCES pagexml_imports(manifest_sha256),
                        page_index INTEGER NOT NULL CHECK (page_index >= 0),
                        revision INTEGER NOT NULL CHECK (revision >= 1),
                        prior_region_ids_json TEXT NOT NULL,
                        region_ids_json TEXT NOT NULL,
                        editor TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (manifest_sha256, page_index, revision),
                        FOREIGN KEY (manifest_sha256, page_index)
                            REFERENCES pages(manifest_sha256, page_index)
                    );
                    PRAGMA user_version = 8;
                    """
                )
            version = 8

        if version == 8:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE region_geometry_revisions (
                        manifest_sha256 TEXT NOT NULL
                            REFERENCES pagexml_imports(manifest_sha256),
                        page_index INTEGER NOT NULL CHECK (page_index >= 0),
                        region_id TEXT NOT NULL,
                        revision INTEGER NOT NULL CHECK (revision >= 1),
                        prior_polygon_json TEXT NOT NULL,
                        polygon_json TEXT NOT NULL,
                        editor TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (manifest_sha256, page_index, region_id, revision),
                        FOREIGN KEY (manifest_sha256, page_index)
                            REFERENCES pages(manifest_sha256, page_index)
                    );
                    PRAGMA user_version = 9;
                    """
                )
            version = 9

        if version == 9:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE documents (
                        manifest_sha256 TEXT PRIMARY KEY
                            REFERENCES pagexml_imports(manifest_sha256),
                        document_id TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL,
                        tags_json TEXT NOT NULL,
                        notes TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                rows = connection.execute(
                    """
                    SELECT manifest_sha256, pagexml_sha256, imported_at
                    FROM pagexml_imports
                    ORDER BY manifest_sha256
                    """
                ).fetchall()
                for manifest_sha256, pagexml_sha256, imported_at in rows:
                    connection.execute(
                        """
                        INSERT INTO documents (
                            manifest_sha256, document_id, title, tags_json,
                            notes, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            manifest_sha256,
                            _document_id(manifest_sha256),
                            f"Imported PAGE XML {pagexml_sha256[:12]}",
                            _canonical_json([]),
                            "",
                            imported_at,
                            imported_at,
                        ),
                    )
                connection.execute("PRAGMA user_version = 10")
            version = 10

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



def _document_id(manifest_sha256: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"aktreader-document:{manifest_sha256}"))

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


_IMAGE_IMPORT_SUFFIXES = frozenset(
    {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
)


def _image_import_inputs(directory: Path) -> list[tuple[Path, int, int]]:
    images: list[tuple[Path, int, int]] = []
    for candidate in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        if not candidate.is_file() or candidate.suffix.lower() not in _IMAGE_IMPORT_SUFFIXES:
            continue
        try:
            with Image.open(candidate) as opened:
                opened.load()
                width, height = opened.size
        except (OSError, UnidentifiedImageError) as error:
            raise ProjectStoreError(
                f"image import cannot read source image: {candidate}"
            ) from error
        if width < 1 or height < 1:
            raise ProjectStoreError(f"image import found invalid dimensions: {candidate}")
        images.append((candidate.resolve(), width, height))
    if not images:
        raise ProjectStoreError(
            "image import directory contains no supported top-level image files"
        )
    return images


def _generated_image_pagexml(images: Sequence[tuple[Path, int, int]]) -> bytes:
    root = ET.Element("PcGts")
    metadata = ET.SubElement(root, "Metadata")
    ET.SubElement(metadata, "Creator").text = "AKT Reader local image import"
    for index, (image, width, height) in enumerate(images, start=1):
        page = ET.SubElement(
            root,
            "Page",
            {
                "id": f"image-{index:04d}",
                "imageFilename": image.name,
                "imageWidth": str(width),
                "imageHeight": str(height),
            },
        )
        region = ET.SubElement(page, "TextRegion", {"id": "region-0001"})
        ET.SubElement(
            region,
            "Coords",
            {"points": f"0,0 {width},0 {width},{height} 0,{height}"},
        )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _write_generated_image_pagexml(root: Path, payload: bytes) -> tuple[Path, str, bool]:
    digest = hashlib.sha256(payload).hexdigest()
    destination = root / "imports" / "generated" / f"image-import-{digest}.xml"
    if destination.exists():
        if not destination.is_file() or _sha256_file(destination) != digest:
            raise ProjectStoreError(f"generated image PAGE XML collision: {destination}")
        return destination, digest, False
    destination.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_bytes(destination, payload, replace_existing=False)
    return destination, digest, True


def import_images_into_project(
    project: Path | str,
    source_directory: Path | str,
    *,
    title: str | None = None,
) -> dict[str, object]:
    """Create an editable PAGE XML document from one local directory of page images."""

    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise ProjectStoreError("image import title must be a nonblank string")
    root = _required_project_root(project)
    directory = _local_path(
        source_directory,
        role="image import directory",
        must_exist=True,
    )
    if not directory.is_dir():
        raise ProjectStoreError(f"image import source is not a directory: {directory}")
    images = _image_import_inputs(directory)
    source_path, generated_sha256, created = _write_generated_image_pagexml(
        root,
        _generated_image_pagexml(images),
    )
    try:
        report = import_pagexml_into_project(root, source_path, image_root=directory)
    except Exception:
        if created:
            try:
                source_path.unlink()
            except OSError:
                pass
        raise

    requested_title = title.strip() if title is not None else directory.name
    if not report["already_imported"] or title is not None:
        update_project_document(
            root,
            manifest_sha256=str(report["manifest_sha256"]),
            title=requested_title or f"Image import {generated_sha256[:12]}",
        )
    return {
        **report,
        "source_kind": "IMAGE_DIRECTORY",
        "source_directory": str(directory),
        "generated_pagexml": str(source_path),
        "generated_pagexml_sha256": generated_sha256,
        "input_image_count": len(images),
        "network_required": False,
    }


MIN_PDF_RENDER_DPI = 72
MAX_PDF_RENDER_DPI = 600
MAX_PDF_PAGE_COUNT = 500
MAX_PDF_RENDER_PIXELS = 50_000_000


def _require_pdf_render_dpi(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProjectStoreError("PDF render DPI must be an integer")
    if not MIN_PDF_RENDER_DPI <= value <= MAX_PDF_RENDER_DPI:
        raise ProjectStoreError(
            f"PDF render DPI must be from {MIN_PDF_RENDER_DPI} to {MAX_PDF_RENDER_DPI}"
        )
    return value


def _pdfium_version() -> str:
    value = getattr(getattr(pdfium, "PYPDFIUM_INFO", None), "version", None)
    if not isinstance(value, str) or not value:
        raise ProjectStoreError("local PDF renderer does not expose a version")
    return value


def _verify_render_directory(
    directory: Path,
    pages: Sequence[dict[str, object]],
) -> None:
    expected_names = {str(page["filename"]) for page in pages}
    observed_names = {child.name for child in directory.iterdir() if child.is_file()}
    if observed_names != expected_names:
        raise ProjectStoreError("existing PDF render directory has unexpected files")
    for page in pages:
        candidate = directory / str(page["filename"])
        if _sha256_file(candidate) != page["sha256"]:
            raise ProjectStoreError("existing PDF render directory failed checksum verification")


def _render_pdf_pages(
    root: Path,
    source: Path,
    *,
    dpi: int,
) -> tuple[Path, str, list[dict[str, object]], str]:
    pdf_sha256 = _sha256_file(source)
    renderer_version = _pdfium_version()
    scale = dpi / 72
    temporary_parent = root / "imports" / "pdf-renders"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".render-", dir=temporary_parent))
    try:
        pages: list[dict[str, object]] = []
        try:
            with pdfium.PdfDocument(source) as document:
                page_count = len(document)
                if not 1 <= page_count <= MAX_PDF_PAGE_COUNT:
                    raise ProjectStoreError(
                        f"PDF page count must be from 1 to {MAX_PDF_PAGE_COUNT}"
                    )
                for page_index in range(page_count):
                    page_width, page_height = document.get_page_size(page_index)
                    estimated_width = math.ceil(page_width * scale)
                    estimated_height = math.ceil(page_height * scale)
                    estimated_pixels = estimated_width * estimated_height
                    if estimated_pixels > MAX_PDF_RENDER_PIXELS:
                        raise ProjectStoreError(
                            f"PDF page {page_index + 1} exceeds the local render pixel limit"
                        )
                    page = document[page_index]
                    try:
                        bitmap = page.render(scale=scale, rev_byteorder=True)
                        try:
                            rendered = bitmap.to_pil().copy()
                        finally:
                            bitmap.close()
                    finally:
                        page.close()
                    try:
                        width_px, height_px = rendered.size
                        if width_px * height_px > MAX_PDF_RENDER_PIXELS:
                            raise ProjectStoreError(
                                f"PDF page {page_index + 1} exceeds the local render pixel limit"
                            )
                        filename = f"page-{page_index + 1:04d}.png"
                        output = temporary / filename
                        rendered.save(output, format="PNG", optimize=False)
                    finally:
                        rendered.close()
                    pages.append(
                        {
                            "page_index": page_index,
                            "filename": filename,
                            "sha256": _sha256_file(output),
                            "width_px": width_px,
                            "height_px": height_px,
                        }
                    )
        except (OSError, pdfium.PdfiumError) as error:
            raise ProjectStoreError(f"cannot render local PDF: {source}") from error

        render_sha256 = hashlib.sha256(_canonical_json(pages).encode()).hexdigest()
        renderer_key = re.sub(r"[^A-Za-z0-9._-]+", "_", renderer_version)
        destination = (
            temporary_parent
            / pdf_sha256
            / f"pypdfium2-{renderer_key}-{dpi}dpi-{render_sha256[:16]}"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if not destination.is_dir():
                raise ProjectStoreError("PDF render destination is not a directory")
            _verify_render_directory(destination, pages)
            shutil.rmtree(temporary)
        else:
            os.replace(temporary, destination)
        return destination, renderer_version, pages, pdf_sha256
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        raise


def _store_pdf_import_receipt(
    root: Path,
    *,
    source: Path,
    source_sha256: str,
    render_directory: Path,
    renderer_version: str,
    dpi: int,
    rendered_pages: Sequence[dict[str, object]],
    report: dict[str, object],
) -> tuple[Path, str]:
    stored_pdf = _store_object(
        root,
        source,
        digest=source_sha256,
        object_kind="pdf",
    )
    imported_at = _timestamp()
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        with connection:
            _insert_object(
                connection,
                digest=source_sha256,
                object_kind="pdf",
                source=source,
                relative_path=stored_pdf,
                imported_at=imported_at,
            )
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot store PDF source object: {error}") from error
    finally:
        connection.close()

    manifest_path = Path(str(report["manifest"]))
    try:
        generated = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectStoreError("generated image document manifest is unreadable") from error
    imported_pages = generated.get("pages")
    if not isinstance(imported_pages, list) or len(imported_pages) != len(rendered_pages):
        raise ProjectStoreError("generated image document manifest has an invalid page count")
    receipt_pages = []
    for rendered, imported in zip(rendered_pages, imported_pages, strict=True):
        image = imported.get("image") if isinstance(imported, dict) else None
        if not isinstance(image, dict) or image.get("sha256") != rendered["sha256"]:
            raise ProjectStoreError("generated image document manifest changed during PDF import")
        receipt_pages.append(
            {
                **rendered,
                "stored_object": image.get("stored_object"),
            }
        )

    manifest_sha256 = str(report["manifest_sha256"])
    payload = {
        "contract": {"name": "aktreader-pdf-import", "version": "1.0.0"},
        "manifest_sha256": manifest_sha256,
        "source": {
            "format": "PDF",
            "path": str(source),
            "sha256": source_sha256,
            "size_bytes": source.stat().st_size,
            "stored_object": stored_pdf,
        },
        "renderer": {
            "name": "pypdfium2",
            "version": renderer_version,
            "dpi": dpi,
        },
        "render_directory": str(render_directory),
        "pages": receipt_pages,
        "network_required": False,
    }
    receipt_relative = Path("imports") / "pdf" / f"{manifest_sha256}.json"
    receipt_path = root / receipt_relative
    if receipt_path.exists():
        try:
            existing = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProjectStoreError("existing PDF import receipt is unreadable") from error
        if _canonical_json(existing) != _canonical_json(payload):
            raise ProjectStoreError("existing PDF import receipt conflicts with this import")
    else:
        _atomic_write_json(receipt_path, payload)
    return receipt_path, stored_pdf


def import_pdf_into_project(
    project: Path | str,
    source: Path | str,
    *,
    dpi: int = 300,
    title: str | None = None,
) -> dict[str, object]:
    """Render one local PDF into an editable, content-addressed PAGE document."""

    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise ProjectStoreError("PDF import title must be a nonblank string")
    dpi = _require_pdf_render_dpi(dpi)
    root = _required_project_root(project)
    pdf_path = _local_path(source, role="PDF source", must_exist=True)
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        raise ProjectStoreError("PDF import source must be a local .pdf file")
    render_directory, renderer_version, rendered_pages, rendered_source_sha256 = _render_pdf_pages(
        root,
        pdf_path,
        dpi=dpi,
    )
    report = import_images_into_project(root, render_directory, title=title)
    if not report["already_imported"] and title is None:
        update_project_document(
            root,
            manifest_sha256=str(report["manifest_sha256"]),
            title=pdf_path.stem,
        )
    source_sha256 = _sha256_file(pdf_path)
    if source_sha256 != rendered_source_sha256:
        raise ProjectStoreError("PDF source changed while it was being rendered")
    receipt_path, stored_pdf = _store_pdf_import_receipt(
        root,
        source=pdf_path,
        source_sha256=source_sha256,
        render_directory=render_directory,
        renderer_version=renderer_version,
        dpi=dpi,
        rendered_pages=rendered_pages,
        report=report,
    )
    return {
        **report,
        "source_kind": "PDF",
        "source_pdf": str(pdf_path),
        "source_pdf_sha256": source_sha256,
        "source_pdf_stored_object": stored_pdf,
        "pdf_receipt": str(receipt_path),
        "renderer": {
            "name": "pypdfium2",
            "version": renderer_version,
            "dpi": dpi,
        },
        "network_required": False,
    }


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
                connection.execute(
                    """
                    INSERT OR IGNORE INTO documents (
                        manifest_sha256, document_id, title, tags_json,
                        notes, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        manifest_sha256,
                        _document_id(manifest_sha256),
                        source_path.stem or f"Imported PAGE XML {pagexml_sha256[:12]}",
                        _canonical_json([]),
                        "",
                        imported_at,
                        imported_at,
                    ),
                )
    finally:
        connection.close()

    return {
        "status": "SUCCEEDED",
        "project": str(root),
        "manifest_sha256": manifest_sha256,
        "manifest": str(manifest_path),
        "document_id": _document_id(manifest_sha256),
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
            _htr_line_key(row[0], row[1], row[2], row[3]): (
                row[4],
                row[5],
                int(row[6]),
                int(row[7]),
            )
            for row in connection.execute(
                """
                SELECT
                    lines.page_index,
                    lines.page_id,
                    lines.region_id,
                    lines.line_id,
                    lines.source_span_id,
                    lines.bbox_json,
                    pages.width_px,
                    pages.height_px
                FROM lines
                JOIN pages
                    ON pages.manifest_sha256 = lines.manifest_sha256
                   AND pages.page_index = lines.page_index
                WHERE lines.manifest_sha256 = ?
                """,
                (manifest_sha256,),
            )
        }
        line_keys_by_span = {
            target_line[0]: key for key, target_line in target_lines.items()
        }
        for source_span_id, polygon_json in connection.execute(
            """
            SELECT source_span_id, polygon_json
            FROM line_geometry_revisions
            WHERE manifest_sha256 = ?
              AND revision = (
                    SELECT MAX(latest.revision)
                    FROM line_geometry_revisions AS latest
                    WHERE latest.manifest_sha256 = line_geometry_revisions.manifest_sha256
                      AND latest.source_span_id = line_geometry_revisions.source_span_id
              )
            """,
            (manifest_sha256,),
        ):
            key = line_keys_by_span.get(source_span_id)
            if key is None:
                raise ProjectStoreError(
                    "stored line geometry refers to an unknown project line"
                )
            source_span, _, width, height = target_lines[key]
            try:
                polygon = json.loads(polygon_json)
            except (TypeError, json.JSONDecodeError) as error:
                raise ProjectStoreError("stored line geometry is unreadable") from error
            effective_polygon = _validated_points(
                polygon,
                role="stored line geometry",
                width=width,
                height=height,
                allow_none=False,
            )
            target_lines[key] = (
                source_span,
                _canonical_json(_geometry_bbox(effective_polygon)),
                width,
                height,
            )
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


def _materialize_project_pagexml_for_kraken(
    root: Path,
    *,
    manifest_sha256: str,
    output: Path,
) -> None:
    """Write effective PAGE XML and local image copies for one pre-segmented run."""

    export_human_pagexml(
        root,
        output,
        manifest_sha256=manifest_sha256,
    )
    try:
        document = ET.parse(output)
    except (OSError, ET.ParseError) as error:
        raise ProjectStoreError("cannot materialize PAGE XML for local Kraken") from error
    pages = [element for element in document.iter() if _xml_local_name(element) == "Page"]
    if not pages:
        raise ProjectStoreError("project PAGE XML contains no pages for local Kraken")
    extensions = Image.registered_extensions()
    for page_index, page in enumerate(pages):
        page_record = load_project_page(
            root,
            manifest_sha256=manifest_sha256,
            page_index=page_index,
        )
        image = Path(str(page_record["image_path"])).resolve()
        if root not in image.parents or image.is_symlink() or not image.is_file():
            raise ProjectStoreError("project image is invalid for local Kraken")
        try:
            with Image.open(image) as opened:
                image_format = opened.format
        except (OSError, UnidentifiedImageError) as error:
            raise ProjectStoreError("project image is unreadable for local Kraken") from error
        suffix = next(
            (
                extension
                for extension, registered_format in extensions.items()
                if registered_format == image_format
            ),
            ".img",
        )
        image_name = f"page-{page_index:04d}{suffix.lower()}"
        destination = output.parent / image_name
        shutil.copyfile(image, destination)
        page.set("imageFilename", image_name)
    document.write(output, encoding="utf-8", xml_declaration=True)


def segment_project_with_kraken(
    project: Path | str,
    *,
    manifest_sha256: str,
    kraken: LocalKraken,
    title: str | None = None,
) -> dict[str, object]:
    """Create a new, provenance-linked PAGE XML layout document from project images.

    The imported source document remains immutable. Each managed page image is copied into a
    temporary local workspace, segmented by the configured Kraken baseline model, and combined
    into a new local PAGE XML import for visual correction and subsequent recognition.
    """

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise ProjectStoreError("layout document title must be a nonblank string")
    root = _required_project_root(project)
    if not isinstance(kraken, LocalKraken):
        raise ProjectStoreError("kraken runner must be a LocalKraken instance")
    source_document = next(
        (
            document
            for document in list_project_documents(root)
            if document["manifest_sha256"] == manifest_sha256
        ),
        None,
    )
    if source_document is None:
        raise ProjectStoreError("project document was not found for Kraken layout")
    page_count = source_document["page_count"]
    if not isinstance(page_count, int) or page_count < 1:
        raise ProjectStoreError("project document has an invalid page count")

    with tempfile.TemporaryDirectory(
        prefix=".aktreader-project-kraken-layout-",
        dir=root.parent,
    ) as temporary:
        workspace = Path(temporary)
        combined_root = ET.Element("PcGts")
        metadata = ET.SubElement(combined_root, "Metadata")
        ET.SubElement(metadata, "Creator").text = "AKT Reader local Kraken baseline segmentation"
        results = []
        extensions = Image.registered_extensions()
        for page_index in range(page_count):
            page_record = load_project_page(
                root,
                manifest_sha256=manifest_sha256,
                page_index=page_index,
            )
            image = Path(str(page_record["image_path"])).resolve()
            if root not in image.parents or image.is_symlink() or not image.is_file():
                raise ProjectStoreError("project image is invalid for local Kraken layout")
            try:
                with Image.open(image) as opened:
                    image_format = opened.format
            except (OSError, UnidentifiedImageError) as error:
                raise ProjectStoreError(
                    "project image is unreadable for local Kraken layout"
                ) from error
            suffix = next(
                (
                    extension
                    for extension, registered_format in extensions.items()
                    if registered_format == image_format
                ),
                ".img",
            )
            materialized_image = workspace / f"page-{page_index:04d}{suffix.lower()}"
            shutil.copyfile(image, materialized_image)
            segmented = workspace / f"page-{page_index:04d}.page.xml"
            result = kraken.segment_image(materialized_image, segmented)
            try:
                segmented_document = ET.parse(segmented)
            except (OSError, ET.ParseError) as error:
                raise ProjectStoreError("cannot parse local Kraken PAGE XML layout") from error
            pages = [
                element
                for element in segmented_document.iter()
                if element.tag.rsplit("}", 1)[-1] == "Page"
            ]
            if len(pages) != 1:
                raise ProjectStoreError(
                    "local Kraken PAGE XML layout must contain exactly one page per image"
                )
            pages[0].set("imageFilename", materialized_image.name)
            combined_root.append(pages[0])
            results.append(
                {
                    "page_index": page_index,
                    "input_image_sha256": result.source_sha256,
                    "layout_pagexml_sha256": result.output_sha256,
                }
            )
        combined = workspace / "kraken-layout.page.xml"
        ET.ElementTree(combined_root).write(combined, encoding="utf-8", xml_declaration=True)
        imported = import_pagexml_into_project(root, combined, image_root=workspace)

    source_tags = source_document["tags"]
    if not isinstance(source_tags, list) or not all(isinstance(tag, str) for tag in source_tags):
        raise ProjectStoreError("project document has invalid tags")
    derived_title = (
        title.strip()
        if title is not None
        else f"{source_document['title']} — Kraken layout"
    )
    derived_tags = list(dict.fromkeys([*source_tags, "kraken-layout"]))
    derived_notes = (
        f"Derived from document manifest {manifest_sha256} with local Kraken baseline "
        f"segmentation runtime {kraken.runtime_fingerprint}."
    )
    document = update_project_document(
        root,
        manifest_sha256=str(imported["manifest_sha256"]),
        title=derived_title,
        tags=derived_tags,
        notes=derived_notes,
    )
    return {
        "status": "SUCCEEDED",
        "source_manifest_sha256": manifest_sha256,
        "manifest_sha256": imported["manifest_sha256"],
        "document_id": imported["document_id"],
        "page_count": imported["page_count"],
        "region_count": imported["region_count"],
        "line_count": imported["line_count"],
        "already_imported": imported["already_imported"],
        "runtime_fingerprint": kraken.runtime_fingerprint,
        "pages": results,
        "document": document,
        "network_required": False,
    }


def recognize_project_with_kraken(
    project: Path | str,
    *,
    manifest_sha256: str,
    kraken: LocalKraken,
) -> dict[str, object]:
    """Run one checksum-pinned Kraken model on effective local project PAGE XML."""

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    root = _required_project_root(project)
    if not isinstance(kraken, LocalKraken):
        raise ProjectStoreError("kraken runner must be a LocalKraken instance")
    with tempfile.TemporaryDirectory(
        prefix=".aktreader-project-kraken-",
        dir=root.parent,
    ) as temporary:
        workspace = Path(temporary)
        prepared = workspace / "input.page.xml"
        recognized = workspace / "recognized.page.xml"
        _materialize_project_pagexml_for_kraken(
            root,
            manifest_sha256=manifest_sha256,
            output=prepared,
        )
        recognition = kraken.recognize_pagexml(prepared, recognized)
        imported = import_htr_suggestions(
            root,
            recognized,
            manifest_sha256=manifest_sha256,
            engine="kraken",
            runtime_fingerprint=recognition.runtime_fingerprint,
            image_root=workspace,
        )
    return {
        **imported,
        "input_pagexml_sha256": recognition.source_sha256,
        "runtime_fingerprint": recognition.runtime_fingerprint,
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




def _replace_region_geometry(region: ET.Element, *, polygon: list[list[int]]) -> None:
    coords = next(
        (child for child in region if _xml_local_name(child) == "Coords"),
        None,
    )
    if coords is None:
        raise ProjectStoreError("stored PAGE XML TextRegion is missing Coords")
    coords.set("points", " ".join(f"{x},{y}" for x, y in polygon))

def _replace_page_reading_order(page: ET.Element, region_ids: Sequence[str]) -> None:
    source_region_ids: list[str] = []
    for element in page.iter():
        if _xml_local_name(element) != "TextRegion":
            continue
        region_id = element.get("id")
        if not isinstance(region_id, str) or not region_id.strip():
            raise ProjectStoreError("stored PAGE XML TextRegion is missing an ID")
        source_region_ids.append(region_id.strip())
    if (
        len(source_region_ids) != len(set(source_region_ids))
        or len(region_ids) != len(source_region_ids)
        or len(set(region_ids)) != len(region_ids)
        or set(region_ids) != set(source_region_ids)
    ):
        raise ProjectStoreError(
            "stored PAGE XML regions no longer match the project's reading-order revision"
        )
    for child in list(page):
        if _xml_local_name(child) == "ReadingOrder":
            page.remove(child)
    reading_order = ET.Element(_xml_tag_like(page, "ReadingOrder"))
    ordered_group = ET.SubElement(
        reading_order,
        _xml_tag_like(reading_order, "OrderedGroup"),
        {"id": "aktreader-revised-reading-order"},
    )
    for index, region_id in enumerate(region_ids):
        ET.SubElement(
            ordered_group,
            _xml_tag_like(ordered_group, "RegionRefIndexed"),
            {"index": str(index), "regionRef": region_id},
        )
    page.insert(0, reading_order)

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
        geometry_rows = connection.execute(
            """
            SELECT
                lines.source_span_id,
                lines.page_index,
                lines.page_id,
                lines.line_id,
                line_geometry_revisions.polygon_json,
                line_geometry_revisions.baseline_json
            FROM lines
            JOIN line_geometry_revisions
                ON line_geometry_revisions.manifest_sha256 = lines.manifest_sha256
               AND line_geometry_revisions.source_span_id = lines.source_span_id
               AND line_geometry_revisions.revision = (
                    SELECT MAX(latest.revision)
                    FROM line_geometry_revisions AS latest
                    WHERE latest.manifest_sha256 = lines.manifest_sha256
                      AND latest.source_span_id = lines.source_span_id
               )
            WHERE lines.manifest_sha256 = ?
            ORDER BY lines.page_index, lines.rowid
            """,
            (manifest_sha256,),
        ).fetchall()
        reading_order_rows = connection.execute(
            """
            SELECT page_index, region_ids_json
            FROM page_reading_order_revisions
            WHERE manifest_sha256 = ?
              AND revision = (
                    SELECT MAX(latest.revision)
                    FROM page_reading_order_revisions AS latest
                    WHERE latest.manifest_sha256 = page_reading_order_revisions.manifest_sha256
                      AND latest.page_index = page_reading_order_revisions.page_index
              )
            ORDER BY page_index
            """,
            (manifest_sha256,),
        ).fetchall()
        region_geometry_rows = connection.execute(
            """
            SELECT
                region_geometry_revisions.page_index,
                region_geometry_revisions.region_id,
                region_geometry_revisions.polygon_json,
                pages.width_px,
                pages.height_px
            FROM region_geometry_revisions
            JOIN pages
                ON pages.manifest_sha256 = region_geometry_revisions.manifest_sha256
               AND pages.page_index = region_geometry_revisions.page_index
            WHERE region_geometry_revisions.manifest_sha256 = ?
              AND region_geometry_revisions.revision = (
                    SELECT MAX(latest.revision)
                    FROM region_geometry_revisions AS latest
                    WHERE latest.manifest_sha256 = region_geometry_revisions.manifest_sha256
                      AND latest.page_index = region_geometry_revisions.page_index
                      AND latest.region_id = region_geometry_revisions.region_id
              )
            ORDER BY region_geometry_revisions.page_index, region_geometry_revisions.region_id
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

    geometries: dict[tuple[int, str, str], tuple[list[list[int]], list[list[int]] | None]] = {}
    for source_span_id, page_index, page_id, line_id, polygon_json, baseline_json in geometry_rows:
        try:
            polygon = json.loads(polygon_json)
            baseline = json.loads(baseline_json) if baseline_json is not None else None
        except (TypeError, json.JSONDecodeError) as error:
            raise ProjectStoreError(
                f"stored geometry is unreadable for project line {source_span_id}"
            ) from error
        if not isinstance(polygon, list) or (
            baseline is not None and not isinstance(baseline, list)
        ):
            raise ProjectStoreError(f"stored geometry is invalid for project line {source_span_id}")
        key = (page_index, page_id, line_id)
        if key in geometries:
            raise ProjectStoreError(f"project contains duplicate geometry locator {key!r}")
        geometries[key] = polygon, baseline

    reading_orders: dict[int, list[str]] = {}
    for page_index, region_ids_json in reading_order_rows:
        try:
            region_ids = json.loads(region_ids_json)
        except (TypeError, json.JSONDecodeError) as error:
            raise ProjectStoreError(
                f"stored reading order is unreadable for project page {page_index}"
            ) from error
        if (
            not isinstance(page_index, int)
            or not isinstance(region_ids, list)
            or any(
                not isinstance(region_id, str) or not region_id.strip()
                for region_id in region_ids
            )
            or len(region_ids) != len(set(region_ids))
        ):
            raise ProjectStoreError(
                f"stored reading order is invalid for project page {page_index}"
            )
        if page_index in reading_orders:
            raise ProjectStoreError(f"project contains duplicate reading order page {page_index}")
        reading_orders[page_index] = region_ids

    region_geometries: dict[tuple[int, str], list[list[int]]] = {}
    for page_index, region_id, polygon_json, width, height in region_geometry_rows:
        try:
            polygon = json.loads(polygon_json)
        except (TypeError, json.JSONDecodeError) as error:
            raise ProjectStoreError(
                f"stored region geometry is unreadable for project region {region_id!r}"
            ) from error
        if (
            not isinstance(page_index, int)
            or not isinstance(region_id, str)
            or not region_id.strip()
        ):
            raise ProjectStoreError("stored region geometry locator is invalid")
        revised_polygon = _validated_points(
            polygon,
            role=f"stored region geometry {region_id!r}",
            width=int(width),
            height=int(height),
            allow_none=False,
        )
        key = (page_index, region_id)
        if key in region_geometries:
            raise ProjectStoreError(f"project contains duplicate region geometry locator {key!r}")
        region_geometries[key] = revised_polygon

    source_bytes = source_path.read_bytes()
    if _FORBIDDEN_PAGE_XML_DECLARATION.search(source_bytes):
        raise ProjectStoreError("stored PAGE XML contains a forbidden XML declaration")
    try:
        document = ET.fromstring(source_bytes)
    except ET.ParseError as error:
        raise ProjectStoreError("stored PAGE XML cannot be parsed for export") from error
    pages = [element for element in document.iter() if _xml_local_name(element) == "Page"]
    seen: set[tuple[int, str, str]] = set()
    seen_geometries: set[tuple[int, str, str]] = set()
    seen_reading_orders: set[int] = set()
    seen_region_geometries: set[tuple[int, str]] = set()
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
            geometry = geometries.get(key)
            if revised_text is not None:
                _replace_text_equiv(line, revised_text)
                seen.add(key)
            if geometry is not None:
                _replace_line_geometry(
                    line,
                    polygon=geometry[0],
                    baseline=geometry[1],
                )
                seen_geometries.add(key)
        region_ids = reading_orders.get(page_index)
        if region_ids is not None:
            _replace_page_reading_order(page, region_ids)
            seen_reading_orders.add(page_index)
        for region in page.iter():
            if _xml_local_name(region) != "TextRegion":
                continue
            raw_region_id = region.get("id")
            if not isinstance(raw_region_id, str) or not raw_region_id.strip():
                continue
            key = (page_index, raw_region_id.strip())
            polygon = region_geometries.get(key)
            if polygon is not None:
                _replace_region_geometry(region, polygon=polygon)
                seen_region_geometries.add(key)
    missing = sorted(set(revisions) - seen)
    if missing:
        raise ProjectStoreError(
            "stored PAGE XML no longer matches the project's revision locators: "
            f"{missing[0]!r}"
        )
    missing_geometries = sorted(set(geometries) - seen_geometries)
    if missing_geometries:
        raise ProjectStoreError(
            "stored PAGE XML no longer matches the project's geometry locators: "
            f"{missing_geometries[0]!r}"
        )
    missing_reading_orders = sorted(set(reading_orders) - seen_reading_orders)
    if missing_reading_orders:
        raise ProjectStoreError(
            "stored PAGE XML no longer has project page "
            f"{missing_reading_orders[0]} for its reading-order revision"
        )
    missing_region_geometries = sorted(set(region_geometries) - seen_region_geometries)
    if missing_region_geometries:
        raise ProjectStoreError(
            "stored PAGE XML no longer matches the project's region geometry locator: "
            f"{missing_region_geometries[0]!r}"
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
        "line_geometry_revision_count": len(geometries),
        "page_reading_order_revision_count": len(reading_orders),
        "region_geometry_revision_count": len(region_geometries),
        "network_required": False,
    }



def _human_transcription_export_context(
    project: Path | str,
    output: Path | str,
    *,
    manifest_sha256: str,
    replace_existing: bool,
    output_role: str,
) -> tuple[Path, str, list[dict[str, int | str]]]:
    """Validate one safe, local transcription export and load effective line text."""

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    if not isinstance(replace_existing, bool):
        raise ProjectStoreError("replace_existing must be a boolean")
    root = _required_project_root(project)
    output_path = _local_path(output, role=output_role, must_exist=False)
    if not output_path.parent.is_dir():
        raise ProjectStoreError(f"{output_role} parent does not exist: {output_path.parent}")
    if output_path == root or root in output_path.parents:
        raise ProjectStoreError(
            f"{output_role} must be outside the project so project objects stay immutable"
        )

    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
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
        rows = connection.execute(
            """
            SELECT
                lines.page_index,
                lines.page_id,
                lines.region_id,
                lines.line_id,
                lines.source_span_id,
                COALESCE(lines.text_equiv, ''),
                COALESCE(latest.revised_text, lines.text_equiv, ''),
                COALESCE(latest.revision, 0),
                COALESCE(latest.editor, '')
            FROM lines
            LEFT JOIN transcription_revisions AS latest
                ON latest.manifest_sha256 = lines.manifest_sha256
               AND latest.source_span_id = lines.source_span_id
               AND latest.revision = (
                    SELECT MAX(previous.revision)
                    FROM transcription_revisions AS previous
                    WHERE previous.manifest_sha256 = lines.manifest_sha256
                      AND previous.source_span_id = lines.source_span_id
               )
            WHERE lines.manifest_sha256 = ?
            ORDER BY lines.page_index, lines.rowid
            """,
            (manifest_sha256,),
        ).fetchall()
    except sqlite3.Error as error:
        raise ProjectStoreError(
            f"cannot load project transcriptions for export: {error}"
        ) from error
    finally:
        connection.close()

    source_sha256, source_relative_path = source
    source_path = root / source_relative_path
    if not source_path.is_file() or _sha256_file(source_path) != source_sha256:
        raise ProjectStoreError("project PAGE XML source object is missing or checksum-mismatched")

    records: list[dict[str, int | str]] = []
    for (
        page_index,
        page_id,
        region_id,
        line_id,
        source_span_id,
        source_text,
        text,
        revision,
        editor,
    ) in rows:
        if (
            not isinstance(page_index, int)
            or page_index < 0
            or not isinstance(page_id, str)
            or not page_id.strip()
            or (region_id is not None and not isinstance(region_id, str))
            or not isinstance(line_id, str)
            or not line_id.strip()
            or not isinstance(source_span_id, str)
            or not source_span_id.strip()
            or not isinstance(source_text, str)
            or not isinstance(text, str)
            or not isinstance(revision, int)
            or revision < 0
            or not isinstance(editor, str)
        ):
            raise ProjectStoreError("project contains an invalid stored transcription export row")
        records.append(
            {
                "page_index": page_index,
                "page_id": page_id,
                "region_id": region_id or "",
                "line_id": line_id,
                "source_span_id": source_span_id,
                "source_text": source_text,
                "text": text,
                "revision": revision,
                "editor": editor,
            }
        )
    return output_path, source_sha256, records


def export_human_transcript(
    project: Path | str,
    output: Path | str,
    *,
    manifest_sha256: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    """Export effective imported/human text as a local UTF-8 transcript.

    Each PAGE XML line is written in source order. A form-feed line separates
    pages. Imported HTR proposals and pending offline-review proposals are
    deliberately excluded; only source text or the latest saved human revision
    is emitted.
    """

    output_path, source_sha256, rows = _human_transcription_export_context(
        project,
        output,
        manifest_sha256=manifest_sha256,
        replace_existing=replace_existing,
        output_role="transcript export",
    )
    rendered_lines: list[str] = []
    previous_page_index: int | None = None
    for row in rows:
        page_index = int(row["page_index"])
        if previous_page_index is not None and page_index != previous_page_index:
            rendered_lines.append("\f")
        rendered_lines.append(str(row["text"]))
        previous_page_index = page_index
    rendered = ("\n".join(rendered_lines) + ("\n" if rendered_lines else "")).encode("utf-8")
    _atomic_write_bytes(output_path, rendered, replace_existing=replace_existing)
    return {
        "status": "SUCCEEDED",
        "project": str(_required_project_root(project)),
        "manifest_sha256": manifest_sha256,
        "source_pagexml_sha256": source_sha256,
        "output": str(output_path),
        "output_sha256": hashlib.sha256(rendered).hexdigest(),
        "line_count": len(rows),
        "human_revision_count": sum(int(row["revision"]) > 0 for row in rows),
        "page_separator": "U+000C FORM FEED",
        "network_required": False,
    }


def export_human_transcriptions_csv(
    project: Path | str,
    output: Path | str,
    *,
    manifest_sha256: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    """Export effective imported/human line text as an interoperable local CSV.

    The CSV preserves imported line identity, source text, and the latest saved
    human revision metadata. It intentionally does not expose HTR suggestions,
    pending offline-review proposals, project paths, or source images.
    """

    output_path, source_sha256, rows = _human_transcription_export_context(
        project,
        output,
        manifest_sha256=manifest_sha256,
        replace_existing=replace_existing,
        output_role="transcription CSV export",
    )
    fieldnames = [
        "manifest_sha256",
        "page_index",
        "page_id",
        "region_id",
        "line_id",
        "source_span_id",
        "source_text",
        "text",
        "revision",
        "editor",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({"manifest_sha256": manifest_sha256, **row})
    rendered = stream.getvalue().encode("utf-8")
    _atomic_write_bytes(output_path, rendered, replace_existing=replace_existing)
    return {
        "status": "SUCCEEDED",
        "project": str(_required_project_root(project)),
        "manifest_sha256": manifest_sha256,
        "source_pagexml_sha256": source_sha256,
        "output": str(output_path),
        "output_sha256": hashlib.sha256(rendered).hexdigest(),
        "line_count": len(rows),
        "human_revision_count": sum(int(row["revision"]) > 0 for row in rows),
        "columns": fieldnames,
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
            SELECT
                lines.source_span_id,
                transcription_revisions.revision,
                htr_suggestions.suggested_text,
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
    human_revision_set: list[dict[str, object]] = []
    for source_span_id, revision, suggested_text, revised_text in rows:
        if (
            not isinstance(source_span_id, str)
            or not source_span_id.strip()
            or not isinstance(revision, int)
            or revision < 1
            or not isinstance(revised_text, str)
        ):
            raise ProjectStoreError("stored human revision is invalid")
        human_revision_set.append(
            {
                "source_span_id": source_span_id,
                "revision": revision,
                "revised_text_sha256": _revision_text_sha256(revised_text),
            }
        )
        if suggested_text is None:
            continue
        if not isinstance(suggested_text, str):
            raise ProjectStoreError("stored HTR suggestion is invalid")
        evaluated_pairs.append(
            (_normalize_htr_text(revised_text), _normalize_htr_text(suggested_text))
        )
    human_revision_set_sha256 = hashlib.sha256(
        _canonical_json(human_revision_set).encode("utf-8")
    ).hexdigest()

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
        "human_revision_set_sha256": human_revision_set_sha256,
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



def list_htr_suggestion_evaluations(
    project: Path | str,
    *,
    manifest_sha256: str,
) -> list[dict[str, object]]:
    """Return current human-vs-HTR evaluation reports for one imported document.

    Reports are calculated from the latest saved human revisions at read time.
    This function does not mark suggestions as accepted, mutate any model
    output, or persist a derived metric as a new source of truth.
    """

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    root = _required_project_root(project)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        runs = connection.execute(
            """
            SELECT output_sha256, imported_at
            FROM htr_runs
            WHERE manifest_sha256 = ?
            ORDER BY imported_at DESC, output_sha256
            """,
            (manifest_sha256,),
        ).fetchall()
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot list imported HTR results: {error}") from error
    finally:
        connection.close()

    evaluations: list[dict[str, object]] = []
    for output_sha256, imported_at in runs:
        if not isinstance(imported_at, str):
            raise ProjectStoreError("stored HTR result import time is invalid")
        report = evaluate_htr_suggestions(
            root,
            manifest_sha256=manifest_sha256,
            result_pagexml_sha256=output_sha256,
        )
        evaluations.append({**report, "imported_at": imported_at})
    return evaluations


def _document_record(row: tuple[object, ...]) -> dict[str, object]:
    try:
        tags = json.loads(row[3])
    except (TypeError, json.JSONDecodeError) as error:
        raise ProjectStoreError("stored document tags are unreadable") from error
    if (
        not isinstance(tags, list)
        or any(not isinstance(tag, str) or not tag.strip() for tag in tags)
        or len(tags) != len(set(tags))
    ):
        raise ProjectStoreError("stored document tags are invalid")
    return {
        "manifest_sha256": row[0],
        "document_id": row[1],
        "title": row[2],
        "tags": tags,
        "notes": row[4],
        "page_count": row[5],
        "region_count": row[6],
        "line_count": row[7],
        "source_pagexml_sha256": row[8],
        "created_at": row[9],
        "updated_at": row[10],
    }


def list_project_documents(path: Path | str) -> list[dict[str, object]]:
    """List each immutable PAGE XML import with mutable local document metadata."""

    root = _required_project_root(path)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        rows = connection.execute(
            """
            SELECT
                documents.manifest_sha256, documents.document_id, documents.title,
                documents.tags_json, documents.notes, pagexml_imports.page_count,
                pagexml_imports.region_count, pagexml_imports.line_count,
                pagexml_imports.pagexml_sha256, documents.created_at, documents.updated_at
            FROM documents
            JOIN pagexml_imports
                ON pagexml_imports.manifest_sha256 = documents.manifest_sha256
            ORDER BY documents.created_at, documents.manifest_sha256
            """
        ).fetchall()
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot list project documents: {error}") from error
    finally:
        connection.close()
    return [_document_record(row) for row in rows]


def _validated_document_tags(tags: Sequence[str]) -> list[str]:
    if isinstance(tags, (str, bytes)) or not isinstance(tags, Sequence):
        raise ProjectStoreError("document tags must be a sequence of nonblank strings")
    normalized: list[str] = []
    for position, tag in enumerate(tags):
        if not isinstance(tag, str) or not tag.strip() or tag != tag.strip():
            raise ProjectStoreError(f"document tags[{position}] must be a nonblank exact string")
        normalized.append(tag)
    if len(normalized) != len(set(normalized)):
        raise ProjectStoreError("document tags must be unique")
    return normalized


def update_project_document(
    path: Path | str,
    *,
    manifest_sha256: str,
    title: str | None = None,
    tags: Sequence[str] | None = None,
    notes: str | None = None,
) -> dict[str, object]:
    """Update mutable local metadata for one immutable PAGE XML import."""

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    if title is None and tags is None and notes is None:
        raise ProjectStoreError("document update requires title, tags, or notes")
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise ProjectStoreError("document title must be a nonblank string")
    if notes is not None and not isinstance(notes, str):
        raise ProjectStoreError("document notes must be a string")
    normalized_tags = None if tags is None else _validated_document_tags(tags)
    root = _required_project_root(path)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        with connection:
            row = connection.execute(
                """
                SELECT
                    documents.manifest_sha256, documents.document_id, documents.title,
                    documents.tags_json, documents.notes, pagexml_imports.page_count,
                    pagexml_imports.region_count, pagexml_imports.line_count,
                    pagexml_imports.pagexml_sha256, documents.created_at, documents.updated_at
                FROM documents
                JOIN pagexml_imports
                    ON pagexml_imports.manifest_sha256 = documents.manifest_sha256
                WHERE documents.manifest_sha256 = ?
                """,
                (manifest_sha256,),
            ).fetchone()
            if row is None:
                raise ProjectStoreError("project document was not found")
            current = _document_record(row)
            next_title = title.strip() if title is not None else current["title"]
            next_tags = normalized_tags if normalized_tags is not None else current["tags"]
            next_notes = notes if notes is not None else current["notes"]
            updated_at = _timestamp()
            connection.execute(
                """
                UPDATE documents
                SET title = ?, tags_json = ?, notes = ?, updated_at = ?
                WHERE manifest_sha256 = ?
                """,
                (next_title, _canonical_json(next_tags), next_notes, updated_at, manifest_sha256),
            )
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot update project document: {error}") from error
    finally:
        connection.close()
    return {
        **current,
        "title": next_title,
        "tags": next_tags,
        "notes": next_notes,
        "updated_at": updated_at,
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
                documents.document_id,
                pages.page_index,
                pages.page_id,
                pages.image_sha256,
                pages.width_px,
                pages.height_px,
                source_objects.relative_path
            FROM pages
            JOIN documents ON documents.manifest_sha256 = pages.manifest_sha256
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
            "document_id": row[1],
            "page_index": row[2],
            "page_id": row[3],
            "image_sha256": row[4],
            "width_px": row[5],
            "height_px": row[6],
            "image_path": str(root / row[7]),
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
        review_rows = connection.execute(
            """
            SELECT
                source_span_id,
                proposal_sha256,
                contributor,
                proposed_text,
                state,
                revised_at
            FROM review_proposals
            WHERE manifest_sha256 = ?
              AND state IN ('PENDING', 'CONFLICT')
            ORDER BY imported_at, proposal_sha256
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
    reviews_by_span: dict[str, list[dict[str, object]]] = {}
    for review in review_rows:
        reviews_by_span.setdefault(review[0], []).append(
            {
                "proposal_sha256": review[1],
                "contributor": review[2],
                "text": review[3],
                "state": review[4],
                "revised_at": review[5],
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
                "review_proposals": reviews_by_span.get(row[0], []),
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
    expected_revision: int | None = None,
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
    if (
        expected_revision is not None
        and (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        )
    ):
        raise ProjectStoreError("expected_revision must be a non-negative integer")
    root = _required_project_root(path)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
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
            if (
                expected_revision is not None
                and current_revision != expected_revision
            ):
                raise ProjectStoreError(
                    "transcription revision conflict; reload the current line"
                )
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


def undo_line_transcription(
    path: Path | str,
    *,
    manifest_sha256: str,
    source_span_id: str,
    editor: str = "local-user",
    expected_revision: int | None = None,
) -> dict[str, object]:
    """Append a reversal of the latest human transcription revision."""

    if not isinstance(manifest_sha256, str) or len(manifest_sha256) != 64:
        raise ProjectStoreError("manifest_sha256 must be a SHA-256 string")
    if not isinstance(source_span_id, str) or not source_span_id.strip():
        raise ProjectStoreError("source_span_id must be a nonblank string")
    if not isinstance(editor, str) or not editor.strip():
        raise ProjectStoreError("editor must be a nonblank string")
    if (
        expected_revision is not None
        and (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 0
        )
    ):
        raise ProjectStoreError("expected_revision must be a non-negative integer")
    root = _required_project_root(path)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        row = connection.execute(
            """
            SELECT
                lines.text_equiv,
                COALESCE(MAX(transcription_revisions.revision), 0)
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
        current_revision = int(row[1])
        if expected_revision is not None and current_revision != expected_revision:
            raise ProjectStoreError(
                "transcription revision conflict; reload the current line"
            )
        if current_revision == 0:
            return {
                "status": "UNDO_UNAVAILABLE",
                "project": str(root),
                "manifest_sha256": manifest_sha256,
                "source_span_id": source_span_id,
                "revision": 0,
                "network_required": False,
            }
        latest = connection.execute(
            """
            SELECT prior_text
            FROM transcription_revisions
            WHERE manifest_sha256 = ? AND source_span_id = ? AND revision = ?
            """,
            (manifest_sha256, source_span_id, current_revision),
        ).fetchone()
        if latest is None:
            raise ProjectStoreError("latest transcription revision is unavailable")
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot load transcription revision: {error}") from error
    finally:
        connection.close()
    prior_text = latest[0] if latest[0] is not None else row[0]
    if not isinstance(prior_text, str):
        prior_text = ""
    result = revise_line_transcription(
        root,
        manifest_sha256=manifest_sha256,
        source_span_id=source_span_id,
        text=prior_text,
        editor=editor,
        expected_revision=current_revision,
    )
    if result["status"] == "SAVED":
        result["status"] = "UNDONE"
        result["undone_revision"] = current_revision
    return result


def list_project_activity(
    path: Path | str,
    *,
    manifest_sha256: str,
    limit: int = 100,
) -> dict[str, object]:
    """List bounded, content-free revision activity for one imported document."""

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 500
    ):
        raise ProjectStoreError("activity limit must be an integer from 1 to 500")
    root = _required_project_root(path)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        rows = connection.execute(
            """
            SELECT
                kind,
                page_index,
                source_span_id,
                line_id,
                region_id,
                revision,
                editor,
                created_at
            FROM (
                SELECT
                    'TRANSCRIPTION' AS kind,
                    lines.page_index,
                    lines.source_span_id,
                    lines.line_id,
                    lines.region_id,
                    transcription_revisions.revision,
                    transcription_revisions.editor,
                    transcription_revisions.created_at
                FROM transcription_revisions
                JOIN lines
                    ON lines.manifest_sha256 = transcription_revisions.manifest_sha256
                   AND lines.source_span_id = transcription_revisions.source_span_id
                WHERE transcription_revisions.manifest_sha256 = ?
                UNION ALL
                SELECT
                    'LINE_GEOMETRY' AS kind,
                    lines.page_index,
                    lines.source_span_id,
                    lines.line_id,
                    lines.region_id,
                    line_geometry_revisions.revision,
                    line_geometry_revisions.editor,
                    line_geometry_revisions.created_at
                FROM line_geometry_revisions
                JOIN lines
                    ON lines.manifest_sha256 = line_geometry_revisions.manifest_sha256
                   AND lines.source_span_id = line_geometry_revisions.source_span_id
                WHERE line_geometry_revisions.manifest_sha256 = ?
                UNION ALL
                SELECT
                    'REGION_GEOMETRY' AS kind,
                    region_geometry_revisions.page_index,
                    NULL AS source_span_id,
                    NULL AS line_id,
                    region_geometry_revisions.region_id,
                    region_geometry_revisions.revision,
                    region_geometry_revisions.editor,
                    region_geometry_revisions.created_at
                FROM region_geometry_revisions
                WHERE region_geometry_revisions.manifest_sha256 = ?
                UNION ALL
                SELECT
                    'READING_ORDER' AS kind,
                    page_reading_order_revisions.page_index,
                    NULL AS source_span_id,
                    NULL AS line_id,
                    NULL AS region_id,
                    page_reading_order_revisions.revision,
                    page_reading_order_revisions.editor,
                    page_reading_order_revisions.created_at
                FROM page_reading_order_revisions
                WHERE page_reading_order_revisions.manifest_sha256 = ?
            )
            ORDER BY created_at DESC, kind ASC, page_index ASC, revision DESC
            LIMIT ?
            """,
            (
                manifest_sha256,
                manifest_sha256,
                manifest_sha256,
                manifest_sha256,
                limit,
            ),
        ).fetchall()
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot load project activity: {error}") from error
    finally:
        connection.close()
    events = [
        {
            "kind": row[0],
            "page_index": int(row[1]),
            "source_span_id": row[2],
            "line_id": row[3],
            "region_id": row[4],
            "revision": int(row[5]),
            "editor": row[6],
            "created_at": row[7],
        }
        for row in rows
    ]
    return {
        "manifest_sha256": manifest_sha256,
        "events": events,
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


_TRAINING_SPLITS = frozenset({"train", "validation", "test"})


def _require_training_split(split: str) -> str:
    if not isinstance(split, str) or split not in _TRAINING_SPLITS:
        allowed = ", ".join(sorted(_TRAINING_SPLITS))
        raise ProjectStoreError(f"split must be one of: {allowed}")
    return split


def _training_image_suffix(image_filename: str | None) -> str:
    if not isinstance(image_filename, str):
        return ".img"
    suffix = Path(image_filename.replace("\\", "/")).suffix
    if re.fullmatch(r"\.[A-Za-z0-9]{1,10}", suffix):
        return suffix.lower()
    return ".img"


def export_consented_training_pagexml(
    project: Path | str,
    output_directory: Path | str,
    *,
    manifest_sha256: str,
    split: str,
) -> dict[str, object]:
    """Create an atomic, consent-gated local PAGE XML training bundle.

    A bundle holds one fully human-revised and actively consented PAGE XML
    import, copied source images, an explicit split manifest, and an opaque
    provenance receipt. It does not run or download a training engine.
    """

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    split = _require_training_split(split)
    root = _required_project_root(project)
    readiness = training_readiness(root, manifest_sha256=manifest_sha256)
    if readiness["status"] != "READY_FOR_PAGEXML_TRAINING_EXPORT":
        raise ProjectStoreError(
            "project import is not ready for training export; every source line needs "
            "a current human revision and active contributor consent"
        )
    destination = _local_path(
        output_directory,
        role="training bundle directory",
        must_exist=False,
    )
    if not destination.parent.is_dir():
        raise ProjectStoreError(
            f"training bundle parent does not exist: {destination.parent}"
        )
    if destination.exists():
        raise ProjectStoreError(f"training bundle destination already exists: {destination}")
    if destination == root or root in destination.parents:
        raise ProjectStoreError(
            "training bundle must be outside the project so project storage stays immutable"
        )

    database = root / PROJECT_DATABASE_NAME
    connection = sqlite3.connect(database)
    try:
        image_rows = connection.execute(
            """
            SELECT pages.page_index, pages.image_sha256, source_objects.relative_path
            FROM pages
            JOIN source_objects ON source_objects.sha256 = pages.image_sha256
            WHERE pages.manifest_sha256 = ?
            ORDER BY pages.page_index
            """,
            (manifest_sha256,),
        ).fetchall()
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot load training-bundle source images: {error}") from error
    finally:
        connection.close()
    images_by_page = {row[0]: (row[1], row[2]) for row in image_rows}

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    moved = False
    try:
        pagexml_path = temporary / "document.page.xml"
        exported = export_human_pagexml(
            root,
            pagexml_path,
            manifest_sha256=manifest_sha256,
        )
        try:
            document = ET.fromstring(pagexml_path.read_bytes())
        except (OSError, ET.ParseError) as error:
            raise ProjectStoreError("generated PAGE XML training export is unreadable") from error
        pages = [element for element in document.iter() if _xml_local_name(element) == "Page"]
        if len(pages) != len(images_by_page):
            raise ProjectStoreError(
                "generated PAGE XML page count does not match the project import"
            )
        copied_images: dict[str, str] = {}
        for page_index, page in enumerate(pages):
            image = images_by_page.get(page_index)
            if image is None:
                raise ProjectStoreError(
                    "generated PAGE XML page order does not match the project import"
                )
            image_sha256, relative_path = image
            source_image = root / relative_path
            if not source_image.is_file() or _sha256_file(source_image) != image_sha256:
                raise ProjectStoreError(
                    f"project image object is missing or checksum-mismatched: {image_sha256}"
                )
            suffix = _training_image_suffix(page.get("imageFilename"))
            relative_destination = (Path("images") / f"{image_sha256}{suffix}").as_posix()
            target_image = temporary / relative_destination
            if relative_destination not in copied_images:
                target_image.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_image, target_image)
                if _sha256_file(target_image) != image_sha256:
                    raise ProjectStoreError(
                        f"training-bundle image copy failed checksum verification: {image_sha256}"
                    )
                copied_images[relative_destination] = image_sha256
            page.set("imageFilename", relative_destination)

        rendered_pagexml = ET.tostring(document, encoding="utf-8", xml_declaration=True)
        _atomic_write_bytes(
            pagexml_path,
            rendered_pagexml,
            replace_existing=True,
        )
        split_manifest = f"{split}.lst"
        split_path = temporary / split_manifest
        _atomic_write_bytes(split_path, b"document.page.xml\n", replace_existing=False)
        project_manifest = _read_project_manifest(root)
        bundle_payload = {
            "contract": {
                "name": "aktreader-consented-pagexml-training-bundle",
                "version": "1.0.0",
            },
            "created_at": _timestamp(),
            "project": {
                "project_id": project_manifest["project_id"],
                "name": project_manifest["name"],
            },
            "source_import": {
                "manifest_sha256": manifest_sha256,
                "source_pagexml_sha256": exported["source_pagexml_sha256"],
                "page_count": len(pages),
                "eligible_training_line_count": readiness["eligible_training_line_count"],
                "active_consent_grant_count": readiness["active_consent_grant_count"],
            },
            "split": split,
            "kraken": {
                "format_type": "xml",
                "manifest": split_manifest,
                "pagexml": pagexml_path.name,
                "compile_command": (
                    f"ketos compile -f xml -o {split}.arrow {pagexml_path.name}"
                ),
            },
            "files": {
                "pagexml": {
                    "path": pagexml_path.name,
                    "sha256": hashlib.sha256(rendered_pagexml).hexdigest(),
                },
                "manifest": {
                    "path": split_manifest,
                    "sha256": _sha256_file(split_path),
                },
                "images": [
                    {"path": path, "sha256": digest}
                    for path, digest in sorted(copied_images.items())
                ],
            },
            "network_required": False,
        }
        bundle_manifest_path = temporary / "bundle.aktreader.json"
        _atomic_write_json(bundle_manifest_path, bundle_payload)
        bundle_manifest_sha256 = _sha256_file(bundle_manifest_path)

        connection = sqlite3.connect(database)
        try:
            with connection:
                existing = connection.execute(
                    """
                    SELECT split
                    FROM training_split_assignments
                    WHERE manifest_sha256 = ?
                    """,
                    (manifest_sha256,),
                ).fetchone()
                if existing is not None and existing[0] != split:
                    raise ProjectStoreError(
                        "project import already has a different immutable training split "
                        f"assignment: {existing[0]}"
                    )
                os.replace(temporary, destination)
                moved = True
                connection.execute(
                    """
                    INSERT INTO training_split_assignments
                        (manifest_sha256, split, bundle_manifest_sha256, exported_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(manifest_sha256) DO UPDATE SET
                        bundle_manifest_sha256 = excluded.bundle_manifest_sha256,
                        exported_at = excluded.exported_at
                    """,
                    (
                        manifest_sha256,
                        split,
                        bundle_manifest_sha256,
                        _timestamp(),
                    ),
                )
        except sqlite3.Error as error:
            raise ProjectStoreError(f"cannot record training split assignment: {error}") from error
        finally:
            connection.close()
    finally:
        if not moved and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)

    return {
        "status": "SUCCEEDED",
        "project": str(root),
        "manifest_sha256": manifest_sha256,
        "split": split,
        "bundle": str(destination),
        "bundle_manifest": str(destination / "bundle.aktreader.json"),
        "bundle_manifest_sha256": bundle_manifest_sha256,
        "pagexml_sha256": hashlib.sha256(rendered_pagexml).hexdigest(),
        "page_count": len(pages),
        "eligible_training_line_count": readiness["eligible_training_line_count"],
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
        training_split_assignment_count = connection.execute(
            "SELECT COUNT(*) FROM training_split_assignments"
        ).fetchone()[0]
        review_proposal_count = connection.execute(
            "SELECT COUNT(*) FROM review_proposals"
        ).fetchone()[0]
        line_geometry_revision_count = connection.execute(
            "SELECT COUNT(*) FROM line_geometry_revisions"
        ).fetchone()[0]
        page_reading_order_revision_count = connection.execute(
            "SELECT COUNT(*) FROM page_reading_order_revisions"
        ).fetchone()[0]
        region_geometry_revision_count = connection.execute(
            "SELECT COUNT(*) FROM region_geometry_revisions"
        ).fetchone()[0]
        document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
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
        "training_split_assignment_count": training_split_assignment_count,
        "review_proposal_count": review_proposal_count,
        "line_geometry_revision_count": line_geometry_revision_count,
        "page_reading_order_revision_count": page_reading_order_revision_count,
        "region_geometry_revision_count": region_geometry_revision_count,
        "document_count": document_count,
        "network_required": False,
    }


_REVIEW_PACKAGE_CONTRACT = {
    "name": "aktreader-offline-review-package",
    "version": "1.0.0",
}


def _text_sha256_or_none(value: str | None) -> str | None:
    return None if value is None else _revision_text_sha256(value)


def _read_strict_json_object(path: Path, *, role: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProjectStoreError(f"{role} is not readable strict JSON: {path}") from error
    if not isinstance(payload, dict):
        raise ProjectStoreError(f"{role} must be a JSON object")
    return payload


def _require_exact_keys(
    payload: dict[str, object],
    *,
    required: set[str],
    role: str,
) -> None:
    keys = set(payload)
    if keys == required:
        return
    details: list[str] = []
    missing = sorted(required - keys)
    extra = sorted(keys - required)
    if missing:
        details.append(f"missing {', '.join(missing)}")
    if extra:
        details.append(f"unexpected {', '.join(extra)}")
    raise ProjectStoreError(f"{role} has invalid keys: {'; '.join(details)}")


def _current_line_text(
    connection: sqlite3.Connection,
    *,
    manifest_sha256: str,
    source_span_id: str,
) -> tuple[int, str | None]:
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
    return int(row[1]), row[2] if row[2] is not None else row[0]


def export_review_package(
    project: Path | str,
    output: Path | str,
    *,
    manifest_sha256: str,
    contributor: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    """Export one reviewer's current revisions as a deterministic local package."""

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    if not isinstance(contributor, str) or not contributor.strip():
        raise ProjectStoreError("review contributor must be a nonblank string")
    if not isinstance(replace_existing, bool):
        raise ProjectStoreError("replace_existing must be a boolean")
    root = _required_project_root(project)
    output_path = _local_path(output, role="review package output", must_exist=False)
    if not output_path.parent.is_dir():
        raise ProjectStoreError(
            f"review package output parent does not exist: {output_path.parent}"
        )
    if output_path == root or root in output_path.parents:
        raise ProjectStoreError("review package output must be outside the project")
    if output_path.exists() and not replace_existing:
        raise ProjectStoreError(
            "review package output already exists; pass replace_existing=True"
        )

    contributor = contributor.strip()
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        source = connection.execute(
            "SELECT pagexml_sha256 FROM pagexml_imports WHERE manifest_sha256 = ?",
            (manifest_sha256,),
        ).fetchone()
        if source is None:
            raise ProjectStoreError("project PAGE XML import was not found")
        rows = connection.execute(
            """
            SELECT
                revisions.source_span_id,
                revisions.prior_text,
                revisions.revised_text,
                revisions.created_at
            FROM transcription_revisions AS revisions
            WHERE revisions.manifest_sha256 = ?
              AND revisions.editor = ?
              AND revisions.revision = (
                  SELECT MAX(latest.revision)
                  FROM transcription_revisions AS latest
                  WHERE latest.manifest_sha256 = revisions.manifest_sha256
                    AND latest.source_span_id = revisions.source_span_id
              )
            ORDER BY revisions.source_span_id
            """,
            (manifest_sha256, contributor),
        ).fetchall()
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot export review package: {error}") from error
    finally:
        connection.close()
    if not rows:
        raise ProjectStoreError(
            "review package has no current human revisions from this contributor"
        )
    proposals = [
        {
            "source_span_id": row[0],
            "base_text_sha256": _text_sha256_or_none(row[1]),
            "proposed_text": row[2],
            "proposed_text_sha256": _revision_text_sha256(row[2]),
            "revised_at": row[3],
        }
        for row in rows
    ]
    package = {
        "contract": _REVIEW_PACKAGE_CONTRACT,
        "source": {"pagexml_sha256": source[0]},
        "contributor": contributor,
        "proposals": proposals,
        "network_required": False,
    }
    _atomic_write_json(output_path, package)
    return {
        "status": "EXPORTED",
        "project": str(root),
        "manifest_sha256": manifest_sha256,
        "contributor": contributor,
        "output": str(output_path),
        "package_sha256": _sha256_file(output_path),
        "proposal_count": len(proposals),
        "network_required": False,
    }


def _validated_review_package(
    package_path: Path,
) -> tuple[dict[str, object], str, list[dict[str, object]]]:
    package = _read_strict_json_object(package_path, role="review package")
    _require_exact_keys(
        package,
        required={"contract", "source", "contributor", "proposals", "network_required"},
        role="review package",
    )
    if package["contract"] != _REVIEW_PACKAGE_CONTRACT:
        raise ProjectStoreError("review package has an unsupported contract")
    if package["network_required"] is not False:
        raise ProjectStoreError("review package must explicitly require no network")
    source = package["source"]
    if not isinstance(source, dict):
        raise ProjectStoreError("review package source must be an object")
    _require_exact_keys(
        source,
        required={"pagexml_sha256"},
        role="review package source",
    )
    _require_sha256(source["pagexml_sha256"], role="review package source PAGE XML SHA-256")
    contributor = package["contributor"]
    if not isinstance(contributor, str) or not contributor.strip():
        raise ProjectStoreError("review package contributor must be a nonblank string")
    raw_proposals = package["proposals"]
    if not isinstance(raw_proposals, list) or not raw_proposals:
        raise ProjectStoreError("review package proposals must be a non-empty array")

    proposals: list[dict[str, object]] = []
    seen_spans: set[str] = set()
    for position, proposal in enumerate(raw_proposals, start=1):
        if not isinstance(proposal, dict):
            raise ProjectStoreError(f"review package proposal {position} must be an object")
        _require_exact_keys(
            proposal,
            required={
                "source_span_id",
                "base_text_sha256",
                "proposed_text",
                "proposed_text_sha256",
                "revised_at",
            },
            role=f"review package proposal {position}",
        )
        source_span_id = proposal["source_span_id"]
        if not isinstance(source_span_id, str) or not source_span_id.strip():
            raise ProjectStoreError(
                f"review package proposal {position} source_span_id must be nonblank"
            )
        if source_span_id in seen_spans:
            raise ProjectStoreError("review package must not repeat a source span")
        seen_spans.add(source_span_id)
        base_text_sha256 = proposal["base_text_sha256"]
        if base_text_sha256 is not None:
            _require_sha256(
                base_text_sha256,
                role=f"review package proposal {position} base_text_sha256",
            )
        proposed_text = proposal["proposed_text"]
        if not isinstance(proposed_text, str):
            raise ProjectStoreError(
                f"review package proposal {position} proposed_text must be a string"
            )
        proposed_text_sha256 = _require_sha256(
            proposal["proposed_text_sha256"],
            role=f"review package proposal {position} proposed_text_sha256",
        )
        if _revision_text_sha256(proposed_text) != proposed_text_sha256:
            raise ProjectStoreError(
                f"review package proposal {position} proposed_text checksum mismatch"
            )
        revised_at = proposal["revised_at"]
        if not isinstance(revised_at, str) or not revised_at.strip():
            raise ProjectStoreError(
                f"review package proposal {position} revised_at must be nonblank"
            )
        proposals.append(
            {
                "source_span_id": source_span_id,
                "base_text_sha256": base_text_sha256,
                "proposed_text": proposed_text,
                "proposed_text_sha256": proposed_text_sha256,
                "revised_at": revised_at,
            }
        )
    if proposals != sorted(proposals, key=lambda item: str(item["source_span_id"])):
        raise ProjectStoreError("review package proposals must be ordered by source_span_id")
    return package, _sha256_file(package_path), proposals


def import_review_package(
    project: Path | str,
    package_path: Path | str,
) -> dict[str, object]:
    """Queue valid offline review proposals without applying their text."""

    root = _required_project_root(project)
    package_file = _local_path(package_path, role="review package", must_exist=True)
    if not package_file.is_file():
        raise ProjectStoreError(f"review package is not a file: {package_file}")
    package, package_sha256, proposals = _validated_review_package(package_file)
    source = package["source"]
    assert isinstance(source, dict)
    source_pagexml_sha256 = _require_sha256(
        source["pagexml_sha256"],
        role="review package source PAGE XML SHA-256",
    )
    contributor = str(package["contributor"]).strip()
    proposal_sha256s: list[str] = []
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            imports = connection.execute(
                """
                SELECT manifest_sha256
                FROM pagexml_imports
                WHERE pagexml_sha256 = ?
                ORDER BY manifest_sha256
                """,
                (source_pagexml_sha256,),
            ).fetchall()
            if len(imports) != 1:
                raise ProjectStoreError(
                    "review package source PAGE XML must match exactly one project import"
                )
            manifest_sha256 = imports[0][0]
            pending_count = 0
            conflict_count = 0
            already_imported_count = 0
            for proposal in proposals:
                source_span_id = str(proposal["source_span_id"])
                _, current_text = _current_line_text(
                    connection,
                    manifest_sha256=manifest_sha256,
                    source_span_id=source_span_id,
                )
                base_text_sha256 = proposal["base_text_sha256"]
                state = (
                    "PENDING"
                    if _text_sha256_or_none(current_text) == base_text_sha256
                    else "CONFLICT"
                )
                proposal_sha256 = hashlib.sha256(
                    _canonical_json(
                        {
                            "package_sha256": package_sha256,
                            "source_span_id": source_span_id,
                            "base_text_sha256": base_text_sha256,
                            "proposed_text_sha256": proposal["proposed_text_sha256"],
                        }
                    ).encode("utf-8")
                ).hexdigest()
                proposal_sha256s.append(proposal_sha256)
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO review_proposals (
                        proposal_sha256, package_sha256, manifest_sha256,
                        source_pagexml_sha256, source_span_id, contributor,
                        base_text_sha256, proposed_text, proposed_text_sha256,
                        revised_at, state, imported_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        proposal_sha256,
                        package_sha256,
                        manifest_sha256,
                        source_pagexml_sha256,
                        source_span_id,
                        contributor,
                        base_text_sha256,
                        proposal["proposed_text"],
                        proposal["proposed_text_sha256"],
                        proposal["revised_at"],
                        state,
                        _timestamp(),
                    ),
                )
                if cursor.rowcount == 0:
                    already_imported_count += 1
                elif state == "PENDING":
                    pending_count += 1
                else:
                    conflict_count += 1
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot import review package: {error}") from error
    finally:
        connection.close()
    return {
        "status": "QUEUED",
        "project": str(root),
        "package": str(package_file),
        "package_sha256": package_sha256,
        "manifest_sha256": manifest_sha256,
        "contributor": contributor,
        "pending_count": pending_count,
        "conflict_count": conflict_count,
        "already_imported_count": already_imported_count,
        "proposal_sha256s": proposal_sha256s,
        "network_required": False,
    }


def resolve_review_proposal(
    project: Path | str,
    *,
    proposal_sha256: str,
    decision: str,
    editor: str,
) -> dict[str, object]:
    """Accept or reject one queued review proposal explicitly."""

    proposal_sha256 = _require_sha256(proposal_sha256, role="proposal_sha256")
    if decision not in {"accept", "reject"}:
        raise ProjectStoreError("review proposal decision must be accept or reject")
    if not isinstance(editor, str) or not editor.strip():
        raise ProjectStoreError("review decision editor must be a nonblank string")
    root = _required_project_root(project)
    editor = editor.strip()
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            proposal = connection.execute(
                """
                SELECT
                    manifest_sha256,
                    source_span_id,
                    contributor,
                    base_text_sha256,
                    proposed_text,
                    state
                FROM review_proposals
                WHERE proposal_sha256 = ?
                """,
                (proposal_sha256,),
            ).fetchone()
            if proposal is None:
                raise ProjectStoreError("review proposal was not found")
            manifest_sha256, source_span_id, contributor, base_sha, proposed_text, state = proposal
            if state in {"ACCEPTED", "REJECTED"}:
                raise ProjectStoreError(
                    f"review proposal was already resolved as {state.lower()}"
                )
            if decision == "reject":
                connection.execute(
                    """
                    UPDATE review_proposals
                    SET state = 'REJECTED', decided_by = ?, decided_at = ?
                    WHERE proposal_sha256 = ?
                    """,
                    (editor, _timestamp(), proposal_sha256),
                )
                return {
                    "status": "REJECTED",
                    "project": str(root),
                    "proposal_sha256": proposal_sha256,
                    "contributor": contributor,
                    "editor": editor,
                    "network_required": False,
                }
            current_revision, current_text = _current_line_text(
                connection,
                manifest_sha256=manifest_sha256,
                source_span_id=source_span_id,
            )
            if _text_sha256_or_none(current_text) != base_sha:
                connection.execute(
                    "UPDATE review_proposals SET state = 'CONFLICT' WHERE proposal_sha256 = ?",
                    (proposal_sha256,),
                )
                return {
                    "status": "CONFLICT",
                    "project": str(root),
                    "proposal_sha256": proposal_sha256,
                    "contributor": contributor,
                    "network_required": False,
                }
            revision = current_revision + 1
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
                    proposed_text,
                    editor,
                    _timestamp(),
                ),
            )
            connection.execute(
                """
                UPDATE review_proposals
                SET state = 'ACCEPTED', decided_by = ?, decided_at = ?
                WHERE proposal_sha256 = ?
                """,
                (editor, _timestamp(), proposal_sha256),
            )
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot resolve review proposal: {error}") from error
    finally:
        connection.close()
    return {
        "status": "ACCEPTED",
        "project": str(root),
        "proposal_sha256": proposal_sha256,
        "contributor": contributor,
        "editor": editor,
        "manifest_sha256": manifest_sha256,
        "source_span_id": source_span_id,
        "revision": revision,
        "network_required": False,
    }


def _validated_points(
    value: object,
    *,
    role: str,
    width: int,
    height: int,
    allow_none: bool,
) -> list[list[int]] | None:
    if value is None and allow_none:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ProjectStoreError(f"{role} must be an array of [x, y] source-pixel points")
    points: list[list[int]] = []
    for position, point in enumerate(value, start=1):
        if (
            isinstance(point, (str, bytes))
            or not isinstance(point, Sequence)
            or len(point) != 2
            or isinstance(point[0], bool)
            or isinstance(point[1], bool)
            or not isinstance(point[0], int)
            or not isinstance(point[1], int)
        ):
            raise ProjectStoreError(f"{role} point {position} must be two integer pixels")
        x, y = point
        if not 0 <= x <= width or not 0 <= y <= height:
            raise ProjectStoreError(
                f"{role} point {position} is outside source image {width}x{height}"
            )
        points.append([x, y])
    if len(points) < 2 or len({tuple(point) for point in points}) < 2:
        raise ProjectStoreError(f"{role} must contain at least two distinct points")
    return points


def _geometry_bbox(points: list[list[int]]) -> dict[str, int | str]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "x": min(xs),
        "y": min(ys),
        "width": max(1, max(xs) - min(xs)),
        "height": max(1, max(ys) - min(ys)),
        "coordinate_space": "source_pixels",
    }



def load_project_page_layout(
    path: Path | str,
    *,
    manifest_sha256: str,
    page_index: int,
) -> dict[str, object]:
    """Load effective region geometry and reading order for one imported page."""

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    if not isinstance(page_index, int) or isinstance(page_index, bool) or page_index < 0:
        raise ProjectStoreError("page_index must be a non-negative integer")
    root = _required_project_root(path)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        page = connection.execute(
            """
            SELECT width_px, height_px
            FROM pages
            WHERE manifest_sha256 = ? AND page_index = ?
            """,
            (manifest_sha256, page_index),
        ).fetchone()
        if page is None:
            raise ProjectStoreError("project page was not found")
        width, height = int(page[0]), int(page[1])
        source_region_ids = _stored_page_region_order(
            root,
            connection,
            manifest_sha256=manifest_sha256,
            page_index=page_index,
        )
        source_polygons = {
            region_id: _validated_points(
                _stored_region_polygon(
                    root,
                    connection,
                    manifest_sha256=manifest_sha256,
                    page_index=page_index,
                    region_id=region_id,
                ),
                role="stored region polygon",
                width=width,
                height=height,
                allow_none=False,
            )
            for region_id in source_region_ids
        }
        line_rows = connection.execute(
            """
            SELECT source_span_id, line_id, locator_json
            FROM lines
            WHERE manifest_sha256 = ? AND page_index = ?
            ORDER BY rowid
            """,
            (manifest_sha256, page_index),
        ).fetchall()
        effective_lines: dict[
            str, tuple[int, list[list[int]], list[list[int]] | None, str]
        ] = {}
        line_order: list[str] = []
        for source_span_id, line_id, locator_json in line_rows:
            if (
                not isinstance(source_span_id, str)
                or not source_span_id.strip()
                or not isinstance(line_id, str)
                or not line_id.strip()
            ):
                raise ProjectStoreError("stored line identity is invalid")
            try:
                locator = json.loads(locator_json)
            except (TypeError, json.JSONDecodeError) as error:
                raise ProjectStoreError("stored line locator is unreadable") from error
            if not isinstance(locator, dict):
                raise ProjectStoreError("stored line locator is invalid")
            polygon = _validated_points(
                locator.get("polygon"),
                role="stored line polygon",
                width=width,
                height=height,
                allow_none=False,
            )
            baseline = _validated_points(
                locator.get("baseline"),
                role="stored line baseline",
                width=width,
                height=height,
                allow_none=True,
            )
            if source_span_id in effective_lines:
                raise ProjectStoreError("project page has duplicate line identities")
            effective_lines[source_span_id] = (0, polygon, baseline, line_id)
            line_order.append(source_span_id)
        geometry_rows = connection.execute(
            """
            SELECT region_id, revision, polygon_json
            FROM region_geometry_revisions
            WHERE manifest_sha256 = ? AND page_index = ?
            ORDER BY region_id, revision
            """,
            (manifest_sha256, page_index),
        ).fetchall()
        effective_regions: dict[str, tuple[int, list[list[int]]]] = {
            region_id: (0, polygon) for region_id, polygon in source_polygons.items()
        }
        for region_id, revision, polygon_json in geometry_rows:
            if region_id not in source_polygons:
                raise ProjectStoreError("stored region geometry refers to an unknown region")
            try:
                polygon = json.loads(polygon_json)
            except (TypeError, json.JSONDecodeError) as error:
                raise ProjectStoreError("stored region geometry is unreadable") from error
            effective_regions[region_id] = (
                int(revision),
                _validated_points(
                    polygon,
                    role="stored region polygon",
                    width=width,
                    height=height,
                    allow_none=False,
                ),
            )
        line_geometry_rows = connection.execute(
            """
            SELECT source_span_id, revision, polygon_json, baseline_json
            FROM line_geometry_revisions
            WHERE manifest_sha256 = ? AND source_span_id IN (
                SELECT source_span_id
                FROM lines
                WHERE manifest_sha256 = ? AND page_index = ?
            )
            ORDER BY source_span_id, revision
            """,
            (manifest_sha256, manifest_sha256, page_index),
        ).fetchall()
        for source_span_id, revision, polygon_json, baseline_json in line_geometry_rows:
            current = effective_lines.get(source_span_id)
            if current is None:
                raise ProjectStoreError("stored line geometry refers to an unknown line")
            try:
                polygon = json.loads(polygon_json)
                baseline = json.loads(baseline_json) if baseline_json is not None else None
            except (TypeError, json.JSONDecodeError) as error:
                raise ProjectStoreError("stored line geometry is unreadable") from error
            effective_lines[source_span_id] = (
                int(revision),
                _validated_points(
                    polygon,
                    role="stored line polygon",
                    width=width,
                    height=height,
                    allow_none=False,
                ),
                _validated_points(
                    baseline,
                    role="stored line baseline",
                    width=width,
                    height=height,
                    allow_none=True,
                ),
                current[3],
            )
        order_row = connection.execute(
            """
            SELECT revision, region_ids_json
            FROM page_reading_order_revisions
            WHERE manifest_sha256 = ? AND page_index = ?
            ORDER BY revision DESC
            LIMIT 1
            """,
            (manifest_sha256, page_index),
        ).fetchone()
        if order_row is None:
            reading_order_revision = 0
            region_ids = source_region_ids
        else:
            try:
                stored_region_ids = json.loads(order_row[1])
            except (TypeError, json.JSONDecodeError) as error:
                raise ProjectStoreError("stored page reading order is unreadable") from error
            reading_order_revision = int(order_row[0])
            region_ids = _validated_region_order(
                stored_region_ids,
                expected_region_ids=source_region_ids,
            )
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot load project page layout: {error}") from error
    finally:
        connection.close()
    return {
        "manifest_sha256": manifest_sha256,
        "page_index": page_index,
        "reading_order": {
            "revision": reading_order_revision,
            "region_ids": region_ids,
        },
        "regions": [
            {
                "region_id": region_id,
                "polygon": effective_regions[region_id][1],
                "revision": effective_regions[region_id][0],
            }
            for region_id in region_ids
        ],
        "lines": [
            {
                "source_span_id": source_span_id,
                "line_id": effective_lines[source_span_id][3],
                "polygon": effective_lines[source_span_id][1],
                "baseline": effective_lines[source_span_id][2],
                "revision": effective_lines[source_span_id][0],
            }
            for source_span_id in line_order
        ],
        "network_required": False,
    }

def _validated_expected_revision(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProjectStoreError("expected_revision must be a non-negative integer")
    return value


def revise_line_geometry(
    project: Path | str,
    *,
    manifest_sha256: str,
    source_span_id: str,
    polygon: Sequence[Sequence[int]],
    baseline: Sequence[Sequence[int]] | None,
    editor: str,
    expected_revision: int | None = None,
) -> dict[str, object]:
    """Append an audited local line geometry revision without altering source XML."""

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    if not isinstance(source_span_id, str) or not source_span_id.strip():
        raise ProjectStoreError("source_span_id must be a nonblank string")
    if not isinstance(editor, str) or not editor.strip():
        raise ProjectStoreError("geometry editor must be a nonblank string")
    expected_revision = _validated_expected_revision(expected_revision)
    root = _required_project_root(project)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT lines.locator_json, pages.width_px, pages.height_px
                FROM lines
                JOIN pages
                    ON pages.manifest_sha256 = lines.manifest_sha256
                   AND pages.page_index = lines.page_index
                WHERE lines.manifest_sha256 = ? AND lines.source_span_id = ?
                """,
                (manifest_sha256, source_span_id),
            ).fetchone()
            if row is None:
                raise ProjectStoreError("project line was not found")
            try:
                locator = json.loads(row[0])
            except (TypeError, json.JSONDecodeError) as error:
                raise ProjectStoreError("stored line locator is unreadable") from error
            if not isinstance(locator, dict):
                raise ProjectStoreError("stored line locator is invalid")
            source_polygon = locator.get("polygon")
            source_baseline = locator.get("baseline")
            if not isinstance(source_polygon, list):
                raise ProjectStoreError("stored line polygon is invalid")
            width, height = int(row[1]), int(row[2])
            revised_polygon = _validated_points(
                polygon,
                role="line polygon",
                width=width,
                height=height,
                allow_none=False,
            )
            revised_baseline = _validated_points(
                baseline,
                role="line baseline",
                width=width,
                height=height,
                allow_none=True,
            )
            latest = connection.execute(
                """
                SELECT revision, polygon_json, baseline_json
                FROM line_geometry_revisions
                WHERE manifest_sha256 = ? AND source_span_id = ?
                ORDER BY revision DESC
                LIMIT 1
                """,
                (manifest_sha256, source_span_id),
            ).fetchone()
            if latest is None:
                current_revision = 0
                prior_polygon = source_polygon
                prior_baseline = source_baseline
            else:
                current_revision = int(latest[0])
                prior_polygon = json.loads(latest[1])
                prior_baseline = json.loads(latest[2]) if latest[2] is not None else None
            if (
                expected_revision is not None
                and current_revision != expected_revision
            ):
                raise ProjectStoreError(
                    "line geometry revision conflict; reload the current page"
                )
            if (
                _canonical_json(prior_polygon) == _canonical_json(revised_polygon)
                and _canonical_json(prior_baseline) == _canonical_json(revised_baseline)
            ):
                return {
                    "status": "UNCHANGED",
                    "project": str(root),
                    "manifest_sha256": manifest_sha256,
                    "source_span_id": source_span_id,
                    "revision": current_revision,
                    "network_required": False,
                }
            revision = current_revision + 1
            connection.execute(
                """
                INSERT INTO line_geometry_revisions (
                    manifest_sha256, source_span_id, revision,
                    prior_polygon_json, prior_baseline_json,
                    polygon_json, baseline_json, editor, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest_sha256,
                    source_span_id,
                    revision,
                    _canonical_json(prior_polygon),
                    _canonical_json(prior_baseline) if prior_baseline is not None else None,
                    _canonical_json(revised_polygon),
                    _canonical_json(revised_baseline)
                    if revised_baseline is not None
                    else None,
                    editor.strip(),
                    _timestamp(),
                ),
            )
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot save line geometry revision: {error}") from error
    finally:
        connection.close()
    return {
        "status": "SAVED",
        "project": str(root),
        "manifest_sha256": manifest_sha256,
        "source_span_id": source_span_id,
        "revision": revision,
        "editor": editor.strip(),
        "polygon": revised_polygon,
        "baseline": revised_baseline,
        "network_required": False,
    }



def _stored_page_region_order(
    root: Path,
    connection: sqlite3.Connection,
    *,
    manifest_sha256: str,
    page_index: int,
) -> list[str]:
    row = connection.execute(
        """
        SELECT manifest_relative_path
        FROM pagexml_imports
        WHERE manifest_sha256 = ?
        """,
        (manifest_sha256,),
    ).fetchone()
    if row is None:
        raise ProjectStoreError("project PAGE XML import was not found")
    relative_path = row[0]
    if not isinstance(relative_path, str):
        raise ProjectStoreError("project import manifest path is invalid")
    manifest_path = (root / relative_path).resolve()
    if root not in manifest_path.parents or not manifest_path.is_file():
        raise ProjectStoreError("project import manifest is missing or outside the project")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProjectStoreError("project import manifest is unreadable") from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get("pages"), list):
        raise ProjectStoreError("project import manifest is invalid")
    page = next(
        (
            item
            for item in manifest["pages"]
            if isinstance(item, dict) and item.get("page_index") == page_index
        ),
        None,
    )
    if page is None:
        raise ProjectStoreError("project page was not found in its import manifest")
    regions = page.get("regions")
    reading_order = page.get("reading_order")
    if not isinstance(regions, list) or not isinstance(reading_order, dict):
        raise ProjectStoreError("project page regions or reading order are invalid")
    source_region_ids: list[str] = []
    for region in regions:
        if not isinstance(region, dict):
            raise ProjectStoreError("project page region is invalid")
        region_id = region.get("region_id")
        if not isinstance(region_id, str) or not region_id.strip():
            raise ProjectStoreError("project page region ID is invalid")
        source_region_ids.append(region_id)
    region_ids = reading_order.get("region_ids")
    if (
        not isinstance(region_ids, list)
        or any(not isinstance(region_id, str) or not region_id.strip() for region_id in region_ids)
        or len(region_ids) != len(source_region_ids)
        or len(set(region_ids)) != len(region_ids)
        or set(region_ids) != set(source_region_ids)
    ):
        raise ProjectStoreError("project page reading order is invalid")
    return list(region_ids)


def _validated_region_order(
    region_ids: Sequence[str],
    *,
    expected_region_ids: Sequence[str],
) -> list[str]:
    if isinstance(region_ids, (str, bytes)) or not isinstance(region_ids, Sequence):
        raise ProjectStoreError("region_ids must be a sequence of imported PAGE XML region IDs")
    normalized: list[str] = []
    for position, region_id in enumerate(region_ids):
        if (
            not isinstance(region_id, str)
            or not region_id.strip()
            or region_id != region_id.strip()
        ):
            raise ProjectStoreError(f"region_ids[{position}] must be a nonblank exact region ID")
        normalized.append(region_id)
    if (
        len(normalized) != len(expected_region_ids)
        or len(set(normalized)) != len(normalized)
        or set(normalized) != set(expected_region_ids)
    ):
        raise ProjectStoreError(
            "region_ids must be an exact permutation of the imported PAGE XML regions"
        )
    return normalized


def revise_page_reading_order(
    project: Path | str,
    *,
    manifest_sha256: str,
    page_index: int,
    region_ids: Sequence[str],
    editor: str,
    expected_revision: int | None = None,
) -> dict[str, object]:
    """Append an audited page-region order revision without altering source XML."""

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    if not isinstance(page_index, int) or isinstance(page_index, bool) or page_index < 0:
        raise ProjectStoreError("page_index must be a non-negative integer")
    if not isinstance(editor, str) or not editor.strip():
        raise ProjectStoreError("reading-order editor must be a nonblank string")
    expected_revision = _validated_expected_revision(expected_revision)
    root = _required_project_root(project)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            source_region_ids = _stored_page_region_order(
                root,
                connection,
                manifest_sha256=manifest_sha256,
                page_index=page_index,
            )
            revised_region_ids = _validated_region_order(
                region_ids,
                expected_region_ids=source_region_ids,
            )
            page = connection.execute(
                """
                SELECT 1
                FROM pages
                WHERE manifest_sha256 = ? AND page_index = ?
                """,
                (manifest_sha256, page_index),
            ).fetchone()
            if page is None:
                raise ProjectStoreError("project page was not found")
            latest = connection.execute(
                """
                SELECT revision, region_ids_json
                FROM page_reading_order_revisions
                WHERE manifest_sha256 = ? AND page_index = ?
                ORDER BY revision DESC
                LIMIT 1
                """,
                (manifest_sha256, page_index),
            ).fetchone()
            if latest is None:
                current_revision = 0
                prior_region_ids = source_region_ids
            else:
                current_revision = int(latest[0])
                try:
                    prior_region_ids = json.loads(latest[1])
                except (TypeError, json.JSONDecodeError) as error:
                    raise ProjectStoreError("stored page reading order is unreadable") from error
                prior_region_ids = _validated_region_order(
                    prior_region_ids,
                    expected_region_ids=source_region_ids,
                )
            if (
                expected_revision is not None
                and current_revision != expected_revision
            ):
                raise ProjectStoreError(
                    "reading-order revision conflict; reload the current page"
                )
            if _canonical_json(prior_region_ids) == _canonical_json(revised_region_ids):
                return {
                    "status": "UNCHANGED",
                    "project": str(root),
                    "manifest_sha256": manifest_sha256,
                    "page_index": page_index,
                    "revision": current_revision,
                    "region_ids": revised_region_ids,
                    "network_required": False,
                }
            revision = current_revision + 1
            connection.execute(
                """
                INSERT INTO page_reading_order_revisions (
                    manifest_sha256, page_index, revision, prior_region_ids_json,
                    region_ids_json, editor, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest_sha256,
                    page_index,
                    revision,
                    _canonical_json(prior_region_ids),
                    _canonical_json(revised_region_ids),
                    editor.strip(),
                    _timestamp(),
                ),
            )
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot save page reading order revision: {error}") from error
    finally:
        connection.close()
    return {
        "status": "SAVED",
        "project": str(root),
        "manifest_sha256": manifest_sha256,
        "page_index": page_index,
        "revision": revision,
        "prior_region_ids": prior_region_ids,
        "region_ids": revised_region_ids,
        "editor": editor.strip(),
        "network_required": False,
    }


def _stored_region_polygon(
    root: Path,
    connection: sqlite3.Connection,
    *,
    manifest_sha256: str,
    page_index: int,
    region_id: str,
) -> object:
    row = connection.execute(
        """
        SELECT manifest_relative_path
        FROM pagexml_imports
        WHERE manifest_sha256 = ?
        """,
        (manifest_sha256,),
    ).fetchone()
    if row is None:
        raise ProjectStoreError("project PAGE XML import was not found")
    relative_path = row[0]
    if not isinstance(relative_path, str):
        raise ProjectStoreError("project import manifest path is invalid")
    manifest_path = (root / relative_path).resolve()
    if root not in manifest_path.parents or not manifest_path.is_file():
        raise ProjectStoreError("project import manifest is missing or outside the project")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProjectStoreError("project import manifest is unreadable") from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get("pages"), list):
        raise ProjectStoreError("project import manifest is invalid")
    page = next(
        (
            item
            for item in manifest["pages"]
            if isinstance(item, dict) and item.get("page_index") == page_index
        ),
        None,
    )
    if page is None or not isinstance(page.get("regions"), list):
        raise ProjectStoreError("project page regions are invalid")
    regions = [
        item
        for item in page["regions"]
        if isinstance(item, dict) and item.get("region_id") == region_id
    ]
    if len(regions) != 1:
        raise ProjectStoreError("project region was not found in its import manifest")
    return regions[0].get("polygon")


def revise_region_geometry(
    project: Path | str,
    *,
    manifest_sha256: str,
    page_index: int,
    region_id: str,
    polygon: Sequence[Sequence[int]],
    editor: str,
    expected_revision: int | None = None,
) -> dict[str, object]:
    """Append an audited local TextRegion polygon revision without altering source XML."""

    manifest_sha256 = _require_sha256(manifest_sha256, role="manifest_sha256")
    if not isinstance(page_index, int) or isinstance(page_index, bool) or page_index < 0:
        raise ProjectStoreError("page_index must be a non-negative integer")
    if (
        not isinstance(region_id, str)
        or not region_id.strip()
        or region_id != region_id.strip()
    ):
        raise ProjectStoreError("region_id must be a nonblank exact PAGE XML region ID")
    if not isinstance(editor, str) or not editor.strip():
        raise ProjectStoreError("region geometry editor must be a nonblank string")
    expected_revision = _validated_expected_revision(expected_revision)
    root = _required_project_root(project)
    connection = sqlite3.connect(root / PROJECT_DATABASE_NAME)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            page = connection.execute(
                """
                SELECT width_px, height_px
                FROM pages
                WHERE manifest_sha256 = ? AND page_index = ?
                """,
                (manifest_sha256, page_index),
            ).fetchone()
            if page is None:
                raise ProjectStoreError("project page was not found")
            width, height = int(page[0]), int(page[1])
            source_polygon = _validated_points(
                _stored_region_polygon(
                    root,
                    connection,
                    manifest_sha256=manifest_sha256,
                    page_index=page_index,
                    region_id=region_id,
                ),
                role="stored region polygon",
                width=width,
                height=height,
                allow_none=False,
            )
            revised_polygon = _validated_points(
                polygon,
                role="region polygon",
                width=width,
                height=height,
                allow_none=False,
            )
            latest = connection.execute(
                """
                SELECT revision, polygon_json
                FROM region_geometry_revisions
                WHERE manifest_sha256 = ? AND page_index = ? AND region_id = ?
                ORDER BY revision DESC
                LIMIT 1
                """,
                (manifest_sha256, page_index, region_id),
            ).fetchone()
            if latest is None:
                current_revision = 0
                prior_polygon = source_polygon
            else:
                current_revision = int(latest[0])
                try:
                    prior_polygon = json.loads(latest[1])
                except (TypeError, json.JSONDecodeError) as error:
                    raise ProjectStoreError("stored region geometry is unreadable") from error
                prior_polygon = _validated_points(
                    prior_polygon,
                    role="stored region polygon",
                    width=width,
                    height=height,
                    allow_none=False,
                )
            if (
                expected_revision is not None
                and current_revision != expected_revision
            ):
                raise ProjectStoreError(
                    "region geometry revision conflict; reload the current page"
                )
            if _canonical_json(prior_polygon) == _canonical_json(revised_polygon):
                return {
                    "status": "UNCHANGED",
                    "project": str(root),
                    "manifest_sha256": manifest_sha256,
                    "page_index": page_index,
                    "region_id": region_id,
                    "revision": current_revision,
                    "polygon": revised_polygon,
                    "network_required": False,
                }
            revision = current_revision + 1
            connection.execute(
                """
                INSERT INTO region_geometry_revisions (
                    manifest_sha256, page_index, region_id, revision,
                    prior_polygon_json, polygon_json, editor, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest_sha256,
                    page_index,
                    region_id,
                    revision,
                    _canonical_json(prior_polygon),
                    _canonical_json(revised_polygon),
                    editor.strip(),
                    _timestamp(),
                ),
            )
    except sqlite3.Error as error:
        raise ProjectStoreError(f"cannot save region geometry revision: {error}") from error
    finally:
        connection.close()
    return {
        "status": "SAVED",
        "project": str(root),
        "manifest_sha256": manifest_sha256,
        "page_index": page_index,
        "region_id": region_id,
        "revision": revision,
        "prior_polygon": prior_polygon,
        "polygon": revised_polygon,
        "editor": editor.strip(),
        "network_required": False,
    }

def _replace_line_geometry(
    line: ET.Element,
    *,
    polygon: list[list[int]],
    baseline: list[list[int]] | None,
) -> None:
    coords = next(
        (child for child in line if _xml_local_name(child) == "Coords"),
        None,
    )
    if coords is None:
        raise ProjectStoreError("stored PAGE XML line is missing Coords")
    coords.set("points", " ".join(f"{x},{y}" for x, y in polygon))
    baselines = [child for child in line if _xml_local_name(child) == "Baseline"]
    if baseline is None:
        for item in baselines:
            line.remove(item)
        return
    if baselines:
        target = baselines[0]
        for duplicate in baselines[1:]:
            line.remove(duplicate)
    else:
        target = ET.Element(_xml_tag_like(line, "Baseline"))
        line.insert(1, target)
    target.set("points", " ".join(f"{x},{y}" for x, y in baseline))
