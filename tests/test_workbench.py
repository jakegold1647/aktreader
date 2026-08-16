from __future__ import annotations

import pytest

from aktreader.workbench import WorkbenchError, _document_page_groups


def _document(manifest_sha256: str, title: str, page_count: int) -> dict[str, object]:
    return {
        "manifest_sha256": manifest_sha256,
        "title": title,
        "page_count": page_count,
    }


def _page(manifest_sha256: str, page_index: int, page_id: str) -> dict[str, object]:
    return {
        "manifest_sha256": manifest_sha256,
        "page_index": page_index,
        "page_id": page_id,
    }


def test_document_page_groups_keep_page_navigation_within_each_document() -> None:
    first = "a" * 64
    second = "b" * 64
    groups = _document_page_groups(
        [
            _document(first, "Serock births, 1831", 2),
            _document(second, "Serock deaths, 1831", 1),
        ],
        [
            _page(first, 0, "births-1"),
            _page(first, 1, "births-2"),
            _page(second, 0, "deaths-1"),
        ],
    )

    assert [document["title"] for document, _pages in groups] == [
        "Serock births, 1831",
        "Serock deaths, 1831",
    ]
    assert [[page["page_id"] for page in pages] for _document, pages in groups] == [
        ["births-1", "births-2"],
        ["deaths-1"],
    ]


def test_document_page_groups_reject_pages_without_a_document() -> None:
    with pytest.raises(WorkbenchError, match="missing document metadata"):
        _document_page_groups(
            [_document("a" * 64, "Serock births, 1831", 1)],
            [_page("b" * 64, 0, "unknown-page")],
        )
