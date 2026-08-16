"""Local, provenance-preserving PAGE XML import.

The importer deliberately does not infer an act, overwrite a transcription, or
contact a service.  It turns a locally supplied PAGE XML document and its local
page images into a deterministic manifest that the workbench and future reader
label schema can consume.  Every line retains the PAGE XML identifiers and
geometry needed to trace an assertion back to the source image.
"""

from __future__ import annotations

import hashlib
import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image, UnidentifiedImageError

PAGE_XML_IMPORT_CONTRACT = "pagexml-import"
PAGE_XML_IMPORT_VERSION = "1.0.0"
MAX_PAGE_XML_BYTES = 50 * 1024 * 1024
_FORBIDDEN_XML_DECLARATION = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


class PageXmlImportError(ValueError):
    """Raised when a local PAGE XML source cannot be imported faithfully."""


def _local_path(path: Path | str, *, role: str, directory: bool = False) -> Path:
    raw = os.fspath(path)
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise PageXmlImportError(f"{role} must be a local path, not a URL or UNC path")
    try:
        resolved = Path(raw).resolve(strict=True)
    except OSError as error:
        raise PageXmlImportError(f"{role} is missing or inaccessible: {raw}") from error
    if directory:
        if not resolved.is_dir():
            raise PageXmlImportError(f"{role} is not a directory: {resolved}")
    elif not resolved.is_file():
        raise PageXmlImportError(f"{role} is not a file: {resolved}")
    return resolved


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> Iterator[ET.Element]:
    for child in element:
        if _local_name(child) == name:
            yield child


def _first_child(element: ET.Element, name: str) -> ET.Element | None:
    return next(_children(element, name), None)


def _required_identifier(element: ET.Element, *, field: str) -> str:
    value = element.get("id")
    if not isinstance(value, str) or not value.strip():
        raise PageXmlImportError(f"{field} is missing a nonblank id")
    return value.strip()


def _positive_integer(value: str | None, *, field: str) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError as error:
        raise PageXmlImportError(f"{field} must be an integer") from error
    if parsed < 1:
        raise PageXmlImportError(f"{field} must be at least 1")
    return parsed


def _points(element: ET.Element | None, *, field: str) -> list[list[int]]:
    if element is None:
        raise PageXmlImportError(f"{field} is missing a Coords element")
    raw = element.get("points")
    if not isinstance(raw, str) or not raw.strip():
        raise PageXmlImportError(f"{field}.Coords is missing points")
    points: list[list[int]] = []
    for token in raw.split():
        values = token.split(",")
        if len(values) != 2:
            raise PageXmlImportError(f"{field}.Coords has an invalid point: {token!r}")
        try:
            x, y = int(values[0]), int(values[1])
        except ValueError as error:
            raise PageXmlImportError(
                f"{field}.Coords has a non-integer point: {token!r}"
            ) from error
        if x < 0 or y < 0:
            raise PageXmlImportError(f"{field}.Coords cannot contain negative pixels")
        points.append([x, y])
    if len(points) < 2:
        raise PageXmlImportError(f"{field}.Coords must contain at least two points")
    return points


def _optional_points(element: ET.Element | None, *, field: str) -> list[list[int]] | None:
    if element is None:
        return None
    return _points(element, field=field)


def _bbox(points: list[list[int]], *, field: str) -> dict[str, int | str]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "x": min(xs),
        "y": min(ys),
        "width": max(1, max(xs) - min(xs)),
        "height": max(1, max(ys) - min(ys)),
        "coordinate_space": "source_pixels",
    }


def _verify_within_image(
    points: list[list[int]],
    *,
    width: int,
    height: int,
    field: str,
) -> None:
    for x, y in points:
        if x > width or y > height:
            raise PageXmlImportError(
                f"{field}.Coords falls outside the source image dimensions {width}x{height}"
            )


def _text_equiv(element: ET.Element, *, field: str) -> tuple[str | None, int | None]:
    candidates: list[tuple[int, int, ET.Element]] = []
    for position, candidate in enumerate(_children(element, "TextEquiv")):
        raw_index = candidate.get("index")
        if raw_index is None:
            index = 0
        else:
            try:
                index = int(raw_index)
            except ValueError as error:
                raise PageXmlImportError(f"{field}.TextEquiv index must be an integer") from error
        candidates.append((index, position, candidate))
    if not candidates:
        return None, None
    _, _, selected = min(candidates, key=lambda item: (item[0], item[1]))
    unicode = _first_child(selected, "Unicode")
    if unicode is None:
        return None, selected.get("index") and int(selected.get("index", "0"))
    return "".join(unicode.itertext()), int(selected.get("index", "0"))


def _safe_image_path(*, image_root: Path, image_filename: str, page_field: str) -> Path:
    raw = image_filename.strip()
    if not raw:
        raise PageXmlImportError(f"{page_field}.imageFilename must be nonblank")
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise PageXmlImportError(f"{page_field}.imageFilename must be a local relative path")
    normalized = raw.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if (
        relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or re.match(r"^[A-Za-z]:", normalized)
    ):
        raise PageXmlImportError(f"{page_field}.imageFilename must stay within the image root")
    try:
        resolved = (image_root.joinpath(*relative.parts)).resolve(strict=True)
    except OSError as error:
        raise PageXmlImportError(
            f"{page_field}.imageFilename is missing or inaccessible: {image_filename}"
        ) from error
    if resolved != image_root and image_root not in resolved.parents:
        raise PageXmlImportError(f"{page_field}.imageFilename escapes the image root")
    if not resolved.is_file():
        raise PageXmlImportError(f"{page_field}.imageFilename is not a file: {resolved}")
    return resolved


def _image_metadata(path: Path, *, page_field: str) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
    except (OSError, UnidentifiedImageError) as error:
        raise PageXmlImportError(
            f"{page_field}.imageFilename is not a readable image: {path}"
        ) from error
    if width < 1 or height < 1:
        raise PageXmlImportError(f"{page_field}.imageFilename has invalid dimensions")
    return width, height


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _explicit_region_order(page: ET.Element, region_ids: set[str]) -> list[str] | None:
    references: list[tuple[int, int, str]] = []
    position = 0
    for element in page.iter():
        if _local_name(element) not in {"RegionRef", "RegionRefIndexed"}:
            continue
        reference = element.get("regionRef")
        if reference is None:
            continue
        if reference not in region_ids:
            raise PageXmlImportError(
                f"page {page.get('id', '<unknown>')} reading order references unknown region "
                f"{reference!r}"
            )
        raw_index = element.get("index")
        if raw_index is None:
            index = position
        else:
            try:
                index = int(raw_index)
            except ValueError as error:
                raise PageXmlImportError(
                    f"page {page.get('id', '<unknown>')} reading order index must be an integer"
                ) from error
        references.append((index, position, reference))
        position += 1
    if not references:
        return None
    ordered: list[str] = []
    for _, _, reference in sorted(references):
        if reference not in ordered:
            ordered.append(reference)
    return ordered


def _line_payload(
    element: ET.Element,
    *,
    document_sha256: str,
    page_id: str,
    page_index: int,
    region_id: str | None,
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    line_id = _required_identifier(element, field=f"page {page_id}.TextLine")
    field = f"page {page_id}.TextLine {line_id}"
    polygon = _points(_first_child(element, "Coords"), field=field)
    baseline = _optional_points(_first_child(element, "Baseline"), field=field)
    _verify_within_image(polygon, width=image_width, height=image_height, field=field)
    if baseline is not None:
        _verify_within_image(baseline, width=image_width, height=image_height, field=field)
    text, text_equiv_index = _text_equiv(element, field=field)
    span_digest = hashlib.sha256(
        f"{document_sha256}\0{page_id}\0{line_id}".encode()
    ).hexdigest()[:24]
    source_span_id = f"pagexml-{span_digest}"
    locator: dict[str, Any] = {
        "kind": "PAGE_XML_TEXT_LINE",
        "pagexml_sha256": document_sha256,
        "page_index": page_index,
        "page_id": page_id,
        "region_id": region_id,
        "line_id": line_id,
        "text_equiv_index": text_equiv_index,
        "polygon": polygon,
        "baseline": baseline,
    }
    return {
        "source_span_id": source_span_id,
        "bbox": _bbox(polygon, field=field),
        "description": f"PAGE XML page {page_id}, line {line_id}",
        "locator": locator,
        "text": text,
    }


def _page_payload(
    page: ET.Element,
    *,
    document_sha256: str,
    page_index: int,
    image_root: Path,
) -> dict[str, Any]:
    declared_page_id = page.get("id")
    if isinstance(declared_page_id, str) and declared_page_id.strip():
        page_id = declared_page_id.strip()
        page_id_origin = "PAGE_XML"
    else:
        page_id = f"page-index-{page_index}"
        page_id_origin = "SYNTHETIC_INDEX"
    page_field = f"page {page_id}"
    image_filename = page.get("imageFilename")
    if not isinstance(image_filename, str):
        raise PageXmlImportError(f"{page_field} is missing imageFilename")
    image_path = _safe_image_path(
        image_root=image_root,
        image_filename=image_filename,
        page_field=page_field,
    )
    actual_width, actual_height = _image_metadata(image_path, page_field=page_field)
    declared_width = _positive_integer(page.get("imageWidth"), field=f"{page_field}.imageWidth")
    declared_height = _positive_integer(page.get("imageHeight"), field=f"{page_field}.imageHeight")
    if declared_width is not None and declared_width != actual_width:
        raise PageXmlImportError(
            f"{page_field}.imageWidth={declared_width} does not match source image width "
            f"{actual_width}"
        )
    if declared_height is not None and declared_height != actual_height:
        raise PageXmlImportError(
            f"{page_field}.imageHeight={declared_height} does not match source image height "
            f"{actual_height}"
        )

    regions: dict[str, dict[str, Any]] = {}
    lines: list[dict[str, Any]] = []
    seen_line_ids: set[str] = set()

    def visit(element: ET.Element, active_region_id: str | None) -> None:
        local = _local_name(element)
        region_id = active_region_id
        if local == "TextRegion":
            region_id = _required_identifier(element, field=f"{page_field}.TextRegion")
            if region_id in regions:
                raise PageXmlImportError(
                    f"{page_field} contains duplicate TextRegion id {region_id!r}"
                )
            region_field = f"{page_field}.TextRegion {region_id}"
            polygon = _points(_first_child(element, "Coords"), field=region_field)
            _verify_within_image(
                polygon,
                width=actual_width,
                height=actual_height,
                field=region_field,
            )
            regions[region_id] = {
                "region_id": region_id,
                "region_type": element.get("type") or "TextRegion",
                "bbox": _bbox(polygon, field=region_field),
                "polygon": polygon,
                "line_ids": [],
            }
        elif local == "TextLine":
            line = _line_payload(
                element,
                document_sha256=document_sha256,
                page_id=page_id,
                page_index=page_index,
                region_id=region_id,
                image_width=actual_width,
                image_height=actual_height,
            )
            line_id = line["locator"]["line_id"]
            if line_id in seen_line_ids:
                raise PageXmlImportError(f"{page_field} contains duplicate TextLine id {line_id!r}")
            seen_line_ids.add(line_id)
            lines.append(line)
            if region_id is not None:
                regions[region_id]["line_ids"].append(line_id)
        for child in element:
            visit(child, region_id)

    for child in page:
        visit(child, None)

    region_order = _explicit_region_order(page, set(regions))
    if region_order is None:
        region_order = list(regions)
        order_source = "DOCUMENT_ORDER"
    else:
        region_order.extend(region_id for region_id in regions if region_id not in region_order)
        order_source = "PAGE_XML_READING_ORDER"

    return {
        "page_index": page_index,
        "page_id": page_id,
        "page_id_origin": page_id_origin,
        "image": {
            "path": str(image_path),
            "sha256": _sha256(image_path),
            "width_px": actual_width,
            "height_px": actual_height,
        },
        "regions": [regions[region_id] for region_id in region_order],
        "lines": lines,
        "reading_order": {
            "source": order_source,
            "region_ids": region_order,
            "line_order": [line["locator"]["line_id"] for line in lines],
        },
    }


def import_pagexml(
    source: Path | str,
    *,
    image_root: Path | str | None = None,
    max_bytes: int = MAX_PAGE_XML_BYTES,
) -> dict[str, Any]:
    """Import one local PAGE XML document into a deterministic AKT manifest.

    PAGE XML and page images stay where the owner placed them; the manifest records
    their resolved local paths and SHA-256 digests.  The function has no network
    behavior and rejects DTD/entity declarations instead of expanding them.
    """

    if max_bytes < 1:
        raise PageXmlImportError("max_bytes must be at least 1")
    source_path = _local_path(source, role="PAGE XML source")
    source_size = source_path.stat().st_size
    if source_size > max_bytes:
        raise PageXmlImportError(
            f"PAGE XML source exceeds the {max_bytes}-byte local import limit"
        )
    try:
        source_bytes = source_path.read_bytes()
    except OSError as error:
        raise PageXmlImportError(f"cannot read PAGE XML source: {source_path}") from error
    if _FORBIDDEN_XML_DECLARATION.search(source_bytes):
        raise PageXmlImportError("PAGE XML DTD and entity declarations are forbidden")
    try:
        root = ET.fromstring(source_bytes)
    except ET.ParseError as error:
        raise PageXmlImportError(f"PAGE XML is not well formed: {error}") from error
    if _local_name(root) != "PcGts":
        raise PageXmlImportError("PAGE XML root element must be PcGts")

    if image_root is None:
        resolved_image_root = source_path.parent
    else:
        resolved_image_root = _local_path(image_root, role="PAGE XML image root", directory=True)

    pages = [element for element in root.iter() if _local_name(element) == "Page"]
    if not pages:
        raise PageXmlImportError("PAGE XML contains no Page elements")
    document_sha256 = hashlib.sha256(source_bytes).hexdigest()
    payloads = [
        _page_payload(
            page,
            document_sha256=document_sha256,
            page_index=index,
            image_root=resolved_image_root,
        )
        for index, page in enumerate(pages)
    ]
    page_ids = [page["page_id"] for page in payloads]
    if len(page_ids) != len(set(page_ids)):
        raise PageXmlImportError("PAGE XML contains duplicate Page ids")
    line_count = sum(len(page["lines"]) for page in payloads)
    region_count = sum(len(page["regions"]) for page in payloads)
    transcribed_line_count = sum(
        1 for page in payloads for line in page["lines"] if line["text"] is not None
    )
    return {
        "contract": {
            "name": PAGE_XML_IMPORT_CONTRACT,
            "version": PAGE_XML_IMPORT_VERSION,
        },
        "source": {
            "format": "PAGE_XML",
            "path": str(source_path),
            "sha256": document_sha256,
            "size_bytes": source_size,
            "image_root": str(resolved_image_root),
        },
        "pages": payloads,
        "summary": {
            "page_count": len(payloads),
            "region_count": region_count,
            "line_count": line_count,
            "transcribed_line_count": transcribed_line_count,
            "untranscribed_line_count": line_count - transcribed_line_count,
        },
        "network_required": False,
    }
