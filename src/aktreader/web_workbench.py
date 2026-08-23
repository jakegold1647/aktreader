"""Loopback-only browser workbench for one local AKT Reader project.

The server is started only by an explicit command, binds only to 127.0.0.1,
and exposes no cross-origin API. It is a single-user browser surface over the
same append-only project store used by the desktop workbench.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from PIL import Image

from aktreader.project import (
    ProjectStoreError,
    inspect_project,
    list_project_documents,
    list_project_pages,
    load_project_page,
    load_project_page_layout,
    load_project_revision_history,
    restore_line_geometry,
    restore_line_transcription,
    restore_page_reading_order,
    restore_region_geometry,
    revise_line_geometry,
    revise_line_transcription,
    revise_page_reading_order,
    revise_region_geometry,
)

LOOPBACK_HOST = "127.0.0.1"
MAX_REQUEST_BYTES = 65536
THUMBNAIL_MAX_SIZE = (240, 180)


class WebWorkbenchError(ValueError):
    """Raised when the self-hosted browser workbench cannot be started or used."""


class _RequestBoundaryError(WebWorkbenchError):
    def __init__(self, message: str, *, status: HTTPStatus) -> None:
        super().__init__(message)
        self.status = status


class SelfHostedWorkbenchServer(ThreadingHTTPServer):
    """Threaded, loopback-only server bound to one local project."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, project: Path, *, port: int) -> None:
        self.project = project
        super().__init__((LOOPBACK_HOST, port), _handler_for_project(project))

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}/"


def _require_manifest_sha256(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value.lower())
    ):
        raise WebWorkbenchError("manifest_sha256 must be a SHA-256 string")
    return value


def _require_page_index(value: object) -> int:
    if isinstance(value, bool):
        raise WebWorkbenchError("page_index must be a non-negative integer")
    try:
        page_index = int(value)
    except (TypeError, ValueError) as error:
        raise WebWorkbenchError("page_index must be a non-negative integer") from error
    if page_index < 0:
        raise WebWorkbenchError("page_index must be a non-negative integer")
    return page_index


def _require_expected_revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WebWorkbenchError("expected_revision must be a non-negative integer")
    return value


def _require_target_revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WebWorkbenchError("target_revision must be a non-negative integer")
    return value


def _require_revision_kind(value: object) -> str:
    if not isinstance(value, str):
        raise WebWorkbenchError("kind must be a supported revision kind")
    kind = value.strip().upper()
    if kind not in {
        "TRANSCRIPTION",
        "LINE_GEOMETRY",
        "REGION_GEOMETRY",
        "READING_ORDER",
    }:
        raise WebWorkbenchError("kind must be a supported revision kind")
    return kind


def _query_value(query: dict[str, list[str]], name: str) -> str:
    values = query.get(name)
    if values is None or len(values) != 1 or not values[0]:
        raise WebWorkbenchError(f"{name} query parameter is required exactly once")
    return values[0]


def _page_query(manifest_sha256: str, page_index: int) -> str:
    return urlencode(
        {
            "manifest_sha256": manifest_sha256,
            "page_index": page_index,
        }
    )


def _project_summary(project: Path) -> dict[str, object]:
    report = inspect_project(project)
    documents = list_project_documents(project)
    return {
        "status": "READY",
        "project_id": report["project_id"],
        "name": report["name"],
        "document_count": len(documents),
        "documents": [
            {
                "manifest_sha256": document["manifest_sha256"],
                "document_id": document["document_id"],
                "title": document["title"],
                "tags": document["tags"],
                "notes": document["notes"],
                "page_count": document["page_count"],
                "region_count": document["region_count"],
                "line_count": document["line_count"],
                "created_at": document["created_at"],
                "updated_at": document["updated_at"],
            }
            for document in documents
        ],
        "network_required": False,
    }


def _document_pages(project: Path, manifest_sha256: str) -> dict[str, object]:
    manifest_sha256 = _require_manifest_sha256(manifest_sha256)
    documents = {
        str(document["manifest_sha256"]): document for document in list_project_documents(project)
    }
    if manifest_sha256 not in documents:
        raise WebWorkbenchError("project document was not found")
    pages = [
        page
        for page in list_project_pages(project)
        if page["manifest_sha256"] == manifest_sha256
    ]
    return {
        "status": "READY",
        "manifest_sha256": manifest_sha256,
        "document_id": documents[manifest_sha256]["document_id"],
        "pages": [
            {
                "page_index": page["page_index"],
                "page_id": page["page_id"],
                "width_px": page["width_px"],
                "height_px": page["height_px"],
                "page_url": f"/api/page?{_page_query(manifest_sha256, int(page['page_index']))}",
                "thumbnail_url": (
                    f"/api/thumbnail?{_page_query(manifest_sha256, int(page['page_index']))}"
                ),
            }
            for page in pages
        ],
        "network_required": False,
    }


def _page_payload(project: Path, manifest_sha256: str, page_index: int) -> dict[str, object]:
    manifest_sha256 = _require_manifest_sha256(manifest_sha256)
    page_index = _require_page_index(page_index)
    page = load_project_page(
        project,
        manifest_sha256=manifest_sha256,
        page_index=page_index,
    )
    layout = load_project_page_layout(
        project,
        manifest_sha256=manifest_sha256,
        page_index=page_index,
    )
    geometry_by_span = {line["source_span_id"]: line for line in layout["lines"]}
    if set(geometry_by_span) != {line["source_span_id"] for line in page["lines"]}:
        raise WebWorkbenchError("project page line geometry does not match its lines")
    lines = []
    for line in page["lines"]:
        geometry = geometry_by_span[line["source_span_id"]]
        lines.append(
            {
                **line,
                "polygon": geometry["polygon"],
                "baseline": geometry["baseline"],
                "geometry_revision": geometry["revision"],
            }
        )
    safe_fields = {
        "manifest_sha256": manifest_sha256,
        "page_index": page_index,
        "page_id": page["page_id"],
        "image_sha256": page["image_sha256"],
        "width_px": page["width_px"],
        "height_px": page["height_px"],
        "lines": lines,
        "regions": layout["regions"],
        "reading_order": layout["reading_order"],
        "image_url": f"/api/image?{_page_query(manifest_sha256, page_index)}",
        "network_required": False,
    }
    return safe_fields


def _revision_history_payload(
    project: Path,
    query: dict[str, list[str]],
) -> dict[str, object]:
    manifest_sha256 = _require_manifest_sha256(_query_value(query, "manifest_sha256"))
    kind = _require_revision_kind(_query_value(query, "kind"))
    common = {"manifest_sha256", "kind"}
    if kind in {"TRANSCRIPTION", "LINE_GEOMETRY"}:
        expected = common | {"source_span_id"}
        if set(query) != expected:
            raise WebWorkbenchError(
                "line revision history requires only manifest_sha256, kind, and source_span_id"
            )
        return load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind=kind,
            source_span_id=_query_value(query, "source_span_id"),
            limit=100,
        )
    if kind == "READING_ORDER":
        expected = common | {"page_index"}
        if set(query) != expected:
            raise WebWorkbenchError(
                "reading-order history requires only manifest_sha256, kind, and page_index"
            )
        return load_project_revision_history(
            project,
            manifest_sha256=manifest_sha256,
            kind=kind,
            page_index=_require_page_index(_query_value(query, "page_index")),
            limit=100,
        )
    expected = common | {"page_index", "region_id"}
    if set(query) != expected:
        raise WebWorkbenchError(
            "region history requires only manifest_sha256, kind, page_index, and region_id"
        )
    return load_project_revision_history(
        project,
        manifest_sha256=manifest_sha256,
        kind=kind,
        page_index=_require_page_index(_query_value(query, "page_index")),
        region_id=_query_value(query, "region_id"),
        limit=100,
    )


def _image_payload(project: Path, manifest_sha256: str, page_index: int) -> tuple[str, bytes]:
    page = load_project_page(
        project,
        manifest_sha256=_require_manifest_sha256(manifest_sha256),
        page_index=_require_page_index(page_index),
    )
    image_path = Path(str(page["image_path"]))
    try:
        image = image_path.read_bytes()
    except OSError as error:
        raise WebWorkbenchError("project image is unavailable") from error
    try:
        with Image.open(image_path) as opened:
            media_type = Image.MIME.get(opened.format or "", "application/octet-stream")
    except OSError as error:
        raise WebWorkbenchError("project image format is unreadable") from error
    return media_type, image


def _thumbnail_payload(
    project: Path,
    manifest_sha256: str,
    page_index: int,
) -> tuple[str, bytes]:
    page = load_project_page(
        project,
        manifest_sha256=_require_manifest_sha256(manifest_sha256),
        page_index=_require_page_index(page_index),
    )
    image_path = Path(str(page["image_path"]))
    try:
        with Image.open(image_path) as opened:
            thumbnail = opened.convert("RGB")
    except OSError as error:
        raise WebWorkbenchError("project image format is unreadable") from error
    try:
        thumbnail.thumbnail(THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
        buffer = BytesIO()
        thumbnail.save(buffer, format="PNG", optimize=False)
        return "image/png", buffer.getvalue()
    except OSError as error:
        raise WebWorkbenchError("project thumbnail cannot be rendered") from error
    finally:
        thumbnail.close()


def _revision_payload(project: Path, payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise WebWorkbenchError("revision request must be a JSON object")
    allowed = {
        "manifest_sha256",
        "source_span_id",
        "text",
        "editor",
        "expected_revision",
    }
    if set(payload) != allowed:
        raise WebWorkbenchError(
            "revision request must contain only manifest_sha256, source_span_id, text, "
            "editor, expected_revision"
        )
    manifest_sha256 = _require_manifest_sha256(payload["manifest_sha256"])
    source_span_id = payload["source_span_id"]
    text = payload["text"]
    editor = payload["editor"]
    if not isinstance(source_span_id, str) or not source_span_id.strip():
        raise WebWorkbenchError("source_span_id must be a nonblank string")
    if not isinstance(text, str):
        raise WebWorkbenchError("text must be a string")
    if not isinstance(editor, str) or not editor.strip():
        raise WebWorkbenchError("editor must be a nonblank string")
    return revise_line_transcription(
        project,
        manifest_sha256=manifest_sha256,
        source_span_id=source_span_id,
        text=text,
        editor=editor,
        expected_revision=_require_expected_revision(payload["expected_revision"]),
    )



def _line_geometry_payload(project: Path, payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise WebWorkbenchError("line geometry request must be a JSON object")
    expected = {
        "manifest_sha256",
        "source_span_id",
        "polygon",
        "baseline",
        "editor",
        "expected_revision",
    }
    if set(payload) != expected:
        raise WebWorkbenchError("line geometry request has invalid keys")
    return revise_line_geometry(
        project,
        manifest_sha256=_require_manifest_sha256(payload["manifest_sha256"]),
        source_span_id=payload["source_span_id"],
        polygon=payload["polygon"],
        baseline=payload["baseline"],
        editor=payload["editor"],
        expected_revision=_require_expected_revision(payload["expected_revision"]),
    )


def _region_geometry_payload(project: Path, payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise WebWorkbenchError("region geometry request must be a JSON object")
    expected = {
        "manifest_sha256",
        "page_index",
        "region_id",
        "polygon",
        "editor",
        "expected_revision",
    }
    if set(payload) != expected:
        raise WebWorkbenchError(
            "region geometry request has invalid keys"
        )
    return revise_region_geometry(
        project,
        manifest_sha256=_require_manifest_sha256(payload["manifest_sha256"]),
        page_index=_require_page_index(payload["page_index"]),
        region_id=payload["region_id"],
        polygon=payload["polygon"],
        editor=payload["editor"],
        expected_revision=_require_expected_revision(payload["expected_revision"]),
    )


def _reading_order_payload(project: Path, payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise WebWorkbenchError("reading-order request must be a JSON object")
    expected = {
        "manifest_sha256",
        "page_index",
        "region_ids",
        "editor",
        "expected_revision",
    }
    if set(payload) != expected:
        raise WebWorkbenchError("reading-order request has invalid keys")
    return revise_page_reading_order(
        project,
        manifest_sha256=_require_manifest_sha256(payload["manifest_sha256"]),
        page_index=_require_page_index(payload["page_index"]),
        region_ids=payload["region_ids"],
        editor=payload["editor"],
        expected_revision=_require_expected_revision(payload["expected_revision"]),
    )


def _restoration_payload(project: Path, payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise WebWorkbenchError("restoration request must be a JSON object")
    common = {
        "manifest_sha256",
        "kind",
        "target_revision",
        "editor",
        "expected_revision",
    }
    kind = _require_revision_kind(payload.get("kind"))
    manifest_sha256 = _require_manifest_sha256(payload.get("manifest_sha256"))
    target_revision = _require_target_revision(payload.get("target_revision"))
    expected_revision = _require_expected_revision(payload.get("expected_revision"))
    if kind in {"TRANSCRIPTION", "LINE_GEOMETRY"}:
        if set(payload) != common | {"source_span_id"}:
            raise WebWorkbenchError("line restoration request has invalid keys")
        restore = (
            restore_line_transcription
            if kind == "TRANSCRIPTION"
            else restore_line_geometry
        )
        return restore(
            project,
            manifest_sha256=manifest_sha256,
            source_span_id=payload["source_span_id"],
            target_revision=target_revision,
            editor=payload.get("editor"),
            expected_revision=expected_revision,
        )
    if kind == "READING_ORDER":
        if set(payload) != common | {"page_index"}:
            raise WebWorkbenchError("reading-order restoration request has invalid keys")
        return restore_page_reading_order(
            project,
            manifest_sha256=manifest_sha256,
            page_index=_require_page_index(payload.get("page_index")),
            target_revision=target_revision,
            editor=payload.get("editor"),
            expected_revision=expected_revision,
        )
    if set(payload) != common | {"page_index", "region_id"}:
        raise WebWorkbenchError("region restoration request has invalid keys")
    return restore_region_geometry(
        project,
        manifest_sha256=manifest_sha256,
        page_index=_require_page_index(payload.get("page_index")),
        region_id=payload.get("region_id"),
        target_revision=target_revision,
        editor=payload.get("editor"),
        expected_revision=expected_revision,
    )

def _handler_for_project(project: Path) -> type[BaseHTTPRequestHandler]:
    class ProjectHandler(BaseHTTPRequestHandler):
        server_version = "AKTReaderWorkbench/0.1"

        def log_message(self, _format: str, *_args: object) -> None:
            """Avoid writing project activity or transcription text to a request log."""

        def _headers(self, status: HTTPStatus, content_type: str) -> None:
            self.send_response(status.value)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; "
                "frame-ancestors 'none'",
            )
            self.end_headers()

        def _json(self, status: HTTPStatus, payload: object) -> None:
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8")
            self.wfile.write(encoded)

        def _bytes(self, status: HTTPStatus, media_type: str, content: bytes) -> None:
            self._headers(status, media_type)
            self.wfile.write(content)

        def _error(self, status: HTTPStatus, message: str) -> None:
            self._json(status, {"status": "ERROR", "message": message, "network_required": False})

        def _validate_request_boundary(self) -> None:
            host_values = self.headers.get_all("Host", [])
            if len(host_values) != 1:
                raise _RequestBoundaryError(
                    "request Host must identify this loopback server",
                    status=HTTPStatus.FORBIDDEN,
                )
            authority = host_values[0].strip().lower()
            port = int(self.server.server_address[1])
            allowed_authorities = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if port == 80:
                allowed_authorities.update({"127.0.0.1", "localhost"})
            if authority not in allowed_authorities:
                raise _RequestBoundaryError(
                    "request Host must identify this loopback server",
                    status=HTTPStatus.FORBIDDEN,
                )

            origin_values = self.headers.get_all("Origin", [])
            if len(origin_values) > 1 or (
                origin_values and origin_values[0].strip().lower() != f"http://{authority}"
            ):
                raise _RequestBoundaryError(
                    "request Origin must match this loopback server",
                    status=HTTPStatus.FORBIDDEN,
                )

            fetch_site_values = self.headers.get_all("Sec-Fetch-Site", [])
            if len(fetch_site_values) > 1 or (
                fetch_site_values
                and fetch_site_values[0].strip().lower() not in {"none", "same-origin"}
            ):
                raise _RequestBoundaryError(
                    "cross-origin browser requests are not allowed",
                    status=HTTPStatus.FORBIDDEN,
                )

        def _request_json(self) -> object:
            content_type_values = self.headers.get_all("Content-Type", [])
            if len(content_type_values) != 1 or (
                content_type_values[0].split(";", 1)[0].strip().lower()
                != "application/json"
            ):
                raise _RequestBoundaryError(
                    "write requests require Content-Type application/json",
                    status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                )
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise WebWorkbenchError("request body length is required")
            try:
                content_length = int(raw_length)
            except ValueError as error:
                raise WebWorkbenchError("request body length is invalid") from error
            if content_length < 1 or content_length > MAX_REQUEST_BYTES:
                raise WebWorkbenchError("request body length is outside the allowed range")
            try:
                raw = self.rfile.read(content_length)
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise WebWorkbenchError("request body must be UTF-8 JSON") from error

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
            try:
                self._validate_request_boundary()
                if parsed.path == "/":
                    self._bytes(
                        HTTPStatus.OK,
                        "text/html; charset=utf-8",
                        _INDEX_HTML.encode("utf-8"),
                    )
                elif parsed.path == "/api/healthz":
                    self._json(HTTPStatus.OK, {"status": "READY", "network_required": False})
                elif parsed.path == "/api/project":
                    self._json(HTTPStatus.OK, _project_summary(project))
                elif parsed.path == "/api/pages":
                    self._json(
                        HTTPStatus.OK,
                        _document_pages(project, _query_value(query, "manifest_sha256")),
                    )
                elif parsed.path == "/api/page":
                    self._json(
                        HTTPStatus.OK,
                        _page_payload(
                            project,
                            _query_value(query, "manifest_sha256"),
                            _require_page_index(_query_value(query, "page_index")),
                        ),
                    )
                elif parsed.path == "/api/revision-history":
                    self._json(
                        HTTPStatus.OK,
                        _revision_history_payload(project, query),
                    )
                elif parsed.path == "/api/image":
                    media_type, image = _image_payload(
                        project,
                        _query_value(query, "manifest_sha256"),
                        _require_page_index(_query_value(query, "page_index")),
                    )
                    self._bytes(HTTPStatus.OK, media_type, image)
                elif parsed.path == "/api/thumbnail":
                    media_type, image = _thumbnail_payload(
                        project,
                        _query_value(query, "manifest_sha256"),
                        _require_page_index(_query_value(query, "page_index")),
                    )
                    self._bytes(HTTPStatus.OK, media_type, image)
                else:
                    self._error(HTTPStatus.NOT_FOUND, "route was not found")
            except _RequestBoundaryError as error:
                self._error(error.status, str(error))
            except (ProjectStoreError, WebWorkbenchError) as error:
                self._error(HTTPStatus.BAD_REQUEST, str(error))

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                self._validate_request_boundary()
                payload = self._request_json()
                if parsed.path == "/api/transcriptions":
                    response = _revision_payload(project, payload)
                elif parsed.path == "/api/line-geometry":
                    response = _line_geometry_payload(project, payload)
                elif parsed.path == "/api/region-geometry":
                    response = _region_geometry_payload(project, payload)
                elif parsed.path == "/api/reading-order":
                    response = _reading_order_payload(project, payload)
                elif parsed.path == "/api/restorations":
                    response = _restoration_payload(project, payload)
                else:
                    self._error(HTTPStatus.NOT_FOUND, "route was not found")
                    return
                self._json(HTTPStatus.OK, response)
            except _RequestBoundaryError as error:
                self._error(error.status, str(error))
            except (ProjectStoreError, WebWorkbenchError) as error:
                self._error(HTTPStatus.BAD_REQUEST, str(error))

    return ProjectHandler


def create_self_hosted_workbench_server(
    project: Path | str,
    *,
    port: int = 8765,
) -> SelfHostedWorkbenchServer:
    """Create a loopback-only server for an existing local project without starting it."""

    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise WebWorkbenchError("port must be an integer from 0 to 65535")
    report = inspect_project(project)
    root = Path(str(report["project"])).resolve()
    return SelfHostedWorkbenchServer(root, port=port)


_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AKT Reader Workbench</title>
<style>
:root { color-scheme: light dark; font-family: system-ui, sans-serif; }
body { margin: 0; background: #f5f7fa; color: #18212f; }
header { background: #172a45; color: white; padding: 16px 24px; }
header h1 { margin: 0; font-size: 1.2rem; }
header p { margin: 4px 0 0; color: #dbeafe; font-size: .9rem; }
main { display: grid; grid-template-columns: minmax(0, 3fr) minmax(320px, 2fr);
  gap: 16px; padding: 16px; }
.panel { background: white; border: 1px solid #d9e1ea; border-radius: 8px; padding: 14px; }
.controls { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
#page-thumbnails { display: flex; gap: 8px; overflow-x: auto; margin-bottom: 12px; }
.page-thumb { background: #e2e8f0; border: 2px solid transparent; color: #18212f;
  display: grid; gap: 3px; min-width: 96px; padding: 4px; text-align: center; }
.page-thumb.selected { border-color: #0f766e; }
.page-thumb img { display: block; height: 72px; object-fit: contain; width: 96px; }
label { display: grid; gap: 4px; font-size: .85rem; font-weight: 650; }
select, input, textarea, button { font: inherit; }
select, input, textarea { border: 1px solid #aab8c7; border-radius: 5px;
  padding: 7px; background: white; color: #18212f; }
.scan { position: relative; display: inline-block; max-width: 100%; background: #18212f; }
#image { display: block; max-width: 100%; height: auto; }
#overlay { position: absolute; inset: 0; width: 100%; height: 100%; }
.region-box { fill: rgba(37, 99, 235, .08); stroke: #2563eb; stroke-width: 2; cursor: pointer; }
.region-box.selected { fill: rgba(37, 99, 235, .17); stroke-width: 3; }
.region-handle { fill: #fff; stroke: #1d4ed8; stroke-width: 2; cursor: move;
  touch-action: none; }
.line-box { fill: rgba(245, 158, 11, .12); stroke: #d97706; stroke-width: 2; cursor: pointer; }
.line-box.selected { fill: rgba(22, 163, 74, .16); stroke: #15803d; stroke-width: 3; }
.line-baseline { fill: none; stroke: #7c3aed; stroke-width: 2; pointer-events: none; }
.line-baseline.selected { stroke-width: 3; }
.line-handle, .baseline-handle { fill: #fff; stroke-width: 2; cursor: move;
  touch-action: none; }
.line-handle { stroke: #15803d; }
.baseline-handle { stroke: #7c3aed; }
#line-list { display: grid; gap: 6px; max-height: 300px; overflow: auto; margin-bottom: 12px; }
.line { text-align: left; border: 1px solid #d9e1ea; border-radius: 5px;
  padding: 8px; background: white; color: #18212f; }
.line.selected { outline: 2px solid #15803d; }
small, #status, #dirty-indicator { color: #52616f; }
#dirty-indicator:not(:empty) { color: #9a3412; font-weight: 600; }
textarea { min-height: 120px; resize: vertical; width: 100%; box-sizing: border-box; }
.actions { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
button { background: #0f766e; border: 0; border-radius: 5px; color: white;
  cursor: pointer; padding: 8px 12px; }
button:disabled { cursor: not-allowed; opacity: .55; }
dialog { border: 1px solid #d9e1ea; border-radius: 8px; max-width: 430px; padding: 20px; }
dialog::backdrop { background: rgb(15 23 42 / .45); }
#detail { white-space: pre-wrap; color: #52616f; font-size: .9rem; }
#history-preview { background: #f8fafc; border: 1px solid #d9e1ea; border-radius: 5px;
  box-sizing: border-box; color: #334155; max-height: 220px; overflow: auto;
  padding: 8px; white-space: pre-wrap; }
@media (max-width: 850px) { main { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header><h1>AKT Reader browser workbench</h1>
<p>Single-user, loopback-only, local project data.</p></header>
<main>
<section class="panel">
  <div class="controls">
    <label>Document <select id="document"></select></label>
    <label>Page <select id="page"></select></label>
  </div>
  <div id="page-thumbnails" aria-label="Page thumbnails"></div>
  <div class="scan"><img id="image" alt="Selected source page">
    <svg id="overlay" aria-label="Effective PAGE XML layout geometry"></svg></div>
</section>
<aside class="panel">
  <label>Editor <input id="editor" value="local-user" autocomplete="off"></label>
  <p id="detail">Choose a document and page.</p>
  <div id="line-list" aria-label="Lines"></div>
  <label>Transcription <textarea id="text" disabled></textarea></label>
  <div class="actions"><button id="save" disabled>Save human revision</button>
    <span id="status"></span></div>
  <p id="dirty-indicator" role="status" aria-live="polite"></p>
  <details open>
    <summary>PAGE layout</summary>
    <p><strong>Selected line geometry</strong></p>
    <label>Line polygon (source pixels)
      <textarea id="line-polygon" disabled></textarea>
    </label>
    <label>Line baseline (source pixels or null)
      <textarea id="line-baseline" disabled></textarea>
    </label>
    <div class="actions"><button id="save-line-geometry" disabled>Save line geometry</button></div>
    <label>Region <select id="region"></select></label>
    <label>Polygon (source pixels)
      <textarea id="polygon" disabled></textarea>
    </label>
    <div class="actions"><button id="save-region" disabled>Save region geometry</button></div>
    <p><strong>Reading order</strong></p>
    <div id="reading-order"></div>
    <div class="actions"><button id="save-order" disabled>Save reading order</button></div>
  </details>
  <details>
    <summary>Revision history and restore</summary>
    <p><small>This view contains local revision values, including human text. Restoring appends a
      new audited revision; it never deletes history.</small></p>
    <label>Stream <select id="history-kind">
      <option value="TRANSCRIPTION">Selected line transcription</option>
      <option value="LINE_GEOMETRY">Selected line geometry</option>
      <option value="REGION_GEOMETRY">Selected region geometry</option>
      <option value="READING_ORDER">Page reading order</option>
    </select></label>
    <div class="actions"><button id="load-history">Load history</button></div>
    <label>Older state <select id="history-revision" disabled></select></label>
    <pre id="history-preview">No revision history loaded.</pre>
    <div class="actions">
      <button id="restore-revision" disabled>Restore as new revision</button>
    </div>
  </details>
</aside>
</main>
<dialog id="discard-dialog" aria-labelledby="discard-title">
  <h2 id="discard-title">Discard unsaved changes?</h2>
  <p id="discard-message"></p>
  <form method="dialog" class="actions">
    <button value="cancel" autofocus>Keep editing</button>
    <button value="discard">Discard changes</button>
  </form>
</dialog>
<script>
const state = {
  document: null, page: null, pages: [], lines: [], selected: null, selectedRegion: null,
  regionOrder: [], drag: null, history: null, pageUrl: null
};
const documentSelect = document.getElementById("document");
const pageSelect = document.getElementById("page");
const pageThumbnails = document.getElementById("page-thumbnails");
const image = document.getElementById("image");
const overlay = document.getElementById("overlay");
const lineList = document.getElementById("line-list");
const text = document.getElementById("text");
const editor = document.getElementById("editor");
const save = document.getElementById("save");
const detail = document.getElementById("detail");
const status = document.getElementById("status");
const dirtyIndicator = document.getElementById("dirty-indicator");
const linePolygon = document.getElementById("line-polygon");
const lineBaseline = document.getElementById("line-baseline");
const saveLineGeometry = document.getElementById("save-line-geometry");
const regionSelect = document.getElementById("region");
const polygon = document.getElementById("polygon");
const saveRegion = document.getElementById("save-region");
const readingOrder = document.getElementById("reading-order");
const saveOrder = document.getElementById("save-order");
const historyKind = document.getElementById("history-kind");
const loadHistoryButton = document.getElementById("load-history");
const historyRevision = document.getElementById("history-revision");
const historyPreview = document.getElementById("history-preview");
const restoreRevision = document.getElementById("restore-revision");
const discardDialog = document.getElementById("discard-dialog");
const discardMessage = document.getElementById("discard-message");

overlay.addEventListener("pointermove", moveGeometryDrag);
overlay.addEventListener("pointerup", finishGeometryDrag);
overlay.addEventListener("pointercancel", finishGeometryDrag);

async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.message || "Local request failed");
  return payload;
}
function option(select, value, label) {
  const item = document.createElement("option");
  item.value = value; item.textContent = label; select.append(item);
}
function setStatus(message) { status.textContent = message; }
function selectedLine() { return state.lines.find(line => line.source_span_id === state.selected); }
function selectedRegion() {
  return state.page && state.page.regions.find(region => region.region_id === state.selectedRegion);
}
function jsonDraft(value, fallback) {
  try { return JSON.parse(value); }
  catch (_error) { return fallback; }
}
function jsonDraftDirty(value, current) {
  try { return JSON.stringify(JSON.parse(value)) !== JSON.stringify(current); }
  catch (_error) { return true; }
}
function dirtyStreams() {
  const streams = [];
  const line = selectedLine();
  const region = selectedRegion();
  if (line && text.value !== (line.text === null ? "" : line.text)) {
    streams.push("transcription");
  }
  if (line && (
    jsonDraftDirty(linePolygon.value, line.polygon)
    || jsonDraftDirty(lineBaseline.value, line.baseline)
  )) streams.push("line geometry");
  if (region && jsonDraftDirty(polygon.value, region.polygon)) {
    streams.push("region geometry");
  }
  if (state.page && JSON.stringify(state.regionOrder)
      !== JSON.stringify(state.page.reading_order.region_ids)) {
    streams.push("reading order");
  }
  return streams;
}
function updateDirtyIndicator() {
  const streams = dirtyStreams();
  dirtyIndicator.textContent = streams.length ? "Unsaved: " + streams.join(", ") : "";
}
async function confirmDiscard(streams) {
  const dirty = dirtyStreams().filter(stream => streams.includes(stream));
  if (!dirty.length) return true;
  discardMessage.textContent = "Discard unsaved " + dirty.join(", ") + " changes?";
  discardDialog.returnValue = "cancel";
  discardDialog.showModal();
  return new Promise(resolve => discardDialog.addEventListener(
    "close", () => resolve(discardDialog.returnValue === "discard"), {once: true}
  ));
}
function renderLineDetail() {
  const line = selectedLine();
  if (!line) {
    detail.textContent = state.page
      ? "This page has no text lines."
      : "Choose a document and page.";
    return;
  }
  const suggestion = line.suggestions && line.suggestions[0];
  const review = line.review_proposals
    && line.review_proposals.find(item => item.state === "PENDING");
  detail.textContent = [
    "Line: " + line.line_id + " · text revision " + line.revision
      + " · geometry revision " + line.geometry_revision,
    suggestion ? "Suggestion: " + (suggestion.text || "no text") : "No engine suggestion",
    review ? "Reviewer proposal: " + review.text : "No pending reviewer proposal"
  ].join("\\n");
}
function clearHistory(message) {
  state.history = null;
  historyRevision.replaceChildren();
  historyRevision.disabled = true;
  restoreRevision.disabled = true;
  historyPreview.textContent = message || "No revision history loaded.";
}
async function selectLine(sourceSpanId, discardConfirmed) {
  if (sourceSpanId === state.selected) return true;
  if (!discardConfirmed && !await confirmDiscard(["transcription", "line geometry"])) {
    renderLines(); drawOverlay();
    return false;
  }
  clearHistory();
  state.selected = sourceSpanId;
  const line = selectedLine();
  text.disabled = !line; save.disabled = !line;
  linePolygon.disabled = !line; lineBaseline.disabled = !line; saveLineGeometry.disabled = !line;
  text.value = line && line.text !== null ? line.text : "";
  linePolygon.value = line ? JSON.stringify(line.polygon) : "";
  lineBaseline.value = line ? JSON.stringify(line.baseline) : "";
  renderLines(); drawOverlay();
  renderLineDetail(); updateDirtyIndicator();
  return true;
}
function renderPageThumbnails() {
  pageThumbnails.replaceChildren();
  state.pages.forEach((page, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "page-thumb" + (page.page_url === pageSelect.value ? " selected" : "");
    const preview = document.createElement("img");
    preview.src = page.thumbnail_url;
    preview.alt = "Page " + (index + 1) + ": " + page.page_id;
    const label = document.createElement("small");
    label.textContent = "Page " + (index + 1);
    button.append(preview, label);
    button.addEventListener("click", () => {
      pageSelect.value = page.page_url;
      loadPage().catch(error => setStatus(error.message));
    });
    pageThumbnails.append(button);
  });
}

function renderLines() {
  lineList.replaceChildren();
  state.lines.forEach(line => {
    const button = document.createElement("button");
    button.className = "line" + (line.source_span_id === state.selected ? " selected" : "");
    button.textContent = line.line_id + " · text r" + line.revision
      + " · geometry r" + line.geometry_revision + " · " + (line.text || "∅");
    button.addEventListener("click", () =>
      selectLine(line.source_span_id).catch(error => setStatus(error.message)));
    lineList.append(button);
  });
}
function displayedRegionPolygon(region) {
  return region.region_id === state.selectedRegion
    ? jsonDraft(polygon.value, region.polygon) : region.polygon;
}
function displayedLinePolygon(line) {
  return line.source_span_id === state.selected
    ? jsonDraft(linePolygon.value, line.polygon) : line.polygon;
}
function displayedLineBaseline(line) {
  return line.source_span_id === state.selected
    ? jsonDraft(lineBaseline.value, line.baseline) : line.baseline;
}
function drawOverlay() {
  overlay.replaceChildren();
  if (!state.page) return;
  overlay.setAttribute("viewBox", "0 0 " + state.page.width_px + " " + state.page.height_px);
  state.page.regions.forEach(region => {
    const shape = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    shape.setAttribute(
      "points", displayedRegionPolygon(region).map(point => point.join(",")).join(" ")
    );
    shape.setAttribute(
      "class", "region-box" + (region.region_id === state.selectedRegion ? " selected" : "")
    );
    shape.addEventListener("click", () =>
      selectRegion(region.region_id).catch(error => setStatus(error.message)));
    overlay.append(shape);
  });
  state.lines.forEach(line => {
    const shape = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    shape.setAttribute(
      "points", displayedLinePolygon(line).map(point => point.join(",")).join(" ")
    );
    shape.setAttribute(
      "class", "line-box" + (line.source_span_id === state.selected ? " selected" : "")
    );
    shape.addEventListener("click", () =>
      selectLine(line.source_span_id).catch(error => setStatus(error.message)));
    overlay.append(shape);
    const displayedBaseline = displayedLineBaseline(line);
    if (displayedBaseline) {
      const baseline = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      baseline.setAttribute("points", displayedBaseline.map(point => point.join(",")).join(" "));
      baseline.setAttribute(
        "class",
        "line-baseline" + (line.source_span_id === state.selected ? " selected" : "")
      );
      overlay.append(baseline);
    }
  });
  const activeRegion = selectedRegion();
  if (activeRegion) {
    displayedRegionPolygon(activeRegion).forEach((point, pointIndex) => {
      const handle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      handle.setAttribute("cx", point[0]); handle.setAttribute("cy", point[1]);
      handle.setAttribute("r", "5"); handle.setAttribute("class", "region-handle");
      handle.setAttribute("aria-label", "Drag region vertex " + (pointIndex + 1));
      handle.addEventListener(
        "pointerdown",
        event => beginGeometryDrag("region", activeRegion.region_id, pointIndex, event)
      );
      overlay.append(handle);
    });
  }
  const activeLine = selectedLine();
  if (!activeLine) return;
  displayedLinePolygon(activeLine).forEach((point, pointIndex) => {
    const handle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    handle.setAttribute("cx", point[0]); handle.setAttribute("cy", point[1]);
    handle.setAttribute("r", "5"); handle.setAttribute("class", "line-handle");
    handle.setAttribute("aria-label", "Drag line polygon vertex " + (pointIndex + 1));
    handle.addEventListener(
      "pointerdown",
      event => beginGeometryDrag("line-polygon", activeLine.source_span_id, pointIndex, event)
    );
    overlay.append(handle);
  });
  (displayedLineBaseline(activeLine) || []).forEach((point, pointIndex) => {
    const handle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    handle.setAttribute("cx", point[0]); handle.setAttribute("cy", point[1]);
    handle.setAttribute("r", "5"); handle.setAttribute("class", "baseline-handle");
    handle.setAttribute("aria-label", "Drag line baseline point " + (pointIndex + 1));
    handle.addEventListener(
      "pointerdown",
      event => beginGeometryDrag("line-baseline", activeLine.source_span_id, pointIndex, event)
    );
    overlay.append(handle);
  });
}
async function selectRegion(regionId, discardConfirmed) {
  if (regionId === state.selectedRegion) return true;
  if (!discardConfirmed && !await confirmDiscard(["region geometry"])) {
    regionSelect.value = state.selectedRegion || "";
    drawOverlay();
    return false;
  }
  clearHistory();
  state.selectedRegion = regionId;
  const region = selectedRegion();
  polygon.disabled = !region;
  saveRegion.disabled = !region;
  polygon.value = region ? JSON.stringify(region.polygon) : "";
  regionSelect.value = regionId || "";
  drawOverlay(); updateDirtyIndicator();
  return true;
}

function sourcePoint(event) {
  if (!state.page) return null;
  const rect = overlay.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return null;
  const x = Math.round((event.clientX - rect.left) * state.page.width_px / rect.width);
  const y = Math.round((event.clientY - rect.top) * state.page.height_px / rect.height);
  return [
    Math.max(0, Math.min(state.page.width_px, x)),
    Math.max(0, Math.min(state.page.height_px, y))
  ];
}

function beginGeometryDrag(kind, identity, pointIndex, event) {
  event.preventDefault(); event.stopPropagation();
  if (kind === "region" && identity !== state.selectedRegion) return;
  if (kind !== "region" && identity !== state.selected) return;
  state.drag = { kind: kind, identity: identity, pointIndex: pointIndex };
  overlay.setPointerCapture(event.pointerId);
}

function moveGeometryDrag(event) {
  if (!state.drag || !state.page) return;
  const point = sourcePoint(event);
  if (!point) return;
  if (state.drag.kind === "region") {
    const region = state.page.regions.find(item => item.region_id === state.drag.identity);
    if (!region) return;
    const points = jsonDraft(polygon.value, region.polygon.map(item => [...item]));
    points[state.drag.pointIndex] = point;
    polygon.value = JSON.stringify(points);
  } else {
    const line = state.lines.find(item => item.source_span_id === state.drag.identity);
    if (!line) return;
    const source = state.drag.kind === "line-polygon" ? linePolygon.value : lineBaseline.value;
    const fallback = state.drag.kind === "line-polygon" ? line.polygon : line.baseline;
    const points = jsonDraft(source, fallback ? fallback.map(item => [...item]) : null);
    if (!points) return;
    points[state.drag.pointIndex] = point;
    if (state.drag.kind === "line-polygon") linePolygon.value = JSON.stringify(points);
    else lineBaseline.value = JSON.stringify(points);
  }
  drawOverlay(); updateDirtyIndicator();
}

function finishGeometryDrag(event) {
  if (!state.drag) return;
  state.drag = null;
  if (overlay.hasPointerCapture(event.pointerId)) {
    overlay.releasePointerCapture(event.pointerId);
  }
}

function renderRegions() {
  regionSelect.replaceChildren();
  if (!state.page) return;
  state.page.regions.forEach(region => {
    option(regionSelect, region.region_id, region.region_id + " · revision " + region.revision);
  });
  regionSelect.value = state.selectedRegion || "";
}

function renderReadingOrder() {
  readingOrder.replaceChildren();
  state.regionOrder.forEach((regionId, index) => {
    const row = document.createElement("div");
    row.textContent = (index + 1) + ". " + regionId + " ";
    const up = document.createElement("button");
    up.textContent = "↑";
    up.disabled = index === 0;
    up.addEventListener("click", () => moveRegion(index, -1));
    const down = document.createElement("button");
    down.textContent = "↓";
    down.disabled = index === state.regionOrder.length - 1;
    down.addEventListener("click", () => moveRegion(index, 1));
    row.append(up, down);
    readingOrder.append(row);
  });
  saveOrder.disabled = state.regionOrder.length === 0;
}

function historyLocator(kind) {
  if (!state.page) throw new Error("Choose a page before loading revision history.");
  if (kind === "TRANSCRIPTION" || kind === "LINE_GEOMETRY") {
    const line = selectedLine();
    if (!line) throw new Error("Choose a line before loading this revision history.");
    return {source_span_id: line.source_span_id};
  }
  if (kind === "REGION_GEOMETRY") {
    const region = selectedRegion();
    if (!region) throw new Error("Choose a region before loading this revision history.");
    return {page_index: state.page.page_index, region_id: region.region_id};
  }
  return {page_index: state.page.page_index};
}

function selectedHistoryState() {
  if (!state.history || historyRevision.value === "") return null;
  const targetRevision = Number(historyRevision.value);
  if (targetRevision === 0) return state.history.imported_state;
  const entry = state.history.revisions.find(item => item.revision === targetRevision);
  return entry ? entry.revised_state : null;
}

function renderHistorySelection() {
  const historicalState = selectedHistoryState();
  restoreRevision.disabled = !historicalState;
  historyPreview.textContent = historicalState
    ? JSON.stringify(historicalState, null, 2)
    : "No older revision is available for this stream.";
}

async function loadHistory() {
  const kind = historyKind.value;
  const locator = historyLocator(kind);
  const query = new URLSearchParams({
    manifest_sha256: state.page.manifest_sha256,
    kind: kind,
    ...locator
  });
  setStatus("Loading revision history…");
  const history = await api("/api/revision-history?" + query.toString());
  state.history = history;
  historyRevision.replaceChildren();
  history.revisions
    .filter(item => item.revision < history.current_revision)
    .forEach(item => option(
      historyRevision,
      String(item.revision),
      "Revision " + item.revision + " · " + item.editor + " · " + item.created_at
    ));
  if (history.current_revision > 0) {
    option(historyRevision, "0", "Imported source · revision 0");
  }
  historyRevision.disabled = historyRevision.options.length === 0;
  if (historyRevision.options.length) historyRevision.selectedIndex = 0;
  renderHistorySelection();
  const suffix = history.pagination.has_more ? " (newest 100 shown)" : "";
  setStatus(
    "Loaded " + history.kind.toLowerCase().replaceAll("_", " ")
      + " history" + suffix + "."
  );
}

function moveRegion(index, offset) {
  const target = index + offset;
  if (target < 0 || target >= state.regionOrder.length) return;
  [state.regionOrder[index], state.regionOrder[target]] = [
    state.regionOrder[target], state.regionOrder[index]
  ];
  renderReadingOrder(); updateDirtyIndicator();
}

async function loadPage(discardConfirmed) {
  const targetPageUrl = pageSelect.value;
  if (targetPageUrl !== state.pageUrl && !discardConfirmed && !await confirmDiscard([
    "transcription", "line geometry", "region geometry", "reading order"
  ])) {
    pageSelect.value = state.pageUrl || "";
    renderPageThumbnails();
    return false;
  }
  clearHistory();
  setStatus("");
  let nextPage;
  try { nextPage = await api(targetPageUrl); }
  catch (error) {
    pageSelect.value = state.pageUrl || "";
    renderPageThumbnails();
    throw error;
  }
  state.page = nextPage;
  state.pageUrl = targetPageUrl;
  state.lines = state.page.lines;
  const firstLine = state.lines.length ? state.lines[0].source_span_id : null;
  const firstRegion = state.page.regions.length ? state.page.regions[0].region_id : null;
  state.selected = undefined;
  state.selectedRegion = undefined;
  state.regionOrder = [...state.page.reading_order.region_ids];
  image.src = state.page.image_url;
  renderPageThumbnails(); renderLines(); renderRegions(); renderReadingOrder(); drawOverlay();
  await selectLine(firstLine, true);
  await selectRegion(firstRegion, true);
  updateDirtyIndicator();
  return true;
}
async function loadDocument(discardConfirmed) {
  const targetDocument = documentSelect.value;
  if (targetDocument !== state.document && !discardConfirmed && !await confirmDiscard([
    "transcription", "line geometry", "region geometry", "reading order"
  ])) {
    documentSelect.value = state.document || "";
    return false;
  }
  const response = await api(
    "/api/pages?manifest_sha256=" + encodeURIComponent(targetDocument)
  );
  state.document = targetDocument;
  pageSelect.replaceChildren();
  state.pages = response.pages;
  response.pages.forEach((page, index) => {
    option(pageSelect, page.page_url,
      (index + 1) + " of " + response.pages.length + ". " + page.page_id);
  });
  renderPageThumbnails();
  if (response.pages.length) await loadPage(true);
  return true;
}
async function boot() {
  try {
    const project = await api("/api/project");
    documentSelect.replaceChildren();
    project.documents.forEach((document, index) => {
      option(documentSelect, document.manifest_sha256,
        (index + 1) + ". " + document.title + " (" + document.page_count + " pages)");
    });
    if (project.documents.length) await loadDocument();
    else detail.textContent = "This project has no imported documents.";
  } catch (error) { detail.textContent = error.message; }
}
documentSelect.addEventListener("change", () =>
  loadDocument().catch(error => setStatus(error.message)));
pageSelect.addEventListener("change", () => loadPage().catch(error => setStatus(error.message)));
regionSelect.addEventListener("change", () =>
  selectRegion(regionSelect.value).catch(error => setStatus(error.message)));
text.addEventListener("input", updateDirtyIndicator);
[linePolygon, lineBaseline, polygon].forEach(control => control.addEventListener("input", () => {
  drawOverlay(); updateDirtyIndicator();
}));
window.addEventListener("beforeunload", event => {
  if (!dirtyStreams().length) return;
  event.preventDefault();
  event.returnValue = "";
});
historyKind.addEventListener("change", () => clearHistory());
historyRevision.addEventListener("change", renderHistorySelection);
loadHistoryButton.addEventListener("click", () =>
  loadHistory().catch(error => setStatus(error.message)));
restoreRevision.addEventListener("click", async () => {
  if (!state.history || historyRevision.value === "") return;
  if (!await confirmDiscard([
    "transcription", "line geometry", "region geometry", "reading order"
  ])) return;
  const kind = state.history.kind;
  const selectedSourceSpanId = state.selected;
  const selectedRegionId = state.selectedRegion;
  try {
    const locator = historyLocator(kind);
    setStatus("Restoring revision " + historyRevision.value + "…");
    const result = await api("/api/restorations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        manifest_sha256: state.page.manifest_sha256,
        kind: kind,
        target_revision: Number(historyRevision.value),
        editor: editor.value,
        expected_revision: state.history.current_revision,
        ...locator
      })
    });
    await loadPage(true);
    if (selectedSourceSpanId) await selectLine(selectedSourceSpanId);
    if (selectedRegionId) await selectRegion(selectedRegionId);
    await loadHistory();
    setStatus(result.status === "UNCHANGED"
      ? "The selected historical value is already current."
      : "Restored revision " + result.target_revision
        + " as new revision " + result.revision + ".");
  } catch (error) { setStatus(error.message); }
});
save.addEventListener("click", async () => {
  const line = selectedLine(); if (!line) return;
  try {
    setStatus("Saving…");
    const result = await api("/api/transcriptions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        manifest_sha256: state.page.manifest_sha256,
        source_span_id: line.source_span_id,
        text: text.value,
        editor: editor.value,
        expected_revision: line.revision
      })
    });
    line.text = text.value;
    line.revision = result.revision;
    clearHistory();
    renderLines(); renderLineDetail(); updateDirtyIndicator();
    setStatus(result.status === "UNCHANGED"
      ? "No change to save."
      : "Saved human revision " + result.revision + ".");
  } catch (error) { setStatus(error.message); }
});
saveLineGeometry.addEventListener("click", async () => {
  const line = selectedLine();
  if (!line) return;
  try {
    const revisedPolygon = JSON.parse(linePolygon.value);
    const revisedBaseline = JSON.parse(lineBaseline.value);
    setStatus("Saving line geometry…");
    const result = await api("/api/line-geometry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        manifest_sha256: state.page.manifest_sha256,
        source_span_id: line.source_span_id,
        polygon: revisedPolygon,
        baseline: revisedBaseline,
        editor: editor.value,
        expected_revision: line.geometry_revision
      })
    });
    line.polygon = revisedPolygon;
    line.baseline = revisedBaseline;
    line.geometry_revision = result.revision;
    linePolygon.value = JSON.stringify(revisedPolygon);
    lineBaseline.value = JSON.stringify(revisedBaseline);
    clearHistory();
    renderLines(); renderLineDetail(); drawOverlay(); updateDirtyIndicator();
    setStatus(result.status === "UNCHANGED"
      ? "No line geometry change to save."
      : "Saved line geometry revision " + result.revision + ".");
  } catch (error) { setStatus(error.message); }
});
saveRegion.addEventListener("click", async () => {
  const region = selectedRegion();
  if (!region) return;
  try {
    const revisedPolygon = JSON.parse(polygon.value);
    setStatus("Saving region geometry…");
    const result = await api("/api/region-geometry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        manifest_sha256: state.page.manifest_sha256,
        page_index: state.page.page_index,
        region_id: region.region_id,
        polygon: revisedPolygon,
        editor: editor.value,
        expected_revision: region.revision
      })
    });
    region.polygon = revisedPolygon;
    region.revision = result.revision;
    polygon.value = JSON.stringify(revisedPolygon);
    clearHistory();
    renderRegions(); drawOverlay(); updateDirtyIndicator();
    setStatus(result.status === "UNCHANGED"
      ? "No region geometry change to save."
      : "Saved region geometry revision " + result.revision + ".");
  } catch (error) { setStatus(error.message); }
});
saveOrder.addEventListener("click", async () => {
  try {
    setStatus("Saving reading order…");
    const result = await api("/api/reading-order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        manifest_sha256: state.page.manifest_sha256,
        page_index: state.page.page_index,
        region_ids: state.regionOrder,
        editor: editor.value,
        expected_revision: state.page.reading_order.revision
      })
    });
    state.page.reading_order.region_ids = [...state.regionOrder];
    state.page.reading_order.revision = result.revision;
    clearHistory(); updateDirtyIndicator();
    setStatus(result.status === "UNCHANGED"
      ? "No reading-order change to save."
      : "Saved reading-order revision " + result.revision + ".");
  } catch (error) { setStatus(error.message); }
});
boot();
</script>
</body>
</html>
"""
