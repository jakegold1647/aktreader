"""Tests for the loopback-only service workspace and durable local backup jobs."""

from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

from aktreader.project import create_project, inspect_project
from aktreader.service import (
    LOOPBACK_HOST,
    add_project_to_service,
    create_project_backup,
    create_self_hosted_service_server,
    create_service_workspace,
    get_service_job,
    inspect_service_workspace,
    list_service_projects,
    restore_project_backup,
    verify_project_backup,
)


def _managed_project(tmp_path: Path) -> tuple[Path, Path, str]:
    project = tmp_path / "register.aktproj"
    created = create_project(project, name="Serock civil register")
    workspace = tmp_path / "service"
    create_service_workspace(workspace)
    added = add_project_to_service(workspace, project)
    return workspace, project, str(added["project"]["project_id"])


def test_service_workspace_owns_a_copy_of_each_project(tmp_path: Path) -> None:
    workspace, project, project_id = _managed_project(tmp_path)

    report = inspect_service_workspace(workspace)
    projects = list_service_projects(workspace)

    assert report["status"] == "READY"
    assert report["project_count"] == 1
    assert report["network_required"] is False
    assert projects == [
        {
            "project_id": project_id,
            "name": "Serock civil register",
            "object_count": 0,
            "document_count": 0,
            "page_count": 0,
            "line_count": 0,
        }
    ]
    managed = workspace / "projects" / f"{project_id}.aktproj"
    assert managed.is_dir()
    assert managed.resolve() != project.resolve()


def test_project_backup_is_deterministic_verified_and_restorable(tmp_path: Path) -> None:
    workspace, _, project_id = _managed_project(tmp_path)

    first = create_project_backup(workspace, project_id)
    second = create_project_backup(workspace, project_id)
    backup = Path(str(first["backup_path"]))
    verified = verify_project_backup(backup)
    restored_path = tmp_path / "restored.aktproj"
    restored = restore_project_backup(backup, restored_path)

    assert first["backup_id"] == second["backup_id"]
    assert first["file_count"] == second["file_count"]
    assert verified["backup_id"] == first["backup_id"]
    assert restored["project_id"] == project_id
    assert inspect_project(restored_path)["project_id"] == project_id


def test_loopback_service_queues_and_completes_a_backup_job(tmp_path: Path) -> None:
    workspace, _, project_id = _managed_project(tmp_path)
    server = create_self_hosted_service_server(workspace, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection(LOOPBACK_HOST, server.server_address[1], timeout=5)
    try:
        connection.request("GET", "/api/healthz")
        health_response = connection.getresponse()
        health = json.loads(health_response.read())
        assert health_response.status == 200
        assert health["status"] == "READY"
        assert health["network_required"] is False

        payload = json.dumps({"kind": "PROJECT_BACKUP", "project_id": project_id})
        connection.request(
            "POST",
            "/api/jobs",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        queued_response = connection.getresponse()
        queued = json.loads(queued_response.read())
        assert queued_response.status == 202
        assert queued["status"] == "QUEUED"

        job = get_service_job(workspace, str(queued["job_id"]))
        for _ in range(100):
            job = get_service_job(workspace, str(queued["job_id"]))
            if job["status"] in {"SUCCEEDED", "FAILED"}:
                break
            time.sleep(0.02)

        assert job["status"] == "SUCCEEDED"
        assert job["result"]["project_id"] == project_id

        connection.request("GET", f"/api/jobs/{queued['job_id']}")
        job_response = connection.getresponse()
        public_job = json.loads(job_response.read())
        assert job_response.status == 200
        assert public_job["status"] == "SUCCEEDED"
        assert public_job["result"]["backup_id"] == job["result"]["backup_id"]
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
