"""Tests for the loopback-only service workspace and durable local backup jobs."""

from __future__ import annotations

import json
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from http.client import HTTPConnection
from pathlib import Path

import pytest
from PIL import Image

from aktreader import kraken as kraken_module
import aktreader.service as service_module
from aktreader.kraken import KrakenConfig, LocalKraken
from aktreader.local_reader import PinnedArtifact, sha256_file
from aktreader.project import create_project, import_pagexml_into_project, inspect_project
from aktreader.service import (
    LOOPBACK_HOST,
    ServiceError,
    ServiceJobWorker,
    activate_service_project_model,
    add_project_to_service,
    attach_service_artifact,
    create_local_account,
    create_project_backup,
    create_self_hosted_service_server,
    create_service_session,
    create_service_workspace,
    get_service_job,
    grant_project_role,
    inspect_service_workspace,
    list_authorized_service_projects,
    list_service_project_model_releases,
    list_service_projects,
    queue_project_kraken_recognition,
    queue_service_project_kraken_training,
    register_service_artifact,
    restore_project_backup,
    rollback_service_project_model,
    verify_project_backup,
)


def _managed_project(tmp_path: Path) -> tuple[Path, Path, str]:
    project = tmp_path / "register.aktproj"
    create_project(project, name="Serock civil register")
    workspace = tmp_path / "service"
    create_service_workspace(workspace)
    added = add_project_to_service(workspace, project)
    return workspace, project, str(added["project"]["project_id"])


def _reviewable_service(tmp_path: Path) -> tuple[Path, str, str]:
    source_root = tmp_path / "source"
    source_root.mkdir()
    image_path = source_root / "page.png"
    image = Image.new("L", (20, 20), color=255)
    try:
        image.save(image_path)
    finally:
        image.close()
    pagexml = source_root / "page.xml"
    pagexml.write_text(
        """<PcGts>
  <Page id="page-1" imageFilename="page.png" imageWidth="20" imageHeight="20">
    <TextRegion id="region-1">
      <Coords points="0,0 20,0 20,20 0,20"/>
      <TextLine id="line-1">
        <Coords points="1,1 19,1 19,10 1,10"/>
        <TextEquiv><Unicode>source text</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
    <TextRegion id="region-2">
      <Coords points="0,10 20,10 20,20 0,20"/>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )
    project = tmp_path / "reviewable.aktproj"
    create_project(project, name="Shared register")
    imported = import_pagexml_into_project(project, pagexml, image_root=source_root)
    workspace = tmp_path / "review-service"
    create_service_workspace(workspace)
    create_local_account(
        workspace,
        username="editor",
        password="a sufficiently long local editor password",
    )
    added = add_project_to_service(workspace, project, owner_username="editor")
    return (
        workspace,
        str(added["project"]["project_id"]),
        str(imported["manifest_sha256"]),
    )


def test_service_container_listener_requires_an_explicit_safe_address(tmp_path: Path) -> None:
    workspace, _, _ = _reviewable_service(tmp_path)
    server = create_self_hosted_service_server(
        workspace,
        host="0.0.0.0",
        port=0,
    )
    try:
        assert server.server_address[0] == "0.0.0.0"
    finally:
        server.server_close()

    with pytest.raises(ServiceError, match="host must be"):
        create_self_hosted_service_server(
            workspace,
            host="192.0.2.10",
            port=0,
        )


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


def test_local_accounts_limit_project_visibility_and_create_sessions(
    tmp_path: Path,
) -> None:
    workspace, _, project_id = _managed_project(tmp_path)
    owner = create_local_account(
        workspace,
        username="owner",
        password="a sufficiently long local owner password",
    )
    viewer = create_local_account(
        workspace,
        username="viewer",
        password="a sufficiently long local viewer password",
    )
    grant_project_role(
        workspace,
        project_id=project_id,
        username="owner",
        role="OWNER",
    )

    assert list_authorized_service_projects(
        workspace,
        account_id=str(owner["account_id"]),
    ) == [
        {
            "project_id": project_id,
            "name": "Serock civil register",
            "object_count": 0,
            "document_count": 0,
            "page_count": 0,
            "line_count": 0,
            "role": "OWNER",
        }
    ]
    assert list_authorized_service_projects(
        workspace,
        account_id=str(viewer["account_id"]),
    ) == []

    grant_project_role(
        workspace,
        project_id=project_id,
        username="viewer",
        role="VIEWER",
    )
    session = create_service_session(
        workspace,
        username="owner",
        password="a sufficiently long local owner password",
    )

    assert session["status"] == "AUTHENTICATED"
    assert session["account"]["account_id"] == owner["account_id"]
    assert session["access_token"]


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
    create_local_account(
        workspace,
        username="owner",
        password="a sufficiently long local owner password",
    )
    grant_project_role(
        workspace,
        project_id=project_id,
        username="owner",
        role="OWNER",
    )
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

        connection.request("GET", "/api/projects")
        anonymous_response = connection.getresponse()
        assert anonymous_response.status == 401
        anonymous_response.read()

        session_payload = json.dumps(
            {
                "username": "owner",
                "password": "a sufficiently long local owner password",
            }
        )
        connection.request(
            "POST",
            "/api/session",
            body=session_payload,
            headers={"Content-Type": "application/json"},
        )
        session_response = connection.getresponse()
        session = json.loads(session_response.read())
        assert session_response.status == 201
        authorization = {"Authorization": f"Bearer {session['access_token']}"}

        connection.request("GET", "/api/projects", headers=authorization)
        projects_response = connection.getresponse()
        projects = json.loads(projects_response.read())
        assert projects_response.status == 200
        assert projects["projects"][0]["role"] == "OWNER"

        payload = json.dumps({"kind": "PROJECT_BACKUP", "project_id": project_id})
        connection.request(
            "POST",
            "/api/jobs",
            body=payload,
            headers={"Content-Type": "application/json", **authorization},
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

        connection.request(
            "GET",
            f"/api/jobs/{queued['job_id']}",
            headers=authorization,
        )
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


def test_authenticated_document_review_api_requires_current_revision(tmp_path: Path) -> None:
    workspace, project_id, manifest_sha256 = _reviewable_service(tmp_path)
    server = create_self_hosted_service_server(workspace, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection(LOOPBACK_HOST, server.server_address[1], timeout=5)
    try:
        connection.request("GET", "/")
        workbench_response = connection.getresponse()
        workbench = workbench_response.read().decode("utf-8")
        assert workbench_response.status == 200
        assert "AKT Reader collaborative workbench" in workbench
        assert "Save region outline" in workbench
        assert "Save line outline" in workbench
        assert "Recent project activity" in workbench
        assert "Search project" in workbench
        assert "/search" in workbench
        assert "openSearchResult" in workbench
        assert "/activity" in workbench
        assert "Project members" in workbench
        assert "/members" in workbench
        assert "Undo latest correction" in workbench
        assert "/transcriptions/undo" in workbench
        assert "Save reading order" in workbench
        assert "Download PAGE XML" in workbench
        assert "Attached models and datasets" in workbench
        assert "Attach registered artifact" in workbench
        assert "available-artifacts" in workbench
        assert "Download transcript" in workbench
        assert "Download CSV" in workbench
        assert "transcriptions-csv" in workbench
        assert "Run local recognition" in workbench
        assert "Keyboard: J/↓ next line" in workbench
        assert "selectAdjacentLine" in workbench
        assert "event.target === text" in workbench
        assert "Recognition suggestions" in workbench
        assert "Recognition evaluation" in workbench
        assert "Download evaluation receipt" in workbench
        assert "/evaluations" in workbench
        assert "Use suggestion" in workbench
        assert "Suggestion copied into the editor. Review it before saving." in workbench
        assert "apply.disabled = !canEdit()" in workbench
        assert "/api/healthz" in workbench
        assert "/recognitions/kraken" in workbench
        assert "kraken_config" not in workbench
        assert "Content-Security-Policy" in workbench_response.headers

        image_route = (
            f"/api/projects/{project_id}/documents/{manifest_sha256}/pages/0/image"
        )
        connection.request("GET", image_route)
        anonymous_image_response = connection.getresponse()
        assert anonymous_image_response.status == 401
        anonymous_image_response.read()

        session_payload = json.dumps(
            {
                "username": "editor",
                "password": "a sufficiently long local editor password",
            }
        )
        connection.request(
            "POST",
            "/api/session",
            body=session_payload,
            headers={"Content-Type": "application/json"},
        )
        session_response = connection.getresponse()
        session = json.loads(session_response.read())
        assert session_response.status == 201
        authorization = {"Authorization": f"Bearer {session['access_token']}"}

        connection.request(
            "GET",
            f"/api/projects/{project_id}/documents",
            headers=authorization,
        )
        documents_response = connection.getresponse()
        documents = json.loads(documents_response.read())
        assert documents_response.status == 200
        assert documents["documents"][0]["manifest_sha256"] == manifest_sha256

        connection.request(
            "GET",
            f"/api/projects/{project_id}/documents/{manifest_sha256}/pages/0",
            headers=authorization,
        )
        page_response = connection.getresponse()
        page = json.loads(page_response.read())["page"]
        assert page_response.status == 200
        assert "image_path" not in page
        assert page["lines"][0]["revision"] == 0
        source_span_id = page["lines"][0]["source_span_id"]

        layout_route = (
            f"/api/projects/{project_id}/documents/{manifest_sha256}/pages/0/layout"
        )
        connection.request("GET", layout_route, headers=authorization)
        layout_response = connection.getresponse()
        layout = json.loads(layout_response.read())["layout"]
        assert layout_response.status == 200
        assert layout["reading_order"] == {
            "revision": 0,
            "region_ids": ["region-1", "region-2"],
        }
        assert layout["regions"][0]["revision"] == 0
        assert layout["lines"][0]["source_span_id"] == source_span_id
        assert layout["lines"][0]["revision"] == 0

        line_geometry_payload = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "source_span_id": source_span_id,
                "polygon": [[1, 1], [18, 1], [18, 9], [1, 9]],
                "baseline": None,
                "expected_revision": 0,
            }
        )
        connection.request(
            "POST",
            f"/api/projects/{project_id}/line-geometry",
            body=line_geometry_payload,
            headers={"Content-Type": "application/json", **authorization},
        )
        line_geometry_response = connection.getresponse()
        line_geometry = json.loads(line_geometry_response.read())
        assert line_geometry_response.status == 200
        assert line_geometry["status"] == "SAVED"
        assert line_geometry["revision"] == 1
        assert "project" not in line_geometry

        connection.request("GET", layout_route, headers=authorization)
        revised_layout_response = connection.getresponse()
        revised_layout = json.loads(revised_layout_response.read())["layout"]
        assert revised_layout_response.status == 200
        assert revised_layout["lines"][0] == {
            "source_span_id": source_span_id,
            "line_id": "line-1",
            "polygon": [[1, 1], [18, 1], [18, 9], [1, 9]],
            "baseline": None,
            "revision": 1,
        }

        connection.request(
            "POST",
            f"/api/projects/{project_id}/line-geometry",
            body=line_geometry_payload,
            headers={"Content-Type": "application/json", **authorization},
        )
        line_geometry_conflict_response = connection.getresponse()
        assert line_geometry_conflict_response.status == 409
        assert "conflict" in json.loads(line_geometry_conflict_response.read())["message"]

        region_geometry_payload = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "page_index": 0,
                "region_id": "region-1",
                "polygon": [[0, 0], [19, 0], [19, 19], [0, 19]],
                "expected_revision": 0,
            }
        )
        connection.request(
            "POST",
            f"/api/projects/{project_id}/region-geometry",
            body=region_geometry_payload,
            headers={"Content-Type": "application/json", **authorization},
        )
        region_geometry_response = connection.getresponse()
        region_geometry = json.loads(region_geometry_response.read())
        assert region_geometry_response.status == 200
        assert region_geometry["status"] == "SAVED"
        assert region_geometry["revision"] == 1
        assert "project" not in region_geometry

        connection.request(
            "POST",
            f"/api/projects/{project_id}/region-geometry",
            body=region_geometry_payload,
            headers={"Content-Type": "application/json", **authorization},
        )
        region_geometry_conflict_response = connection.getresponse()
        assert region_geometry_conflict_response.status == 409
        assert "conflict" in json.loads(region_geometry_conflict_response.read())["message"]

        reading_order_payload = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "page_index": 0,
                "region_ids": ["region-2", "region-1"],
                "expected_revision": 0,
            }
        )
        connection.request(
            "POST",
            f"/api/projects/{project_id}/reading-order",
            body=reading_order_payload,
            headers={"Content-Type": "application/json", **authorization},
        )
        reading_order_response = connection.getresponse()
        reading_order = json.loads(reading_order_response.read())
        assert reading_order_response.status == 200
        assert reading_order["status"] == "SAVED"
        assert reading_order["revision"] == 1
        assert "project" not in reading_order

        connection.request(
            "POST",
            f"/api/projects/{project_id}/reading-order",
            body=reading_order_payload,
            headers={"Content-Type": "application/json", **authorization},
        )
        reading_order_conflict_response = connection.getresponse()
        assert reading_order_conflict_response.status == 409
        assert "conflict" in json.loads(reading_order_conflict_response.read())["message"]

        connection.request("GET", image_route, headers=authorization)
        image_response = connection.getresponse()
        image_bytes = image_response.read()
        assert image_response.status == 200
        assert image_response.headers["Content-Type"].startswith("image/png")
        assert image_bytes.startswith(b"\x89PNG")

        revision_payload = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "source_span_id": source_span_id,
                "text": "reviewed text",
                "expected_revision": 0,
            }
        )
        connection.request(
            "POST",
            f"/api/projects/{project_id}/transcriptions",
            body=revision_payload,
            headers={"Content-Type": "application/json", **authorization},
        )
        revision_response = connection.getresponse()
        revision = json.loads(revision_response.read())
        assert revision_response.status == 200
        assert revision["status"] == "SAVED"
        assert revision["revision"] == 1
        assert revision["editor"] == "editor"
        assert "project" not in revision

        search_payload = json.dumps({"query": "reviewed", "field": "text"})
        connection.request(
            "POST",
            f"/api/projects/{project_id}/search",
            body=search_payload,
            headers={"Content-Type": "application/json", **authorization},
        )
        search_response = connection.getresponse()
        search = json.loads(search_response.read())
        assert search_response.status == 200
        assert search["network_required"] is False
        assert search["result_count"] == 1
        assert search["truncated"] is False
        assert search["results"][0]["manifest_sha256"] == manifest_sha256
        assert search["results"][0]["text"] == "reviewed text"
        assert search["results"][0]["revision"] == 1
        assert "project" not in search["results"][0]
        assert "image_path" not in search["results"][0]

        invalid_search_payload = json.dumps({"query": "reviewed", "field": []})
        connection.request(
            "POST",
            f"/api/projects/{project_id}/search",
            body=invalid_search_payload,
            headers={"Content-Type": "application/json", **authorization},
        )
        invalid_search_response = connection.getresponse()
        assert invalid_search_response.status == 400
        assert "search field" in json.loads(invalid_search_response.read())["message"]

        connection.request(
            "POST",
            f"/api/projects/{project_id}/transcriptions",
            body=revision_payload,
            headers={"Content-Type": "application/json", **authorization},
        )
        conflict_response = connection.getresponse()
        conflict = json.loads(conflict_response.read())
        assert conflict_response.status == 409
        assert "conflict" in conflict["message"]

        export_route = (
            f"/api/projects/{project_id}/documents/{manifest_sha256}/export/pagexml"
        )
        connection.request("GET", export_route, headers=authorization)
        export_response = connection.getresponse()
        exported_pagexml = export_response.read()
        assert export_response.status == 200
        assert export_response.headers["Content-Type"].startswith(
            "application/vnd.prima.page+xml"
        )
        assert export_response.headers["Content-Disposition"] == (
            f'attachment; filename="aktreader-{manifest_sha256[:12]}.page.xml"'
        )
        assert b"reviewed text" in exported_pagexml
        assert b'points="0,0 19,0 19,19 0,19"' in exported_pagexml
        exported = ET.fromstring(exported_pagexml)
        exported_order = [
            element.get("regionRef")
            for element in exported.iter()
            if element.tag.rsplit("}", 1)[-1] == "RegionRefIndexed"
        ]
        assert exported_order == ["region-2", "region-1"]

        transcript_route = (
            f"/api/projects/{project_id}/documents/{manifest_sha256}/export/transcript"
        )
        connection.request("GET", transcript_route, headers=authorization)
        transcript_response = connection.getresponse()
        exported_transcript = transcript_response.read()
        assert transcript_response.status == 200
        assert transcript_response.headers["Content-Type"].startswith("text/plain")
        assert transcript_response.headers["Content-Disposition"] == (
            f'attachment; filename="aktreader-{manifest_sha256[:12]}.txt"'
        )
        assert exported_transcript == b"reviewed text\n"

        csv_route = (
            f"/api/projects/{project_id}/documents/{manifest_sha256}/export/transcriptions-csv"
        )
        connection.request("GET", csv_route, headers=authorization)
        csv_response = connection.getresponse()
        exported_csv = csv_response.read()
        assert csv_response.status == 200
        assert csv_response.headers["Content-Type"].startswith("text/csv")
        assert csv_response.headers["Content-Disposition"] == (
            f'attachment; filename="aktreader-{manifest_sha256[:12]}-lines.csv"'
        )
        assert exported_csv.startswith(
            b"manifest_sha256,page_index,page_id,region_id,line_id,source_span_id,"
        )
        assert b"source text,reviewed text,1,editor" in exported_csv

        undo_payload = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "source_span_id": source_span_id,
                "expected_revision": 1,
            }
        )
        connection.request(
            "POST",
            f"/api/projects/{project_id}/transcriptions/undo",
            body=undo_payload,
            headers={"Content-Type": "application/json", **authorization},
        )
        undo_response = connection.getresponse()
        undone = json.loads(undo_response.read())
        assert undo_response.status == 200
        assert undone["status"] == "UNDONE"
        assert undone["revision"] == 2
        assert undone["undone_revision"] == 1
        assert undone["editor"] == "editor"
        assert "project" not in undone

        connection.request(
            "GET",
            f"/api/projects/{project_id}/documents/{manifest_sha256}/pages/0",
            headers=authorization,
        )
        undone_page_response = connection.getresponse()
        undone_page = json.loads(undone_page_response.read())["page"]
        assert undone_page_response.status == 200
        assert undone_page["lines"][0]["text"] == page["lines"][0]["text"]
        assert undone_page["lines"][0]["revision"] == 2

        activity_route = (
            f"/api/projects/{project_id}/documents/{manifest_sha256}/activity"
        )
        connection.request("GET", activity_route, headers=authorization)
        activity_response = connection.getresponse()
        activity = json.loads(activity_response.read())["activity"]
        assert activity_response.status == 200
        assert activity["manifest_sha256"] == manifest_sha256
        assert activity["network_required"] is False
        assert len(activity["events"]) == 5
        assert {event["kind"] for event in activity["events"]} == {
            "TRANSCRIPTION",
            "LINE_GEOMETRY",
            "REGION_GEOMETRY",
            "READING_ORDER",
        }
        assert all("project" not in event for event in activity["events"])
        assert all("prior_text" not in event for event in activity["events"])
        assert all("revised_text" not in event for event in activity["events"])
        assert all(event["editor"] == "editor" for event in activity["events"])

        connection.request(
            "POST",
            f"/api/projects/{project_id}/transcriptions/undo",
            body=undo_payload,
            headers={"Content-Type": "application/json", **authorization},
        )
        stale_undo_response = connection.getresponse()
        assert stale_undo_response.status == 409
        assert "conflict" in json.loads(stale_undo_response.read())["message"]
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_owner_can_manage_existing_project_members(tmp_path: Path) -> None:
    workspace, project_id, manifest_sha256 = _reviewable_service(tmp_path)
    create_local_account(
        workspace,
        username="reviewer",
        password="a sufficiently long local reviewer password",
    )
    with pytest.raises(ServiceError, match="retain at least one owner"):
        grant_project_role(
            workspace,
            project_id=project_id,
            username="editor",
            role="EDITOR",
        )

    server = create_self_hosted_service_server(workspace, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection(LOOPBACK_HOST, server.server_address[1], timeout=5)
    try:
        owner_payload = json.dumps(
            {
                "username": "editor",
                "password": "a sufficiently long local editor password",
            }
        )
        connection.request(
            "POST",
            "/api/session",
            body=owner_payload,
            headers={"Content-Type": "application/json"},
        )
        owner_session = json.loads(connection.getresponse().read())
        owner_headers = {"Authorization": f"Bearer {owner_session['access_token']}"}

        accounts_route = f"/api/projects/{project_id}/accounts"
        connection.request("GET", accounts_route, headers=owner_headers)
        accounts_response = connection.getresponse()
        accounts = json.loads(accounts_response.read())
        assert accounts_response.status == 200
        assert {account["username"] for account in accounts["accounts"]} == {
            "editor",
            "reviewer",
        }
        assert all("password_hash" not in account for account in accounts["accounts"])

        members_route = f"/api/projects/{project_id}/members"
        membership_payload = json.dumps({"username": "reviewer", "role": "EDITOR"})
        connection.request(
            "POST",
            members_route,
            body=membership_payload,
            headers={"Content-Type": "application/json", **owner_headers},
        )
        membership_response = connection.getresponse()
        membership = json.loads(membership_response.read())
        assert membership_response.status == 200
        assert membership["status"] == "GRANTED"
        assert membership["username"] == "reviewer"
        assert membership["role"] == "EDITOR"

        connection.request("GET", members_route, headers=owner_headers)
        members_response = connection.getresponse()
        members = json.loads(members_response.read())["members"]
        assert members_response.status == 200
        assert {(member["username"], member["role"]) for member in members} == {
            ("editor", "OWNER"),
            ("reviewer", "EDITOR"),
        }

        reviewer_payload = json.dumps(
            {
                "username": "reviewer",
                "password": "a sufficiently long local reviewer password",
            }
        )
        connection.request(
            "POST",
            "/api/session",
            body=reviewer_payload,
            headers={"Content-Type": "application/json"},
        )
        reviewer_session = json.loads(connection.getresponse().read())
        reviewer_headers = {"Authorization": f"Bearer {reviewer_session['access_token']}"}

        connection.request("GET", accounts_route, headers=reviewer_headers)
        reviewer_accounts_response = connection.getresponse()
        assert reviewer_accounts_response.status == 403
        reviewer_accounts_response.read()

        connection.request(
            "GET",
            f"/api/projects/{project_id}/documents",
            headers=reviewer_headers,
        )
        reviewer_documents_response = connection.getresponse()
        reviewer_documents = json.loads(reviewer_documents_response.read())
        assert reviewer_documents_response.status == 200
        assert reviewer_documents["documents"][0]["manifest_sha256"] == manifest_sha256
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_owner_can_attach_model_metadata_without_exposing_artifact_paths(
    tmp_path: Path,
) -> None:
    workspace, project_id, _ = _reviewable_service(tmp_path)
    source = tmp_path / "register-model.bin"
    source.write_bytes(b"local model artifact")
    registered = register_service_artifact(
        workspace,
        source,
        kind="MODEL",
        name="Serock baseline",
        license_id="Apache-2.0",
        description="A local test model",
    )
    artifact_id = str(registered["artifact"]["artifact_id"])

    server = create_self_hosted_service_server(workspace, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection(LOOPBACK_HOST, server.server_address[1], timeout=5)
    try:
        session_payload = json.dumps(
            {
                "username": "editor",
                "password": "a sufficiently long local editor password",
            }
        )
        connection.request(
            "POST",
            "/api/session",
            body=session_payload,
            headers={"Content-Type": "application/json"},
        )
        session = json.loads(connection.getresponse().read())
        authorization = {"Authorization": f"Bearer {session['access_token']}"}

        available_route = f"/api/projects/{project_id}/available-artifacts"
        connection.request("GET", available_route, headers=authorization)
        available_response = connection.getresponse()
        available = json.loads(available_response.read())
        assert available_response.status == 200
        assert available["artifacts"] == [registered["artifact"]]

        attachment_payload = json.dumps({"artifact_id": artifact_id})
        connection.request(
            "POST",
            f"/api/projects/{project_id}/artifacts",
            body=attachment_payload,
            headers={"Content-Type": "application/json", **authorization},
        )
        attachment_response = connection.getresponse()
        attachment = json.loads(attachment_response.read())
        assert attachment_response.status == 200
        assert attachment["artifact"]["sha256"] == registered["artifact"]["sha256"]

        connection.request(
            "GET",
            f"/api/projects/{project_id}/artifacts",
            headers=authorization,
        )
        artifacts_response = connection.getresponse()
        artifacts = json.loads(artifacts_response.read())
        assert artifacts_response.status == 200
        assert artifacts["artifacts"] == [registered["artifact"]]
        assert "relative_path" not in artifacts["artifacts"][0]

        connection.request("GET", available_route, headers=authorization)
        attached_available_response = connection.getresponse()
        attached_available = json.loads(attached_available_response.read())
        assert attached_available_response.status == 200
        assert attached_available["artifacts"] == []
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)



def test_service_training_job_snapshots_inputs_and_registers_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, project_id, _ = _reviewable_service(tmp_path)
    config = tmp_path / "training-config.json"
    plan = tmp_path / "corpus-plan.json"
    corpus = tmp_path / "corpus"
    config.write_text('{"source":"original-config"}', encoding="utf-8")
    plan.write_text('{"source":"original-plan"}', encoding="utf-8")
    corpus.mkdir()
    (corpus / "source.txt").write_text("original corpus", encoding="utf-8")
    inspected = {
        "corpus_manifest_sha256": "a" * 64,
        "source_plan_sha256": "b" * 64,
    }
    observed: dict[str, Path] = {}

    class _Config:
        config_sha256 = "c" * 64

    def fake_inspect(plan_path: Path, corpus_path: Path) -> dict[str, object]:
        assert plan_path.is_file()
        assert corpus_path.is_dir()
        return dict(inspected)

    def fake_run(
        config_path: Path,
        plan_path: Path,
        corpus_directory: Path,
        output_directory: Path,
    ) -> dict[str, object]:
        observed["config"] = config_path
        observed["plan"] = plan_path
        observed["corpus"] = corpus_directory
        assert config_path.read_text(encoding="utf-8") == '{"source":"original-config"}'
        assert plan_path.read_text(encoding="utf-8") == '{"source":"original-plan"}'
        assert (corpus_directory / "source.txt").read_text(encoding="utf-8") == "original corpus"
        weights = output_directory / "checkpoints" / "model.safetensors"
        weights.parent.mkdir(parents=True)
        weights.write_bytes(b"trained local weights")
        receipt = {
            "outputs": [
                {
                    "path": "checkpoints/model.safetensors",
                    "sha256": sha256_file(weights),
                    "size_bytes": weights.stat().st_size,
                }
            ]
        }
        (output_directory / "training-run.aktreader.json").write_text(
            json.dumps(receipt),
            encoding="utf-8",
        )
        return {"receipt_sha256": "d" * 64}

    monkeypatch.setattr(
        service_module,
        "load_kraken_training_config",
        lambda _path: _Config(),
    )
    monkeypatch.setattr(service_module, "inspect_consented_training_corpus", fake_inspect)
    monkeypatch.setattr(service_module, "run_kraken_training", fake_run)

    queued = queue_service_project_kraken_training(
        workspace,
        project_id=project_id,
        config_path=config,
        plan_path=plan,
        corpus_directory=corpus,
        model_name="Local Serock training run",
        model_license_id="Apache-2.0",
        model_description="Consent-checked local test output",
    )
    config.write_text('{"source":"mutated-config"}', encoding="utf-8")
    plan.write_text('{"source":"mutated-plan"}', encoding="utf-8")
    (corpus / "source.txt").write_text("mutated corpus", encoding="utf-8")

    worker = ServiceJobWorker(workspace)
    worker.start()
    try:
        for _ in range(100):
            job = get_service_job(workspace, str(queued["job_id"]))
            if job["status"] in {"SUCCEEDED", "FAILED"}:
                break
            time.sleep(0.02)
    finally:
        worker.stop()

    assert job["status"] == "SUCCEEDED"
    assert observed["config"] != config
    assert observed["plan"] != plan
    assert observed["corpus"] != corpus
    assert job["result"]["corpus_manifest_sha256"] == "a" * 64
    assert job["result"]["source_plan_sha256"] == "b" * 64
    assert job["result"]["training_receipt_sha256"] == "d" * 64
    assert job["result"]["registered_models"] == [
        {
            "artifact_id": job["result"]["registered_models"][0]["artifact_id"],
            "kind": "MODEL",
            "name": "Local Serock training run",
            "license_id": "Apache-2.0",
            "description": "Consent-checked local test output",
            "sha256": sha256_file(
                workspace
                / "artifacts"
                / "sha256"
                / job["result"]["registered_models"][0]["sha256"][:2]
                / job["result"]["registered_models"][0]["sha256"]
            ),
            "size_bytes": len(b"trained local weights"),
            "created_at": job["result"]["registered_models"][0]["created_at"],
        }
    ]


def test_service_model_releases_pin_queued_recognition_and_support_rollback(
    tmp_path: Path,
) -> None:
    workspace, project_id, manifest_sha256 = _reviewable_service(tmp_path)
    first_source = tmp_path / "first-model.bin"
    second_source = tmp_path / "second-model.bin"
    first_source.write_bytes(b"first local model")
    second_source.write_bytes(b"second local model")
    first = register_service_artifact(
        workspace,
        first_source,
        kind="MODEL",
        name="Serock model v1",
        license_id="Apache-2.0",
    )
    second = register_service_artifact(
        workspace,
        second_source,
        kind="MODEL",
        name="Serock model v2",
        license_id="Apache-2.0",
    )
    first_artifact_id = str(first["artifact"]["artifact_id"])
    second_artifact_id = str(second["artifact"]["artifact_id"])
    attach_service_artifact(
        workspace,
        project_id=project_id,
        artifact_id=first_artifact_id,
    )
    attach_service_artifact(
        workspace,
        project_id=project_id,
        artifact_id=second_artifact_id,
    )

    first_release = activate_service_project_model(
        workspace,
        project_id=project_id,
        artifact_id=first_artifact_id,
    )
    second_release = activate_service_project_model(
        workspace,
        project_id=project_id,
        artifact_id=second_artifact_id,
    )
    session = create_service_session(
        workspace,
        username="editor",
        password="a sufficiently long local editor password",
    )
    queued = queue_project_kraken_recognition(
        workspace,
        project_id,
        account_id=str(session["account"]["account_id"]),
        manifest_sha256=manifest_sha256,
        kraken=object(),
    )
    stored_job = get_service_job(workspace, str(queued["job_id"]))

    assert queued["model_artifact_id"] == second_artifact_id
    assert stored_job["model_artifact_id"] == second_artifact_id
    assert first_release["active_model"]["artifact"]["artifact_id"] == first_artifact_id
    assert second_release["active_model"]["prior_release_id"] == (
        first_release["active_model"]["release_id"]
    )

    rolled_back = rollback_service_project_model(
        workspace,
        project_id=project_id,
        release_id=str(first_release["active_model"]["release_id"]),
    )
    history = list_service_project_model_releases(workspace, project_id=project_id)

    assert rolled_back["status"] == "ROLLED_BACK"
    assert history["active_model"]["artifact"]["artifact_id"] == first_artifact_id
    assert history["active_model"]["prior_release_id"] == (
        second_release["active_model"]["release_id"]
    )
    assert [release["action"] for release in history["releases"]] == [
        "ROLLED_BACK",
        "ACTIVATED",
        "ACTIVATED",
    ]
    assert "relative_path" not in history["active_model"]["artifact"]

def _editor_authorization(connection: HTTPConnection) -> dict[str, str]:
    connection.request(
        "POST",
        "/api/session",
        body=json.dumps(
            {
                "username": "editor",
                "password": "a sufficiently long local editor password",
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    session = json.loads(response.read())
    assert response.status == 201
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_kraken_recognition_endpoint_requires_startup_configuration(
    tmp_path: Path,
) -> None:
    workspace, project_id, manifest_sha256 = _reviewable_service(tmp_path)
    server = create_self_hosted_service_server(workspace, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection(LOOPBACK_HOST, server.server_address[1], timeout=5)
    try:
        authorization = _editor_authorization(connection)
        connection.request("GET", "/api/healthz")
        health_response = connection.getresponse()
        health = json.loads(health_response.read())
        assert health_response.status == 200
        assert health["kraken_recognition_enabled"] is False

        connection.request(
            "POST",
            f"/api/projects/{project_id}/recognitions/kraken",
            body=json.dumps(
                {
                    "manifest_sha256": manifest_sha256,
                    "kraken_config": "browser supplied paths are rejected",
                }
            ),
            headers={"Content-Type": "application/json", **authorization},
        )
        invalid_response = connection.getresponse()
        assert invalid_response.status == 400
        assert "invalid keys" in json.loads(invalid_response.read())["message"]

        connection.request(
            "POST",
            f"/api/projects/{project_id}/recognitions/kraken",
            body=json.dumps({"manifest_sha256": manifest_sha256}),
            headers={"Content-Type": "application/json", **authorization},
        )
        unavailable_response = connection.getresponse()
        assert unavailable_response.status == 400
        assert "not configured" in json.loads(unavailable_response.read())["message"]
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_configured_kraken_recognition_job_imports_local_suggestions(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    workspace, project_id, manifest_sha256 = _reviewable_service(tmp_path)
    executable = tmp_path / "kraken"
    model = tmp_path / "serock.mlmodel"
    executable.write_bytes(b"fake local kraken executable")
    model.write_bytes(b"fake local kraken model")
    kraken = LocalKraken(
        KrakenConfig(
            executable=PinnedArtifact(executable, sha256_file(executable)),
            model=PinnedArtifact(model, sha256_file(model)),
        )
    )
    registered_model = register_service_artifact(
        workspace,
        model,
        kind="MODEL",
        name="Service-managed test model",
        license_id="Apache-2.0",
    )
    model_artifact_id = str(registered_model["artifact"]["artifact_id"])
    attach_service_artifact(
        workspace,
        project_id=project_id,
        artifact_id=model_artifact_id,
    )
    activate_service_project_model(
        workspace,
        project_id=project_id,
        artifact_id=model_artifact_id,
    )
    used_model_paths: list[Path] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        source = Path(command[command.index("-i") + 1])
        destination = Path(command[command.index("-i") + 2])
        used_model = Path(command[command.index("-m") + 1])
        used_model_paths.append(used_model)
        assert used_model.read_bytes() == b"fake local kraken model"
        document = ET.parse(source)
        for element in document.getroot().iter():
            if element.tag.rsplit("}", 1)[-1] == "Unicode":
                element.text = "recognized by configured local Kraken"
        document.write(destination, encoding="utf-8", xml_declaration=True)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(kraken_module.subprocess, "run", fake_run)
    server = create_self_hosted_service_server(workspace, port=0, kraken=kraken)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection(LOOPBACK_HOST, server.server_address[1], timeout=5)
    try:
        authorization = _editor_authorization(connection)
        connection.request("GET", "/api/healthz")
        health_response = connection.getresponse()
        health = json.loads(health_response.read())
        assert health_response.status == 200
        assert health["kraken_recognition_enabled"] is True

        connection.request(
            "POST",
            f"/api/projects/{project_id}/recognitions/kraken",
            body=json.dumps({"manifest_sha256": manifest_sha256}),
            headers={"Content-Type": "application/json", **authorization},
        )
        queued_response = connection.getresponse()
        queued = json.loads(queued_response.read())
        assert queued_response.status == 202
        assert queued["kind"] == "PROJECT_KRAKEN_RECOGNITION"

        for _ in range(100):
            job = get_service_job(workspace, str(queued["job_id"]))
            if job["status"] in {"SUCCEEDED", "FAILED"}:
                break
            time.sleep(0.02)

        assert job["status"] == "SUCCEEDED"
        assert job["result"] == {
            "project_id": project_id,
            "manifest_sha256": manifest_sha256,
            "result_pagexml_sha256": job["result"]["result_pagexml_sha256"],
            "suggestion_count": 1,
            "runtime_fingerprint": kraken.runtime_fingerprint,
            "model_artifact_id": model_artifact_id,
        }
        assert len(used_model_paths) == 1
        assert used_model_paths[0] != model

        connection.request(
            "GET",
            f"/api/jobs/{queued['job_id']}",
            headers=authorization,
        )
        public_response = connection.getresponse()
        public_job = json.loads(public_response.read())
        assert public_response.status == 200
        assert public_job["status"] == "SUCCEEDED"
        assert public_job["result"]["runtime_fingerprint"] == kraken.runtime_fingerprint

        connection.request(
            "GET",
            f"/api/projects/{project_id}/documents/{manifest_sha256}/pages/0",
            headers=authorization,
        )
        page_response = connection.getresponse()
        page = json.loads(page_response.read())["page"]
        assert page_response.status == 200
        assert page["lines"][0]["text"] == "source text"
        assert page["lines"][0]["suggestions"] == [
            {
                "engine": "kraken",
                "runtime_fingerprint": kraken.runtime_fingerprint,
                "result_pagexml_sha256": job["result"]["result_pagexml_sha256"],
                "text": "recognized by configured local Kraken",
                "imported_at": page["lines"][0]["suggestions"][0]["imported_at"],
            }
        ]

        evaluation_route = (
            f"/api/projects/{project_id}/documents/{manifest_sha256}/evaluations"
        )
        connection.request("GET", evaluation_route, headers=authorization)
        initial_evaluation_response = connection.getresponse()
        initial_evaluations = json.loads(initial_evaluation_response.read())
        assert initial_evaluation_response.status == 200
        assert initial_evaluations["evaluations"][0]["status"] == (
            "NO_EVALUABLE_HUMAN_REVISIONS"
        )
        assert "project" not in initial_evaluations["evaluations"][0]

        source_span_id = page["lines"][0]["source_span_id"]
        connection.request(
            "POST",
            f"/api/projects/{project_id}/transcriptions",
            body=json.dumps(
                {
                    "manifest_sha256": manifest_sha256,
                    "source_span_id": source_span_id,
                    "text": "recognized by configured local Kraken",
                    "expected_revision": 0,
                }
            ),
            headers={"Content-Type": "application/json", **authorization},
        )
        revision_response = connection.getresponse()
        assert revision_response.status == 200
        revision_response.read()

        connection.request("GET", evaluation_route, headers=authorization)
        evaluated_response = connection.getresponse()
        evaluations = json.loads(evaluated_response.read())
        assert evaluated_response.status == 200
        assert evaluations["evaluations"][0]["status"] == "SUCCEEDED"
        assert evaluations["evaluations"][0]["evaluated_line_count"] == 1
        assert evaluations["evaluations"][0]["character_error_rate"] == 0
        assert evaluations["evaluations"][0]["word_error_rate"] == 0

        receipt_route = (
            f"/api/projects/{project_id}/documents/{manifest_sha256}/evaluations/"
            f"{job['result']['result_pagexml_sha256']}/receipt"
        )
        connection.request("GET", receipt_route, headers=authorization)
        receipt_response = connection.getresponse()
        receipt_bytes = receipt_response.read()
        receipt = json.loads(receipt_bytes)
        assert receipt_response.status == 200
        assert receipt_response.headers["Content-Type"].startswith("application/json")
        assert receipt_response.headers["Content-Disposition"] == (
            "attachment; filename="
            f'"aktreader-{manifest_sha256[:12]}-'
            f'{job["result"]["result_pagexml_sha256"][:12]}.evaluation.json"'
        )
        assert receipt["contract"] == {
            "name": "aktreader-htr-evaluation-receipt",
            "version": "1.0.0",
        }
        assert receipt["report"]["result_pagexml_sha256"] == (
            job["result"]["result_pagexml_sha256"]
        )
        assert len(receipt["report"]["human_revision_set_sha256"]) == 64
        assert len(receipt["report_sha256"]) == 64
        assert "project" not in receipt["report"]
        assert b"recognized by configured local Kraken" not in receipt_bytes
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
