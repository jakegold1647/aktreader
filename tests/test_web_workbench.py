from __future__ import annotations

import http.client
import json
import threading
from io import BytesIO
from pathlib import Path

from PIL import Image

from aktreader.project import create_project, import_pagexml_into_project, inspect_project
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
        <Baseline points="4,10 36,10"/>
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
        assert b"Page thumbnails" in root
        assert b"region-handle" in root
        assert b"Drag region vertex" in root
        assert b"line-handle" in root
        assert b"Drag line polygon vertex" in root
        assert b"baseline-handle" in root
        assert b"Drag line baseline point" in root
        assert b'].join("\\n");' in root

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
        thumbnail_url = pages["pages"][0]["thumbnail_url"]
        thumbnail_status, thumbnail_headers, thumbnail = _request(
            port,
            "GET",
            thumbnail_url,
        )
        with Image.open(BytesIO(thumbnail)) as opened_thumbnail:
            thumbnail_size = opened_thumbnail.size
        assert thumbnail_status == 200
        assert thumbnail_headers["Content-Type"].startswith("image/png")
        assert thumbnail_size[0] <= 240
        assert thumbnail_size[1] <= 180

        page_status, _page_headers, page_body = _request(port, "GET", page_url)
        page = json.loads(page_body)
        assert page_status == 200
        assert "image_path" not in page
        assert page["lines"][0]["text"] == "Alexander record"
        assert page["lines"][0]["polygon"] == [[2, 2], [38, 2], [38, 12], [2, 12]]
        assert page["lines"][0]["baseline"] == [[4, 10], [36, 10]]
        assert page["lines"][0]["geometry_revision"] == 0

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
                "expected_revision": 0,
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

        stale_request = json.dumps(
            {
                "manifest_sha256": imported["manifest_sha256"],
                "source_span_id": page["lines"][0]["source_span_id"],
                "text": "stale tab text",
                "editor": "reviewer-2",
                "expected_revision": 0,
            }
        ).encode("utf-8")
        stale_status, _stale_headers, stale_body = _request(
            port,
            "POST",
            "/api/transcriptions",
            body=stale_request,
        )
        stale = json.loads(stale_body)
        assert stale_status == 400
        assert stale["status"] == "ERROR"
        assert "transcription revision conflict" in stale["message"]
        unchanged_status, _unchanged_headers, unchanged_body = _request(
            port,
            "GET",
            page_url,
        )
        unchanged = json.loads(unchanged_body)
        assert unchanged_status == 200
        assert unchanged["lines"][0]["text"] == "Aleksander corrected"
        assert unchanged["lines"][0]["revision"] == 1
        assert inspect_project(project)["transcription_revision_count"] == 1
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

        source_span_id = page["lines"][0]["source_span_id"]
        revised_line_polygon = [[3, 3], [37, 3], [37, 13], [3, 13]]
        revised_line_baseline = [[4, 11], [36, 11]]
        line_request = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "source_span_id": source_span_id,
                "polygon": revised_line_polygon,
                "baseline": revised_line_baseline,
                "editor": "layout-reviewer",
                "expected_revision": 0,
            }
        ).encode("utf-8")
        line_status, _line_headers, line_body = _request(
            port,
            "POST",
            "/api/line-geometry",
            body=line_request,
        )
        line = json.loads(line_body)
        assert line_status == 200
        assert line["status"] == "SAVED"
        assert line["revision"] == 1

        unchanged_line_request = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "source_span_id": source_span_id,
                "polygon": revised_line_polygon,
                "baseline": revised_line_baseline,
                "editor": "layout-reviewer",
                "expected_revision": 1,
            }
        ).encode("utf-8")
        unchanged_line_status, _unchanged_line_headers, unchanged_line_body = _request(
            port,
            "POST",
            "/api/line-geometry",
            body=unchanged_line_request,
        )
        unchanged_line = json.loads(unchanged_line_body)
        assert unchanged_line_status == 200
        assert unchanged_line["status"] == "UNCHANGED"
        assert unchanged_line["revision"] == 1

        invalid_line_request = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "source_span_id": source_span_id,
                "polygon": revised_line_polygon,
                "baseline": "not-points",
                "editor": "layout-reviewer",
                "expected_revision": 1,
            }
        ).encode("utf-8")
        invalid_line_status, _invalid_line_headers, invalid_line_body = _request(
            port,
            "POST",
            "/api/line-geometry",
            body=invalid_line_request,
        )
        invalid_line = json.loads(invalid_line_body)
        assert invalid_line_status == 400
        assert invalid_line["status"] == "ERROR"
        assert "line baseline" in invalid_line["message"]

        region_request = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "page_index": 0,
                "region_id": "region-1",
                "polygon": [[1, 1], [39, 1], [39, 14], [1, 14]],
                "editor": "layout-reviewer",
                "expected_revision": 0,
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
                "expected_revision": 0,
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
        assert refreshed["lines"][0]["geometry_revision"] == 1
        assert refreshed["lines"][0]["polygon"] == revised_line_polygon
        assert refreshed["lines"][0]["baseline"] == revised_line_baseline

        stale_line_request = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "source_span_id": source_span_id,
                "polygon": [[4, 3], [36, 3], [36, 13], [4, 13]],
                "baseline": revised_line_baseline,
                "editor": "layout-reviewer",
                "expected_revision": 0,
            }
        ).encode("utf-8")
        stale_line_status, _stale_line_headers, stale_line_body = _request(
            port,
            "POST",
            "/api/line-geometry",
            body=stale_line_request,
        )
        stale_line = json.loads(stale_line_body)
        assert stale_line_status == 400
        assert "line geometry revision conflict" in stale_line["message"]

        stale_region_request = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "page_index": 0,
                "region_id": "region-1",
                "polygon": [[2, 1], [38, 1], [38, 14], [2, 14]],
                "editor": "layout-reviewer",
                "expected_revision": 0,
            }
        ).encode("utf-8")
        stale_region_status, _stale_region_headers, stale_region_body = _request(
            port,
            "POST",
            "/api/region-geometry",
            body=stale_region_request,
        )
        stale_region = json.loads(stale_region_body)
        assert stale_region_status == 400
        assert "region geometry revision conflict" in stale_region["message"]

        stale_order_request = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "page_index": 0,
                "region_ids": ["region-1", "region-2"],
                "editor": "layout-reviewer",
                "expected_revision": 0,
            }
        ).encode("utf-8")
        stale_order_status, _stale_order_headers, stale_order_body = _request(
            port,
            "POST",
            "/api/reading-order",
            body=stale_order_request,
        )
        stale_order = json.loads(stale_order_body)
        assert stale_order_status == 400
        assert "reading-order revision conflict" in stale_order["message"]
        summary = inspect_project(project)
        assert summary["line_geometry_revision_count"] == 1
        assert summary["region_geometry_revision_count"] == 1
        assert summary["page_reading_order_revision_count"] == 1
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_loopback_browser_workbench_requires_integer_revision_preconditions(
    tmp_path: Path,
) -> None:
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
        source_span_id = page["lines"][0]["source_span_id"]

        missing_preconditions = [
            (
                "/api/transcriptions",
                {
                    "manifest_sha256": manifest_sha256,
                    "source_span_id": source_span_id,
                    "text": "revised",
                    "editor": "reviewer",
                },
            ),
            (
                "/api/line-geometry",
                {
                    "manifest_sha256": manifest_sha256,
                    "source_span_id": source_span_id,
                    "polygon": [[2, 2], [38, 2], [38, 12], [2, 12]],
                    "baseline": [[4, 10], [36, 10]],
                    "editor": "reviewer",
                },
            ),
            (
                "/api/region-geometry",
                {
                    "manifest_sha256": manifest_sha256,
                    "page_index": 0,
                    "region_id": "region-1",
                    "polygon": [[1, 1], [39, 1], [39, 29], [1, 29]],
                    "editor": "reviewer",
                },
            ),
            (
                "/api/reading-order",
                {
                    "manifest_sha256": manifest_sha256,
                    "page_index": 0,
                    "region_ids": ["region-2", "region-1"],
                    "editor": "reviewer",
                },
            ),
        ]
        for route, payload in missing_preconditions:
            response_status, _response_headers, response_body = _request(
                port,
                "POST",
                route,
                body=json.dumps(payload).encode("utf-8"),
            )
            response = json.loads(response_body)
            assert response_status == 400
            assert response["status"] == "ERROR"
            assert "invalid keys" in response["message"] or "must contain only" in response[
                "message"
            ]

        for invalid_revision in [True, "0", -1]:
            response_status, _response_headers, response_body = _request(
                port,
                "POST",
                "/api/transcriptions",
                body=json.dumps(
                    {
                        "manifest_sha256": manifest_sha256,
                        "source_span_id": source_span_id,
                        "text": "revised",
                        "editor": "reviewer",
                        "expected_revision": invalid_revision,
                    }
                ).encode("utf-8"),
            )
            response = json.loads(response_body)
            assert response_status == 400
            assert response["message"] == (
                "expected_revision must be a non-negative integer"
            )

        summary = inspect_project(project)
        assert summary["transcription_revision_count"] == 0
        assert summary["line_geometry_revision_count"] == 0
        assert summary["region_geometry_revision_count"] == 0
        assert summary["page_reading_order_revision_count"] == 0
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
