"""Resumable, interrupt-safe local inference over folders or job manifests."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from aktreader.checkpoint import CheckpointStore, JobSnapshot, JobStatus, Progress
from aktreader.privacy import (
    DEFAULT_PRIVACY_POLICY,
    PrivacyOutcome,
    PrivacyPolicy,
    evaluate_privacy,
)

SUPPORTED_SCAN_SUFFIXES = frozenset({".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"})
_ALLOWED_TARGET_KINDS = frozenset({"act", "crop", "region", "whole_scan"})
_REVIEW_TARGET_KINDS = frozenset({"multi_act", "multiple_acts", "page", "unknown"})


class BatchReader(Protocol):
    """Minimal dependency boundary for a local reader implementation."""

    def __call__(self, job: BatchJob) -> Mapping[str, Any]:
        """Read one explicit act target and return a schema-ready JSON mapping."""


@dataclass(frozen=True)
class BatchJob:
    """One scan/target/output unit with explicit privacy metadata."""

    job_id: str
    scan_path: Path
    output_path: Path
    act_type: str | None = None
    act_year: int | None = None
    target: Any = None
    crop: Any = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("job_id must not be empty")


@dataclass(frozen=True)
class InferenceIdentity:
    """All reader inputs that must invalidate a prior success when changed."""

    model_hash: str
    prompt_hash: str
    schema: str
    decoding_config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (
            ("model_hash", self.model_hash),
            ("prompt_hash", self.prompt_hash),
            ("schema", self.schema),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        _canonical_json(self.decoding_config)


@dataclass(frozen=True)
class JobFingerprint:
    """The digest and scan hash stored for audit and testing."""

    value: str
    scan_sha256: str
    inputs: Mapping[str, Any]


ProgressCallback = Callable[[Progress, JobSnapshot | None], None]


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"value is not canonical JSON data: {error}") from error


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_job_fingerprint(
    job: BatchJob,
    identity: InferenceIdentity,
    *,
    privacy_policy: PrivacyPolicy = DEFAULT_PRIVACY_POLICY,
) -> JobFingerprint:
    """Hash every material scan, target, model, prompt, schema, and decoding input."""
    scan_path = job.scan_path.resolve(strict=True)
    if not scan_path.is_file():
        raise FileNotFoundError(f"scan is not a file: {scan_path}")
    scan_hash = _sha256_file(scan_path)
    inputs = {
        "scan_sha256": scan_hash,
        "crop": job.crop,
        "target": job.target,
        "act_type": job.act_type,
        "act_year": job.act_year,
        "model_hash": identity.model_hash,
        "prompt_hash": identity.prompt_hash,
        "schema": identity.schema,
        "decoding_config": identity.decoding_config,
        "privacy_policy": asdict(privacy_policy),
        "output_path": str(job.output_path.resolve()),
    }
    serialized = _canonical_json(inputs)
    return JobFingerprint(
        value=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        scan_sha256=scan_hash,
        inputs=inputs,
    )


def target_review_reason(job: BatchJob) -> str | None:
    """Return why the scan target cannot safely be inferred, or ``None``."""
    if job.crop is not None:
        try:
            _canonical_json(job.crop)
        except ValueError as error:
            return f"invalid crop: {error}"

    target = job.target
    if target is None:
        if job.crop is not None:
            return None
        return "act target is unknown; a multi-act page must not be guessed"

    if isinstance(target, str):
        kind = target.strip().lower()
    elif isinstance(target, Mapping):
        raw_kind = target.get("kind")
        kind = raw_kind.strip().lower() if isinstance(raw_kind, str) else ""
        try:
            _canonical_json(target)
        except ValueError as error:
            return f"invalid target: {error}"
    else:
        return "act target must be a string or JSON object"

    if kind in _REVIEW_TARGET_KINDS:
        return f"target kind {kind!r} may contain multiple or unknown acts"
    if kind not in _ALLOWED_TARGET_KINDS:
        return f"target kind {kind!r} is not an explicit supported act target"
    return None


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write JSON via a flushed same-directory temporary file and ``os.replace``."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(
                payload,
                stream,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _valid_completed_output(path: Path) -> bool:
    """Accept a checkpointed success only while its output is one readable JSON object."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict)


def discover_folder_jobs(
    scan_dir: Path,
    output_dir: Path,
    *,
    recursive: bool = True,
    act_type: str | None = None,
    act_year: int | None = None,
    target: Any = None,
) -> list[BatchJob]:
    """Discover scans without inferring act metadata from filenames.

    The default ``target=None`` deliberately routes every discovered image to
    REVIEW_REQUIRED. A caller may explicitly assert ``{"kind": "whole_scan"}``
    only when it knows each image contains exactly one target act.
    """
    source_root = Path(scan_dir).resolve(strict=True)
    if not source_root.is_dir():
        raise NotADirectoryError(source_root)
    destination_root = Path(output_dir).resolve()
    candidates = source_root.rglob("*") if recursive else source_root.iterdir()
    scan_paths = sorted(
        (
            path
            for path in candidates
            if path.is_file() and path.suffix.lower() in SUPPORTED_SCAN_SUFFIXES
        ),
        key=lambda path: path.relative_to(source_root).as_posix().casefold(),
    )

    jobs: list[BatchJob] = []
    for scan_path in scan_paths:
        relative = scan_path.relative_to(source_root)
        relative_key = relative.as_posix()
        short_hash = hashlib.sha256(relative_key.encode("utf-8")).hexdigest()[:12]
        job_id = f"folder-{short_hash}"
        jobs.append(
            BatchJob(
                job_id=job_id,
                scan_path=scan_path,
                output_path=destination_root / relative.with_suffix(".json"),
                act_type=act_type,
                act_year=act_year,
                target=target,
                metadata={"discovered_relative_path": relative_key},
            )
        )
    return jobs


def _manifest_path(raw: Any, *, base: Path, label: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"manifest {label} must be a non-empty path string")
    path = Path(raw)
    return path if path.is_absolute() else base / path


def _manifest_target(item: Mapping[str, Any]) -> Any:
    if item.get("multi_act") is True:
        return {"kind": "multi_act"}
    targets = item.get("targets")
    if targets is not None:
        if not isinstance(targets, list):
            return {"kind": "unknown", "reason": "manifest targets is not a list"}
        if len(targets) != 1:
            return {"kind": "multi_act", "target_count": len(targets)}
        return targets[0]
    return item.get("target")


def load_manifest_jobs(
    manifest_path: Path,
    *,
    output_root: Path | None = None,
) -> list[BatchJob]:
    """Load explicit jobs from a JSON manifest without filename inference."""
    source = Path(manifest_path).resolve(strict=True)
    payload = json.loads(source.read_text(encoding="utf-8"))
    raw_jobs = payload.get("jobs") if isinstance(payload, dict) else payload
    if not isinstance(raw_jobs, list):
        raise ValueError("manifest must be a JSON list or an object with a jobs list")

    output_base = Path(output_root).resolve() if output_root is not None else source.parent
    jobs: list[BatchJob] = []
    seen_ids: set[str] = set()
    seen_outputs: set[Path] = set()
    for index, raw_item in enumerate(raw_jobs):
        if not isinstance(raw_item, dict):
            raise ValueError(f"manifest jobs[{index}] must be an object")

        scan_path = _manifest_path(raw_item.get("scan"), base=source.parent, label="scan").resolve()
        if not scan_path.is_file():
            raise FileNotFoundError(f"manifest scan does not exist: {scan_path}")
        target = _manifest_target(raw_item)

        raw_id = raw_item.get("id")
        if raw_id is None:
            id_material = _canonical_json(
                {"scan": str(scan_path), "target": target, "index": index}
            )
            job_id = f"manifest-{hashlib.sha256(id_material.encode('utf-8')).hexdigest()[:12]}"
        elif isinstance(raw_id, str) and raw_id.strip():
            job_id = raw_id.strip()
        else:
            raise ValueError(f"manifest jobs[{index}].id must be a non-empty string")
        if job_id in seen_ids:
            raise ValueError(f"duplicate manifest job id: {job_id}")
        seen_ids.add(job_id)

        raw_output = raw_item.get("output")
        if raw_output is None:
            output_path = output_base / f"{job_id}.json"
        else:
            output_path = _manifest_path(raw_output, base=output_base, label="output")
        output_path = output_path.resolve()
        if output_path in seen_outputs:
            raise ValueError(f"duplicate manifest output path: {output_path}")
        seen_outputs.add(output_path)

        act_year = raw_item.get("year", raw_item.get("act_year"))
        if act_year is not None and (isinstance(act_year, bool) or not isinstance(act_year, int)):
            raise ValueError(f"manifest jobs[{index}].year must be an integer or null")
        act_type = raw_item.get("act_type")
        if act_type is not None and not isinstance(act_type, str):
            raise ValueError(f"manifest jobs[{index}].act_type must be a string or null")
        crop = raw_item.get("crop")
        metadata = raw_item.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError(f"manifest jobs[{index}].metadata must be an object")

        jobs.append(
            BatchJob(
                job_id=job_id,
                scan_path=scan_path,
                output_path=output_path,
                act_type=act_type,
                act_year=act_year,
                target=target,
                crop=crop,
                metadata=metadata,
            )
        )
    return jobs


class BatchRunner:
    """Run each eligible job once per invocation and resume from SQLite."""

    def __init__(
        self,
        *,
        jobs: Iterable[BatchJob],
        reader: BatchReader,
        identity: InferenceIdentity,
        checkpoint_path: Path,
        privacy_policy: PrivacyPolicy = DEFAULT_PRIVACY_POLICY,
        as_of_year: int | None = None,
        max_retries: int = 2,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.jobs = list(jobs)
        ids = [job.job_id for job in self.jobs]
        if len(ids) != len(set(ids)):
            raise ValueError("batch job IDs must be unique")
        outputs = [job.output_path.resolve() for job in self.jobs]
        if len(outputs) != len(set(outputs)):
            raise ValueError("batch output paths must be unique")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        self.reader = reader
        self.identity = identity
        self.store = CheckpointStore(checkpoint_path)
        self.privacy_policy = privacy_policy
        self.as_of_year = as_of_year
        self.max_retries = max_retries
        self.progress_callback = progress_callback

    def _report(self, job_id: str | None = None) -> Progress:
        progress = self.store.progress()
        if self.progress_callback is not None:
            snapshot = self.store.get_job(job_id) if job_id is not None else None
            self.progress_callback(progress, snapshot)
        return progress

    @staticmethod
    def _job_json(job: BatchJob, fingerprint: JobFingerprint) -> str:
        return _canonical_json(
            {
                "job_id": job.job_id,
                "scan_path": str(job.scan_path.resolve()),
                "output_path": str(job.output_path.resolve()),
                "act_type": job.act_type,
                "act_year": job.act_year,
                "target": job.target,
                "crop": job.crop,
                "metadata": job.metadata,
                "scan_sha256": fingerprint.scan_sha256,
                "fingerprint_inputs": fingerprint.inputs,
            }
        )

    def run(self) -> Progress:
        """Resume the batch, preserving every success and durable failure state."""
        self.store.reset_stale_running()
        prepared: list[tuple[BatchJob, JobFingerprint]] = []
        for job in self.jobs:
            fingerprint = build_job_fingerprint(
                job,
                self.identity,
                privacy_policy=self.privacy_policy,
            )
            self.store.upsert_job(
                job_id=job.job_id,
                fingerprint=fingerprint.value,
                scan_path=str(job.scan_path.resolve()),
                output_path=str(job.output_path.resolve()),
                job_json=self._job_json(job, fingerprint),
            )
            prepared.append((job, fingerprint))
        self._report()

        for job, fingerprint in prepared:
            snapshot = self.store.get_job(job.job_id)
            if (
                snapshot.status is JobStatus.SUCCEEDED
                and snapshot.fingerprint == fingerprint.value
            ):
                if _valid_completed_output(job.output_path):
                    continue
                self.store.requeue_invalid_success(
                    job.job_id,
                    reason="checkpointed success has no readable JSON-object output; rerun",
                )
                self._report(job.job_id)

            review_reason = target_review_reason(job)
            if review_reason is not None:
                if self.store.block_job(
                    job.job_id,
                    JobStatus.REVIEW_REQUIRED,
                    reason=review_reason,
                ):
                    self._report(job.job_id)
                continue

            privacy = evaluate_privacy(
                job.act_type,
                job.act_year,
                policy=self.privacy_policy,
                as_of_year=self.as_of_year,
            )
            if privacy.outcome is not PrivacyOutcome.ALLOW:
                blocked_status = (
                    JobStatus.REVIEW_REQUIRED
                    if privacy.outcome is PrivacyOutcome.REVIEW_REQUIRED
                    else JobStatus.PRIVACY_REFUSED
                )
                if self.store.block_job(job.job_id, blocked_status, reason=privacy.reason):
                    self._report(job.job_id)
                continue

            self.store.requeue_blocked(job.job_id)
            if not self.store.claim_job(
                job.job_id,
                fingerprint.value,
                max_retries=self.max_retries,
            ):
                continue
            self._report(job.job_id)

            try:
                result = self.reader(job)
                if not isinstance(result, Mapping):
                    raise TypeError("local reader must return a JSON object")
                atomic_write_json(job.output_path, result)
            except (KeyboardInterrupt, SystemExit) as error:
                self.store.finish_running(
                    job.job_id,
                    JobStatus.INTERRUPTED,
                    error=f"{type(error).__name__}: {error}",
                )
                self._report(job.job_id)
                raise
            except Exception as error:
                self.store.finish_running(
                    job.job_id,
                    JobStatus.FAILED,
                    error=f"{type(error).__name__}: {error}",
                )
                self._report(job.job_id)
                continue

            self.store.finish_running(job.job_id, JobStatus.SUCCEEDED)
            self._report(job.job_id)

        return self._report()
