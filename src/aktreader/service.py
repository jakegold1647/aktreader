"""Loopback-only service workspace, durable backup jobs, and verified restore."""

from __future__ import annotations

import hashlib
import json
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

from PIL import Image

from aktreader.kraken import KrakenError, LocalKraken
from aktreader.project import (
    ProjectStoreError,
    evaluate_htr_suggestions,
    export_human_pagexml,
    export_human_transcript,
    export_human_transcriptions_csv,
    inspect_project,
    list_htr_suggestion_evaluations,
    list_project_activity,
    list_project_documents,
    load_project_page,
    load_project_page_layout,
    recognize_project_with_kraken,
    revise_line_geometry,
    revise_line_transcription,
    revise_page_reading_order,
    revise_region_geometry,
    search_project_transcriptions,
    undo_line_transcription,
)

SERVICE_MANIFEST_NAME = "service.akt.json"
SERVICE_DATABASE_NAME = "service.sqlite3"
SERVICE_CONTRACT = {"name": "aktreader-self-hosted-service", "version": "1.0.0"}
BACKUP_MANIFEST_NAME = "backup.aktreader.json"
BACKUP_CONTRACT = {"name": "aktreader-project-backup", "version": "1.0.0"}
HTR_EVALUATION_RECEIPT_CONTRACT = {
    "name": "aktreader-htr-evaluation-receipt",
    "version": "1.0.0",
}
PROJECTS_DIRECTORY = "projects"
BACKUPS_DIRECTORY = "backups"
ARTIFACTS_DIRECTORY = "artifacts"
LOOPBACK_HOST = "127.0.0.1"
CONTAINER_LISTEN_HOST = "0.0.0.0"
MAX_REQUEST_BYTES = 65_536
MAX_BACKUP_FILES = 100_000
MAX_BACKUP_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_NAME_LENGTH = 160
MAX_ARTIFACT_DESCRIPTION_LENGTH = 4_000
MAX_IMAGE_RESPONSE_BYTES = 100 * 1024 * 1024
MAX_EXPORT_RESPONSE_BYTES = 100 * 1024 * 1024
_COPY_BUFFER_BYTES = 1024 * 1024
ARTIFACT_KINDS = ("MODEL", "DATASET")
PASSWORD_SCRYPT_N = 16_384
PASSWORD_SCRYPT_R = 8
PASSWORD_SCRYPT_P = 1
SESSION_TTL_SECONDS = 8 * 60 * 60
PROJECT_ROLES = ("VIEWER", "EDITOR", "OWNER")
_ROLE_RANK = {role: index for index, role in enumerate(PROJECT_ROLES)}
_REVISION_CONFLICT_MESSAGES = frozenset(
    {
        "transcription revision conflict; reload the current line",
        "line geometry revision conflict; reload the current page",
        "region geometry revision conflict; reload the current page",
        "reading-order revision conflict; reload the current page",
    }
)


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
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT role
                FROM service_project_roles
                WHERE project_id = ? AND account_id = ?
                """,
                (canonical_project_id, account["account_id"]),
            ).fetchone()
            if (
                existing is not None
                and str(existing["role"]) == "OWNER"
                and canonical_role != "OWNER"
            ):
                owner_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM service_project_roles
                    WHERE project_id = ? AND role = 'OWNER'
                    """,
                    (canonical_project_id,),
                ).fetchone()[0]
                if int(owner_count) <= 1:
                    raise ServiceError("project must retain at least one owner")
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


def list_authorized_project_members(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
) -> list[dict[str, object]]:
    """List project memberships for an owner without password material."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="OWNER",
    )
    connection = _connection(root)
    try:
        rows = connection.execute(
            """
            SELECT
                service_accounts.account_id,
                service_accounts.username,
                service_project_roles.role,
                service_project_roles.granted_at
            FROM service_project_roles
            JOIN service_accounts
                ON service_accounts.account_id = service_project_roles.account_id
            WHERE service_project_roles.project_id = ?
            ORDER BY service_accounts.username, service_accounts.account_id
            """,
            (canonical_id,),
        ).fetchall()
    finally:
        connection.close()
    return [
        {
            "account_id": str(row["account_id"]),
            "username": str(row["username"]),
            "role": str(row["role"]),
            "granted_at": str(row["granted_at"]),
        }
        for row in rows
    ]


def list_authorized_project_accounts(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
) -> list[dict[str, object]]:
    """List local account identities for a project owner."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="OWNER",
    )
    return list_local_accounts(root)


def grant_authorized_project_role(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    username: str,
    role: str,
) -> dict[str, object]:
    """Let an owner grant an existing local account a project role."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="OWNER",
    )
    target = _account_by_username(root, username)
    if str(target["account_id"]) == _require_uuid(account_id, role="account_id"):
        raise ServiceError("owners cannot change their own project role through the service")
    return grant_project_role(
        root,
        project_id=canonical_id,
        username=username,
        role=role,
    )


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



def list_authorized_attachable_project_artifacts(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
) -> list[dict[str, object]]:
    """List registry metadata an owner may attach to one managed project."""

    root = _service_root(service_workspace)
    canonical_project_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_project_id,
        account_id=account_id,
        minimum_role="OWNER",
    )
    inspect_project(_managed_project_path(root, canonical_project_id))
    connection = _connection(root)
    try:
        attached_ids = {
            str(row["artifact_id"])
            for row in connection.execute(
                """
                SELECT artifact_id
                FROM service_project_artifacts
                WHERE project_id = ?
                """,
                (canonical_project_id,),
            ).fetchall()
        }
    finally:
        connection.close()
    return [
        artifact
        for artifact in list_service_artifacts(root)
        if str(artifact["artifact_id"]) not in attached_ids
    ]


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


def queue_project_kraken_recognition(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
    kraken: LocalKraken | None,
) -> dict[str, object]:
    """Persist one editor-authorized run of the owner's pinned Kraken adapter."""

    if kraken is None:
        raise ServiceError("local Kraken recognition is not configured for this service")
    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    canonical_manifest = _require_sha256(manifest_sha256, role="manifest_sha256")
    inspect_project(_managed_project_path(root, canonical_id))
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
                VALUES (?, 'PROJECT_KRAKEN_RECOGNITION', ?, 'PENDING', NULL, NULL, ?, ?)
                """,
                (
                    job_id,
                    _canonical_json(
                        {
                            "project_id": canonical_id,
                            "manifest_sha256": canonical_manifest,
                        }
                    ),
                    now,
                    now,
                ),
            )
    finally:
        connection.close()
    return {
        "status": "QUEUED",
        "job_id": job_id,
        "kind": "PROJECT_KRAKEN_RECOGNITION",
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

    def __init__(
        self,
        service_workspace: Path | str,
        *,
        kraken: LocalKraken | None = None,
    ) -> None:
        self._root = _service_root(service_workspace)
        self._kraken = kraken
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
                payload = job["payload"]
                if not isinstance(payload, dict):
                    raise ServiceError("service job payload is invalid")
                if job["kind"] == "PROJECT_BACKUP":
                    backup = create_project_backup(self._root, str(payload["project_id"]))
                    result = {
                        "project_id": backup["project_id"],
                        "backup_id": backup["backup_id"],
                        "file_count": backup["file_count"],
                    }
                elif job["kind"] == "PROJECT_KRAKEN_RECOGNITION":
                    if self._kraken is None:
                        raise ServiceError(
                            "local Kraken recognition is not configured for this service"
                        )
                    recognition = recognize_project_with_kraken(
                        _managed_project_path(self._root, str(payload["project_id"])),
                        manifest_sha256=str(payload["manifest_sha256"]),
                        kraken=self._kraken,
                    )
                    result = {
                        "project_id": payload["project_id"],
                        "manifest_sha256": recognition["manifest_sha256"],
                        "result_pagexml_sha256": recognition["result_pagexml_sha256"],
                        "suggestion_count": recognition["suggestion_count"],
                        "runtime_fingerprint": recognition["runtime_fingerprint"],
                    }
                else:
                    raise ServiceError("service worker received an unsupported job")
                _finish_job(
                    self._root,
                    str(job["job_id"]),
                    status="SUCCEEDED",
                    result=result,
                )
            except (
                KrakenError,
                OSError,
                ProjectStoreError,
                ServiceError,
                TypeError,
                ValueError,
            ):
                _finish_job(
                    self._root,
                    str(job["job_id"]),
                    status="FAILED",
                    error="local service job failed; inspect the local service log",
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

def list_authorized_project_activity(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
) -> dict[str, object]:
    """List document activity for an authorized viewer without exposing local paths."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="VIEWER",
    )
    return list_project_activity(
        _managed_project_path(root, canonical_id),
        manifest_sha256=manifest_sha256,
    )



def list_authorized_project_htr_evaluations(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
) -> list[dict[str, object]]:
    """List current HTR quality reports for an authorized document viewer."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="VIEWER",
    )
    reports = list_htr_suggestion_evaluations(
        _managed_project_path(root, canonical_id),
        manifest_sha256=manifest_sha256,
    )
    return [{key: value for key, value in report.items() if key != "project"} for report in reports]




def search_authorized_project_transcriptions(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    query: str,
    field: str,
) -> dict[str, object]:
    """Search effective transcription lines for an authorized project viewer."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="VIEWER",
    )
    return search_project_transcriptions(
        _managed_project_path(root, canonical_id),
        query=query,
        field=field,
    )



def export_authorized_project_htr_evaluation_receipt(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
    result_pagexml_sha256: str,
) -> tuple[str, bytes]:
    """Render one authorized, provenance-pinned HTR evaluation receipt."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    canonical_manifest = _require_sha256(manifest_sha256, role="manifest_sha256")
    canonical_result = _require_sha256(
        result_pagexml_sha256,
        role="result_pagexml_sha256",
    )
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="VIEWER",
    )
    report = evaluate_htr_suggestions(
        _managed_project_path(root, canonical_id),
        manifest_sha256=canonical_manifest,
        result_pagexml_sha256=canonical_result,
    )
    public_report = {key: value for key, value in report.items() if key != "project"}
    report_sha256 = hashlib.sha256(
        _canonical_json(public_report).encode("utf-8")
    ).hexdigest()
    receipt = {
        "contract": HTR_EVALUATION_RECEIPT_CONTRACT,
        "report": public_report,
        "report_sha256": report_sha256,
        "network_required": False,
    }
    payload = (_canonical_json(receipt) + "\n").encode("utf-8")
    if len(payload) > MAX_EXPORT_RESPONSE_BYTES:
        raise ServiceError("generated HTR evaluation receipt exceeds the response size limit")
    filename = (
        f"aktreader-{canonical_manifest[:12]}-{canonical_result[:12]}.evaluation.json"
    )
    return filename, payload



def load_authorized_project_layout(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
    page_index: int,
) -> dict[str, object]:
    """Load revision-aware layout without disclosing a managed project path."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="VIEWER",
    )
    layout = load_project_page_layout(
        _managed_project_path(root, canonical_id),
        manifest_sha256=manifest_sha256,
        page_index=page_index,
    )
    return {key: value for key, value in layout.items() if key != "project"}


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
    try:
        with Image.open(image) as opened:
            media_type = Image.MIME.get(opened.format or "", "application/octet-stream")
        payload = image.read_bytes()
    except OSError as error:
        raise ServiceError("managed project image is unreadable") from error
    if not media_type.startswith("image/"):
        raise ServiceError("managed project image has an unsupported media type")
    return media_type, payload



def export_authorized_project_pagexml(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
) -> tuple[str, bytes]:
    """Render an authorized project's effective PAGE XML as a download payload."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    canonical_manifest = _require_sha256(manifest_sha256, role="manifest_sha256")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="VIEWER",
    )
    with tempfile.TemporaryDirectory(prefix="aktreader-pagexml-", dir=root) as temporary:
        output = Path(temporary) / "document.page.xml"
        export_human_pagexml(
            _managed_project_path(root, canonical_id),
            output,
            manifest_sha256=canonical_manifest,
        )
        try:
            payload = output.read_bytes()
        except OSError as error:
            raise ServiceError("generated PAGE XML export is unreadable") from error
    if len(payload) > MAX_EXPORT_RESPONSE_BYTES:
        raise ServiceError("generated PAGE XML export exceeds the response size limit")
    filename = f"aktreader-{canonical_manifest[:12]}.page.xml"
    return filename, payload


def export_authorized_project_transcript(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
) -> tuple[str, bytes]:
    """Render an authorized project's effective transcript as a download payload."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    canonical_manifest = _require_sha256(manifest_sha256, role="manifest_sha256")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="VIEWER",
    )
    with tempfile.TemporaryDirectory(prefix="aktreader-transcript-", dir=root) as temporary:
        output = Path(temporary) / "document.txt"
        export_human_transcript(
            _managed_project_path(root, canonical_id),
            output,
            manifest_sha256=canonical_manifest,
        )
        try:
            payload = output.read_bytes()
        except OSError as error:
            raise ServiceError("generated transcript export is unreadable") from error
    if len(payload) > MAX_EXPORT_RESPONSE_BYTES:
        raise ServiceError("generated transcript export exceeds the response size limit")
    filename = f"aktreader-{canonical_manifest[:12]}.txt"
    return filename, payload


def export_authorized_project_transcriptions_csv(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
) -> tuple[str, bytes]:
    """Render an authorized project's effective line CSV as a download payload."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    canonical_manifest = _require_sha256(manifest_sha256, role="manifest_sha256")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="VIEWER",
    )
    with tempfile.TemporaryDirectory(prefix="aktreader-csv-", dir=root) as temporary:
        output = Path(temporary) / "document.csv"
        export_human_transcriptions_csv(
            _managed_project_path(root, canonical_id),
            output,
            manifest_sha256=canonical_manifest,
        )
        try:
            payload = output.read_bytes()
        except OSError as error:
            raise ServiceError("generated transcription CSV export is unreadable") from error
    if len(payload) > MAX_EXPORT_RESPONSE_BYTES:
        raise ServiceError("generated transcription CSV export exceeds the response size limit")
    filename = f"aktreader-{canonical_manifest[:12]}-lines.csv"
    return filename, payload


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

def undo_authorized_project_line(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
    source_span_id: str,
    expected_revision: int,
) -> dict[str, object]:
    """Append a role-checked reversal without removing project history."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="EDITOR",
    )
    account = _account_by_id(root, account_id)
    revision = undo_line_transcription(
        _managed_project_path(root, canonical_id),
        manifest_sha256=manifest_sha256,
        source_span_id=source_span_id,
        editor=str(account["username"]),
        expected_revision=expected_revision,
    )
    return {key: value for key, value in revision.items() if key != "project"}


def revise_authorized_project_line_geometry(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
    source_span_id: str,
    polygon: object,
    baseline: object,
    expected_revision: object,
) -> dict[str, object]:
    """Append one optimistic, role-checked line-geometry revision."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="EDITOR",
    )
    account = _account_by_id(root, account_id)
    revision = revise_line_geometry(
        _managed_project_path(root, canonical_id),
        manifest_sha256=manifest_sha256,
        source_span_id=source_span_id,
        polygon=polygon,
        baseline=baseline,
        editor=str(account["username"]),
        expected_revision=expected_revision,
    )
    return {key: value for key, value in revision.items() if key != "project"}


def revise_authorized_project_region_geometry(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
    page_index: object,
    region_id: str,
    polygon: object,
    expected_revision: object,
) -> dict[str, object]:
    """Append one optimistic, role-checked region-geometry revision."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="EDITOR",
    )
    account = _account_by_id(root, account_id)
    revision = revise_region_geometry(
        _managed_project_path(root, canonical_id),
        manifest_sha256=manifest_sha256,
        page_index=page_index,
        region_id=region_id,
        polygon=polygon,
        editor=str(account["username"]),
        expected_revision=expected_revision,
    )
    return {key: value for key, value in revision.items() if key != "project"}


def revise_authorized_project_reading_order(
    service_workspace: Path | str,
    project_id: str,
    *,
    account_id: str,
    manifest_sha256: str,
    page_index: object,
    region_ids: object,
    expected_revision: object,
) -> dict[str, object]:
    """Append one optimistic, role-checked page reading-order revision."""

    root = _service_root(service_workspace)
    canonical_id = _require_uuid(project_id, role="project_id")
    _require_project_role(
        root,
        project_id=canonical_id,
        account_id=account_id,
        minimum_role="EDITOR",
    )
    account = _account_by_id(root, account_id)
    revision = revise_page_reading_order(
        _managed_project_path(root, canonical_id),
        manifest_sha256=manifest_sha256,
        page_index=page_index,
        region_ids=region_ids,
        editor=str(account["username"]),
        expected_revision=expected_revision,
    )
    return {key: value for key, value in revision.items() if key != "project"}



def _public_job(report: dict[str, object]) -> dict[str, object]:
    return {
        "job_id": report["job_id"],
        "kind": report["kind"],
        "project_id": report["project_id"],
        "status": report["status"],
        "result": report["result"],
        "error": None if report["error"] is None else "local service job failed",
        "created_at": report["created_at"],
        "updated_at": report["updated_at"],
        "network_required": False,
    }


class _ServiceRequestHandler(BaseHTTPRequestHandler):
    server: SelfHostedServiceServer

    def log_message(self, format: str, *args: object) -> None:
        """Keep local service request details out of stdout and CI logs."""

    def _headers(
        self,
        status: HTTPStatus,
        content_type: str,
        *,
        content_security_policy: str = "default-src 'none'",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", content_security_policy)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")

    def _json(self, status: HTTPStatus, payload: object) -> None:
        body = (_canonical_json(payload) + "\n").encode("utf-8")
        self._headers(status, "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bytes(
        self,
        status: HTTPStatus,
        media_type: str,
        payload: bytes,
        *,
        download_name: str | None = None,
    ) -> None:
        self._headers(status, media_type)
        if download_name is not None:
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{download_name}"',
            )
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _html(self, payload: str) -> None:
        body = payload.encode("utf-8")
        self._headers(
            HTTPStatus.OK,
            "text/html; charset=utf-8",
            content_security_policy=(
                "default-src 'self'; base-uri 'none'; connect-src 'self'; "
                "frame-ancestors 'none'; img-src 'self' blob:; "
                "script-src 'unsafe-inline'; style-src 'unsafe-inline'"
            ),
        )
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
            if path == "/":
                self._html(SERVICE_WORKBENCH_HTML)
                return
            if path == "/api/healthz":
                report = inspect_service_workspace(self.server.service_workspace)
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "READY",
                        "service_id": report["service_id"],
                        "project_count": report["project_count"],
                        "job_counts": report["job_counts"],
                        "kraken_recognition_enabled": self.server.kraken is not None,
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
                and parts[4] == "members"
            ):
                account = self._account()
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "READY",
                        "members": list_authorized_project_members(
                            self.server.service_workspace,
                            parts[3],
                            account_id=str(account["account_id"]),
                        ),
                        "network_required": False,
                    },
                )
                return
            if (
                len(parts) == 5
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "accounts"
            ):
                account = self._account()
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "READY",
                        "accounts": list_authorized_project_accounts(
                            self.server.service_workspace,
                            parts[3],
                            account_id=str(account["account_id"]),
                        ),
                        "network_required": False,
                    },
                )
                return
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
                len(parts) == 7
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "documents"
                and parts[6] == "activity"
            ):
                account = self._account()
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "READY",
                        "activity": list_authorized_project_activity(
                            self.server.service_workspace,
                            parts[3],
                            account_id=str(account["account_id"]),
                            manifest_sha256=parts[5],
                        ),
                        "network_required": False,
                    },
                )
                return
            if (
                len(parts) == 9
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "documents"
                and parts[6] == "evaluations"
                and parts[8] == "receipt"
            ):
                account = self._account()
                filename, receipt = export_authorized_project_htr_evaluation_receipt(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    manifest_sha256=parts[5],
                    result_pagexml_sha256=parts[7],
                )
                self._bytes(
                    HTTPStatus.OK,
                    "application/json; charset=utf-8",
                    receipt,
                    download_name=filename,
                )
                return
            if (
                len(parts) == 7
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "documents"
                and parts[6] == "evaluations"
            ):
                account = self._account()
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "READY",
                        "evaluations": list_authorized_project_htr_evaluations(
                            self.server.service_workspace,
                            parts[3],
                            account_id=str(account["account_id"]),
                            manifest_sha256=parts[5],
                        ),
                        "network_required": False,
                    },
                )
                return
            if (
                len(parts) == 8
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "documents"
                and parts[6:] == ["export", "transcript"]
            ):
                account = self._account()
                filename, transcript = export_authorized_project_transcript(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    manifest_sha256=parts[5],
                )
                self._bytes(
                    HTTPStatus.OK,
                    "text/plain; charset=utf-8",
                    transcript,
                    download_name=filename,
                )
                return
            if (
                len(parts) == 8
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "documents"
                and parts[6:] == ["export", "transcriptions-csv"]
            ):
                account = self._account()
                filename, transcription_csv = export_authorized_project_transcriptions_csv(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    manifest_sha256=parts[5],
                )
                self._bytes(
                    HTTPStatus.OK,
                    "text/csv; charset=utf-8",
                    transcription_csv,
                    download_name=filename,
                )
                return
            if (
                len(parts) == 8
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "documents"
                and parts[6:] == ["export", "pagexml"]
            ):
                account = self._account()
                filename, pagexml = export_authorized_project_pagexml(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    manifest_sha256=parts[5],
                )
                self._bytes(
                    HTTPStatus.OK,
                    "application/vnd.prima.page+xml; charset=utf-8",
                    pagexml,
                    download_name=filename,
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
                len(parts) == 9
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "documents"
                and parts[6] == "pages"
                and parts[8] == "layout"
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
                        "layout": load_authorized_project_layout(
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
                len(parts) == 9
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "documents"
                and parts[6] == "pages"
                and parts[8] == "image"
            ):
                try:
                    page_index = int(parts[7])
                except ValueError as error:
                    raise ServiceError("page index must be an integer") from error
                account = self._account()
                media_type, image = load_authorized_project_image(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    manifest_sha256=parts[5],
                    page_index=page_index,
                )
                self._bytes(HTTPStatus.OK, media_type, image)
                return
            if (
                len(parts) == 5
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "available-artifacts"
            ):
                account = self._account()
                self._json(
                    HTTPStatus.OK,
                    {
                        "status": "READY",
                        "artifacts": list_authorized_attachable_project_artifacts(
                            self.server.service_workspace,
                            parts[3],
                            account_id=str(account["account_id"]),
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
                and parts[4] == "search"
            ):
                if set(payload) != {"query", "field"}:
                    raise ServiceError("project search has invalid keys")
                account = self._account()
                report = search_authorized_project_transcriptions(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    query=payload["query"],
                    field=payload["field"],
                )
                self._json(HTTPStatus.OK, report)
                return
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
                and parts[4] == "members"
            ):
                if set(payload) != {"username", "role"}:
                    raise ServiceError("project membership update has invalid keys")
                account = self._account()
                membership = grant_authorized_project_role(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    username=str(payload["username"]),
                    role=str(payload["role"]),
                )
                self._json(HTTPStatus.OK, membership)
                return
            if (
                len(parts) == 6
                and parts[:3] == ["", "api", "projects"]
                and parts[4:] == ["transcriptions", "undo"]
            ):
                required = {
                    "manifest_sha256",
                    "source_span_id",
                    "expected_revision",
                }
                if set(payload) != required:
                    raise ServiceError("transcription undo has invalid keys")
                account = self._account()
                revision = undo_authorized_project_line(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    manifest_sha256=str(payload["manifest_sha256"]),
                    source_span_id=str(payload["source_span_id"]),
                    expected_revision=payload["expected_revision"],
                )
                self._json(HTTPStatus.OK, revision)
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
            if (
                len(parts) == 5
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "line-geometry"
            ):
                required = {
                    "manifest_sha256",
                    "source_span_id",
                    "polygon",
                    "baseline",
                    "expected_revision",
                }
                if set(payload) != required:
                    raise ServiceError("line geometry update has invalid keys")
                account = self._account()
                revision = revise_authorized_project_line_geometry(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    manifest_sha256=str(payload["manifest_sha256"]),
                    source_span_id=str(payload["source_span_id"]),
                    polygon=payload["polygon"],
                    baseline=payload["baseline"],
                    expected_revision=payload["expected_revision"],
                )
                self._json(HTTPStatus.OK, revision)
                return
            if (
                len(parts) == 5
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "region-geometry"
            ):
                required = {
                    "manifest_sha256",
                    "page_index",
                    "region_id",
                    "polygon",
                    "expected_revision",
                }
                if set(payload) != required:
                    raise ServiceError("region geometry update has invalid keys")
                account = self._account()
                revision = revise_authorized_project_region_geometry(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    manifest_sha256=str(payload["manifest_sha256"]),
                    page_index=payload["page_index"],
                    region_id=str(payload["region_id"]),
                    polygon=payload["polygon"],
                    expected_revision=payload["expected_revision"],
                )
                self._json(HTTPStatus.OK, revision)
                return
            if (
                len(parts) == 5
                and parts[:3] == ["", "api", "projects"]
                and parts[4] == "reading-order"
            ):
                required = {
                    "manifest_sha256",
                    "page_index",
                    "region_ids",
                    "expected_revision",
                }
                if set(payload) != required:
                    raise ServiceError("reading-order update has invalid keys")
                account = self._account()
                revision = revise_authorized_project_reading_order(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    manifest_sha256=str(payload["manifest_sha256"]),
                    page_index=payload["page_index"],
                    region_ids=payload["region_ids"],
                    expected_revision=payload["expected_revision"],
                )
                self._json(HTTPStatus.OK, revision)
                return
            if (
                len(parts) == 6
                and parts[:3] == ["", "api", "projects"]
                and parts[4:] == ["recognitions", "kraken"]
            ):
                if set(payload) != {"manifest_sha256"}:
                    raise ServiceError("Kraken recognition request has invalid keys")
                account = self._account()
                job = queue_project_kraken_recognition(
                    self.server.service_workspace,
                    parts[3],
                    account_id=str(account["account_id"]),
                    manifest_sha256=str(payload["manifest_sha256"]),
                    kraken=self.server.kraken,
                )
                self._json(HTTPStatus.ACCEPTED, job)
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
                if str(error) in _REVISION_CONFLICT_MESSAGES
                else HTTPStatus.BAD_REQUEST
            )
            self._error(status, str(error))
        except ServiceError as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))


class SelfHostedServiceServer(ThreadingHTTPServer):
    """A local service process with one durable worker and an explicit bind address."""

    allow_reuse_address = True

    def __init__(
        self,
        service_workspace: Path | str,
        *,
        host: str,
        port: int,
        kraken: LocalKraken | None = None,
    ) -> None:
        if host not in {LOOPBACK_HOST, CONTAINER_LISTEN_HOST}:
            raise ServiceError(
                "host must be the loopback address or the explicit container listener"
            )
        self.service_workspace = _service_root(service_workspace)
        self.kraken = kraken
        self.worker = ServiceJobWorker(self.service_workspace, kraken=kraken)
        super().__init__((host, port), _ServiceRequestHandler)
        self.worker.start()

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"

    def server_close(self) -> None:
        self.worker.stop()
        super().server_close()


SERVICE_WORKBENCH_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AKT Reader Collaborative Workbench</title>
<style>
:root { color-scheme: light dark; font-family: system-ui, sans-serif; }
body { margin: 0; background: #f5f7fa; color: #18212f; }
header { background: #172a45; color: #fff; padding: 16px 24px; }
header h1 { margin: 0; font-size: 1.25rem; }
header p { color: #dbeafe; margin: 4px 0 0; }
main { margin: 0 auto; max-width: 1400px; padding: 18px; }
.panel { background: #fff; border: 1px solid #d9e1ea; border-radius: 8px; padding: 16px; }
#app { display: grid; grid-template-columns: minmax(0, 3fr) minmax(300px, 2fr); gap: 16px; }
.controls { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
label { display: grid; gap: 5px; font-weight: 650; }
input, select, textarea, button { font: inherit; }
input, select, textarea { border: 1px solid #aab8c7; border-radius: 5px; padding: 8px; }
button { background: #0f766e; border: 0; border-radius: 5px; color: #fff; cursor: pointer;
  padding: 8px 12px; }
button.secondary { background: #475569; }
button:disabled { cursor: not-allowed; opacity: .55; }
#scan { background: #18212f; display: inline-block; max-width: 100%; position: relative; }
#image { display: block; height: auto; max-width: 100%; }
#overlay { height: 100%; inset: 0; pointer-events: auto; position: absolute; width: 100%; }
.line-box { cursor: pointer; fill: rgba(245, 158, 11, .12); stroke: #d97706; stroke-width: 2; }
.line-box.selected { fill: rgba(22, 163, 74, .18); stroke: #15803d; stroke-width: 3; }
.line-shape { cursor: pointer; fill: rgba(245, 158, 11, .12); stroke: #d97706; stroke-width: 2; }
.line-shape.selected { fill: rgba(22, 163, 74, .18); stroke: #15803d; stroke-width: 3; }
.line-baseline { fill: none; pointer-events: none; stroke: #7c3aed; stroke-width: 2; }
.line-vertex { cursor: grab; fill: #d97706; stroke: #fff; stroke-width: 1.5; }
#line-list { display: grid; gap: 6px; max-height: 260px; overflow: auto; }
.line { background: #fff; color: #18212f; text-align: left; }
.line.selected { outline: 3px solid #15803d; }
textarea { box-sizing: border-box; min-height: 130px; resize: vertical; width: 100%; }
.actions { align-items: center; display: flex; gap: 8px; margin-top: 8px; }
#status, #detail, #review-shortcuts { color: #475569; white-space: pre-wrap; }
#review-shortcuts { font-size: .9rem; margin: 10px 0 0; }
#project-activity { border-top: 1px solid #d9e1ea; margin-top: 18px; padding-top: 14px; }
#project-activity h2 { margin: 8px 0; }
#project-search { border-top: 1px solid #d9e1ea; margin-top: 18px; padding-top: 14px; }
#project-search h2 { margin: 8px 0; }
#search-results { display: grid; gap: 6px; list-style: none; margin: 8px 0 0; max-height: 220px;
  overflow: auto; padding: 0; }
.search-result { background: #fff; color: #18212f; text-align: left; }
#activity-list { display: grid; gap: 6px; list-style: none; margin: 0; max-height: 220px;
  overflow: auto; padding: 0; }
.activity { background: #fff; color: #18212f; text-align: left; }
#membership { border-top: 1px solid #d9e1ea; margin-top: 18px; padding-top: 14px; }
#membership h2 { margin: 8px 0; }
#member-list { display: grid; gap: 6px; list-style: none; margin: 8px 0 0; padding: 0; }
.member { color: #475569; }
#recognition-suggestions { border-top: 1px solid #d9e1ea; margin-top: 18px; padding-top: 14px; }
#recognition-suggestions h2 { margin: 8px 0; }
#suggestions { display: grid; gap: 8px; }
#recognition-evaluation { border-top: 1px solid #d9e1ea; margin-top: 18px; padding-top: 14px; }
#recognition-evaluation h2 { margin: 8px 0; }
#evaluation-list { display: grid; gap: 6px; list-style: none; margin: 0; padding: 0; }
.suggestion { background: #f8fafc; border: 1px solid #d9e1ea; border-radius: 6px; padding: 10px; }
.suggestion p { color: #475569; margin: 0 0 6px; }
.suggestion pre { font: inherit; margin: 0 0 8px; overflow-wrap: anywhere; white-space: pre-wrap; }
#layout-editor { border-top: 1px solid #d9e1ea; margin-top: 18px; padding-top: 14px; }
#layout-editor h2, #layout-editor h3 { margin: 8px 0; }
#region-polygon, #line-polygon, #line-baseline { min-height: 92px; }
#reading-order { display: grid; gap: 6px; list-style: none; margin: 0; padding: 0; }
.order-row { align-items: center; display: flex; gap: 6px; }
.order-row span { flex: 1; overflow-wrap: anywhere; }
.order-row button { padding: 4px 8px; }
.region-shape { cursor: pointer; fill: rgba(37, 99, 235, .10); stroke: #2563eb; stroke-width: 2; }
.region-shape.selected { fill: rgba(21, 128, 61, .16); stroke: #15803d; stroke-width: 3; }
.vertex { cursor: grab; fill: #15803d; stroke: #fff; stroke-width: 1.5; }
#login { margin: 48px auto; max-width: 430px; }
#login form { display: grid; gap: 12px; }
.hidden { display: none !important; }
@media (max-width: 860px) { #app { grid-template-columns: 1fr; }
  .controls { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
  <h1>AKT Reader collaborative workbench</h1>
  <p>Authenticated local review service. This page is available only on loopback.</p>
</header>
<main>
  <section id="login" class="panel" aria-labelledby="login-title">
    <h2 id="login-title">Sign in</h2>
    <form id="login-form">
      <label>Username <input id="username" autocomplete="username" required></label>
      <label>Password <input id="password" type="password"
        autocomplete="current-password" required></label>
      <button type="submit">Sign in</button>
      <p id="login-status" role="status" aria-live="polite"></p>
    </form>
  </section>
  <section id="workspace" class="hidden">
    <div class="actions">
      <strong id="identity"></strong>
      <button id="download-pagexml" class="secondary" type="button" disabled>
        Download PAGE XML
      </button>
      <button id="download-transcript" class="secondary" type="button" disabled>
        Download transcript
      </button>
      <button id="download-transcriptions-csv" class="secondary" type="button" disabled>
        Download CSV
      </button>
      <button id="run-kraken" type="button" disabled>
        Run local recognition
      </button>
      <button id="logout" class="secondary" type="button">Sign out</button>
      <span id="status" role="status" aria-live="polite"></span>
    </div>
    <div id="app">
      <section class="panel">
        <div class="controls">
          <label>Project <select id="project"></select></label>
          <label>Document <select id="document"></select></label>
          <label>Page <select id="page"></select></label>
        </div>
        <p id="page-detail">Choose a project.</p>
        <div id="scan">
          <img id="image" alt="Selected source page">
          <svg id="overlay" aria-label="PAGE XML layout"></svg>
        </div>
      </section>
      <aside class="panel">
        <p id="detail">Choose a line to review its transcription.</p>
        <div id="line-list" aria-label="Transcription lines"></div>
        <label>Transcription <textarea id="text" disabled></textarea></label>
        <div class="actions">
          <button id="save" type="button" disabled>Save correction</button>
          <button id="undo" type="button" disabled>Undo latest correction</button>
          <span id="role"></span>
        </div>
        <p id="review-shortcuts">Keyboard: J/↓ next line · K/↑ previous line ·
          Ctrl/⌘+Enter saves a reviewed correction (editors and owners).</p>
        <section id="project-activity" aria-labelledby="activity-title">
          <h2 id="activity-title">Recent project activity</h2>
          <ol id="activity-list" aria-live="polite"></ol>
        </section>
        <section id="project-search" aria-labelledby="search-title">
          <h2 id="search-title">Search project</h2>
          <p>Search the current human-visible transcriptions, document titles, or tags.</p>
          <form id="search-form" class="controls">
            <label>Field
              <select id="search-field">
                <option value="text">Transcription</option>
                <option value="title">Document title</option>
                <option value="tag">Tag</option>
              </select>
            </label>
            <label>Query <input id="search-query" maxlength="200" required></label>
            <button id="search-submit" type="submit">Search</button>
          </form>
          <ol id="search-results" aria-live="polite"></ol>
        </section>
        <section id="membership" class="hidden" aria-labelledby="membership-title">
          <h2 id="membership-title">Project members</h2>
          <form id="member-form">
            <label>Account <select id="member-account" required></select></label>
            <label>Role
              <select id="member-role">
                <option value="VIEWER">Viewer</option>
                <option value="EDITOR">Editor</option>
                <option value="OWNER">Owner</option>
              </select>
            </label>
            <button id="save-member" type="submit">Save project role</button>
          </form>
          <ul id="member-list" aria-live="polite"></ul>
        </section>
        <section id="artifacts" aria-labelledby="artifacts-title">
          <h2 id="artifacts-title">Attached models and datasets</h2>
          <p>Metadata is shown for provenance. Artifact files are never served to the browser.</p>
          <ul id="artifact-list" aria-live="polite"></ul>
          <form id="artifact-form" class="hidden">
            <label>Attach registered artifact
              <select id="artifact-select" required></select>
            </label>
            <button id="save-artifact" type="submit">Attach artifact</button>
          </form>
        </section>
        <section id="recognition-suggestions" aria-labelledby="suggestions-title">
          <h2 id="suggestions-title">Recognition suggestions</h2>
          <p>Copy a local model suggestion into the editor, then review and save it as a
            human correction.</p>
          <div id="suggestions" aria-live="polite"></div>
        </section>
        <section id="recognition-evaluation" aria-labelledby="evaluation-title">
          <h2 id="evaluation-title">Recognition evaluation</h2>
          <p>These metrics compare local suggestions with saved human corrections only.</p>
          <ol id="evaluation-list" aria-live="polite"></ol>
        </section>
        <section id="layout-editor" aria-labelledby="layout-title">
          <h2 id="layout-title">Layout</h2>
          <h3>Line geometry</h3>
          <label>Line polygon (JSON)
            <textarea id="line-polygon" disabled></textarea>
          </label>
          <label>Line baseline (JSON or null)
            <textarea id="line-baseline" disabled></textarea>
          </label>
          <div class="actions">
            <button id="save-line-geometry" type="button" disabled>Save line outline</button>
          </div>
          <h3>Region geometry</h3>
          <label>Region <select id="region"></select></label>
          <label>Region polygon (JSON)
            <textarea id="region-polygon" disabled></textarea>
          </label>
          <div class="actions">
            <button id="save-region" type="button" disabled>Save region outline</button>
          </div>
          <h3>Reading order</h3>
          <ol id="reading-order" aria-label="Region reading order"></ol>
          <div class="actions">
            <button id="save-reading-order" type="button" disabled>Save reading order</button>
          </div>
        </section>
      </aside>
    </div>
  </section>
</main>
<script>
"use strict";

const state = {
  token: null, account: null, projects: [], project: null, documents: [], page: null,
  layout: null, selected: null, selectedRegion: null, drag: null, imageUrl: null,
  activity: [], evaluations: [], members: [], accounts: [], artifacts: [], attachableArtifacts: [],
  searchResults: [], searchTruncated: false, krakenRecognitionEnabled: false
};
const login = document.getElementById("login");
const workspace = document.getElementById("workspace");
const loginForm = document.getElementById("login-form");
const username = document.getElementById("username");
const password = document.getElementById("password");
const loginStatus = document.getElementById("login-status");
const identity = document.getElementById("identity");
const status = document.getElementById("status");
const projectSelect = document.getElementById("project");
const documentSelect = document.getElementById("document");
const pageSelect = document.getElementById("page");
const pageDetail = document.getElementById("page-detail");
const image = document.getElementById("image");
const overlay = document.getElementById("overlay");
const lineList = document.getElementById("line-list");
const activityList = document.getElementById("activity-list");
const searchForm = document.getElementById("search-form");
const searchField = document.getElementById("search-field");
const searchQuery = document.getElementById("search-query");
const searchSubmit = document.getElementById("search-submit");
const searchResults = document.getElementById("search-results");
const evaluationList = document.getElementById("evaluation-list");
const membership = document.getElementById("membership");
const memberForm = document.getElementById("member-form");
const memberAccount = document.getElementById("member-account");
const memberRole = document.getElementById("member-role");
const memberList = document.getElementById("member-list");
const artifactList = document.getElementById("artifact-list");
const artifactForm = document.getElementById("artifact-form");
const artifactSelect = document.getElementById("artifact-select");
const saveArtifact = document.getElementById("save-artifact");
const saveMember = document.getElementById("save-member");
const detail = document.getElementById("detail");
const suggestions = document.getElementById("suggestions");
const text = document.getElementById("text");
const save = document.getElementById("save");
const undo = document.getElementById("undo");
const role = document.getElementById("role");
const regionSelect = document.getElementById("region");
const polygon = document.getElementById("region-polygon");
const saveRegion = document.getElementById("save-region");
const readingOrder = document.getElementById("reading-order");
const saveReadingOrder = document.getElementById("save-reading-order");
const downloadPagexml = document.getElementById("download-pagexml");
const downloadTranscript = document.getElementById("download-transcript");
const downloadTranscriptionsCsv = document.getElementById("download-transcriptions-csv");
const linePolygon = document.getElementById("line-polygon");
const lineBaseline = document.getElementById("line-baseline");
const saveLineGeometry = document.getElementById("save-line-geometry");
const runKraken = document.getElementById("run-kraken");

function setExportDisabled(disabled) {
  [downloadPagexml, downloadTranscript, downloadTranscriptionsCsv].forEach(
    control => { control.disabled = disabled; }
  );
}
function setStatus(message) { status.textContent = message; }
function apiHeaders(extra) {
  const headers = Object.assign({}, extra || {});
  if (state.token) headers.Authorization = "Bearer " + state.token;
  return headers;
}
async function api(path, options) {
  const response = await fetch(path, Object.assign({}, options || {}, { headers: apiHeaders(
    (options && options.headers) || {}
  ) }));
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.message || "Local request failed");
  return payload;
}
function option(select, value, label) {
  const item = document.createElement("option");
  item.value = value;
  item.textContent = label;
  select.append(item);
}
function currentDocument() {
  return state.documents.find(item => item.manifest_sha256 === documentSelect.value);
}
function selectedLine() {
  return state.page && state.page.lines.find(item => item.source_span_id === state.selected);
}
function selectedRegion() {
  return state.layout && state.layout.regions.find(item => item.region_id === state.selectedRegion);
}
function selectedLineGeometry() {
  return state.layout && state.layout.lines &&
    state.layout.lines.find(item => item.source_span_id === state.selected);
}
function canEdit() {
  return state.project && (state.project.role === "EDITOR" || state.project.role === "OWNER");
}
function isOwner() {
  return state.project && state.project.role === "OWNER";
}
function updateRecognitionControl() {
  const available = state.krakenRecognitionEnabled && canEdit() && currentDocument();
  runKraken.disabled = !available;
  runKraken.title = state.krakenRecognitionEnabled
    ? (canEdit() ? "Queue recognition for the selected document." :
      "Only editors and owners can queue local recognition.")
    : "Local recognition is not configured for this service.";
}
function renderLines() {
  lineList.replaceChildren();
  if (!state.page) return;
  state.page.lines.forEach(line => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "line" + (line.source_span_id === state.selected ? " selected" : "");
    button.textContent = line.line_id + " · revision " + line.revision + " · " + (line.text || "∅");
    button.addEventListener("click", () => selectLine(line.source_span_id));
    lineList.append(button);
  });
}
function renderActivity() {
  activityList.replaceChildren();
  if (!state.activity.length) {
    const note = document.createElement("li");
    note.textContent = "No human revision activity for this document yet.";
    activityList.append(note);
    return;
  }
  const names = {
    TRANSCRIPTION: "transcription",
    LINE_GEOMETRY: "line outline",
    REGION_GEOMETRY: "region outline",
    READING_ORDER: "reading order"
  };
  state.activity.forEach(event => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "activity";
    const scope = event.line_id
      ? "line " + event.line_id
      : (event.region_id
        ? "region " + event.region_id
        : "page " + (Number(event.page_index) + 1));
    button.textContent = event.created_at + " · " + event.editor + " · " +
      (names[event.kind] || event.kind) + " · " + scope +
      " · revision " + event.revision;
    button.addEventListener("click", async () => {
      if (String(event.page_index) !== pageSelect.value) {
        pageSelect.value = String(event.page_index);
        try {
          await loadPage();
        } catch (error) {
          setStatus(error.message);
          return;
        }
      }
      if (event.source_span_id) selectLine(event.source_span_id);
    });
    item.append(button);
    activityList.append(item);
  });
}

function renderSearchResults() {
  searchResults.replaceChildren();
  if (!state.searchResults.length) {
    const note = document.createElement("li");
    note.textContent = "No current search results.";
    searchResults.append(note);
    return;
  }
  state.searchResults.forEach(result => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "search-result";
    button.textContent = result.title + " · page " + (Number(result.page_index) + 1) +
      " · " + result.line_id + " · " + (result.text || "∅");
    button.addEventListener("click", () => {
      openSearchResult(result).catch(error => setStatus(error.message));
    });
    item.append(button);
    searchResults.append(item);
  });
  if (state.searchTruncated) {
    const note = document.createElement("li");
    note.textContent = "Showing the first 50 matches. Refine the query to narrow it.";
    searchResults.append(note);
  }
}
async function runProjectSearch(event) {
  event.preventDefault();
  const query = searchQuery.value.trim();
  if (!state.project || !query) {
    setStatus("Enter a search query.");
    return;
  }
  searchSubmit.disabled = true;
  try {
    const payload = await api(
      "/api/projects/" + encodeURIComponent(state.project.project_id) + "/search",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, field: searchField.value })
      }
    );
    state.searchResults = payload.results;
    state.searchTruncated = payload.truncated;
    renderSearchResults();
    setStatus(payload.result_count + " search result" +
      (payload.result_count === 1 ? "." : "s."));
  } catch (error) {
    setStatus(error.message);
  } finally {
    searchSubmit.disabled = false;
  }
}
async function openSearchResult(result) {
  if (!state.project) return;
  if (documentSelect.value !== result.manifest_sha256) {
    documentSelect.value = result.manifest_sha256;
    await loadDocument();
  }
  if (pageSelect.value !== String(result.page_index)) {
    pageSelect.value = String(result.page_index);
    await loadPage();
  }
  selectLine(result.source_span_id);
  setStatus("Opened search result.");
}

function renderEvaluations() {
  evaluationList.replaceChildren();
  if (!state.evaluations.length) {
    const note = document.createElement("li");
    note.textContent = "No local recognition results are ready to evaluate.";
    evaluationList.append(note);
    return;
  }
  state.evaluations.forEach(evaluation => {
    const item = document.createElement("li");
    const summary = document.createElement("span");
    const fingerprint = evaluation.runtime_fingerprint
      ? " · " + evaluation.runtime_fingerprint.slice(0, 12)
      : "";
    if (evaluation.status === "NO_EVALUABLE_HUMAN_REVISIONS") {
      summary.textContent = evaluation.engine + fingerprint +
        " · no saved human corrections are available yet.";
    } else {
      const cer = evaluation.character_error_rate === null
        ? "CER unavailable"
        : "CER " + (evaluation.character_error_rate * 100).toFixed(2) + "%";
      const wer = evaluation.word_error_rate === null
        ? "WER unavailable"
        : "WER " + (evaluation.word_error_rate * 100).toFixed(2) + "%";
      summary.textContent = evaluation.engine + fingerprint + " · " + cer + " · " + wer +
        " · " + evaluation.evaluated_line_count + " reviewed line(s)";
    }
    const receipt = document.createElement("button");
    receipt.type = "button";
    receipt.className = "secondary";
    receipt.textContent = "Download evaluation receipt";
    receipt.addEventListener("click", () => downloadEvaluationReceipt(evaluation, receipt));
    item.append(summary, receipt);
    evaluationList.append(item);
  });
}
async function downloadEvaluationReceipt(evaluation, control) {
  const doc = currentDocument();
  if (!doc || !state.project) return;
  control.disabled = true;
  try {
    const response = await fetch(
      "/api/projects/" + encodeURIComponent(state.project.project_id) +
      "/documents/" + encodeURIComponent(doc.manifest_sha256) + "/evaluations/" +
      encodeURIComponent(evaluation.result_pagexml_sha256) + "/receipt",
      { headers: apiHeaders() }
    );
    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.message || "Could not export evaluation receipt");
    }
    const objectUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = "aktreader-evaluation-receipt.json";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    setStatus("Evaluation receipt downloaded.");
  } catch (error) {
    setStatus(error.message);
  } finally {
    control.disabled = false;
  }
}

function renderMembership() {
  membership.classList.toggle("hidden", !isOwner());
  memberList.replaceChildren();
  memberAccount.replaceChildren();
  if (!isOwner()) return;
  state.accounts
    .filter(account => account.username !== state.account.username)
    .forEach(account => option(memberAccount, account.username, account.username));
  state.members.forEach(member => {
    const item = document.createElement("li");
    item.className = "member";
    item.textContent = member.username + " · " + member.role + " · granted " +
      member.granted_at;
    memberList.append(item);
  });
  saveMember.disabled = !memberAccount.value;
}
async function loadMembership() {
  if (!isOwner()) {
    state.members = [];
    state.accounts = [];
    renderMembership();
    return;
  }
  const base = "/api/projects/" + encodeURIComponent(state.project.project_id);
  const responses = await Promise.all([api(base + "/members"), api(base + "/accounts")]);
  state.members = responses[0].members;
  state.accounts = responses[1].accounts;
  renderMembership();
}

function renderArtifacts() {
  artifactList.replaceChildren();
  if (!state.artifacts.length) {
    const note = document.createElement("li");
    note.textContent = "No model or dataset artifacts are attached to this project.";
    artifactList.append(note);
  } else {
    state.artifacts.forEach(artifact => {
      const item = document.createElement("li");
      item.textContent = artifact.kind + " · " + artifact.name + " · " +
        artifact.license_id + " · SHA-256 " + artifact.sha256.slice(0, 12);
      artifactList.append(item);
    });
  }
  artifactForm.classList.toggle("hidden", !isOwner());
  artifactSelect.replaceChildren();
  if (!isOwner()) return;
  state.attachableArtifacts.forEach(artifact => option(
    artifactSelect,
    artifact.artifact_id,
    artifact.kind + " · " + artifact.name + " · " + artifact.sha256.slice(0, 12)
  ));
  saveArtifact.disabled = !artifactSelect.value;
}
async function loadArtifacts() {
  if (!state.project) {
    state.artifacts = [];
    state.attachableArtifacts = [];
    renderArtifacts();
    return;
  }
  const base = "/api/projects/" + encodeURIComponent(state.project.project_id);
  const attached = await api(base + "/artifacts");
  state.artifacts = attached.artifacts;
  if (isOwner()) {
    const available = await api(base + "/available-artifacts");
    state.attachableArtifacts = available.artifacts;
  } else {
    state.attachableArtifacts = [];
  }
  renderArtifacts();
}
async function attachArtifact(event) {
  event.preventDefault();
  if (!isOwner() || !artifactSelect.value) return;
  saveArtifact.disabled = true;
  try {
    const payload = await api(
      "/api/projects/" + encodeURIComponent(state.project.project_id) + "/artifacts",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ artifact_id: artifactSelect.value })
      }
    );
    await loadArtifacts();
    setStatus(payload.artifact.name + " is now attached to this project.");
  } catch (error) {
    setStatus(error.message);
  } finally {
    saveArtifact.disabled = !artifactSelect.value;
  }
}

function renderSuggestions() {
  suggestions.replaceChildren();
  const line = selectedLine();
  if (!line) return;
  const proposals = Array.isArray(line.suggestions) ? line.suggestions : [];
  if (!proposals.length) {
    const note = document.createElement("p");
    note.textContent = "No local recognition suggestions for this line.";
    suggestions.append(note);
    return;
  }
  proposals.forEach(suggestion => {
    const card = document.createElement("article");
    card.className = "suggestion";
    const provenance = document.createElement("p");
    const engine = String(suggestion.engine || "Local recognition");
    const fingerprint = suggestion.runtime_fingerprint
      ? " · " + String(suggestion.runtime_fingerprint).slice(0, 12)
      : "";
    provenance.textContent = engine + fingerprint;
    const proposedText = document.createElement("pre");
    proposedText.textContent = suggestion.text || "∅";
    const apply = document.createElement("button");
    apply.type = "button";
    apply.textContent = "Use suggestion";
    apply.disabled = !canEdit();
    apply.title = canEdit()
      ? "Copy this proposal into the editor. Save separately to create a human revision."
      : "Only editors and owners can copy a recognition suggestion into the editor.";
    apply.addEventListener("click", () => {
      text.value = suggestion.text || "";
      text.focus();
      setStatus("Suggestion copied into the editor. Review it before saving.");
    });
    card.append(provenance, proposedText, apply);
    suggestions.append(card);
  });
}
function drawOverlay() {
  overlay.replaceChildren();
  if (!state.page) return;
  overlay.setAttribute("viewBox", "0 0 " + state.page.width_px + " " + state.page.height_px);
  const selectedRegionItem = selectedRegion();
  const selectedLineItem = selectedLineGeometry();
  if (state.layout) {
    state.layout.regions.forEach(region => {
      const shape = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
      shape.setAttribute("points", region.polygon.map(point => point.join(",")).join(" "));
      shape.setAttribute("class", "region-shape" + (
        region.region_id === state.selectedRegion ? " selected" : ""
      ));
      shape.addEventListener("click", () => selectRegion(region.region_id));
      overlay.append(shape);
    });
    state.layout.lines.forEach(line => {
      const tag = line.polygon.length < 3 ? "polyline" : "polygon";
      const shape = document.createElementNS("http://www.w3.org/2000/svg", tag);
      shape.setAttribute("points", line.polygon.map(point => point.join(",")).join(" "));
      shape.setAttribute("class", "line-shape" + (
        line.source_span_id === state.selected ? " selected" : ""
      ));
      shape.addEventListener("click", () => selectLine(line.source_span_id));
      overlay.append(shape);
      if (line.baseline) {
        const baseline = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
        baseline.setAttribute("points", line.baseline.map(point => point.join(",")).join(" "));
        baseline.setAttribute("class", "line-baseline");
        overlay.append(baseline);
      }
    });
  }
  if (selectedRegionItem) {
    selectedRegionItem.polygon.forEach((point, index) => {
      const vertex = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      vertex.setAttribute("cx", point[0]);
      vertex.setAttribute("cy", point[1]);
      vertex.setAttribute("r", "4");
      vertex.setAttribute("class", "vertex");
      if (canEdit()) {
        vertex.addEventListener("pointerdown", event => {
          event.preventDefault();
          state.drag = {
            kind: "region", regionId: selectedRegionItem.region_id, pointIndex: index
          };
          overlay.setPointerCapture(event.pointerId);
        });
      }
      overlay.append(vertex);
    });
  }
  if (selectedLineItem) {
    selectedLineItem.polygon.forEach((point, index) => {
      const vertex = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      vertex.setAttribute("cx", point[0]);
      vertex.setAttribute("cy", point[1]);
      vertex.setAttribute("r", "3.5");
      vertex.setAttribute("class", "line-vertex");
      if (canEdit()) {
        vertex.addEventListener("pointerdown", event => {
          event.preventDefault();
          state.drag = {
            kind: "line", sourceSpanId: selectedLineItem.source_span_id, pointIndex: index
          };
          overlay.setPointerCapture(event.pointerId);
        });
      }
      overlay.append(vertex);
    });
  }
}
function selectLine(sourceSpanId) {
  state.selected = sourceSpanId;
  const line = selectedLine();
  const geometry = selectedLineGeometry();
  text.disabled = !line || !canEdit();
  save.disabled = !line || !canEdit();
  undo.disabled = !line || !canEdit() || line.revision === 0;
  undo.title = !line || line.revision === 0
    ? "There is no human correction to undo."
    : (canEdit()
      ? "Append a new revision with the text before the latest correction."
      : "Only editors and owners can undo a correction.");
  text.value = line ? (line.text || "") : "";
  linePolygon.value = geometry ? JSON.stringify(geometry.polygon) : "";
  lineBaseline.value = geometry ? JSON.stringify(geometry.baseline) : "";
  linePolygon.disabled = !geometry || !canEdit();
  lineBaseline.disabled = !geometry || !canEdit();
  saveLineGeometry.disabled = !geometry || !canEdit();
  detail.textContent = line ? (
    "Line: " + line.line_id + "\\nCurrent text revision: " + line.revision +
    (geometry ? "\\nCurrent geometry revision: " + geometry.revision : "") +
    (canEdit() ? "" : "\\nYour VIEWER role can inspect but not save corrections.")
  ) : "Choose a line to review its transcription.";
  renderSuggestions();
  renderLines();
  drawOverlay();
}
function selectAdjacentLine(offset) {
  if (!state.page || !state.page.lines.length) return;
  const index = state.page.lines.findIndex(line => line.source_span_id === state.selected);
  const targetIndex = Math.max(0, Math.min(state.page.lines.length - 1, index + offset));
  selectLine(state.page.lines[targetIndex].source_span_id);
}
function renderReadingOrder() {
  readingOrder.replaceChildren();
  if (!state.layout) return;
  state.layout.reading_order.region_ids.forEach((regionId, index) => {
    const item = document.createElement("li");
    item.className = "order-row";
    const name = document.createElement("span");
    name.textContent = (index + 1) + ". " + regionId;
    item.append(name);
    for (const direction of [-1, 1]) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = direction < 0 ? "Up" : "Down";
      button.disabled = !canEdit() || index + direction < 0 ||
        index + direction >= state.layout.reading_order.region_ids.length;
      button.addEventListener("click", () => moveRegion(regionId, direction));
      item.append(button);
    }
    readingOrder.append(item);
  });
  saveReadingOrder.disabled = !canEdit() || !state.layout;
}
function renderLayout() {
  regionSelect.replaceChildren();
  if (!state.layout) return;
  state.layout.regions.forEach(region => option(
    regionSelect, region.region_id, region.region_id + " · revision " + region.revision
  ));
  if (!state.layout.regions.some(region => region.region_id === state.selectedRegion)) {
    state.selectedRegion = state.layout.regions.length ? state.layout.regions[0].region_id : null;
  }
  selectRegion(state.selectedRegion);
}
function selectRegion(regionId) {
  state.selectedRegion = regionId;
  if (regionId) regionSelect.value = regionId;
  const region = selectedRegion();
  polygon.value = region ? JSON.stringify(region.polygon) : "";
  polygon.disabled = !region || !canEdit();
  saveRegion.disabled = !region || !canEdit();
  renderReadingOrder();
  drawOverlay();
}
function moveRegion(regionId, direction) {
  if (!state.layout || !canEdit()) return;
  const regionIds = state.layout.reading_order.region_ids;
  const index = regionIds.indexOf(regionId);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= regionIds.length) return;
  [regionIds[index], regionIds[target]] = [regionIds[target], regionIds[index]];
  renderReadingOrder();
}
function pagePoint(event) {
  const matrix = overlay.getScreenCTM();
  if (!matrix || !state.page) return null;
  const point = overlay.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  const local = point.matrixTransform(matrix.inverse());
  return [
    Math.max(0, Math.min(state.page.width_px, Math.round(local.x))),
    Math.max(0, Math.min(state.page.height_px, Math.round(local.y)))
  ];
}
async function saveLineGeometryRevision() {
  const line = selectedLineGeometry();
  const doc = currentDocument();
  if (!line || !doc || !canEdit()) return;
  let revisedPolygon;
  let revisedBaseline;
  try {
    revisedPolygon = JSON.parse(linePolygon.value);
    revisedBaseline = JSON.parse(lineBaseline.value);
  } catch (error) {
    setStatus("Line geometry must use valid JSON.");
    return;
  }
  saveLineGeometry.disabled = true;
  try {
    const payload = await api(
      "/api/projects/" + encodeURIComponent(state.project.project_id) + "/line-geometry",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          manifest_sha256: doc.manifest_sha256,
          source_span_id: line.source_span_id,
          polygon: revisedPolygon,
          baseline: revisedBaseline,
          expected_revision: line.revision
        })
      }
    );
    setStatus(payload.status === "SAVED" ? "Line outline saved." : "No change was needed.");
    await loadPage();
  } catch (error) {
    setStatus(error.message);
    await loadPage();
  } finally {
    saveLineGeometry.disabled = !canEdit();
  }
}

async function saveRegionRevision() {
  const region = selectedRegion();
  const doc = currentDocument();
  if (!region || !doc || !canEdit()) return;
  let revisedPolygon;
  try {
    revisedPolygon = JSON.parse(polygon.value);
  } catch (error) {
    setStatus("Region polygon must be valid JSON.");
    return;
  }
  saveRegion.disabled = true;
  try {
    const payload = await api(
      "/api/projects/" + encodeURIComponent(state.project.project_id) + "/region-geometry",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          manifest_sha256: doc.manifest_sha256,
          page_index: Number(pageSelect.value),
          region_id: region.region_id,
          polygon: revisedPolygon,
          expected_revision: region.revision
        })
      }
    );
    setStatus(payload.status === "SAVED" ? "Region outline saved." : "No change was needed.");
    await loadPage();
  } catch (error) {
    setStatus(error.message);
    await loadPage();
  } finally {
    saveRegion.disabled = !canEdit();
  }
}
async function saveReadingOrderRevision() {
  const doc = currentDocument();
  if (!state.layout || !doc || !canEdit()) return;
  saveReadingOrder.disabled = true;
  try {
    const payload = await api(
      "/api/projects/" + encodeURIComponent(state.project.project_id) + "/reading-order",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          manifest_sha256: doc.manifest_sha256,
          page_index: Number(pageSelect.value),
          region_ids: state.layout.reading_order.region_ids,
          expected_revision: state.layout.reading_order.revision
        })
      }
    );
    setStatus(payload.status === "SAVED" ? "Reading order saved." : "No change was needed.");
    await loadPage();
  } catch (error) {
    setStatus(error.message);
    await loadPage();
  } finally {
    saveReadingOrder.disabled = !canEdit();
  }
}
async function loadImage() {
  const doc = currentDocument();
  const response = await fetch(
    "/api/projects/" + encodeURIComponent(state.project.project_id) +
    "/documents/" + encodeURIComponent(doc.manifest_sha256) +
    "/pages/" + encodeURIComponent(pageSelect.value) + "/image",
    { headers: apiHeaders() }
  );
  if (!response.ok) {
    const payload = await response.json();
    throw new Error(payload.message || "Could not load the local page image");
  }
  const blob = await response.blob();
  if (state.imageUrl) URL.revokeObjectURL(state.imageUrl);
  state.imageUrl = URL.createObjectURL(blob);
  image.src = state.imageUrl;
}
async function loadPage() {
  const doc = currentDocument();
  if (!doc || pageSelect.value === "") return;
  setStatus("Loading page…");
  setExportDisabled(true);
  const pagePath = "/api/projects/" + encodeURIComponent(state.project.project_id) +
    "/documents/" + encodeURIComponent(doc.manifest_sha256) +
    "/pages/" + encodeURIComponent(pageSelect.value);
  const responses = await Promise.all([
    api(pagePath),
    api(pagePath + "/layout"),
    api(
      "/api/projects/" + encodeURIComponent(state.project.project_id) +
      "/documents/" + encodeURIComponent(doc.manifest_sha256) + "/activity"
    ),
    api(
      "/api/projects/" + encodeURIComponent(state.project.project_id) +
      "/documents/" + encodeURIComponent(doc.manifest_sha256) + "/evaluations"
    )
  ]);
  state.page = responses[0].page;
  state.layout = responses[1].layout;
  state.activity = responses[2].activity.events;
  state.evaluations = responses[3].evaluations;
  state.selected = state.page.lines.length ? state.page.lines[0].source_span_id : null;
  state.selectedRegion = state.layout.regions.length ? state.layout.regions[0].region_id : null;
  pageDetail.textContent = "Page " + (Number(pageSelect.value) + 1) + " · " +
    state.page.page_id + " · " + state.page.lines.length + " lines · " +
    state.layout.regions.length + " regions";
  renderLayout();
  renderActivity();
  renderEvaluations();
  await loadImage();
  selectLine(state.selected);
  setExportDisabled(false);
  updateRecognitionControl();
  setStatus("");
}
async function loadDocument() {
  pageSelect.replaceChildren();
  const doc = currentDocument();
  if (!doc) return;
  for (let index = 0; index < doc.page_count; index += 1) {
    option(pageSelect, String(index), "Page " + (index + 1) + " of " + doc.page_count);
  }
  await loadPage();
}
async function loadProjects() {
  const payload = await api("/api/projects");
  state.projects = payload.projects;
  projectSelect.replaceChildren();
  state.projects.forEach(project => option(
    projectSelect, project.project_id, project.name + " (" + project.role + ")"
  ));
  if (!state.projects.length) {
    setStatus("No projects are assigned to this account.");
    return;
  }
  await loadProject();
}
async function loadProject() {
  state.project = state.projects.find(item => item.project_id === projectSelect.value);
  state.searchResults = [];
  state.searchTruncated = false;
  renderSearchResults();
  role.textContent = state.project ? "Role: " + state.project.role : "";
  documentSelect.replaceChildren();
  const payload = await api(
    "/api/projects/" + encodeURIComponent(state.project.project_id) + "/documents"
  );
  state.documents = payload.documents;
  state.documents.forEach((document, index) => option(
    documentSelect, document.manifest_sha256,
    (index + 1) + ". " + document.title + " (" + document.page_count + " pages)"
  ));
  if (!state.documents.length) {
    state.page = null;
    state.layout = null;
    state.activity = [];
    state.evaluations = [];
    state.members = [];
    state.accounts = [];
    state.artifacts = [];
    state.attachableArtifacts = [];
    renderActivity();
    renderEvaluations();
    renderMembership();
    renderArtifacts();
    setExportDisabled(true);
    updateRecognitionControl();
    lineList.replaceChildren();
    await Promise.all([loadMembership(), loadArtifacts()]);
    setStatus("This project has no imported PAGE XML documents.");
    return;
  }
  await Promise.all([loadDocument(), loadMembership(), loadArtifacts()]);
}
async function saveMemberRole(event) {
  event.preventDefault();
  if (!isOwner() || !memberAccount.value) return;
  saveMember.disabled = true;
  try {
    const payload = await api(
      "/api/projects/" + encodeURIComponent(state.project.project_id) + "/members",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: memberAccount.value,
          role: memberRole.value
        })
      }
    );
    await loadMembership();
    setStatus(payload.username + " is now a " + payload.role + " on this project.");
  } catch (error) {
    setStatus(error.message);
  } finally {
    saveMember.disabled = !isOwner() || !memberAccount.value;
  }
}
async function queueKrakenRecognition() {
  const doc = currentDocument();
  if (!doc || !state.project || !canEdit() || !state.krakenRecognitionEnabled) return;
  runKraken.disabled = true;
  try {
    const queued = await api(
      "/api/projects/" + encodeURIComponent(state.project.project_id) + "/recognitions/kraken",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ manifest_sha256: doc.manifest_sha256 })
      }
    );
    setStatus("Local recognition queued (job " + queued.job_id.slice(0, 8) + ").");
  } catch (error) {
    setStatus(error.message);
  } finally {
    updateRecognitionControl();
  }
}
async function saveRevision() {
  const line = selectedLine();
  const doc = currentDocument();
  if (!line || !doc || !canEdit()) return;
  save.disabled = true;
  try {
    const payload = await api(
      "/api/projects/" + encodeURIComponent(state.project.project_id) + "/transcriptions",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          manifest_sha256: doc.manifest_sha256,
          source_span_id: line.source_span_id,
          text: text.value,
          expected_revision: line.revision
        })
      }
    );
    setStatus(payload.status === "SAVED" ? "Correction saved." : "No change was needed.");
    await loadPage();
  } catch (error) {
    setStatus(error.message);
    await loadPage();
  } finally {
    save.disabled = !canEdit();
  }
}
async function undoRevision() {
  const line = selectedLine();
  const doc = currentDocument();
  if (!line || !doc || !canEdit() || line.revision === 0) return;
  undo.disabled = true;
  try {
    const payload = await api(
      "/api/projects/" + encodeURIComponent(state.project.project_id) +
      "/transcriptions/undo",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          manifest_sha256: doc.manifest_sha256,
          source_span_id: line.source_span_id,
          expected_revision: line.revision
        })
      }
    );
    await loadPage();
    setStatus(payload.status === "UNDONE"
      ? "Latest correction undone as a new revision."
      : "No human correction is available to undo.");
  } catch (error) {
    setStatus(error.message);
    await loadPage();
  } finally {
    const current = selectedLine();
    undo.disabled = !current || !canEdit() || current.revision === 0;
  }
}
loginForm.addEventListener("submit", async event => {
  event.preventDefault();
  loginStatus.textContent = "Signing in…";
  try {
    const payload = await api("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: username.value, password: password.value })
    });
    state.token = payload.access_token;
    state.account = payload.account;
    password.value = "";
    identity.textContent = "Signed in as " + state.account.username;
    login.classList.add("hidden");
    workspace.classList.remove("hidden");
    const health = await api("/api/healthz");
    state.krakenRecognitionEnabled = health.kraken_recognition_enabled === true;
    await loadProjects();
    loginStatus.textContent = "";
  } catch (error) {
    loginStatus.textContent = error.message;
  }
});
projectSelect.addEventListener(
  "change", () => loadProject().catch(error => setStatus(error.message))
);
documentSelect.addEventListener(
  "change", () => loadDocument().catch(error => setStatus(error.message))
);
pageSelect.addEventListener("change", () => loadPage().catch(error => setStatus(error.message)));
memberForm.addEventListener("submit", event => saveMemberRole(event));
artifactForm.addEventListener("submit", event => attachArtifact(event));
searchForm.addEventListener("submit", event => runProjectSearch(event));
document.addEventListener("keydown", event => {
  if (event.defaultPrevented) return;
  if (
    (event.ctrlKey || event.metaKey) &&
    event.key === "Enter" &&
    event.target === text &&
    !save.disabled
  ) {
    event.preventDefault();
    saveRevision();
    return;
  }
  const target = event.target;
  const tagName = target && target.tagName;
  if (
    event.altKey ||
    event.ctrlKey ||
    event.metaKey ||
    tagName === "INPUT" ||
    tagName === "TEXTAREA" ||
    tagName === "SELECT" ||
    (target && target.isContentEditable)
  ) {
    return;
  }
  const key = event.key.toLowerCase();
  const offset = key === "j" || event.key === "ArrowDown"
    ? 1
    : (key === "k" || event.key === "ArrowUp" ? -1 : 0);
  if (!offset) return;
  event.preventDefault();
  selectAdjacentLine(offset);
});
save.addEventListener("click", () => saveRevision());
undo.addEventListener("click", () => undoRevision());
saveLineGeometry.addEventListener("click", () => saveLineGeometryRevision());
regionSelect.addEventListener("change", () => selectRegion(regionSelect.value));
saveRegion.addEventListener("click", () => saveRegionRevision());
saveReadingOrder.addEventListener("click", () => saveReadingOrderRevision());
runKraken.addEventListener("click", () => queueKrakenRecognition());
async function downloadDocumentExport(exportName, filename, successMessage, control) {
  const doc = currentDocument();
  if (!doc || !state.project) return;
  control.disabled = true;
  try {
    const response = await fetch(
      "/api/projects/" + encodeURIComponent(state.project.project_id) +
      "/documents/" + encodeURIComponent(doc.manifest_sha256) + "/export/" + exportName,
      { headers: apiHeaders() }
    );
    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.message || "Could not export document");
    }
    const objectUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    setStatus(successMessage);
  } catch (error) {
    setStatus(error.message);
  } finally {
    control.disabled = !currentDocument();
  }
}
downloadPagexml.addEventListener(
  "click",
  () => downloadDocumentExport(
    "pagexml", "aktreader-export.page.xml", "PAGE XML export downloaded.", downloadPagexml
  )
);
downloadTranscript.addEventListener(
  "click",
  () => downloadDocumentExport(
    "transcript", "aktreader-export.txt", "Transcript export downloaded.", downloadTranscript
  )
);
downloadTranscriptionsCsv.addEventListener(
  "click",
  () => downloadDocumentExport(
    "transcriptions-csv", "aktreader-export-lines.csv", "CSV export downloaded.",
    downloadTranscriptionsCsv
  )
);
overlay.addEventListener("pointermove", event => {
  if (!state.drag || !state.layout) return;
  const point = pagePoint(event);
  if (!point) return;
  if (state.drag.kind === "region") {
    const region = state.layout.regions.find(item => item.region_id === state.drag.regionId);
    if (!region) return;
    region.polygon[state.drag.pointIndex] = point;
    polygon.value = JSON.stringify(region.polygon);
  } else if (state.drag.kind === "line") {
    const line = state.layout.lines.find(item => item.source_span_id === state.drag.sourceSpanId);
    if (!line) return;
    line.polygon[state.drag.pointIndex] = point;
    linePolygon.value = JSON.stringify(line.polygon);
  } else {
    return;
  }
  drawOverlay();
});
overlay.addEventListener("pointerup", () => { state.drag = null; });
overlay.addEventListener("pointercancel", () => { state.drag = null; });
document.getElementById("logout").addEventListener("click", () => {
  state.token = null;
  state.account = null;
  state.projects = [];
  state.project = null;
  state.documents = [];
  state.page = null;
  state.layout = null;
  state.activity = [];
  state.evaluations = [];
  state.members = [];
  state.accounts = [];
  state.artifacts = [];
  state.attachableArtifacts = [];
  renderMembership();
  renderArtifacts();
  renderEvaluations();
  state.selectedRegion = null;
  state.drag = null;
  state.krakenRecognitionEnabled = false;
  setExportDisabled(true);
  updateRecognitionControl();
  if (state.imageUrl) URL.revokeObjectURL(state.imageUrl);
  state.imageUrl = null;
  image.removeAttribute("src");
  workspace.classList.add("hidden");
  login.classList.remove("hidden");
  username.focus();
});
</script>
</body>
</html>
"""


def create_self_hosted_service_server(
    service_workspace: Path | str,
    *,
    host: str = LOOPBACK_HOST,
    port: int = 8780,
    kraken: LocalKraken | None = None,
) -> SelfHostedServiceServer:
    """Create a loopback server or an explicit container listener without serving yet."""

    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ServiceError("port must be an integer from 0 to 65535")
    if kraken is not None and not isinstance(kraken, LocalKraken):
        raise ServiceError("kraken runner must be a LocalKraken instance")
    return SelfHostedServiceServer(
        service_workspace,
        host=host,
        port=port,
        kraken=kraken,
    )
