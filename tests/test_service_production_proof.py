"""Production-proof checks for the loopback collaborative service."""

from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path

from PIL import Image

from aktreader.project import create_project, import_pagexml_into_project
from aktreader.service import (
    LOOPBACK_HOST,
    add_project_to_service,
    create_local_account,
    create_self_hosted_service_server,
    create_service_workspace,
)


def _reviewable_service(tmp_path: Path) -> tuple[Path, str, str]:
    source = tmp_path / "source"
    source.mkdir()
    image_path = source / "page.png"
    image = Image.new("L", (24, 24), color=255)
    try:
        image.save(image_path)
    finally:
        image.close()
    pagexml = source / "page.xml"
    pagexml.write_text(
        """<PcGts>
  <Page id="page-1" imageFilename="page.png" imageWidth="24" imageHeight="24">
    <TextRegion id="region-1">
      <Coords points="0,0 24,0 24,24 0,24"/>
      <TextLine id="line-1">
        <Coords points="2,2 22,2 22,12 2,12"/>
        <TextEquiv><Unicode>synthetic service proof</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )
    project = tmp_path / "proof.aktproj"
    create_project(project, name="Synthetic service proof")
    imported = import_pagexml_into_project(project, pagexml, image_root=source)
    workspace = tmp_path / "service"
    create_service_workspace(workspace)
    create_local_account(
        workspace,
        username="reviewer",
        password="a sufficiently long local reviewer password",
    )
    added = add_project_to_service(workspace, project, owner_username="reviewer")
    return workspace, str(added["project"]["project_id"]), str(imported["manifest_sha256"])


def _authorized_headers(port: int) -> dict[str, str]:
    connection = HTTPConnection(LOOPBACK_HOST, port, timeout=5)
    try:
        connection.request(
            "POST",
            "/api/session",
            body=json.dumps(
                {
                    "username": "reviewer",
                    "password": "a sufficiently long local reviewer password",
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 201
        return {"Authorization": f"Bearer {payload['access_token']}"}
    finally:
        connection.close()


def test_loopback_workbench_has_accessibility_basics(tmp_path: Path) -> None:
    workspace, _, _ = _reviewable_service(tmp_path)
    server = create_self_hosted_service_server(workspace, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection(LOOPBACK_HOST, server.server_address[1], timeout=5)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        page = response.read().decode("utf-8")
        assert response.status == 200
        assert '<a class="skip-link" href="#main-content">' in page
        assert '<main id="main-content" tabindex="-1">' in page
        assert 'alt="Selected source page"' in page
        assert 'aria-label="PAGE XML layout"' in page
        assert 'id="login-status" role="status" aria-live="polite"' in page
        assert 'id="status" role="status" aria-live="polite"' in page
        controls = re.findall(
            r"<(?:input|select|textarea)\b[^>]*\bid=\"([^\"]+)\"",
            page,
        )
        assert {"username", "password", "project", "document", "page", "text"} <= set(controls)
        assert '<label>Username <input id="username"' in page
        assert '<label>Password <input id="password"' in page
        assert '<label>Transcription <textarea id="text"' in page
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_loopback_service_handles_bounded_concurrent_review_reads(tmp_path: Path) -> None:
    workspace, project_id, manifest_sha256 = _reviewable_service(tmp_path)
    server = create_self_hosted_service_server(workspace, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        headers = _authorized_headers(server.server_address[1])
        document_route = f"/api/projects/{project_id}/documents"
        page_route = f"/api/projects/{project_id}/documents/{manifest_sha256}/pages/0"

        def read_document_and_page(_: int) -> tuple[int, int, bool]:
            connection = HTTPConnection(LOOPBACK_HOST, server.server_address[1], timeout=5)
            try:
                connection.request("GET", document_route, headers=headers)
                documents = connection.getresponse()
                document_payload = json.loads(documents.read())
                connection.request("GET", page_route, headers=headers)
                page = connection.getresponse()
                page_payload = json.loads(page.read())
                return (
                    documents.status,
                    page.status,
                    document_payload["network_required"] is False
                    and page_payload["network_required"] is False,
                )
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(read_document_and_page, range(48)))

        assert results == [(200, 200, True)] * 48
        health = HTTPConnection(LOOPBACK_HOST, server.server_address[1], timeout=5)
        try:
            health.request("GET", "/api/healthz")
            response = health.getresponse()
            payload = json.loads(response.read())
            assert response.status == 200
            assert payload["status"] == "READY"
        finally:
            health.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
