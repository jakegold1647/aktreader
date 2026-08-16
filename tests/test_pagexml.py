from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from aktreader.pagexml import PageXmlImportError, import_pagexml


def _write_image(path: Path, *, width: int = 100, height: int = 80) -> None:
    Image.new("L", (width, height), color=255).save(path)


def _write_pagexml(
    path: Path,
    *,
    image_filename: str = "page.png",
    image_width: int = 100,
    image_height: int = 80,
    include_text: bool = True,
) -> None:
    text_equiv = "<TextEquiv index=\"0\"><Unicode>Александр</Unicode></TextEquiv>" if include_text else ""
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
  <Page id="page-1" imageFilename="{image_filename}" imageWidth="{image_width}" imageHeight="{image_height}">
    <ReadingOrder>
      <OrderedGroup id="ro">
        <RegionRefIndexed index="0" regionRef="region-2"/>
        <RegionRefIndexed index="1" regionRef="region-1"/>
      </OrderedGroup>
    </ReadingOrder>
    <TextRegion id="region-1" type="paragraph">
      <Coords points="10,10 90,10 90,35 10,35"/>
      <TextLine id="line-1">
        <Coords points="12,12 88,12 88,22 12,22"/>
        <Baseline points="12,20 88,20"/>
        {text_equiv}
      </TextLine>
    </TextRegion>
    <TextRegion id="region-2">
      <Coords points="10,40 90,40 90,70 10,70"/>
      <TextLine id="line-2">
        <Coords points="12,45 88,45 88,55 12,55"/>
        <TextEquiv><Unicode>Иван</Unicode></TextEquiv>
      </TextLine>
    </TextRegion>
  </Page>
</PcGts>
""",
        encoding="utf-8",
    )


def test_import_pagexml_preserves_line_provenance_and_geometry(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    source = tmp_path / "page.xml"
    _write_image(image)
    _write_pagexml(source)

    first = import_pagexml(source)
    second = import_pagexml(source)

    assert first == second
    assert first["contract"] == {"name": "pagexml-import", "version": "1.0.0"}
    assert first["network_required"] is False
    assert first["summary"] == {
        "page_count": 1,
        "region_count": 2,
        "line_count": 2,
        "transcribed_line_count": 2,
        "untranscribed_line_count": 0,
    }

    page = first["pages"][0]
    assert page["image"]["path"] == str(image.resolve())
    assert page["image"]["width_px"] == 100
    assert page["image"]["height_px"] == 80
    assert [region["region_id"] for region in page["regions"]] == ["region-2", "region-1"]
    assert page["reading_order"] == {
        "source": "PAGE_XML_READING_ORDER",
        "region_ids": ["region-2", "region-1"],
        "line_order": ["line-1", "line-2"],
    }

    line = page["lines"][0]
    assert line["text"] == "Александр"
    assert line["bbox"] == {
        "x": 12,
        "y": 12,
        "width": 76,
        "height": 10,
        "coordinate_space": "source_pixels",
    }
    assert line["locator"] == {
        "kind": "PAGE_XML_TEXT_LINE",
        "pagexml_sha256": first["source"]["sha256"],
        "page_index": 0,
        "page_id": "page-1",
        "region_id": "region-1",
        "line_id": "line-1",
        "text_equiv_index": 0,
        "polygon": [[12, 12], [88, 12], [88, 22], [12, 22]],
        "baseline": [[12, 20], [88, 20]],
    }
    assert line["source_span_id"].startswith("pagexml-")
    assert len(line["source_span_id"]) == len("pagexml-") + 24


def test_import_pagexml_supports_a_separate_local_image_root(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    image_root = tmp_path / "images"
    source_root.mkdir()
    image_root.mkdir()
    _write_image(image_root / "page.png")
    source = source_root / "page.xml"
    _write_pagexml(source)

    payload = import_pagexml(source, image_root=image_root)

    assert payload["source"]["image_root"] == str(image_root.resolve())
    assert payload["pages"][0]["image"]["path"] == str((image_root / "page.png").resolve())


def test_import_pagexml_retains_untranscribed_lines(tmp_path: Path) -> None:
    _write_image(tmp_path / "page.png")
    source = tmp_path / "page.xml"
    _write_pagexml(source, include_text=False)

    payload = import_pagexml(source)

    assert payload["pages"][0]["lines"][0]["text"] is None
    assert payload["pages"][0]["lines"][0]["locator"]["text_equiv_index"] is None
    assert payload["summary"]["transcribed_line_count"] == 1
    assert payload["summary"]["untranscribed_line_count"] == 1


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        (
            """<!DOCTYPE PcGts [<!ENTITY injection "x">]>
<PcGts><Page id="page-1" imageFilename="page.png"/></PcGts>""",
            "DTD and entity declarations are forbidden",
        ),
        ("<not-page/>", "root element must be PcGts"),
    ],
)
def test_import_pagexml_rejects_unsafe_or_non_pagexml_input(
    tmp_path: Path,
    xml: str,
    message: str,
) -> None:
    _write_image(tmp_path / "page.png")
    source = tmp_path / "source.xml"
    source.write_text(xml, encoding="utf-8")

    with pytest.raises(PageXmlImportError, match=message):
        import_pagexml(source)


def test_import_pagexml_rejects_image_dimension_mismatch(tmp_path: Path) -> None:
    _write_image(tmp_path / "page.png")
    source = tmp_path / "page.xml"
    _write_pagexml(source, image_width=99)

    with pytest.raises(PageXmlImportError, match="does not match source image width"):
        import_pagexml(source)


def test_import_pagexml_rejects_image_path_escape(tmp_path: Path) -> None:
    _write_image(tmp_path / "page.png")
    source = tmp_path / "page.xml"
    _write_pagexml(source, image_filename="../page.png")

    with pytest.raises(PageXmlImportError, match="must stay within the image root"):
        import_pagexml(source)


def test_pagexml_manifest_is_json_serializable(tmp_path: Path) -> None:
    _write_image(tmp_path / "page.png")
    source = tmp_path / "page.xml"
    _write_pagexml(source)

    rendered = json.dumps(import_pagexml(source), ensure_ascii=False, sort_keys=True)

    assert "PAGE_XML_TEXT_LINE" in rendered
