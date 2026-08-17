"""Loopback-only service workspace, durable backup jobs, and verified restore."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import secrets
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
import zipfile
from collections.abc import Iterator
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

from aktreader.project import (
    ProjectStoreError,
    inspect_project,
    list_project_documents,
    load_project_page,
    revise_line_transcription,
)

SERVICE_MANIFEST_NAME = "service.akt.json"
SERVICE_DATABASE_NAME = "service.sqlite3"
SERVICE_CONTRACT = {"name": "aktreader-self-hosted-service", "version": "1.0.0"}
BACKUP_MANIFEST_NAME = "backup.aktreader.json"
BACKUP_CONTRACT = {"name": "aktreader-project-backup", "version": "1.0.0"}
PROJECTS_DIRECTORY = "projects"
BACKUPS_DIRECTORY = "backups"
ARTIFACTS_DIRECTORY = "artifacts"
LOOPBACK_HOST = "127.0.0.1"
MAX_REQUEST_BYTES = 65_536
MAX_BACKUP_FILES = 100_000
MAX_BACKUP_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_NAME_LENGTH = 160
MAX_ARTIFACT_DESCRIPTION_LENGTH = 4_000
MAX_IMAGE_RESPONSE_BYTES = 100 * 1024 * 1024
_COPY_BUFFER_BYTES = 1024 * 1024
ARTIFACT_KINDS = ("MODEL", "DATASET")
PASSWORD_SCRYPT_N = 16_384
PASSWORD_SCRYPT_R = 8
PASSWORD_SCRYPT_P = 1
SESSION_TTL_SECONDS = 8 * 60 * 60
PROJECT_ROLES = ("VIEWER", "EDITOR", "OWNER")
_ROLE_RANK = {role: index for index, role in enumerate(PROJECT_ROLES)}


class ServiceError(ValueError):
    """Raised when a local self-hosted service contract is invalid."""


class AuthenticationError(ServiceError):
    """Raised when credentials or a local session cannot be authenticated."""


class AuthorizationError(ServiceError):
    """Raised when an authenticated account lacks a required project role."""


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_COPY_BUFFER_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _local_path(path: Path | str, *, role: str, must_exist: bool) -> Path:
    raw = os.fspath(path)
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise ServiceError(f"{role} must be a local path, not a URL or UNC path")
    candidate = Path(raw)
    try:
        return candidate.resolve(strict=must_exist)
    except OSError as error:
        raise ServiceError(f"{role} is missing or inaccessible: {raw}") from error


def _require_uuid(value: object, *, role: str) -> str:
    if not isinstance(value, str):
        raise ServiceError(f"{role} must be a UUID string")
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        raise ServiceError(f"{role} must be a UUID string") from error
    if str(parsed) != value:
        raise ServiceError(f"{role} must use canonical lowercase UUID form")
    return value


def _require_sha256(value: object, *, role: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ServiceError(f"{role} must be a SHA-256 hex digest")
    if any(character not in "0123456789abcdef" for character in value):
        raise ServiceError(f"{role} must be a lowercase SHA-256 hex digest")
    return value


def _initialize_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.executescript(
                """
                CREATE TABLE service_jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')),
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX service_jobs_status_created
                    ON service_jobs (status, created_at, job_id);
                """
            )
    finally:
        connection.close()
    _migrate_service_database(path)


def _migrate_service_database(path: Path) -> None:
    """Add identity tables without changing the service workspace contract."""

    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS service_accounts (
                    account_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS service_project_roles (
                    project_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('VIEWER', 'EDITOR', 'OWNER')),
                    granted_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, account_id)
                );
                CREATE INDEX IF NOT EXISTS service_project_roles_account_project
                    ON service_project_roles (account_id, project_id);
                CREATE TABLE IF NOT EXISTS service_sessions (
                    token_sha256 TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS service_sessions_account_expiry
                    ON service_sessions (account_id, expires_at);
                CREATE TABLE IF NOT EXISTS service_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL CHECK (kind IN ('MODEL', 'DATASET')),
                    name TEXT NOT NULL,
                    license_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    relative_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS service_artifacts_kind_created
                    ON service_artifacts (kind, created_at, artifact_id);
                CREATE TABLE IF NOT EXISTS service_project_artifacts (
                    project_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    attached_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, artifact_id)
                );
                CREATE INDEX IF NOT EXISTS service_project_artifacts_artifact
                    ON service_project_artifacts (artifact_id, project_id);
                """
            )
    finally:
        connection.close()


def _service_root(path: Path | str) -> Path:
    root = _local_path(path, role="service workspace", must_exist=True)
    if not root.is_dir():
        raise ServiceError(f"service workspace is not a directory: {root}")
    manifest_path = root / SERVICE_MANIFEST_NAME
    database_path = root / SERVICE_DATABASE_NAME
    if not manifest_path.is_file() or not database_path.is_file():
        raise ServiceError("service workspace is missing its manifest or database")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ServiceError("service workspace manifest is unreadable") from error
    if not isinstance(manifest, dict) or manifest.get("contract") != SERVICE_CONTRACT:
        raise ServiceError("service workspace has an unsupported contract")
    _require_uuid(manifest.get("service_id"), role="service workspace service_id")
    if manifest.get("network_required") is not False:
        raise ServiceError("service workspace must declare network_required false")
    for directory in (
        root / PROJECTS_DIRECTORY,
        root / BACKUPS_DIRECTORY,
        root / ARTIFACTS_DIRECTORY,
    ):
        if not directory.is_dir() or directory.is_symlink():
            raise ServiceError(f"service workspace is missing managed {directory.name} storage")
    _migrate_service_database(database_path)
    return root


def _connection(root: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(root / SERVICE_DATABASE_NAME, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def create_service_workspace(path: Path | str) -> dict[str, object]:
    """Create an empty, local-only managed service workspace atomically."""

    destination = _local_path(path, role="service workspace destination", must_exist=False)
    if destination.exists():
        raise ServiceError(f"service workspace destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise ServiceError("service workspace destination parent does not exist")

    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    manifest = {
        "contract": SERVICE_CONTRACT,
        "service_id": str(uuid.uuid4()),
        "created_at": _timestamp(),
        "storage": {
            "database": SERVICE_DATABASE_NAME,
            "projects": PROJECTS_DIRECTORY,
            "backups": BACKUPS_DIRECTORY,
            "artifacts": ARTIFACTS_DIRECTORY,
        },
        "network_required": False,
    }
    try:
        (temporary / PROJECTS_DIRECTORY).mkdir()
        (temporary / BACKUPS_DIRECTORY).mkdir()
        (temporary / ARTIFACTS_DIRECTORY).mkdir()
        (temporary / SERVICE_MANIFEST_NAME).write_text(
            _canonical_json(manifest) + "\n",
            encoding="utf-8",
        )
        _initialize_database(temporary / SERVICE_DATABASE_NAME)
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return inspect_service_workspace(destination)


def _job_counts(root: Path) -> dict[str, int]:
    connection = _connection(root)
    try:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM service_jobs GROUP BY status"
        ).fetchall()
    finally:
        connection.close()
    counts = {"PENDING": 0, "RUNNING": 0, "SUCCEEDED": 0, "FAILED": 0}
    for row in rows:
        counts[str(row["status"])] = int(row["count"])
    return counts


def _project_summary(report: dict[str, object]) -> dict[str, object]:
    return {
        "project_id": report["project_id"],
        "name": report["name"],
        "object_count": report["object_count"],
        "document_count": report["document_count"],
        "page_count": report["page_count"],
        "line_count": report["line_count"],
    }


def inspect_service_workspace(path: Path | str) -> dict[str, object]:
    """Return local service identity, managed project count, and durable job counts."""

    root = _service_root(path)
    manifest = json.loads((root / SERVICE_MANIFEST_NAME).read_text(encoding="utf-8"))
    return {
        "status": "READY",
        "service_workspace": str(root),
        "service_id": manifest["service_id"],
        "contract": manifest["contract"],
        "project_count": len(list_service_projects(root)),
        "job_counts": _job_counts(root),
        "network_required": False,
    }


def _validated_username(value: object) -> str:
    if not isinstance(value, str):
        raise ServiceError("username must be a string")
    username = value.strip().lower()
    if not 3 <= len(username) <= 64:
        raise ServiceError("username must contain 3 to 64 characters")
    if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in username):
        raise ServiceError(
            "username may contain only lowercase letters, digits, dot, dash, and underscore"
        )
    return username


def _password_digest(password: str, salt: bytes) -> bytes:
    if not isinstance(password, str) or not 12 <= len(password) <= 512:
        raise ServiceError("password must contain 12 to 512 characters")
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_SCRYPT_N,
        r=PASSWORD_SCRYPT_R,
        p=PASSWORD_SCRYPT_P,
        dklen=32,
    )


def _account_by_username(root: Path, username: str) -> dict[str, object]:
    connection = _connection(root)
    try:
        row = connection.execute(
            """
            SELECT account_id, username, password_salt, password_hash, created_at
            FROM service_accounts WHERE username = ?
            """,
            (_validated_username(username),),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ServiceError("local account was not found")
    return {
        "account_id": str(row["account_id"]),
        "username": str(row["username"]),
        "password_salt": bytes(row["password_salt"]),
        "password_hash": bytes(row["password_hash"]),
        "created_at": str(row["created_at"]),
    }


def _account_by_id(root: Path, account_id: str) -> dict[str, object]:
    canonical_id = _require_uuid(account_id, role="account_id")
    connection = _connection(root)
    try:
        row = connection.execute(
            """
            SELECT account_id, username, created_at
            FROM service_accounts WHERE account_id = ?
            """,
            (canonical_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise AuthenticationError("authentication is required")
    return {
        "account_id": str(row["account_id"]),
        "username": str(row["username"]),
        "created_at": str(row["created_at"]),
    }


def create_local_account(
    service_workspace: Path | str,
    *,
    username: str,
    password: str,
) -> dict[str, object]:
    """Create one password-protected local account without exposing its secret."""

    root = _service_root(service_workspace)
    canonical_username = _validated_username(username)
    salt = secrets.token_bytes(16)
    digest = _password_digest(password, salt)
    account_id = str(uuid.uuid4())
    connection = _connection(root)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO service_accounts
                    (account_id, username, password_salt, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (account_id, canonical_username, salt, digest, _timestamp()),
            )
    except sqlite3.IntegrityError as error:
        raise ServiceError("username is already in use") from error
    finally:
        connection.close()
    return {
        "status": "CREATED",
        "account_id": account_id,
        "username": canonical_username,
        "network_required": False,
    }


def list_local_accounts(service_workspace: Path | str) -> list[dict[str, object]]:
    """List local account identities without returning password material."""

    root = _service_root(service_workspace)
    connection = _connection(root)
    try:
        rows = connection.execute(
            """
            SELECT account_id, username, created_at
            FROM service_accounts
            ORDER BY username, account_id
            """
        ).fetchall()
    finally:
        connection.close()
    return [
        {
            "account_id": str(row["account_id"]),
            "username": str(row["username"]),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]


def authenticate_local_account(
    service_workspace: Path | str,
    *,
    username: str,
    password: str,
) -> dict[str, object]:
    """Verify a local account password and return only its public identity."""

    root = _service_root(service_workspace)
    try:
        account = _account_by_username(root, username)
        candidate = _password_digest(password, bytes(account["password_salt"]))
    except ServiceError as error:
        raise AuthenticationError("sign-in failed") from error
    if not secrets.compare_digest(candidate, bytes(account["password_hash"])):
        raise AuthenticationError("sign-in failed")
    return {
        "account_id": account["account_id"],
        "username": account["username"],
        "created_at": account["created_at"],
    }


def create_service_session(
    service_workspace: Path | str,
    *,
    username: str,
    password: str,
) -> dict[str, object]:
    """Create one short-lived bearer session after verifying a local password."""

    root = _service_root(service_workspace)
    account = authenticate_local_account(root, username=username, password=password)
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    connection = _connection(root)
    try:
        with connection:
            connection.execute(
                "DELETE FROM service_sessions WHERE expires_at <= ?",
                (int(time.time()),),
            )
            connection.execute(
                """
                INSERT INTO service_sessions
                    (token_sha256, account_id, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    hashlib.sha256(token.encode("utf-8")).hexdigest(),
                    account["account_id"],
                    expires_at,
                    _timestamp(),
                ),
            )
    finally:
        connection.close()
    return {
        "status": "AUTHENTICATED",
        "access_token": token,
        "token_type": "Bearer",
        "expires_at": expires_at,
        "account": account,
        "network_required": False,
    }


def authenticated_service_account(
    service_workspace: Path | str,
    authorization: object,
) -> dict[str, object]:
    """Resolve an unexpired Bearer session to a local account identity."""

    root = _service_root(service_workspace)
    if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
        raise AuthenticationError("authentication is required")
    token = authorization.removeprefix("Bearer ")
    if not token or any(character.isspace() for character in token):
        raise AuthenticationError("authentication is required")
    connection = _connection(root)
    try:
        with connection:
            connection.execute(
                "DELETE FROM service_sessions WHERE expires_at <= ?",
                (int(time.time()),),
            )
            row = connection.execute(
                """
                SELECT account_id FROM service_sessions
                WHERE token_sha256 = ? AND expires_at > ?
                """,
                (hashlib.sha256(token.encode("utf-8")).hexdigest(), int(time.time())),
            ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise AuthenticationError("authentication is required")
    return _account_by_id(root, str(row["account_id"]))


def _validated_project_role(value: object) -> str:
    if not isinstance(value, str) or value not in PROJECT_ROLES:
        raise ServiceError("project role must be VIEWER, EDITOR, or OWNER")
    return value


def _project_role(root: Path, project_id: str, account_id: str) -> str | None:
    canonical_project_id = _require_uuid(project_id, role="project_id")
    canonical_account_id = _require_uuid(account_id, role="account_id")
    connection = _connection(root)
    try:
        row = connection.execute(
            """
            SELECT role FROM service_project_roles
            WHERE project_id = ? AND account_id = ?
            """,
            (canonical_project_id, canonical_account_id),
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else str(row["role"])


def _require_project_role(
    root: Path,
    *,
    project_id: str,
    account_id: str,
    minimum_role: str,
) -> str:
    role = _project_role(root, project_id, account_id)
    if role is None or _ROLE_RANK[role] < _ROLE_RANK[minimum_role]:
        raise AuthorizationError("account is not authorized for this project")
    return role


def grant_project_role(
    service_workspace: Path | str,
    *,
    project_id: str,
    username: str,
    role: str,
) -> dict[str, object]:
    """Grant or replace one local account's role on a managed project."""

    root = _service_root(service_workspace)
    canonical_project_id = _require_uuid(project_id, role="project_id")
    inspect_project(_managed_project_path(root, canonical_project_id))
    account = _account_by_username(root, username)
    canonical_role = _validated_project_role(role)
    connection = _connection(root)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO service_project_roles
                    (project_id, account_id, role, granted_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id, account_id)
                DO UPDATE SET role = excluded.role, granted_at = excluded.granted_at
                """,
                (
                    canonical_project_id,
                    account["account_id"],
                    canonical_role,
                    _timestamp(),
                ),
            )
    finally:
        connection.close()
    return {
        "status": "GRANTED",
        "project_id": canonical_project_id,
        "account_id": account["account_id"],
        "username": account["username"],
        "role": canonical_role,
        "network_required": False,
    }


def list_authorized_service_projects(
    service_workspace: Path | str,
    *,
    account_id: str,
) -> list[dict[str, object]]:
    """List only the service projects visible to one authenticated local account."""

    root = _service_root(service_workspace)
    canonical_account_id = _require_uuid(account_id, role="account_id")
    roles = _connection(root)
    try:
        role_rows = roles.execute(
            """
            SELECT project_id, role FROM service_project_roles
            WHERE account_id = ?
            """,
            (canonical_account_id,),
        ).fetchall()
    finally:
        roles.close()
    roles_by_project = {str(row["project_id"]): str(row["role"]) for row in role_rows}
    return [
        {**project, "role": roles_by_project[str(project["project_id"])]}
        for project in list_service_projects(root)
        if str(project["project_id"]) in roles_by_project
    ]


def _validated_artifact_kind(value: object) -> str:
    if not isinstance(value, str) or value not in ARTIFACT_KINDS:
        raise ServiceError("artifact kind must be MODEL or DATASET")
    return value


def _validated_artifact_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServiceError("artifact name must be a nonblank string")
    name = value.strip()
    if len(name) > MAX_ARTIFACT_NAME_LENGTH:
        raise ServiceError("artifact name exceeds the length limit")
    return name


def _validated_license_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServiceError("artifact license_id must be a nonblank string")
    license_id = value.strip()
    if len(license_id) > 128 or any(character.isspace() for character in license_id):
        raise ServiceError("artifact license_id is invalid")
    return license_id


def _validated_artifact_description(value: object) -> str:
    if not isinstance(value, str):
        raise ServiceError("artifact description must be a string")
    if len(value) > MAX_ARTIFACT_DESCRIPTION_LENGTH:
        raise ServiceError("artifact description exceeds the length limit")
    return value


def _artifact_report(row: sqlite3.Row) -> dict[str, object]:
    return {
        "artifact_id": str(row["artifact_id"]),
        "kind": str(row["kind"]),
        "name": str(row["name"]),
        "license_id": str(row["license_id"]),
        "description": str(row["description"]),
        "sha256": str(row["sha256"]),
        "size_bytes": int(row["size_bytes"]),
        "created_at": str(row["created_at"]),
    }


def _artifact_by_id(root: Path, artifact_id: str) -> sqlite3.Row:
    canonical_id = _require_uuid(artifact_id, role="artifact_id")
    connection = _connection(root)
    try:
        row = connection.execute(
            """
            SELECT artifact_id, kind, name, license_id, description, sha256,
                   size_bytes, relative_path, created_at
            FROM service_artifacts
            WHERE artifact_id = ?
            """,
            (canonical_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ServiceError("service artifact was not found")
    return row


def register_service_artifact(
    service_workspace: Path | str,
    source: Path | str,
    *,
    kind: str,
    name: str,
    license_id: str,
    description: str = "",
) -> dict[str, object]:
    """Copy one local model or dataset artifact into content-addressed storage."""

    root = _service_root(service_workspace)
    source_path = _local_path(source, role="artifact source", must_exist=True)
    if source_path.is_symlink() or not source_path.is_file():
        raise ServiceError("artifact source must be a regular local file")
    canonical_kind = _validated_artifact_kind(kind)
    canonical_name = _validated_artifact_name(name)
    canonical_license_id = _validated_license_id(license_id)
    canonical_description = _validated_artifact_description(description)

    object_root = root / ARTIFACTS_DIRECTORY / "sha256"
    object_root.mkdir(exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".artifact.", dir=object_root)
    os.close(descriptor)
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with source_path.open("rb") as input_file, temporary.open("wb") as output_file:
            while chunk := input_file.read(_COPY_BUFFER_BYTES):
                digest.update(chunk)
                size_bytes += len(chunk)
                output_file.write(chunk)
        sha256 = digest.hexdigest()
        destination_directory = object_root / sha256[:2]
        destination_directory.mkdir(exist_ok=True)
        destination = destination_directory / sha256
        if destination.exists():
            if destination.is_symlink() or not destination.is_file():
                raise ServiceError("managed artifact storage contains an invalid entry")
            if destination.stat().st_size != size_bytes or _sha256_file(destination) != sha256:
                raise ServiceError("managed artifact storage hash does not match its path")
            temporary.unlink()
        else:
            os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    artifact_id = str(uuid.uuid4())
    relative_path = destination.relative_to(root / ARTIFACTS_DIRECTORY).as_posix()
    connection = _connection(root)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO service_artifacts
                    (artifact_id, kind, name, license_id, description, sha256,
                     size_bytes, relative_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    canonical_kind,
                    canonical_name,
                    canonical_license_id,
                    canonical_description,
                    sha256,
                    size_bytes,
                    relative_path,
                    _timestamp(),
                ),
            )
            row = connection.execute(
                """
                SELECT artifact_id, kind, name, license_id, description, sha256,
                       size_bytes, created_at
                FROM service_artifacts
                WHERE artifact_id = ?
                """,
                (artifact_id,),
            ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ServiceError("registered artifact could not be read")
    return {"status": "REGISTERED", "artifact": _artifact_report(row), "network_required": False}


def list_service_artifacts(service_workspace: Path | str) -> list[dict[str, object]]:
    """List registered model and dataset metadata without local storage paths."""

    root = _service_root(service_workspace)
    connection = _connection(root)
    try:
        rows = connection.execute(
            """
            SELECT artifact_id, kind, name, license_id, description, sha256,
                   size_bytes, created_at
            FROM service_artifacts
            ORDER BY created_at, artifact_id
            """
        ).fetchall()
    finally:
        connection.close()
    return [_artifact_report(row) for row in rows]


def attach_service_artifact(
    service_workspace: Path | str,
    *,
    project_id: str,
    artifact_id: str,
) -> dict[str, object]:
    """Attach an already registered model or dataset to one managed project."""

    root = _service_root(service_workspace)
    canonical_project_id = _require_uuid(project_id, role="project_id")
    inspect_project(_managed_project_path(root, canonical_project_id))
    artifact = _artifact_by_id(root, artifact_id)
    connection = _connection(root)
    try:
        with connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO service_project_artifacts
                    (project_id, artifact_id, attached_at)
                VALUES (?, ?, ?)
                """,
                (canonical_project_id, artifact["artifact_id"], _timestamp()),
            )
    finally:
        connection.close()
    return {
        "status": "ATTACHED",
        "project_id": canonical_project_id,
        "artifact": _artifact_report(artifact),
        "network_required": False,
    }


def list_authorized_project_artifacts(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
) -> list[dict[str, object]]:
    """List model and dataset metadata visible to an authorized project viewer."""

    root = _service_root(service_workspace)
    canonical_project_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_project_id,
        account_id=account_id,
        minimum_role="VIEWER",
    )
    connection = _connection(root)
    try:
        rows = connection.execute(
            """
            SELECT artifact_id, kind, name, license_id, description, sha256,
                   size_bytes, created_at
            FROM service_artifacts
            JOIN service_project_artifacts USING (artifact_id)
            WHERE service_project_artifacts.project_id = ?
            ORDER BY service_project_artifacts.attached_at, artifact_id
            """,
            (canonical_project_id,),
        ).fetchall()
    finally:
        connection.close()
    return [_artifact_report(row) for row in rows]


def attach_authorized_project_artifact(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    artifact_id: str,
) -> dict[str, object]:
    """Attach an artifact only when the authenticated account owns the project."""

    root = _service_root(service_workspace)
    canonical_project_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_project_id,
        account_id=account_id,
        minimum_role="OWNER",
    )
    return attach_service_artifact(
        root,
        project_id=canonical_project_id,
        artifact_id=artifact_id,
    )


def _safe_project_files(root: Path) -> Iterator[tuple[Path, str]]:
    for current_raw, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_raw)
        directory_names.sort()
        file_names.sort()
        retained_directories: list[str] = []
        for name in directory_names:
            candidate = current / name
            if candidate.is_symlink():
                raise ServiceError("managed projects may not contain symbolic links")
            retained_directories.append(name)
        directory_names[:] = retained_directories
        for name in file_names:
            candidate = current / name
            if candidate.is_symlink() or not candidate.is_file():
                raise ServiceError("managed projects may only contain regular files")
            relative = candidate.relative_to(root).as_posix()
            yield candidate, relative


def _managed_project_path(root: Path, project_id: str) -> Path:
    canonical_id = _require_uuid(project_id, role="project_id")
    project = root / PROJECTS_DIRECTORY / f"{canonical_id}.aktproj"
    if not project.is_dir() or project.is_symlink():
        raise ServiceError("managed project was not found")
    return project


def add_project_to_service(
    service_workspace: Path | str,
    project: Path | str,
    *,
    owner_username: str | None = None,
) -> dict[str, object]:
    """Copy one validated local project into the service-owned workspace."""

    root = _service_root(service_workspace)
    report = inspect_project(project)
    project_id = _require_uuid(report["project_id"], role="project project_id")
    source = Path(str(report["project"])).resolve()
    list(_safe_project_files(source))
    owner = (
        None
        if owner_username is None
        else _account_by_username(root, owner_username)
    )
    destination = root / PROJECTS_DIRECTORY / f"{project_id}.aktproj"
    if destination.exists():
        raise ServiceError("service already manages this project_id")

    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    shutil.rmtree(temporary)
    try:
        shutil.copytree(source, temporary)
        list(_safe_project_files(temporary))
        managed_report = inspect_project(temporary)
        if managed_report["project_id"] != project_id:
            raise ServiceError("managed project identity changed during copy")
        os.replace(temporary, destination)
        if owner is not None:
            grant_project_role(
                root,
                project_id=project_id,
                username=str(owner["username"]),
                role="OWNER",
            )
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "status": "ADDED",
        "project": _project_summary(inspect_project(destination)),
        "owner": (
            None
            if owner is None
            else {
                "account_id": owner["account_id"],
                "username": owner["username"],
                "role": "OWNER",
            }
        ),
        "network_required": False,
    }


def list_service_projects(service_workspace: Path | str) -> list[dict[str, object]]:
    """List validated projects owned by a service workspace without source paths."""

    root = _service_root(service_workspace)
    projects: list[dict[str, object]] = []
    for candidate in sorted((root / PROJECTS_DIRECTORY).iterdir(), key=lambda item: item.name):
        if candidate.is_symlink() or not candidate.is_dir():
            raise ServiceError("managed project storage contains an invalid entry")
        if not candidate.name.endswith(".aktproj"):
            raise ServiceError("managed project storage contains an invalid entry")
        report = inspect_project(candidate)
        project_id = _require_uuid(report["project_id"], role="managed project_id")
        if candidate.name != f"{project_id}.aktproj":
            raise ServiceError("managed project directory does not match its project_id")
        projects.append(_project_summary(report))
    return projects


def _snapshot_files(project: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for candidate, relative in _safe_project_files(project):
        files.append(
            {
                "path": relative,
                "size_bytes": candidate.stat().st_size,
                "sha256": _sha256_file(candidate),
            }
        )
    if not files:
        raise ServiceError("managed project contains no files to back up")
    if len(files) > MAX_BACKUP_FILES:
        raise ServiceError("managed project exceeds the backup file limit")
    return files


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o600 << 16
    return info


def _write_file_to_archive(archive: zipfile.ZipFile, name: str, source: Path) -> None:
    with source.open("rb") as input_file, archive.open(_zip_info(name), "w") as output_file:
        shutil.copyfileobj(input_file, output_file, length=_COPY_BUFFER_BYTES)


def _write_bytes_to_archive(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    with archive.open(_zip_info(name), "w") as output_file:
        output_file.write(payload)


def create_project_backup(
    service_workspace: Path | str,
    project_id: str,
) -> dict[str, object]:
    """Create one deterministic archive of a service-managed project."""

    root = _service_root(service_workspace)
    source = _managed_project_path(root, project_id)
    report = inspect_project(source)
    files = _snapshot_files(source)
    snapshot_sha256 = hashlib.sha256(_canonical_json(files).encode("utf-8")).hexdigest()
    archive_manifest = {
        "contract": BACKUP_CONTRACT,
        "project_id": report["project_id"],
        "snapshot_sha256": snapshot_sha256,
        "files": files,
        "network_required": False,
    }
    backup_directory = root / BACKUPS_DIRECTORY / project_id
    if backup_directory.exists():
        if backup_directory.is_symlink() or not backup_directory.is_dir():
            raise ServiceError("managed backup storage contains an invalid entry")
    else:
        backup_directory.mkdir()
    destination = backup_directory / f"{snapshot_sha256}.aktbackup.zip"
    if destination.exists():
        verified = verify_project_backup(destination)
        if verified["snapshot_sha256"] != snapshot_sha256:
            raise ServiceError("existing backup archive does not match its file name")
        return {
            "status": "READY",
            "project_id": project_id,
            "backup_id": snapshot_sha256,
            "backup_path": str(destination),
            "file_count": verified["file_count"],
            "network_required": False,
        }

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for entry in files:
                _write_file_to_archive(
                    archive,
                    str(entry["path"]),
                    source / str(entry["path"]),
                )
            _write_bytes_to_archive(
                archive,
                BACKUP_MANIFEST_NAME,
                (_canonical_json(archive_manifest) + "\n").encode("utf-8"),
            )
        verified = verify_project_backup(temporary)
        if verified["snapshot_sha256"] != snapshot_sha256:
            raise ServiceError("written backup archive did not verify")
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "status": "READY",
        "project_id": project_id,
        "backup_id": snapshot_sha256,
        "backup_path": str(destination),
        "file_count": len(files),
        "network_required": False,
    }


def _safe_archive_member(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or "\\" in name
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ServiceError("backup archive contains an unsafe member name")
    return path.as_posix()


def _read_backup_manifest(archive: zipfile.ZipFile) -> dict[str, object]:
    try:
        member = archive.getinfo(BACKUP_MANIFEST_NAME)
    except KeyError as error:
        raise ServiceError("backup archive is missing its manifest") from error
    if member.file_size > MAX_BACKUP_MANIFEST_BYTES:
        raise ServiceError("backup archive manifest exceeds the size limit")
    try:
        payload = json.loads(archive.read(member).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        raise ServiceError("backup archive manifest is unreadable") from error
    if not isinstance(payload, dict):
        raise ServiceError("backup archive manifest must be a JSON object")
    return payload


def _validated_backup_entries(payload: dict[str, object]) -> list[dict[str, object]]:
    required = {
        "contract",
        "project_id",
        "snapshot_sha256",
        "files",
        "network_required",
    }
    if set(payload) != required or payload["contract"] != BACKUP_CONTRACT:
        raise ServiceError("backup archive has an unsupported contract")
    _require_uuid(payload["project_id"], role="backup project_id")
    snapshot_sha256 = _require_sha256(payload["snapshot_sha256"], role="backup snapshot_sha256")
    if payload["network_required"] is not False:
        raise ServiceError("backup archive must declare network_required false")
    entries = payload["files"]
    if not isinstance(entries, list) or not entries or len(entries) > MAX_BACKUP_FILES:
        raise ServiceError("backup archive files are invalid")
    validated: list[dict[str, object]] = []
    paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "size_bytes", "sha256"}:
            raise ServiceError("backup archive file entry has invalid keys")
        path = _safe_archive_member(entry["path"]) if isinstance(entry["path"], str) else ""
        if not path or path == BACKUP_MANIFEST_NAME or path in paths:
            raise ServiceError("backup archive file paths are invalid")
        size_bytes = entry["size_bytes"]
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
            raise ServiceError("backup archive file size is invalid")
        paths.add(path)
        validated.append(
            {
                "path": path,
                "size_bytes": size_bytes,
                "sha256": _require_sha256(entry["sha256"], role="backup file sha256"),
            }
        )
    if validated != sorted(validated, key=lambda entry: str(entry["path"])):
        raise ServiceError("backup archive file entries are not sorted")
    expected_snapshot = hashlib.sha256(
        _canonical_json(validated).encode("utf-8")
    ).hexdigest()
    if snapshot_sha256 != expected_snapshot:
        raise ServiceError("backup archive snapshot hash does not match its manifest")
    return validated


def verify_project_backup(path: Path | str) -> dict[str, object]:
    """Verify every declared archive member and return its non-sensitive identity."""

    backup = _local_path(path, role="backup archive", must_exist=True)
    if not backup.is_file() or backup.is_symlink():
        raise ServiceError("backup archive is not a regular file")
    try:
        with zipfile.ZipFile(backup) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_BACKUP_FILES + 1:
                raise ServiceError("backup archive has an invalid number of members")
            names = [_safe_archive_member(member.filename) for member in members]
            if len(set(names)) != len(names):
                raise ServiceError("backup archive contains duplicate member names")
            if any(member.is_dir() for member in members):
                raise ServiceError("backup archive may not contain directory members")
            manifest = _read_backup_manifest(archive)
            entries = _validated_backup_entries(manifest)
            expected_names = {BACKUP_MANIFEST_NAME, *(str(entry["path"]) for entry in entries)}
            if set(names) != expected_names:
                raise ServiceError("backup archive members do not match its manifest")
            for entry in entries:
                member = archive.getinfo(str(entry["path"]))
                if member.file_size != entry["size_bytes"]:
                    raise ServiceError("backup archive member size does not match its manifest")
                digest = hashlib.sha256()
                with archive.open(member) as source:
                    while chunk := source.read(_COPY_BUFFER_BYTES):
                        digest.update(chunk)
                if digest.hexdigest() != entry["sha256"]:
                    raise ServiceError("backup archive member hash does not match its manifest")
    except (OSError, zipfile.BadZipFile) as error:
        raise ServiceError("backup archive is unreadable") from error
    return {
        "status": "VERIFIED",
        "project_id": manifest["project_id"],
        "backup_id": manifest["snapshot_sha256"],
        "snapshot_sha256": manifest["snapshot_sha256"],
        "file_count": len(entries),
        "network_required": False,
    }


def restore_project_backup(
    backup: Path | str,
    destination: Path | str,
) -> dict[str, object]:
    """Verify then restore one archive into a previously nonexistent local project path."""

    verified = verify_project_backup(backup)
    destination_path = _local_path(
        destination,
        role="restored project destination",
        must_exist=False,
    )
    if destination_path.exists():
        raise ServiceError("restored project destination already exists")
    if not destination_path.parent.is_dir():
        raise ServiceError("restored project destination parent does not exist")
    backup_path = _local_path(backup, role="backup archive", must_exist=True)

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination_path.name}.", dir=destination_path.parent)
    )
    try:
        with zipfile.ZipFile(backup_path) as archive:
            manifest = _read_backup_manifest(archive)
            entries = _validated_backup_entries(manifest)
            if (
                manifest["project_id"] != verified["project_id"]
                or manifest["snapshot_sha256"] != verified["snapshot_sha256"]
            ):
                raise ServiceError("backup archive changed after verification")
            for entry in entries:
                member = archive.getinfo(str(entry["path"]))
                if member.file_size != entry["size_bytes"]:
                    raise ServiceError("backup archive changed after verification")
                target = temporary.joinpath(*PurePosixPath(str(entry["path"])).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with archive.open(member) as source, target.open("xb") as output:
                    while chunk := source.read(_COPY_BUFFER_BYTES):
                        digest.update(chunk)
                        output.write(chunk)
                if digest.hexdigest() != entry["sha256"]:
                    raise ServiceError("backup archive changed after verification")
        restored = inspect_project(temporary)
        if restored["project_id"] != verified["project_id"]:
            raise ServiceError("restored project identity does not match the backup")
        os.replace(temporary, destination_path)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "status": "RESTORED",
        "project_id": verified["project_id"],
        "backup_id": verified["backup_id"],
        "project": str(destination_path),
        "network_required": False,
    }


def _recover_running_jobs(root: Path) -> None:
    connection = _connection(root)
    try:
        with connection:
            connection.execute(
                """
                UPDATE service_jobs
                SET status = 'PENDING', updated_at = ?
                WHERE status = 'RUNNING'
                """,
                (_timestamp(),),
            )
    finally:
        connection.close()


def queue_project_backup(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str | None = None,
) -> dict[str, object]:
    """Persist a backup job for one managed project without starting network work."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    inspect_project(_managed_project_path(root, canonical_id))
    if account_id is not None:
        _require_project_role(
            root,
            project_id=canonical_id,
            account_id=account_id,
            minimum_role="EDITOR",
        )
    job_id = str(uuid.uuid4())
    now = _timestamp()
    connection = _connection(root)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO service_jobs
                    (job_id, kind, payload_json, status, result_json, error, created_at, updated_at)
                VALUES (?, 'PROJECT_BACKUP', ?, 'PENDING', NULL, NULL, ?, ?)
                """,
                (
                    job_id,
                    _canonical_json({"project_id": canonical_id}),
                    now,
                    now,
                ),
            )
    finally:
        connection.close()
    return {
        "status": "QUEUED",
        "job_id": job_id,
        "kind": "PROJECT_BACKUP",
        "project_id": canonical_id,
        "network_required": False,
    }


def get_service_job(service_workspace: Path | str, job_id: str) -> dict[str, object]:
    """Read one persisted job using a canonical job identifier."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(job_id, role="job_id")
    connection = _connection(root)
    try:
        row = connection.execute(
            """
            SELECT job_id, kind, payload_json, status, result_json, error, created_at, updated_at
            FROM service_jobs WHERE job_id = ?
            """,
            (canonical_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ServiceError("service job was not found")
    payload = json.loads(str(row["payload_json"]))
    result = None if row["result_json"] is None else json.loads(str(row["result_json"]))
    return {
        "job_id": row["job_id"],
        "kind": row["kind"],
        "project_id": payload["project_id"],
        "status": row["status"],
        "result": result,
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "network_required": False,
    }


def get_authorized_service_job(
    service_workspace: Path | str,
    job_id: str,
    *,
    account_id: str,
) -> dict[str, object]:
    """Read a persisted job only when the account can view its project."""

    root = _service_root(service_workspace)
    report = get_service_job(root, job_id)
    _require_project_role(
        root,
        project_id=str(report["project_id"]),
        account_id=account_id,
        minimum_role="VIEWER",
    )
    return report


def _claim_next_job(root: Path) -> dict[str, object] | None:
    connection = _connection(root)
    try:
        with connection:
            row = connection.execute(
                """
                SELECT job_id, kind, payload_json
                FROM service_jobs
                WHERE status = 'PENDING'
                ORDER BY created_at, job_id
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            now = _timestamp()
            updated = connection.execute(
                """
                UPDATE service_jobs
                SET status = 'RUNNING', updated_at = ?
                WHERE job_id = ? AND status = 'PENDING'
                """,
                (now, row["job_id"]),
            ).rowcount
            if updated != 1:
                return None
            return {
                "job_id": row["job_id"],
                "kind": row["kind"],
                "payload": json.loads(str(row["payload_json"])),
            }
    finally:
        connection.close()


def _finish_job(
    root: Path,
    job_id: str,
    *,
    status: str,
    result: dict[str, object] | None = None,
    error: str | None = None,
) -> None:
    connection = _connection(root)
    try:
        with connection:
            connection.execute(
                """
                UPDATE service_jobs
                SET status = ?, result_json = ?, error = ?, updated_at = ?
                WHERE job_id = ? AND status = 'RUNNING'
                """,
                (
                    status,
                    None if result is None else _canonical_json(result),
                    error,
                    _timestamp(),
                    job_id,
                ),
            )
    finally:
        connection.close()


class ServiceJobWorker:
    """Single-process durable worker for explicit local service jobs."""

    def __init__(self, service_workspace: Path | str) -> None:
        self._root = _service_root(service_workspace)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="aktreader-service-worker",
            daemon=True,
        )

    def start(self) -> None:
        _recover_running_jobs(self._root)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            job = _claim_next_job(self._root)
            if job is None:
                self._stop_event.wait(0.1)
                continue
            try:
                if job["kind"] != "PROJECT_BACKUP":
                    raise ServiceError("service worker received an unsupported job")
                payload = job["payload"]
                if not isinstance(payload, dict):
                    raise ServiceError("service job payload is invalid")
                backup = create_project_backup(self._root, str(payload["project_id"]))
                _finish_job(
                    self._root,
                    str(job["job_id"]),
                    status="SUCCEEDED",
                    result={
                        "project_id": backup["project_id"],
                        "backup_id": backup["backup_id"],
                        "file_count": backup["file_count"],
                    },
                )
            except (OSError, ProjectStoreError, ServiceError, TypeError, ValueError):
                _finish_job(
                    self._root,
                    str(job["job_id"]),
                    status="FAILED",
                    error="local backup job failed; inspect the local service log",
                )


def list_authorized_project_documents(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
) -> list[dict[str, object]]:
    """List PAGE XML document records visible to one project viewer."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="VIEWER",
    )
    return list_project_documents(_managed_project_path(root, canonical_id))


def load_authorized_project_page(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
    page_index: int,
) -> dict[str, object]:
    """Load one revision-aware PAGE record without exposing a local image path."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="VIEWER",
    )
    page = load_project_page(
        _managed_project_path(root, canonical_id),
        manifest_sha256=manifest_sha256,
        page_index=page_index,
    )
    return {key: value for key, value in page.items() if key != "image_path"}


def load_authorized_project_image(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
    page_index: int,
) -> tuple[str, bytes]:
    """Read one project image only after viewer authorization and path containment checks."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="VIEWER",
    )
    project = _managed_project_path(root, canonical_id)
    page = load_project_page(
        project,
        manifest_sha256=manifest_sha256,
        page_index=page_index,
    )
    image = Path(str(page["image_path"])).resolve()
    if project not in image.parents or image.is_symlink() or not image.is_file():
        raise ServiceError("managed project image is invalid")
    if image.stat().st_size > MAX_IMAGE_RESPONSE_BYTES:
        raise ServiceError("managed project image exceeds the response size limit")
    media_type = mimetypes.guess_type(image.name)[0]
    if media_type is None or not media_type.startswith("image/"):
        raise ServiceError("managed project image has an unsupported media type")
    try:
        return media_type, image.read_bytes()
    except OSError as error:
        raise ServiceError("managed project image is unreadable") from error


def revise_authorized_project_line(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
    source_span_id: str,
    text: str,
    expected_revision: int,
) -> dict[str, object]:
    """Append one optimistic, role-checked human transcription revision."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="EDITOR",
    )
    account = _account_by_id(root, account_id)
    revision = revise_line_transcription(
        _managed_project_path(root, canonical_id),
        manifest_sha256=manifest_sha256,
        source_span_id=source_span_id,
        text=text,
        editor=str(account["username"]),
        expected_revision=expected_revision,
    )
    return {
        key: value
        for key, value in revision.items()
        if key != "project"
    }


def _public_job(report: dict[str, object]) -> dict[str, object]:
    return {
        "job_id": report["job_id"],
        "kind": report["kind"],
        "project_id": report["project_id"],
        "status": report["status"],
        "result": report["result"],
        "error": None if report["error"] is None else "local backup job failed",
        "created_at": report["created_at"],
        "updated_at": report["updated_at"],
        "network_required": False,
    }


class _ServiceRequestHandler(BaseHTTPRequestHandler):
    server: SelfHostedServiceServer

    def log_message(self, format: str, *args: object) -> None:
        """Keep local service request details out of stdout and CI logs."""

    def _headers(self, status: HTTPStatus, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")

    def _json(self, status: HTTPStatus, payload: object) -> None:
        body = (_canonical_json(payload) + "\n").encode("utf-8")
        self._headers(status, "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json(status, {"status": "ERROR", "message": message, "network_required": False})

    def _read_json(self) -> dict[str, object]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ServiceError("request must include Content-Length")
        try:
            length = int(raw_length)
        except ValueError as error:
            raise ServiceError("request Content-Length is invalid") from error
        if length < 1 or length > MAX_REQUEST_BYTES:
            raise ServiceError("request body size is invalid")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ServiceError("request body must be a JSON object") from error
        if not isinstance(payload, dict):
            raise ServiceError("request body must be a JSON object")
        return payload

    def _path(self) -> str:
        parsed = urlparse(self.path)
        if parsed.query or parsed.fragment:
            raise ServiceError("query parameters are not supported")
        return unquote(parsed.path)

    def _account(self) -> dict[str, object]:
        return authenticated_service_account(
            self.server.service_workspace,
            self.headers.get("Authorization"),
        )

    def do_GET(self) -> None:
        try:
            path = self._path()
            if path == "/api/healthz":
                report = inspect_service_workspace(self.server.service_workspace)
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "READY",
                        "service_id": report["service_id"],
                        "project_count": report["project_count"],
                        "job_counts": report["job_counts"],
                        "network_required": False,
                    },
                )
                return
            if path == "/api/projects":
                account = self._account()
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "READY",
                        "projects": list_authorized_service_projects(
                            self.server.service_workspace,
                            account_id=str(account["account_id"]),
                        ),
                        "network_required": False,
                    },
                )
                return
            parts = path.split("/")
            if (
                len(parts) == 5
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "documents"
            ):
                account = self._account()
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "READY",
                        "documents": list_authorized_project_documents(
                            self.server.service_workspace,
                            parts[3],
                            account_id=str(account["account_id"]),
                        ),
                        "network_required": False,
                    },
                )
                return
            if (
                len(parts) == 8
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "documents"
                and parts[6] == "pages"
            ):
                try:
                    page_index = int(parts[7])
                except ValueError as error:
                    raise ServiceError("page index must be an integer") from error
                account = self._account()
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "READY",
                        "page": load_authorized_project_page(
                            self.server.service_workspace,
                            parts[3],
                            account_id=str(account["account_id"]),
                            manifest_sha256=parts[5],
                            page_index=page_index,
                        ),
                        "network_required": False,
                    },
                )
                return
            if (
                len(parts) == 5
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "artifacts"
            ):
                account = self._account()
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "READY",
                        "artifacts": list_authorized_project_artifacts(
                            self.server.service_workspace,
                            parts[3],
                            account_id=str(account["account_id"]),
                        ),
                        "network_required": False,
                    },
                )
                return
            prefix = "/api/jobs/"
            if path.startswith(prefix) and "/" not in path[len(prefix) :]:
                account = self._account()
                job = get_authorized_service_job(
                    self.server.service_workspace,
                    path[len(prefix) :],
                    account_id=str(account["account_id"]),
                )
                self._json(HTTPStatus.OK, _public_job(job))
                return
            self._error(HTTPStatus.NOT_FOUND, "route was not found")
        except AuthenticationError:
            self._error(HTTPStatus.UNAUTHORIZED, "authentication is required")
        except AuthorizationError:
            self._error(HTTPStatus.FORBIDDEN, "account is not authorized for this project")
        except ProjectStoreError as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))
        except ServiceError as error:
            status = (
                HTTPStatus.NOT_FOUND
                if str(error) == "service job was not found"
                else HTTPStatus.BAD_REQUEST
            )
            self._error(status, str(error))

    def do_POST(self) -> None:
        try:
            path = self._path()
            payload = self._read_json()
            if path == "/api/session":
                if set(payload) != {"username", "password"}:
                    raise ServiceError("sign-in requires username and password")
                session = create_service_session(
                    self.server.service_workspace,
                    username=str(payload["username"]),
                    password=str(payload["password"]),
                )
                self._json(HTTPStatus.CREATED, session)
                return
            parts = path.split("/")
            if (
                len(parts) == 5
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "artifacts"
            ):
                if set(payload) != {"artifact_id"}:
                    raise ServiceError("artifact attachment has invalid keys")
                account = self._account()
                attachment = attach_authorized_project_artifact(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    artifact_id=str(payload["artifact_id"]),
                )
                self._json(HTTPStatus.OK, attachment)
                return
            if (
                len(parts) == 5
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "transcriptions"
            ):
                required = {
                    "manifest_sha256",
                    "source_span_id",
                    "text",
                    "expected_revision",
                }
                if set(payload) != required:
                    raise ServiceError("transcription update has invalid keys")
                account = self._account()
                revision = revise_authorized_project_line(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    manifest_sha256=str(payload["manifest_sha256"]),
                    source_span_id=str(payload["source_span_id"]),
                    text=payload["text"],
                    expected_revision=payload["expected_revision"],
                )
                self._json(HTTPStatus.OK, revision)
                return
            if path != "/api/jobs":
                self._error(HTTPStatus.NOT_FOUND, "route was not found")
                return
            if set(payload) != {"kind", "project_id"} or payload["kind"] != "PROJECT_BACKUP":
                raise ServiceError("request must be a PROJECT_BACKUP job with project_id")
            account = self._account()
            job = queue_project_backup(
                self.server.service_workspace,
                _require_uuid(payload["project_id"], role="project_id"),
                account_id=str(account["account_id"]),
            )
            self._json(HTTPStatus.ACCEPTED, job)
        except AuthenticationError:
            self._error(HTTPStatus.UNAUTHORIZED, "sign-in failed")
        except AuthorizationError:
            self._error(HTTPStatus.FORBIDDEN, "account is not authorized for this project")
        except ProjectStoreError as error:
            status = (
                HTTPStatus.CONFLICT
                if str(error) == "transcription revision conflict; reload the current line"
                else HTTPStatus.BAD_REQUEST
            )
            self._error(status, str(error))
        except ServiceError as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))


class SelfHostedServiceServer(ThreadingHTTPServer):
    """A loopback-only local service process with one durable worker."""

    allow_reuse_address = True

    def __init__(self, service_workspace: Path | str, *, port: int) -> None:
        self.service_workspace = _service_root(service_workspace)
        self.worker = ServiceJobWorker(self.service_workspace)
        super().__init__((LOOPBACK_HOST, port), _ServiceRequestHandler)
        self.worker.start()

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"

    def server_close(self) -> None:
        self.worker.stop()
        super().server_close()


def create_self_hosted_service_server(
    service_workspace: Path | str,
    *,
    port: int = 8780,
) -> SelfHostedServiceServer:
    """Create a loopback-only service server without starting its request loop."""

    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ServiceError("port must be an integer from 0 to 65535")
    return SelfHostedServiceServer(service_workspace, port=port)
