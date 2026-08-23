from __future__ import annotations

import http.client
import json
import threading
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode

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
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    request_headers = dict(headers or {})
    if body is not None and not any(
        name.lower() == "content-type" for name in request_headers
    ):
        request_headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def _assert_workbench_security_headers(headers: dict[str, str]) -> None:
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert headers["Content-Security-Policy"] == (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; "
        "object-src 'none'; form-action 'none'; frame-ancestors 'none'"
    )


def test_loopback_browser_workbench_serves_and_saves_project_revisions(tmp_path: Path) -> None:
    project, imported = _project_with_one_page(tmp_path)
    server = create_self_hosted_workbench_server(project, port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        host, port = server.server_address[:2]
        assert host == "127.0.0.1"

        root_status, root_headers, root = _request(port, "GET", "/")
        assert root_status == 200
        _assert_workbench_security_headers(root_headers)
        assert b"AKT Reader browser workbench" in root
        assert b"Page thumbnails" in root
        assert b"region-handle" in root
        assert b"Drag region vertex" in root
        assert b"line-handle" in root
        assert b"Drag line polygon vertex" in root
        assert b"baseline-handle" in root
        assert b"Drag line baseline point" in root
        assert b"Revision history and restore" in root
        assert b"Restore as new revision" in root
        assert b'id="dirty-indicator"' in root
        assert b'window.addEventListener("beforeunload"' in root
        assert b"Discard unsaved " in root
        assert b"Keep editing" in root
        assert b"Discard changes" in root
        assert b"jsonDraftDirty" in root
        assert b'id="previous-line"' in root
        assert b'id="next-line"' in root
        assert b'id="line-position" role="status" aria-live="polite"' in root
        assert b'aria-keyshortcuts="Alt+ArrowUp"' in root
        assert b'aria-keyshortcuts="Alt+ArrowDown"' in root
        assert b'aria-keyshortcuts="Control+Enter Meta+Enter"' in root
        assert b"async function navigateLine(offset, focusList)" in root
        assert b'lineList.addEventListener("keydown"' in root
        assert b'reviewPanel.addEventListener("keydown"' in root
        assert b"save.click();" in root
        assert b"Document details" in root
        assert b'id="document-metadata-form"' in root
        assert b'id="document-title"' in root
        assert b'id="document-tags"' in root
        assert b'id="document-notes"' in root
        assert b'id="metadata-status" role="status" aria-live="polite"' in root
        assert b"function documentMetadataDirty()" in root
        assert b"async function saveDocumentMetadataDraft()" in root
        assert b"split(/\\r?\\n/)" in root
        assert b'record.tags.join("\\n")' in root
        assert b'api("/api/documents"' in root
        assert b"expected_updated_at: record.updated_at" in root
        assert b'streams.push("document metadata")' in root
        assert b'streams.unshift("document metadata")' in root
        assert b'"document metadata", "transcription", "line geometry"' in root
        assert b'[documentTitle, documentTags, documentNotes]' in root
        assert b'id="search-query"' in root
        assert b'id="search-field"' in root
        assert b'id="search-status" role="status" aria-live="polite"' in root
        assert b"async function jumpToSearchResult(result)" in root
        assert b'"transcription", "line geometry", "region geometry", "reading order"' in root
        assert b'api("/api/search?" + parameters.toString())' in root
        assert b"Recent changes" in root
        assert b'id="activity-status" role="status" aria-live="polite"' in root
        assert b'id="activity-list" aria-label="Recent project activity"' in root
        assert b'id="activity-kind"' in root
        assert b'<option value="LINE_GEOMETRY">Line geometry</option>' in root
        assert b'id="activity-scope"' in root
        assert b'<option value="line">Selected line</option>' in root
        assert b"function activityParameters()" in root
        assert b'parameters.set("source_span_id", line.source_span_id)' in root
        assert b'parameters.set("region_id", region.region_id)' in root
        assert b'if (activityScope.value === "line") await loadActivity();' in root
        assert b'if (activityScope.value === "region") await loadActivity();' in root
        assert b'if (activityScope.value === "page") await loadActivity();' in root
        assert b'activityKind.addEventListener("change"' in root
        assert b'activityScope.addEventListener("change"' in root
        assert b"async function jumpToActivityEvent(event)" in root
        assert b'api("/api/activity?" + parameters.toString())' in root
        assert b"It does not include transcription values or local paths." in root
        assert b"line.text = text.value" in root
        assert b"state.page.reading_order.region_ids = [...state.regionOrder]" in root
        assert b'].join("\\n");' in root

        project_status, project_headers, project_body = _request(port, "GET", "/api/project")
        project_report = json.loads(project_body)
        assert project_status == 200
        _assert_workbench_security_headers(project_headers)
        assert project_report["name"] == "Serock births"
        document = project_report["documents"][0]
        assert document["manifest_sha256"] == imported["manifest_sha256"]

        search_status, search_headers, search_body = _request(
            port,
            "GET",
            "/api/search?" + urlencode({"q": "alex", "field": "text"}),
        )
        search_report = json.loads(search_body)
        assert search_status == 200
        _assert_workbench_security_headers(search_headers)
        assert search_report["network_required"] is False
        assert search_report["limit"] == 50
        assert search_report["result_count"] == 1
        assert search_report["truncated"] is False
        assert search_report["results"][0]["manifest_sha256"] == imported["manifest_sha256"]
        assert search_report["results"][0]["page_index"] == 0
        assert search_report["results"][0]["line_id"] == "line-1"
        assert search_report["results"][0]["text"] == "Alexander record"
        assert "image_path" not in search_report["results"][0]

        title_status, _title_headers, title_body = _request(
            port,
            "GET",
            "/api/search?" + urlencode({"q": document["title"], "field": "title"}),
        )
        assert title_status == 200
        assert json.loads(title_body)["result_count"] == 1

        invalid_search_status, _invalid_search_headers, invalid_search_body = _request(
            port,
            "GET",
            "/api/search?" + urlencode({"q": "alex", "field": "text", "limit": "500"}),
        )
        assert invalid_search_status == 400
        assert "requires only q and field" in json.loads(invalid_search_body)["message"]

        metadata_request = json.dumps(
            {
                "manifest_sha256": document["manifest_sha256"],
                "title": "Serock civil register, 1890",
                "tags": ["Serock", "births"],
                "notes": "Private local review note.",
                "expected_updated_at": document["updated_at"],
            }
        ).encode("utf-8")
        metadata_status, metadata_headers, metadata_body = _request(
            port,
            "POST",
            "/api/documents",
            body=metadata_request,
        )
        metadata = json.loads(metadata_body)
        assert metadata_status == 200
        _assert_workbench_security_headers(metadata_headers)
        assert metadata["title"] == "Serock civil register, 1890"
        assert metadata["tags"] == ["Serock", "births"]
        assert metadata["notes"] == "Private local review note."
        assert metadata["updated_at"] != document["updated_at"]
        assert metadata["network_required"] is False

        refreshed_project_status, _refreshed_project_headers, refreshed_project_body = (
            _request(port, "GET", "/api/project")
        )
        refreshed_document = json.loads(refreshed_project_body)["documents"][0]
        assert refreshed_project_status == 200
        assert refreshed_document["title"] == "Serock civil register, 1890"
        assert refreshed_document["tags"] == ["Serock", "births"]

        refreshed_title_status, _refreshed_title_headers, refreshed_title_body = (
            _request(
                port,
                "GET",
                "/api/search?" + urlencode({"q": "civil register", "field": "title"}),
            )
        )
        assert refreshed_title_status == 200
        assert json.loads(refreshed_title_body)["result_count"] == 1

        stale_metadata_status, _stale_metadata_headers, stale_metadata_body = _request(
            port,
            "POST",
            "/api/documents",
            body=metadata_request,
        )
        assert stale_metadata_status == 409
        assert "document metadata conflict" in json.loads(stale_metadata_body)["message"]

        invalid_metadata_status, _invalid_metadata_headers, invalid_metadata_body = (
            _request(
                port,
                "POST",
                "/api/documents",
                body=json.dumps(
                    {
                        "manifest_sha256": document["manifest_sha256"],
                        "title": "Missing optimistic token",
                        "tags": [],
                        "notes": "",
                    }
                ).encode("utf-8"),
            )
        )
        assert invalid_metadata_status == 400
        assert "invalid keys" in json.loads(invalid_metadata_body)["message"]

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
        _assert_workbench_security_headers(thumbnail_headers)
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
        _assert_workbench_security_headers(image_headers)
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
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Origin": f"http://127.0.0.1:{port}",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        saved = json.loads(save_body)
        assert save_status == 200
        assert saved["status"] == "SAVED"
        assert saved["revision"] == 1

        activity_status, activity_headers, activity_body = _request(
            port,
            "GET",
            "/api/activity?" + urlencode(
                {"manifest_sha256": imported["manifest_sha256"]}
            ),
        )
        activity = json.loads(activity_body)
        assert activity_status == 200
        _assert_workbench_security_headers(activity_headers)
        assert activity["manifest_sha256"] == imported["manifest_sha256"]
        assert activity["network_required"] is False
        assert activity["limit"] == 50
        assert activity["event_count"] == 1
        assert activity["filters"] == {
            "kind": None,
            "page_index": None,
            "source_span_id": None,
            "region_id": None,
        }
        assert activity["events"] == [
            {
                "kind": "TRANSCRIPTION",
                "page_index": 0,
                "source_span_id": page["lines"][0]["source_span_id"],
                "line_id": "line-1",
                "region_id": "region-1",
                "revision": 1,
                "editor": "reviewer-1",
                "created_at": activity["events"][0]["created_at"],
            }
        ]
        assert "Aleksander corrected" not in activity_body.decode("utf-8")
        assert "prior_text" not in activity_body.decode("utf-8")
        assert "revised_text" not in activity_body.decode("utf-8")
        assert str(project) not in activity_body.decode("utf-8")

        filtered_activity_status, _, filtered_activity_body = _request(
            port,
            "GET",
            "/api/activity?"
            + urlencode(
                {
                    "manifest_sha256": imported["manifest_sha256"],
                    "kind": "transcription",
                    "page_index": 0,
                    "source_span_id": page["lines"][0]["source_span_id"],
                }
            ),
        )
        filtered_activity = json.loads(filtered_activity_body)
        assert filtered_activity_status == 200
        assert filtered_activity["filters"] == {
            "kind": "TRANSCRIPTION",
            "page_index": 0,
            "source_span_id": page["lines"][0]["source_span_id"],
            "region_id": None,
        }
        assert filtered_activity["event_count"] == 1
        assert filtered_activity["events"] == activity["events"]
        assert "Aleksander corrected" not in filtered_activity_body.decode("utf-8")
        assert str(project) not in filtered_activity_body.decode("utf-8")

        region_activity_status, _, region_activity_body = _request(
            port,
            "GET",
            "/api/activity?"
            + urlencode(
                {
                    "manifest_sha256": imported["manifest_sha256"],
                    "page_index": 0,
                    "region_id": "region-1",
                }
            ),
        )
        assert region_activity_status == 200
        assert json.loads(region_activity_body)["event_count"] == 1

        empty_activity_status, _, empty_activity_body = _request(
            port,
            "GET",
            "/api/activity?"
            + urlencode(
                {
                    "manifest_sha256": imported["manifest_sha256"],
                    "kind": "READING_ORDER",
                    "page_index": 0,
                }
            ),
        )
        assert empty_activity_status == 200
        assert json.loads(empty_activity_body)["event_count"] == 0

        invalid_activity_status, _invalid_activity_headers, invalid_activity_body = _request(
            port,
            "GET",
            "/api/activity?"
            + urlencode({"manifest_sha256": imported["manifest_sha256"], "limit": "500"}),
        )
        assert invalid_activity_status == 400
        assert (
            "supports manifest_sha256 plus optional" in json.loads(invalid_activity_body)["message"]
        )

        unscoped_line_status, _, unscoped_line_body = _request(
            port,
            "GET",
            "/api/activity?"
            + urlencode(
                {
                    "manifest_sha256": imported["manifest_sha256"],
                    "source_span_id": page["lines"][0]["source_span_id"],
                }
            ),
        )
        assert unscoped_line_status == 400
        assert json.loads(unscoped_line_body)["message"] == (
            "line and region activity scopes require page_index"
        )

        missing_line_status, _, missing_line_body = _request(
            port,
            "GET",
            "/api/activity?"
            + urlencode(
                {
                    "manifest_sha256": imported["manifest_sha256"],
                    "page_index": 0,
                    "source_span_id": "missing-line",
                }
            ),
        )
        assert missing_line_status == 400
        assert json.loads(missing_line_body)["message"] == (
            "activity scope line was not found on the selected page"
        )

        missing_activity_status, _missing_activity_headers, missing_activity_body = _request(
            port,
            "GET",
            "/api/activity?" + urlencode({"manifest_sha256": "0" * 64}),
        )
        assert missing_activity_status == 400
        assert json.loads(missing_activity_body)["message"] == (
            "project document was not found"
        )

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
        assert stale_status == 409
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


def test_loopback_browser_workbench_rejects_nonlocal_request_boundaries(
    tmp_path: Path,
) -> None:
    project, imported = _project_with_one_page(tmp_path)
    server = create_self_hosted_workbench_server(project, port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    try:
        _host, port = server.server_address[:2]
        local_status, _local_headers, local_body = _request(
            port,
            "GET",
            "/api/project",
            headers={
                "Host": f"localhost:{port}",
                "Origin": f"http://localhost:{port}",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        assert local_status == 200
        assert json.loads(local_body)["status"] == "READY"

        manifest_sha256 = imported["manifest_sha256"]
        page_url = f"/api/page?manifest_sha256={manifest_sha256}&page_index=0"
        page_status, _page_headers, page_body = _request(port, "GET", page_url)
        assert page_status == 200
        source_span_id = json.loads(page_body)["lines"][0]["source_span_id"]
        valid_write = json.dumps(
            {
                "manifest_sha256": manifest_sha256,
                "source_span_id": source_span_id,
                "text": "must not be saved",
                "editor": "remote-page",
                "expected_revision": 0,
            }
        ).encode("utf-8")
        rejected_requests = [
            (
                "GET",
                "/api/project",
                None,
                {"Host": f"attacker.example:{port}"},
                403,
                "Host",
            ),
            (
                "GET",
                "/api/project",
                None,
                {"Origin": "https://attacker.example"},
                403,
                "Origin",
            ),
            (
                "GET",
                "/api/project",
                None,
                {"Sec-Fetch-Site": "cross-site"},
                403,
                "cross-origin",
            ),
            (
                "POST",
                "/api/transcriptions",
                valid_write,
                {"Origin": "https://attacker.example"},
                403,
                "Origin",
            ),
            (
                "POST",
                "/api/transcriptions",
                valid_write,
                {"Sec-Fetch-Site": "same-site"},
                403,
                "cross-origin",
            ),
            (
                "POST",
                "/api/transcriptions",
                valid_write,
                {"Content-Type": "text/plain"},
                415,
                "Content-Type application/json",
            ),
        ]
        for method, path, body, headers, expected_status, expected_message in rejected_requests:
            response_status, response_headers, response_body = _request(
                port,
                method,
                path,
                body=body,
                headers=headers,
            )
            response = json.loads(response_body)
            assert response_status == expected_status
            _assert_workbench_security_headers(response_headers)
            assert response["status"] == "ERROR"
            assert expected_message in response["message"]

        assert inspect_project(project)["transcription_revision_count"] == 0
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
        assert stale_line_status == 409
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
        assert stale_region_status == 409
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
        assert stale_order_status == 409
        assert "reading-order revision conflict" in stale_order["message"]
        summary = inspect_project(project)
        assert summary["line_geometry_revision_count"] == 1
        assert summary["region_geometry_revision_count"] == 1
        assert summary["page_reading_order_revision_count"] == 1
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_loopback_browser_workbench_reads_and_restores_all_revision_streams(
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

        def post(route: str, payload: dict[str, object]) -> dict[str, object]:
            response_status, _response_headers, response_body = _request(
                port,
                "POST",
                route,
                body=json.dumps(payload).encode("utf-8"),
            )
            response = json.loads(response_body)
            assert response_status == 200, response
            return response

        line_polygons = [
            [[3, 2], [37, 2], [37, 12], [3, 12]],
            [[4, 2], [36, 2], [36, 12], [4, 12]],
        ]
        region_polygons = [
            [[1, 1], [39, 1], [39, 14], [1, 14]],
            [[2, 1], [38, 1], [38, 14], [2, 14]],
        ]
        orders = [["region-2", "region-1"], ["region-1", "region-2"]]
        for revision in [0, 1]:
            expected_revision = revision
            post(
                "/api/transcriptions",
                {
                    "manifest_sha256": manifest_sha256,
                    "source_span_id": source_span_id,
                    "text": ["First correction", "Second correction"][revision],
                    "editor": "history-reviewer",
                    "expected_revision": expected_revision,
                },
            )
            post(
                "/api/line-geometry",
                {
                    "manifest_sha256": manifest_sha256,
                    "source_span_id": source_span_id,
                    "polygon": line_polygons[revision],
                    "baseline": [[4, 10 + revision], [36, 10 + revision]],
                    "editor": "history-reviewer",
                    "expected_revision": expected_revision,
                },
            )
            post(
                "/api/region-geometry",
                {
                    "manifest_sha256": manifest_sha256,
                    "page_index": 0,
                    "region_id": "region-1",
                    "polygon": region_polygons[revision],
                    "editor": "history-reviewer",
                    "expected_revision": expected_revision,
                },
            )
            post(
                "/api/reading-order",
                {
                    "manifest_sha256": manifest_sha256,
                    "page_index": 0,
                    "region_ids": orders[revision],
                    "editor": "history-reviewer",
                    "expected_revision": expected_revision,
                },
            )

        history_queries = {
            "TRANSCRIPTION": {"source_span_id": source_span_id},
            "LINE_GEOMETRY": {"source_span_id": source_span_id},
            "REGION_GEOMETRY": {"page_index": 0, "region_id": "region-1"},
            "READING_ORDER": {"page_index": 0},
        }
        histories = {}
        for kind, locator in history_queries.items():
            query = urlencode(
                {"manifest_sha256": manifest_sha256, "kind": kind, **locator}
            )
            history_status, _history_headers, history_body = _request(
                port,
                "GET",
                f"/api/revision-history?{query}",
            )
            history = json.loads(history_body)
            assert history_status == 200, history
            assert history["kind"] == kind
            assert history["current_revision"] == 2
            assert [item["revision"] for item in history["revisions"]] == [2, 1]
            assert history["pagination"] == {
                "limit": 100,
                "before_revision": None,
                "has_more": False,
                "next_before_revision": None,
            }
            assert history["content_included"] is True
            assert history["network_required"] is False
            histories[kind] = history

        assert histories["TRANSCRIPTION"]["imported_state"] == {
            "text": "Alexander record"
        }
        assert histories["TRANSCRIPTION"]["contains_human_text"] is True
        assert histories["LINE_GEOMETRY"]["contains_human_text"] is False

        restore_payloads = {
            "TRANSCRIPTION": {
                "source_span_id": source_span_id,
            },
            "LINE_GEOMETRY": {
                "source_span_id": source_span_id,
            },
            "REGION_GEOMETRY": {
                "page_index": 0,
                "region_id": "region-1",
            },
            "READING_ORDER": {
                "page_index": 0,
            },
        }
        for kind, locator in restore_payloads.items():
            restored = post(
                "/api/restorations",
                {
                    "manifest_sha256": manifest_sha256,
                    "kind": kind,
                    "target_revision": 1,
                    "editor": "history-reviewer",
                    "expected_revision": 2,
                    **locator,
                },
            )
            assert restored["status"] == "RESTORED"
            assert restored["revision"] == 3
            assert restored["target_revision"] == 1

        refreshed_status, _refreshed_headers, refreshed_body = _request(
            port, "GET", page_url
        )
        refreshed = json.loads(refreshed_body)
        assert refreshed_status == 200
        assert refreshed["lines"][0]["text"] == "First correction"
        assert refreshed["lines"][0]["polygon"] == line_polygons[0]
        assert refreshed["regions"][1]["polygon"] == region_polygons[0]
        assert refreshed["reading_order"]["region_ids"] == orders[0]

        stale_status, _stale_headers, stale_body = _request(
            port,
            "POST",
            "/api/restorations",
            body=json.dumps(
                {
                    "manifest_sha256": manifest_sha256,
                    "kind": "TRANSCRIPTION",
                    "source_span_id": source_span_id,
                    "target_revision": 0,
                    "editor": "stale-tab",
                    "expected_revision": 2,
                }
            ).encode("utf-8"),
        )
        assert stale_status == 409
        assert "transcription revision conflict" in json.loads(stale_body)["message"]

        invalid_status, _invalid_headers, invalid_body = _request(
            port,
            "POST",
            "/api/restorations",
            body=json.dumps(
                {
                    "manifest_sha256": manifest_sha256,
                    "kind": "TRANSCRIPTION",
                    "source_span_id": source_span_id,
                    "target_revision": True,
                    "editor": "history-reviewer",
                    "expected_revision": 3,
                }
            ).encode("utf-8"),
        )
        assert invalid_status == 400
        assert json.loads(invalid_body)["message"] == (
            "target_revision must be a non-negative integer"
        )
        summary = inspect_project(project)
        assert summary["transcription_revision_count"] == 3
        assert summary["line_geometry_revision_count"] == 3
        assert summary["region_geometry_revision_count"] == 3
        assert summary["page_reading_order_revision_count"] == 3
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
