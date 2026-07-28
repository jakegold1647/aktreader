from pathlib import Path

from aktreader.batch import BatchJob, InferenceIdentity, build_job_fingerprint
from aktreader.checkpoint import CheckpointStore, JobStatus


def _register(
    store: CheckpointStore,
    job: BatchJob,
    fingerprint: str,
) -> None:
    store.upsert_job(
        job_id=job.job_id,
        fingerprint=fingerprint,
        scan_path=str(job.scan_path),
        output_path=str(job.output_path),
        job_json="{}",
    )


def test_matching_success_is_never_claimed_and_changed_fingerprint_resets(tmp_path: Path) -> None:
    scan = tmp_path / "scan.jpg"
    scan.write_bytes(b"scan-v1")
    job = BatchJob(
        "one",
        scan,
        tmp_path / "one.json",
        "birth",
        1900,
        {"kind": "whole_scan"},
    )
    identity = InferenceIdentity("model-a", "prompt-a", "schema-1", {"temperature": 0})
    first = build_job_fingerprint(job, identity)
    store = CheckpointStore(tmp_path / "run.sqlite3")

    _register(store, job, first.value)
    assert store.claim_job("one", first.value, max_retries=2)
    store.finish_running("one", JobStatus.SUCCEEDED)
    _register(store, job, first.value)
    assert not store.claim_job("one", first.value, max_retries=2)
    assert store.get_job("one").status is JobStatus.SUCCEEDED

    changed = build_job_fingerprint(
        job,
        InferenceIdentity("model-a", "prompt-b", "schema-1", {"temperature": 0}),
    )
    _register(store, job, changed.value)
    reset = store.get_job("one")
    assert reset.status is JobStatus.PENDING
    assert reset.retry_count == 0
    assert store.claim_job("one", changed.value, max_retries=2)


def test_scan_crop_target_and_decoding_changes_affect_fingerprint(tmp_path: Path) -> None:
    scan = tmp_path / "scan.jpg"
    scan.write_bytes(b"first")
    base = BatchJob("one", scan, tmp_path / "one.json", "death", 1900, "whole_scan")
    identity = InferenceIdentity("model", "prompt", "schema", {"temperature": 0})
    initial = build_job_fingerprint(base, identity).value

    scan.write_bytes(b"second")
    assert build_job_fingerprint(base, identity).value != initial
    scan.write_bytes(b"first")
    cropped = BatchJob(
        "one",
        scan,
        tmp_path / "one.json",
        "death",
        1900,
        {"kind": "act", "act_no": 4},
        {"x": 0, "y": 0, "width": 20, "height": 20},
    )
    assert build_job_fingerprint(cropped, identity).value != initial
    hotter = InferenceIdentity("model", "prompt", "schema", {"temperature": 0.1})
    assert build_job_fingerprint(base, hotter).value != initial


def test_stale_running_becomes_interrupted_and_progress_balances(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "run.sqlite3")
    job = BatchJob("one", tmp_path / "scan.jpg", tmp_path / "one.json")
    job.scan_path.write_bytes(b"x")
    _register(store, job, "fingerprint")
    assert store.claim_job("one", "fingerprint", max_retries=2)

    assert store.reset_stale_running() == 1
    snapshot = store.get_job("one")
    assert snapshot.status is JobStatus.INTERRUPTED
    assert "previous process stopped" in (snapshot.error or "")
    progress = store.progress()
    assert progress.total == progress.accounted == 1
    assert progress.interrupted == 1
    assert store.claim_job("one", "fingerprint", max_retries=2)
    assert store.get_job("one").retry_count == 1


def test_interruption_remains_resumable_when_failure_retries_are_disabled(
    tmp_path: Path,
) -> None:
    store = CheckpointStore(tmp_path / "run.sqlite3")
    job = BatchJob("one", tmp_path / "scan.jpg", tmp_path / "one.json")
    job.scan_path.write_bytes(b"x")
    _register(store, job, "fingerprint")
    assert store.claim_job("one", "fingerprint", max_retries=0)
    store.finish_running("one", JobStatus.INTERRUPTED, error="planned stop")

    assert store.claim_job("one", "fingerprint", max_retries=0)
    assert store.get_job("one").retry_count == 1
