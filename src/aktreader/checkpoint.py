"""Transactional SQLite checkpoints for long-running local inference."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class JobStatus(str, Enum):
    """Every durable state in the local batch state machine."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PRIVACY_REFUSED = "PRIVACY_REFUSED"


_RETRYABLE = {JobStatus.PENDING, JobStatus.FAILED, JobStatus.INTERRUPTED}
_BLOCKED = {JobStatus.REVIEW_REQUIRED, JobStatus.PRIVACY_REFUSED}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class JobSnapshot:
    """A durable job row exposed without leaking a SQLite connection."""

    job_id: str
    fingerprint: str
    scan_path: str
    output_path: str
    job_json: str
    status: JobStatus
    retry_count: int
    error: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True)
class Progress:
    """Exact state totals from one checkpoint database."""

    total: int
    pending: int
    running: int
    succeeded: int
    failed: int
    interrupted: int
    review_required: int
    privacy_refused: int

    @property
    def accounted(self) -> int:
        """Return the sum of all mutually exclusive status counts."""
        return (
            self.pending
            + self.running
            + self.succeeded
            + self.failed
            + self.interrupted
            + self.review_required
            + self.privacy_refused
        )

    def as_dict(self) -> dict[str, int]:
        """Return stable JSON-ready progress keys."""
        return {
            "total": self.total,
            "pending": self.pending,
            "running": self.running,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "interrupted": self.interrupted,
            "review_required": self.review_required,
            "privacy_refused": self.privacy_refused,
        }


class CheckpointStore:
    """One crash-safe SQLite database for one batch run.

    A database is intentionally single-run and single-runner. SQLite serializes every
    transition with ``BEGIN IMMEDIATE``; callers should not execute the same run from two
    processes concurrently.
    """

    SCHEMA_VERSION = "1"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        statuses = ", ".join(f"'{status.value}'" for status in JobStatus)
        with self._transaction() as connection:
            connection.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS checkpoint_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    scan_path TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    job_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ({statuses})),
                    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );

                CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status);
                """
            )
            row = connection.execute(
                "SELECT value FROM checkpoint_meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO checkpoint_meta(key, value) VALUES ('schema_version', ?)",
                    (self.SCHEMA_VERSION,),
                )
            elif row["value"] != self.SCHEMA_VERSION:
                raise RuntimeError(
                    f"checkpoint schema {row['value']!r} is not supported "
                    f"(expected {self.SCHEMA_VERSION!r})"
                )

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> JobSnapshot:
        return JobSnapshot(
            job_id=row["job_id"],
            fingerprint=row["fingerprint"],
            scan_path=row["scan_path"],
            output_path=row["output_path"],
            job_json=row["job_json"],
            status=JobStatus(row["status"]),
            retry_count=row["retry_count"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    def upsert_job(
        self,
        *,
        job_id: str,
        fingerprint: str,
        scan_path: str,
        output_path: str,
        job_json: str,
    ) -> JobSnapshot:
        """Register a job, resetting it only when its fingerprint changed."""
        if not job_id:
            raise ValueError("job_id must not be empty")
        if not fingerprint:
            raise ValueError("fingerprint must not be empty")

        now = _utc_now()
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO jobs(
                        job_id, fingerprint, scan_path, output_path, job_json, status,
                        retry_count, error, created_at, updated_at, started_at, finished_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, NULL, NULL)
                    """,
                    (
                        job_id,
                        fingerprint,
                        scan_path,
                        output_path,
                        job_json,
                        JobStatus.PENDING.value,
                        now,
                        now,
                    ),
                )
            elif row["fingerprint"] != fingerprint:
                connection.execute(
                    """
                    UPDATE jobs
                    SET fingerprint = ?, scan_path = ?, output_path = ?, job_json = ?,
                        status = ?, retry_count = 0, error = NULL, updated_at = ?,
                        started_at = NULL, finished_at = NULL
                    WHERE job_id = ?
                    """,
                    (
                        fingerprint,
                        scan_path,
                        output_path,
                        job_json,
                        JobStatus.PENDING.value,
                        now,
                        job_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE jobs
                    SET scan_path = ?, output_path = ?, job_json = ?
                    WHERE job_id = ?
                    """,
                    (scan_path, output_path, job_json, job_id),
                )
            updated = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if updated is None:  # pragma: no cover - protected by the transaction
            raise RuntimeError(f"job {job_id!r} vanished during registration")
        return self._snapshot(updated)

    def get_job(self, job_id: str) -> JobSnapshot:
        """Return one job or raise ``KeyError``."""
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._snapshot(row)

    def list_jobs(self) -> list[JobSnapshot]:
        """Return all jobs in stable ID order."""
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY job_id").fetchall()
        return [self._snapshot(row) for row in rows]

    def reset_stale_running(self) -> int:
        """Turn crash-left RUNNING rows into resumable INTERRUPTED rows."""
        now = _utc_now()
        reason = "previous process stopped while this job was RUNNING"
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, error = ?, updated_at = ?, finished_at = ?
                WHERE status = ?
                """,
                (
                    JobStatus.INTERRUPTED.value,
                    reason,
                    now,
                    now,
                    JobStatus.RUNNING.value,
                ),
            )
            return cursor.rowcount

    def claim_job(self, job_id: str, fingerprint: str, *, max_retries: int) -> bool:
        """Atomically transition an eligible job to RUNNING.

        The first PENDING attempt has retry count zero. Claiming a FAILED or
        INTERRUPTED job increments the audit count. ``max_retries`` limits actual
        failures; deliberate or crash-caused interruptions remain resumable.
        """
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")

        now = _utc_now()
        with self._transaction() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["fingerprint"] != fingerprint:
                return False

            status = JobStatus(row["status"])
            if status not in _RETRYABLE:
                return False
            retry_count = row["retry_count"]
            if status is JobStatus.FAILED:
                if retry_count >= max_retries:
                    return False
                retry_count += 1
            elif status is JobStatus.INTERRUPTED:
                retry_count += 1

            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, retry_count = ?, error = NULL, updated_at = ?,
                    started_at = ?, finished_at = NULL
                WHERE job_id = ? AND fingerprint = ? AND status = ?
                """,
                (
                    JobStatus.RUNNING.value,
                    retry_count,
                    now,
                    now,
                    job_id,
                    fingerprint,
                    status.value,
                ),
            )
            return cursor.rowcount == 1

    def finish_running(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
    ) -> None:
        """Finish a RUNNING job in a durable terminal or resumable state."""
        if status not in {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.INTERRUPTED,
            JobStatus.REVIEW_REQUIRED,
            JobStatus.PRIVACY_REFUSED,
        }:
            raise ValueError(f"cannot finish a RUNNING job as {status.value}")
        if status is JobStatus.SUCCEEDED and error is not None:
            raise ValueError("a SUCCEEDED job cannot carry an error")

        now = _utc_now()
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, error = ?, updated_at = ?, finished_at = ?
                WHERE job_id = ? AND status = ?
                """,
                (
                    status.value,
                    error,
                    now,
                    now,
                    job_id,
                    JobStatus.RUNNING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"job {job_id!r} is not RUNNING")

    def block_job(self, job_id: str, status: JobStatus, *, reason: str) -> bool:
        """Move a non-running, non-successful job to a fail-closed state."""
        if status not in _BLOCKED:
            raise ValueError("block_job requires REVIEW_REQUIRED or PRIVACY_REFUSED")
        now = _utc_now()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT status FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            current = JobStatus(row["status"])
            if current in {JobStatus.SUCCEEDED, JobStatus.RUNNING}:
                return False
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, error = ?, updated_at = ?, finished_at = ?
                WHERE job_id = ?
                """,
                (status.value, reason, now, now, job_id),
            )
            return True

    def requeue_blocked(self, job_id: str) -> bool:
        """Requeue a formerly blocked job after current preflight allows it."""
        now = _utc_now()
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, error = NULL, updated_at = ?, finished_at = NULL
                WHERE job_id IN (
                    SELECT job_id FROM jobs
                    WHERE job_id = ? AND status IN (?, ?)
                )
                """,
                (
                    JobStatus.PENDING.value,
                    now,
                    job_id,
                    JobStatus.REVIEW_REQUIRED.value,
                    JobStatus.PRIVACY_REFUSED.value,
                ),
            )
            return cursor.rowcount == 1

    def requeue_invalid_success(self, job_id: str, *, reason: str) -> bool:
        """Requeue a success whose promised output is missing or no longer valid JSON."""
        now = _utc_now()
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, error = ?, updated_at = ?, started_at = NULL,
                    finished_at = NULL
                WHERE job_id = ? AND status = ?
                """,
                (
                    JobStatus.PENDING.value,
                    reason,
                    now,
                    job_id,
                    JobStatus.SUCCEEDED.value,
                ),
            )
            return cursor.rowcount == 1

    def progress(self) -> Progress:
        """Read exact totals using one SQLite snapshot."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
            ).fetchall()
        counts = {JobStatus(row["status"]): row["count"] for row in rows}
        progress = Progress(
            total=sum(counts.values()),
            pending=counts.get(JobStatus.PENDING, 0),
            running=counts.get(JobStatus.RUNNING, 0),
            succeeded=counts.get(JobStatus.SUCCEEDED, 0),
            failed=counts.get(JobStatus.FAILED, 0),
            interrupted=counts.get(JobStatus.INTERRUPTED, 0),
            review_required=counts.get(JobStatus.REVIEW_REQUIRED, 0),
            privacy_refused=counts.get(JobStatus.PRIVACY_REFUSED, 0),
        )
        if progress.accounted != progress.total:  # pragma: no cover - database CHECK protects this
            raise RuntimeError("checkpoint progress totals do not balance")
        return progress
