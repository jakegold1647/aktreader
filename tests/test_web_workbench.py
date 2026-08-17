from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

from PIL import Image

from aktreader.project import create_project, import_pagexml_into_project
from aktreader.web_workbench import create_self_hosted_workbench_server


def _project_with_one_page(root: Path) -> tuple[Path, dict[str, object]]:
    source_root = root / "source"
    source_root.mkdir()
    Image.new("L", (40, 30), color=255).save(source_root / "page.png")
    pagexml = source_root / "page.xml"
    pagexml.write_text(
        """<PcGts>
  <Page imageFilename="page.png" imageWidth="40" imageHeight="30">
    <TextRegion id="region-1">
      <Coords points="0,0 40,0 40,30 0,30"/>
      <TextLine id="line-1">
        <Coords points="2,2 38,2 38,12 2,12"/>
        <TextEquiv><Unicode>Alexander record</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
    <TextRegion id="region-2">
      <Coords points="0,15 40,15 40,30 0,30"/>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )
    project = root / "register.aktproj"
    create_project(project, name="Serock births")
    return project, import_pagexml_into_project(project, pagexml)


def _request(
    port: int,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    headers = {"Content-Type": "application/json"} if body is not None else {}
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_loopback_browser_workbench_serves_and_saves_project_revisions(tmp_path: Path) -> None:
    project, imported = _project_with_one_page(tmp_path)
    server = create_self_hosted_workbench_server(project, port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        host, port = server.server_address[:2]
        assert host == "127.0.0.1"

        root_status, _root_headers, root = _request(port, "GET", "/")
        assert root_status == 200
        assert b"AKT Reader browser workbench" in root

        project_status, _project_headers, project_body = _request(port, "GET", "/api/project")
        project_report = json.loads(project_body)
        assert project_status == 200
        assert project_report["name"] == "Serock births"
        document = project_report["documents"][0]
        assert document["manifest_sha256"] == imported["manifest_sha256"]

        pages_status, _pages_headers, pages_body = _request(
            port,
            "GET",
            f"/api/pages?manifest_sha256={document['manifest_sha256']}",
        )
        pages = json.loads(pages_body)
        assert pages_status == 200
        assert pages["pages"][0]["page_id"]
        page_url = pages["pages"][0]["page_url"]

        page_status, _page_headers, page_body = _request(port, "GET", page_url)
        page = json.loads(page_body)
        assert page_status == 200
        assert "image_path" not in page
        assert page["lines"][0]["text"] == "Alexander record"

        image_status, image_headers, image = _request(port, "GET", page["image_url"])
        assert image_status == 200
        assert image_headers["Content-Type"].startswith("image/")
        assert image.startswith(b"\x89PNG")

        revision_request = json.dumps(
            {
                "manifest_sha256": imported["manifest_sha256"],
                "source_span_id": page["lines"][0]["source_span_id"],
                "text": "Aleksander corrected",
                "editor": "reviewer-1",
            }
        ).encode("utf-8")
        save_status, _save_headers, save_body = _request(
            port,
            "POST",
            "/api/transcriptions",
            body=revision_request,
        )
        saved = json.loads(save_body)
        assert save_status == 200
        assert saved["status"] == "SAVED"
        assert saved["revision"] == 1

        refreshed_status, _refreshed_headers, refreshed_body = _request(port, "GET", page_url)
        refreshed = json.loads(refreshed_body)
        assert refreshed_status == 200
        assert refreshed["lines"][0]["text"] == "Aleksander corrected"
        assert refreshed["lines"][0]["revision"] == 1
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_loopback_browser_workbench_saves_page_layout_revisions(tmp_path: Path) -> None:
    project, imported = _project_with_one_page(tmp_path)
    server = create_self_hosted_workbench_server(project, port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        _host, port = server.server_address[:2]
        manifest_sha256 = imported["manifest_sha256"]
        page_url = f"/api/page?manifest_sha256={manifest_sha256}&page_index=0"

        page_status, _page_headers, page_body = _request(port, "GET", page_url)
        page = json.loads(page_body)
        assert page_status == 200
        assert page["reading_order"]["region_ids"] == ["region-1", "region-2"]
        assert [region["region_id"] for region in page["regions"]] == [
            "region-1",
            "region-2",
        ]

        region_request = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "page_index": 0,
                "region_id": "region-1",
                "polygon": [[1, 1], [39, 1], [39, 14], [1, 14]],
                "editor": "layout-reviewer",
            }
        ).encode("utf-8")
        region_status, _region_headers, region_body = _request(
            port,
            "POST",
            "/api/region-geometry",
            body=region_request,
        )
        region = json.loads(region_body)
        assert region_status == 200
        assert region["status"] == "SAVED"
        assert region["revision"] == 1

        order_request = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "page_index": 0,
                "region_ids": ["region-2", "region-1"],
                "editor": "layout-reviewer",
            }
        ).encode("utf-8")
        order_status, _order_headers, order_body = _request(
            port,
            "POST",
            "/api/reading-order",
            body=order_request,
        )
        order = json.loads(order_body)
        assert order_status == 200
        assert order["status"] == "SAVED"
        assert order["revision"] == 1

        refreshed_status, _refreshed_headers, refreshed_body = _request(port, "GET", page_url)
        refreshed = json.loads(refreshed_body)
        assert refreshed_status == 200
        assert refreshed["reading_order"]["revision"] == 1
        assert refreshed["reading_order"]["region_ids"] == ["region-2", "region-1"]
        assert refreshed["regions"][1]["revision"] == 1
        assert refreshed["regions"][1]["polygon"] == [[1, 1], [39, 1], [39, 14], [1, 14]]
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
