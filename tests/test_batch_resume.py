import json
import sqlite3
from pathlib import Path

import pytest

from aktreader.batch import (
    BatchJob,
    BatchRunner,
    InferenceIdentity,
    discover_folder_jobs,
    load_manifest_jobs,
)
from aktreader.checkpoint import JobStatus


def _jobs(tmp_path: Path) -> list[BatchJob]:
    scans = tmp_path / "scans"
    outputs = tmp_path / "outputs"
    scans.mkdir()
    jobs = []
    for name in ("a", "b", "c"):
        scan = scans / f"{name}.jpg"
        scan.write_bytes(f"scan-{name}".encode())
        jobs.append(
            BatchJob(
                job_id=name,
                scan_path=scan,
                output_path=outputs / f"{name}.json",
                act_type="birth",
                act_year=1900,
                target={"kind": "whole_scan"},
            )
        )
    return jobs


def test_interrupt_then_resume_skips_matching_success(tmp_path: Path) -> None:
    jobs = _jobs(tmp_path)
    calls: list[str] = []
    interrupted = False

    def first_reader(job: BatchJob) -> dict[str, str]:
        nonlocal interrupted
        calls.append(job.job_id)
        if job.job_id == "b" and not interrupted:
            interrupted = True
            raise KeyboardInterrupt("test stop")
        return {"job_id": job.job_id}

    checkpoint = tmp_path / "run.sqlite3"
    identity = InferenceIdentity("model", "prompt", "schema", {"temperature": 0})
    first = BatchRunner(
        jobs=jobs,
        reader=first_reader,
        identity=identity,
        checkpoint_path=checkpoint,
        as_of_year=2026,
    )

    with pytest.raises(KeyboardInterrupt):
        first.run()
    assert first.store.get_job("a").status is JobStatus.SUCCEEDED
    assert first.store.get_job("b").status is JobStatus.INTERRUPTED
    assert first.store.get_job("c").status is JobStatus.PENDING

    resumed_calls: list[str] = []

    def resumed_reader(job: BatchJob) -> dict[str, str]:
        resumed_calls.append(job.job_id)
        return {"job_id": job.job_id}

    resumed = BatchRunner(
        jobs=jobs,
        reader=resumed_reader,
        identity=identity,
        checkpoint_path=checkpoint,
        as_of_year=2026,
    )
    progress = resumed.run()

    assert calls == ["a", "b"]
    assert resumed_calls == ["b", "c"]
    assert progress.total == progress.accounted == 3
    assert progress.succeeded == 3
    assert resumed.store.get_job("b").retry_count == 1
    for job in jobs:
        assert json.loads(job.output_path.read_text(encoding="utf-8")) == {"job_id": job.job_id}


def test_changed_prompt_fingerprint_reruns_prior_success(tmp_path: Path) -> None:
    jobs = _jobs(tmp_path)[:1]
    checkpoint = tmp_path / "run.sqlite3"
    calls: list[str] = []

    def reader(job: BatchJob) -> dict[str, int | str]:
        calls.append(job.job_id)
        return {"job_id": job.job_id, "pass": len(calls)}

    BatchRunner(
        jobs=jobs,
        reader=reader,
        identity=InferenceIdentity("model", "prompt-1", "schema", {}),
        checkpoint_path=checkpoint,
        as_of_year=2026,
    ).run()
    BatchRunner(
        jobs=jobs,
        reader=reader,
        identity=InferenceIdentity("model", "prompt-1", "schema", {}),
        checkpoint_path=checkpoint,
        as_of_year=2026,
    ).run()
    BatchRunner(
        jobs=jobs,
        reader=reader,
        identity=InferenceIdentity("model", "prompt-2", "schema", {}),
        checkpoint_path=checkpoint,
        as_of_year=2026,
    ).run()

    assert calls == ["a", "a"]
    assert json.loads(jobs[0].output_path.read_text(encoding="utf-8"))["pass"] == 2


@pytest.mark.parametrize("damage", ["missing", "invalid"])
def test_matching_success_reruns_when_output_is_not_valid_json_object(
    tmp_path: Path, damage: str
) -> None:
    jobs = _jobs(tmp_path)[:1]
    checkpoint = tmp_path / "run.sqlite3"
    identity = InferenceIdentity("model", "prompt", "schema", {})
    calls: list[str] = []

    def reader(job: BatchJob) -> dict[str, int | str]:
        calls.append(job.job_id)
        return {"job_id": job.job_id, "pass": len(calls)}

    BatchRunner(
        jobs=jobs,
        reader=reader,
        identity=identity,
        checkpoint_path=checkpoint,
        as_of_year=2026,
    ).run()
    if damage == "missing":
        jobs[0].output_path.unlink()
    else:
        jobs[0].output_path.write_text("not json", encoding="utf-8")

    resumed = BatchRunner(
        jobs=jobs,
        reader=reader,
        identity=identity,
        checkpoint_path=checkpoint,
        as_of_year=2026,
    )
    progress = resumed.run()

    assert calls == ["a", "a"]
    assert progress.succeeded == 1
    assert json.loads(jobs[0].output_path.read_text(encoding="utf-8"))["pass"] == 2


def test_matching_success_reruns_when_valid_json_output_changed(tmp_path: Path) -> None:
    jobs = _jobs(tmp_path)[:1]
    checkpoint = tmp_path / "run.sqlite3"
    identity = InferenceIdentity("model", "prompt", "schema", {})
    calls: list[str] = []

    def reader(job: BatchJob) -> dict[str, int | str]:
        calls.append(job.job_id)
        return {"job_id": job.job_id, "pass": len(calls)}

    BatchRunner(
        jobs=jobs,
        reader=reader,
        identity=identity,
        checkpoint_path=checkpoint,
        as_of_year=2026,
    ).run()
    jobs[0].output_path.write_text('{"job_id":"a","pass":99}\n', encoding="utf-8")

    progress = BatchRunner(
        jobs=jobs,
        reader=reader,
        identity=identity,
        checkpoint_path=checkpoint,
        as_of_year=2026,
    ).run()

    assert calls == ["a", "a"]
    assert progress.succeeded == 1
    assert json.loads(jobs[0].output_path.read_text(encoding="utf-8"))["pass"] == 2


def test_matching_success_without_recorded_output_digest_reruns(tmp_path: Path) -> None:
    jobs = _jobs(tmp_path)[:1]
    checkpoint = tmp_path / "run.sqlite3"
    identity = InferenceIdentity("model", "prompt", "schema", {})
    calls: list[str] = []

    def reader(job: BatchJob) -> dict[str, int | str]:
        calls.append(job.job_id)
        return {"job_id": job.job_id, "pass": len(calls)}

    BatchRunner(
        jobs=jobs,
        reader=reader,
        identity=identity,
        checkpoint_path=checkpoint,
        as_of_year=2026,
    ).run()
    with sqlite3.connect(checkpoint) as connection:
        connection.execute("UPDATE jobs SET output_sha256 = NULL WHERE job_id = 'a'")

    resumed = BatchRunner(
        jobs=jobs,
        reader=reader,
        identity=identity,
        checkpoint_path=checkpoint,
        as_of_year=2026,
    )
    progress = resumed.run()

    assert calls == ["a", "a"]
    assert progress.succeeded == 1
    assert resumed.store.get_job("a").output_sha256 is not None


def test_discovery_and_manifest_fail_closed_on_unknown_or_multi_act_targets(
    tmp_path: Path,
) -> None:
    scan_dir = tmp_path / "scans"
    scan_dir.mkdir()
    (scan_dir / "page.jpg").write_bytes(b"page")
    discovered = discover_folder_jobs(
        scan_dir,
        tmp_path / "discovered-output",
        act_type="death",
        act_year=1900,
    )
    called: list[str] = []

    runner = BatchRunner(
        jobs=discovered,
        reader=lambda job: called.append(job.job_id) or {"unexpected": True},
        identity=InferenceIdentity("model", "prompt", "schema", {}),
        checkpoint_path=tmp_path / "discovered.sqlite3",
        as_of_year=2026,
    )
    progress = runner.run()
    assert progress.review_required == 1
    assert called == []

    manifest = tmp_path / "jobs.json"
    manifest.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "explicit",
                        "scan": "scans/page.jpg",
                        "act_type": "death",
                        "year": 1900,
                        "target": {"kind": "act", "act_no": 7},
                    },
                    {
                        "id": "multi",
                        "scan": "scans/page.jpg",
                        "act_type": "death",
                        "year": 1900,
                        "targets": [
                            {"kind": "act", "act_no": 7},
                            {"kind": "act", "act_no": 8},
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest_jobs = load_manifest_jobs(manifest, output_root=tmp_path / "manifest-output")
    manifest_calls: list[str] = []
    manifest_runner = BatchRunner(
        jobs=manifest_jobs,
        reader=lambda job: manifest_calls.append(job.job_id) or {"job_id": job.job_id},
        identity=InferenceIdentity("model", "prompt", "schema", {}),
        checkpoint_path=tmp_path / "manifest.sqlite3",
        as_of_year=2026,
    )
    manifest_progress = manifest_runner.run()

    assert manifest_calls == ["explicit"]
    assert manifest_progress.succeeded == 1
    assert manifest_progress.review_required == 1


def test_unknown_year_is_privacy_refused_without_calling_reader(tmp_path: Path) -> None:
    scan = tmp_path / "scan.jpg"
    scan.write_bytes(b"scan")
    job = BatchJob(
        "unknown-year",
        scan,
        tmp_path / "result.json",
        "birth",
        None,
        {"kind": "whole_scan"},
    )
    calls: list[str] = []
    runner = BatchRunner(
        jobs=[job],
        reader=lambda item: calls.append(item.job_id) or {},
        identity=InferenceIdentity("model", "prompt", "schema", {}),
        checkpoint_path=tmp_path / "privacy.sqlite3",
        as_of_year=2026,
    )

    progress = runner.run()
    assert calls == []
    assert progress.privacy_refused == 1
    assert not job.output_path.exists()


def test_failed_atomic_json_write_preserves_existing_output(tmp_path: Path) -> None:
    scan = tmp_path / "scan.jpg"
    scan.write_bytes(b"scan")
    output = tmp_path / "result.json"
    output.write_text('{"previous": true}\n', encoding="utf-8")
    job = BatchJob(
        "bad-json",
        scan,
        output,
        "death",
        1900,
        {"kind": "whole_scan"},
    )
    runner = BatchRunner(
        jobs=[job],
        reader=lambda item: {"not_json": object()},
        identity=InferenceIdentity("model", "prompt", "schema", {}),
        checkpoint_path=tmp_path / "atomic.sqlite3",
        as_of_year=2026,
    )

    progress = runner.run()
    assert progress.failed == 1
    assert output.read_text(encoding="utf-8") == '{"previous": true}\n'
    assert list(tmp_path.glob(".result.json.*.tmp")) == []
