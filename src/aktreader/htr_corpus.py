"""Build fail-closed local PAGE XML HTR corpora from consented projects.

A corpus is assembled from current project state rather than from an arbitrary
directory of old exports. This rechecks revision-bound consent immediately
before the corpus is written and emits explicit Kraken train, validation, and
optional test manifests. Nothing in this module downloads, uploads, or runs a
training engine.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aktreader.project import (
    PROJECT_DATABASE_NAME,
    export_consented_training_pagexml,
    export_human_pagexml,
    training_readiness,
)

_PLAN_CONTRACT = {
    "name": "aktreader-local-htr-corpus-plan",
    "version": "1.0.0",
}
_CORPUS_CONTRACT = {
    "name": "aktreader-consented-pagexml-training-corpus",
    "version": "1.0.0",
}
_BUNDLE_CONTRACT = {
    "name": "aktreader-consented-pagexml-training-bundle",
    "version": "1.0.0",
}
_SPLITS = ("train", "validation", "test")
_FORBIDDEN_XML_DECLARATIONS = (b"<!DOCTYPE", b"<!ENTITY")


class HtrCorpusError(ValueError):
    """Raised when a local HTR corpus plan or source bundle is not trustworthy."""


@dataclass(frozen=True)
class CorpusInput:
    """One current project import assigned to one immutable HTR split."""

    project: Path
    manifest_sha256: str
    split: str
    source_pagexml_sha256: str


@dataclass(frozen=True)
class VerifiedBundle:
    """Checksummed evidence about one just-exported local training bundle."""

    bundle_manifest_sha256: str
    source_pagexml_sha256: str
    source_manifest_sha256: str
    pagexml_sha256: str
    pagexml_content_sha256: str
    split: str
    project_id: str
    project_name: str
    page_count: int
    line_count: int
    image_count: int


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_sha256(value: object, *, role: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise HtrCorpusError(f"{role} must be a lowercase SHA-256 string")
    try:
        int(value, 16)
    except ValueError as error:
        raise HtrCorpusError(f"{role} must be a lowercase SHA-256 string") from error
    if value != value.lower():
        raise HtrCorpusError(f"{role} must be a lowercase SHA-256 string")
    return value


def _resolve_local_path(path: Path | str, *, role: str, must_exist: bool) -> Path:
    raw = os.fspath(path)
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise HtrCorpusError(f"{role} must be a local path, not a URL or UNC path")
    candidate = Path(raw)
    try:
        resolved = candidate.resolve(strict=must_exist)
    except OSError as error:
        raise HtrCorpusError(f"{role} is missing or inaccessible: {raw}") from error
    if os.fspath(resolved).startswith(("\\\\", "//")):
        raise HtrCorpusError(f"{role} must not resolve to a UNC path")
    return resolved


def _read_json(path: Path, *, role: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HtrCorpusError(f"{role} is not readable strict JSON: {path}") from error
    if not isinstance(payload, dict):
        raise HtrCorpusError(f"{role} must be a JSON object: {path}")
    return payload


def _required_keys(
    payload: dict[str, Any],
    *,
    required: set[str],
    role: str,
) -> None:
    keys = set(payload)
    if keys != required:
        missing = sorted(required - keys)
        extra = sorted(keys - required)
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if extra:
            detail.append(f"unexpected {', '.join(extra)}")
        raise HtrCorpusError(f"{role} has invalid keys: {'; '.join(detail)}")


def _resolve_plan_project(plan_path: Path, value: object, *, position: int) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise HtrCorpusError(f"plan input {position}.project must be a non-empty local path")
    raw = value.strip()
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise HtrCorpusError(
            f"plan input {position}.project must be a local path, not a URL or UNC path"
        )
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = plan_path.parent / candidate
    project = _resolve_local_path(candidate, role=f"plan input {position}.project", must_exist=True)
    if not project.is_dir():
        raise HtrCorpusError(f"plan input {position}.project is not a directory: {project}")
    return project


def _source_pagexml_sha256(project: Path, manifest_sha256: str) -> str:
    database = project / PROJECT_DATABASE_NAME
    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            """
            SELECT pagexml_sha256
            FROM pagexml_imports
            WHERE manifest_sha256 = ?
            """,
            (manifest_sha256,),
        ).fetchone()
    except sqlite3.Error as error:
        raise HtrCorpusError(f"cannot inspect project training source: {error}") from error
    finally:
        connection.close()
    if row is None:
        raise HtrCorpusError("project PAGE XML import was not found")
    return _require_sha256(row[0], role="project source PAGE XML SHA-256")


def _load_corpus_plan(plan: Path | str) -> tuple[Path, list[CorpusInput]]:
    plan_path = _resolve_local_path(plan, role="HTR corpus plan", must_exist=True)
    if not plan_path.is_file():
        raise HtrCorpusError(f"HTR corpus plan is not a file: {plan_path}")
    payload = _read_json(plan_path, role="HTR corpus plan")
    _required_keys(payload, required={"contract", "inputs"}, role="HTR corpus plan")
    if payload["contract"] != _PLAN_CONTRACT:
        raise HtrCorpusError("HTR corpus plan has an unsupported contract")
    raw_inputs = payload["inputs"]
    if not isinstance(raw_inputs, list) or not raw_inputs:
        raise HtrCorpusError("HTR corpus plan inputs must be a non-empty array")

    inputs: list[CorpusInput] = []
    seen_project_imports: set[tuple[Path, str]] = set()
    seen_source_pagexml: set[str] = set()
    split_counts = {split: 0 for split in _SPLITS}
    for position, raw_input in enumerate(raw_inputs, start=1):
        if not isinstance(raw_input, dict):
            raise HtrCorpusError(f"plan input {position} must be an object")
        _required_keys(
            raw_input,
            required={"project", "manifest_sha256", "split"},
            role=f"plan input {position}",
        )
        project = _resolve_plan_project(plan_path, raw_input["project"], position=position)
        manifest_sha256 = _require_sha256(
            raw_input["manifest_sha256"],
            role=f"plan input {position}.manifest_sha256",
        )
        split = raw_input["split"]
        if split not in _SPLITS:
            allowed = ", ".join(_SPLITS)
            raise HtrCorpusError(f"plan input {position}.split must be one of: {allowed}")
        identity = project, manifest_sha256
        if identity in seen_project_imports:
            raise HtrCorpusError("HTR corpus plan repeats the same project import")
        seen_project_imports.add(identity)

        readiness = training_readiness(project, manifest_sha256=manifest_sha256)
        if readiness["status"] != "READY_FOR_PAGEXML_TRAINING_EXPORT":
            raise HtrCorpusError(
                f"plan input {position} is not currently eligible for training export: "
                f"{readiness['status']}"
            )
        source_pagexml_sha256 = _source_pagexml_sha256(project, manifest_sha256)
        if source_pagexml_sha256 in seen_source_pagexml:
            raise HtrCorpusError(
                "HTR corpus plan repeats a source PAGE XML document across project inputs"
            )
        seen_source_pagexml.add(source_pagexml_sha256)
        split_counts[split] += 1
        inputs.append(
            CorpusInput(
                project=project,
                manifest_sha256=manifest_sha256,
                split=split,
                source_pagexml_sha256=source_pagexml_sha256,
            )
        )
    if split_counts["train"] == 0:
        raise HtrCorpusError("HTR corpus plan must contain at least one train input")
    if split_counts["validation"] == 0:
        raise HtrCorpusError(
            "HTR corpus plan must contain at least one validation input; "
            "random trainer partitioning is not allowed"
        )
    return plan_path, sorted(
        inputs,
        key=lambda item: (_SPLITS.index(item.split), item.manifest_sha256),
    )


def _pagexml_content_sha256(document: ET.Element) -> str:
    """Hash PAGE XML after removing only its local Page image references."""

    normalized = ET.fromstring(ET.tostring(document, encoding="utf-8"))
    for element in normalized.iter():
        if element.tag.rsplit("}", 1)[-1] == "Page":
            element.attrib.pop("imageFilename", None)
    rendered = ET.tostring(normalized, encoding="utf-8", xml_declaration=True)
    return hashlib.sha256(rendered).hexdigest()


def _bundle_path(bundle: Path, value: object, *, role: str) -> Path:
    if not isinstance(value, str) or not value:
        raise HtrCorpusError(f"{role} must be a non-empty bundle-relative path")
    normalized = value.replace("\\", "/")
    if "://" in normalized or normalized.startswith(("/", "\\", "//")):
        raise HtrCorpusError(f"{role} must be a safe bundle-relative path")
    relative = Path(normalized)
    unsafe_parts = any(part in ("", ".", "..") for part in relative.parts)
    if relative.is_absolute() or ":" in normalized or unsafe_parts:
        raise HtrCorpusError(f"{role} must be a safe bundle-relative path")
    try:
        resolved = (bundle / relative).resolve(strict=True)
        resolved.relative_to(bundle)
    except (OSError, ValueError) as error:
        raise HtrCorpusError(f"{role} escapes or is missing from the bundle") from error
    return resolved


def _verify_bundle(
    bundle: Path,
    *,
    source: CorpusInput,
) -> VerifiedBundle:
    manifest_path = bundle / "bundle.aktreader.json"
    payload = _read_json(manifest_path, role="training bundle manifest")
    _required_keys(
        payload,
        required={
            "contract",
            "created_at",
            "project",
            "source_import",
            "split",
            "kraken",
            "files",
            "network_required",
        },
        role="training bundle manifest",
    )
    if payload["contract"] != _BUNDLE_CONTRACT:
        raise HtrCorpusError("training bundle manifest has an unsupported contract")
    if payload["network_required"] is not False:
        raise HtrCorpusError("training bundle must explicitly require no network")
    if payload["split"] != source.split:
        raise HtrCorpusError("training bundle split does not match the corpus plan")

    project = payload["project"]
    if not isinstance(project, dict) or set(project) != {"project_id", "name"}:
        raise HtrCorpusError("training bundle project identity is invalid")
    project_id = project["project_id"]
    project_name = project["name"]
    if not isinstance(project_id, str) or not project_id:
        raise HtrCorpusError("training bundle project ID is invalid")
    if not isinstance(project_name, str) or not project_name:
        raise HtrCorpusError("training bundle project name is invalid")

    source_import = payload["source_import"]
    if not isinstance(source_import, dict):
        raise HtrCorpusError("training bundle source import is invalid")
    _required_keys(
        source_import,
        required={
            "manifest_sha256",
            "source_pagexml_sha256",
            "page_count",
            "eligible_training_line_count",
            "active_consent_grant_count",
        },
        role="training bundle source import",
    )
    source_manifest_sha256 = _require_sha256(
        source_import["manifest_sha256"],
        role="training bundle source import manifest SHA-256",
    )
    source_pagexml_sha256 = _require_sha256(
        source_import["source_pagexml_sha256"],
        role="training bundle source PAGE XML SHA-256",
    )
    if source_manifest_sha256 != source.manifest_sha256:
        raise HtrCorpusError("training bundle import does not match the corpus plan")
    if source_pagexml_sha256 != source.source_pagexml_sha256:
        raise HtrCorpusError("training bundle source PAGE XML does not match the project")
    page_count = source_import["page_count"]
    line_count = source_import["eligible_training_line_count"]
    active_consent_grant_count = source_import["active_consent_grant_count"]
    if (
        isinstance(page_count, bool)
        or not isinstance(page_count, int)
        or page_count < 1
        or isinstance(line_count, bool)
        or not isinstance(line_count, int)
        or line_count < 1
        or isinstance(active_consent_grant_count, bool)
        or not isinstance(active_consent_grant_count, int)
        or active_consent_grant_count < line_count
    ):
        raise HtrCorpusError("training bundle source counts are invalid")

    kraken = payload["kraken"]
    if not isinstance(kraken, dict) or set(kraken) != {
        "format_type",
        "manifest",
        "pagexml",
        "compile_command",
    }:
        raise HtrCorpusError("training bundle Kraken metadata is invalid")
    if kraken["format_type"] != "xml":
        raise HtrCorpusError("training bundle format_type must be xml")
    expected_split_manifest = f"{source.split}.lst"
    if kraken["manifest"] != expected_split_manifest or kraken["pagexml"] != "document.page.xml":
        raise HtrCorpusError("training bundle Kraken paths are invalid")

    files = payload["files"]
    if not isinstance(files, dict) or set(files) != {"pagexml", "manifest", "images"}:
        raise HtrCorpusError("training bundle file inventory is invalid")
    pagexml_entry = files["pagexml"]
    manifest_entry = files["manifest"]
    images = files["images"]
    if not isinstance(pagexml_entry, dict) or set(pagexml_entry) != {"path", "sha256"}:
        raise HtrCorpusError("training bundle PAGE XML inventory is invalid")
    if not isinstance(manifest_entry, dict) or set(manifest_entry) != {"path", "sha256"}:
        raise HtrCorpusError("training bundle split manifest inventory is invalid")
    if pagexml_entry["path"] != "document.page.xml":
        raise HtrCorpusError("training bundle PAGE XML path must be document.page.xml")
    if manifest_entry["path"] != expected_split_manifest:
        raise HtrCorpusError("training bundle split manifest path is invalid")

    pagexml_path = _bundle_path(bundle, pagexml_entry["path"], role="training bundle PAGE XML path")
    split_manifest_path = _bundle_path(
        bundle,
        manifest_entry["path"],
        role="training bundle split manifest path",
    )
    if _sha256_file(pagexml_path) != _require_sha256(
        pagexml_entry["sha256"],
        role="training bundle PAGE XML SHA-256",
    ):
        raise HtrCorpusError("training bundle PAGE XML checksum mismatch")
    if _sha256_file(split_manifest_path) != _require_sha256(
        manifest_entry["sha256"],
        role="training bundle split manifest SHA-256",
    ):
        raise HtrCorpusError("training bundle split manifest checksum mismatch")
    if split_manifest_path.read_text(encoding="utf-8") != "document.page.xml\n":
        raise HtrCorpusError("training bundle split manifest must name its PAGE XML exactly once")

    if not isinstance(images, list) or not images:
        raise HtrCorpusError("training bundle image inventory must be a non-empty array")
    image_digests: dict[str, str] = {}
    for position, image in enumerate(images, start=1):
        if not isinstance(image, dict) or set(image) != {"path", "sha256"}:
            raise HtrCorpusError(f"training bundle image {position} inventory is invalid")
        image_path = image["path"]
        if image_path in image_digests:
            raise HtrCorpusError("training bundle image inventory repeats a path")
        image_digests[image_path] = _require_sha256(
            image["sha256"],
            role=f"training bundle image {position} SHA-256",
        )
        resolved = _bundle_path(bundle, image_path, role=f"training bundle image {position} path")
        if _sha256_file(resolved) != image_digests[image_path]:
            raise HtrCorpusError("training bundle image checksum mismatch")

    pagexml_bytes = pagexml_path.read_bytes()
    if any(marker in pagexml_bytes.upper() for marker in _FORBIDDEN_XML_DECLARATIONS):
        raise HtrCorpusError("training bundle PAGE XML contains a forbidden declaration")
    try:
        document = ET.fromstring(pagexml_bytes)
    except ET.ParseError as error:
        raise HtrCorpusError("training bundle PAGE XML is not well formed") from error
    if document.tag.rsplit("}", 1)[-1] != "PcGts":
        raise HtrCorpusError("training bundle PAGE XML root must be PcGts")
    pages = [element for element in document.iter() if element.tag.rsplit("}", 1)[-1] == "Page"]
    if len(pages) != page_count:
        raise HtrCorpusError("training bundle PAGE XML page count is inconsistent")
    lines = [
        element
        for element in document.iter()
        if element.tag.rsplit("}", 1)[-1] == "TextLine"
    ]
    if len(lines) != line_count:
        raise HtrCorpusError("training bundle PAGE XML line count is inconsistent")
    for line in lines:
        text_equivs = [
            child for child in line if child.tag.rsplit("}", 1)[-1] == "TextEquiv"
        ]
        if not text_equivs:
            raise HtrCorpusError("training bundle PAGE XML line is missing TextEquiv")
        if not any(
            child.tag.rsplit("}", 1)[-1] == "Unicode"
            for text_equiv in text_equivs
            for child in text_equiv
        ):
            raise HtrCorpusError("training bundle PAGE XML line is missing Unicode text")
    referenced_images: set[str] = set()
    for page in pages:
        image_filename = page.get("imageFilename")
        _bundle_path(bundle, image_filename, role="training bundle PAGE XML imageFilename")
        if image_filename not in image_digests:
            raise HtrCorpusError("training bundle PAGE XML image is missing from its inventory")
        referenced_images.add(image_filename)
    if referenced_images != set(image_digests):
        raise HtrCorpusError(
            "training bundle image inventory is not exactly the PAGE XML image set"
        )

    return VerifiedBundle(
        bundle_manifest_sha256=_sha256_file(manifest_path),
        source_pagexml_sha256=source_pagexml_sha256,
        source_manifest_sha256=source_manifest_sha256,
        pagexml_sha256=_sha256_file(pagexml_path),
        pagexml_content_sha256=_pagexml_content_sha256(document),
        split=source.split,
        project_id=project_id,
        project_name=project_name,
        page_count=page_count,
        line_count=line_count,
        image_count=len(image_digests),
    )


def _write_utf8(path: Path, value: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json(path: Path, value: dict[str, Any]) -> None:
    _write_utf8(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def assemble_consented_training_corpus(
    plan: Path | str,
    output_directory: Path | str,
) -> dict[str, object]:
    """Build an atomic local Kraken PAGE XML corpus from current-consent projects.

    Every plan input is rechecked before export. The completed corpus has
    explicit train and validation manifests, refuses duplicate source PAGE XML,
    and never permits the trainer to choose a random partition.
    """

    plan_path, inputs = _load_corpus_plan(plan)
    destination = _resolve_local_path(
        output_directory,
        role="HTR training corpus directory",
        must_exist=False,
    )
    if not destination.parent.is_dir():
        raise HtrCorpusError(
            f"HTR training corpus parent does not exist: {destination.parent}"
        )
    if destination.exists():
        raise HtrCorpusError(
            f"HTR training corpus destination already exists: {destination}"
        )
    for source in inputs:
        if destination == source.project or source.project in destination.parents:
            raise HtrCorpusError(
                "HTR training corpus must be outside every source project"
            )

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    moved = False
    try:
        bundles_directory = temporary / "bundles"
        bundles_directory.mkdir()
        data_directory = temporary / "data"
        data_directory.mkdir()
        split_pagexml: dict[str, list[str]] = {split: [] for split in _SPLITS}
        receipts: list[dict[str, object]] = []

        for source in inputs:
            staged_bundle = bundles_directory / source.manifest_sha256
            export_consented_training_pagexml(
                source.project,
                staged_bundle,
                manifest_sha256=source.manifest_sha256,
                split=source.split,
            )
            verified = _verify_bundle(staged_bundle, source=source)
            corpus_bundle = data_directory / source.manifest_sha256
            shutil.move(str(staged_bundle), str(corpus_bundle))
            relative_pagexml = (
                Path("data") / source.manifest_sha256 / "document.page.xml"
            ).as_posix()
            split_pagexml[source.split].append(relative_pagexml)
            receipts.append(
                {
                    "project": {
                        "project_id": verified.project_id,
                        "name": verified.project_name,
                    },
                    "source_import": {
                        "manifest_sha256": verified.source_manifest_sha256,
                        "source_pagexml_sha256": verified.source_pagexml_sha256,
                    },
                    "split": verified.split,
                    "bundle": {
                        "path": (Path("data") / source.manifest_sha256).as_posix(),
                        "manifest_sha256": verified.bundle_manifest_sha256,
                    },
                    "page_count": verified.page_count,
                    "eligible_training_line_count": verified.line_count,
                    "image_count": verified.image_count,
                }
            )

        for split in _SPLITS:
            paths = split_pagexml[split]
            if paths:
                _write_utf8(temporary / f"{split}.lst", "\n".join(paths) + "\n")

        manifests = {
            split: f"{split}.lst"
            for split in _SPLITS
            if split_pagexml[split]
        }
        corpus_manifest = {
            "contract": _CORPUS_CONTRACT,
            "created_at": _timestamp(),
            "source_plan_sha256": _sha256_file(plan_path),
            "format_type": "xml",
            "inputs": receipts,
            "splits": {
                split: {
                    "manifest": manifests[split],
                    "pagexml_count": len(split_pagexml[split]),
                }
                for split in _SPLITS
                if split in manifests
            },
            "kraken": {
                "working_directory": ".",
                "format_type": "xml",
                "automatic_partitioning": False,
                "train_command": [
                    "ketos",
                    "train",
                    "-f",
                    "xml",
                    "-t",
                    "train.lst",
                    "-e",
                    "validation.lst",
                ],
                "test_command": (
                    [
                        "ketos",
                        "test",
                        "-f",
                        "xml",
                        "-e",
                        "test.lst",
                        "-m",
                        "<local-model-weights>",
                    ]
                    if "test" in manifests
                    else None
                ),
            },
            "network_required": False,
        }
        corpus_manifest_path = temporary / "corpus.aktreader.json"
        _write_json(corpus_manifest_path, corpus_manifest)
        corpus_manifest_sha256 = _sha256_file(corpus_manifest_path)
        shutil.rmtree(bundles_directory)
        os.replace(temporary, destination)
        moved = True
    finally:
        if not moved and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)

    return {
        "status": "SUCCEEDED",
        "corpus": str(destination),
        "corpus_manifest": str(destination / "corpus.aktreader.json"),
        "corpus_manifest_sha256": corpus_manifest_sha256,
        "split_pagexml_counts": {
            split: len(split_pagexml[split])
            for split in _SPLITS
            if split_pagexml[split]
        },
        "network_required": False,
    }



def inspect_consented_training_corpus(
    plan: Path | str,
    corpus_directory: Path | str,
) -> dict[str, object]:
    """Verify a corpus against its current-consent plan without running Kraken.

    The plan is loaded through the same current-revision and active-consent
    gate used during assembly. The on-disk corpus then has to reproduce that
    plan exactly, including each copied PAGE XML bundle and root split list.
    """

    plan_path, inputs = _load_corpus_plan(plan)
    corpus = _resolve_local_path(
        corpus_directory,
        role="HTR training corpus directory",
        must_exist=True,
    )
    if not corpus.is_dir():
        raise HtrCorpusError(f"HTR training corpus is not a directory: {corpus}")
    manifest_path = corpus / "corpus.aktreader.json"
    payload = _read_json(manifest_path, role="HTR corpus manifest")
    _required_keys(
        payload,
        required={
            "contract",
            "created_at",
            "source_plan_sha256",
            "format_type",
            "inputs",
            "splits",
            "kraken",
            "network_required",
        },
        role="HTR corpus manifest",
    )
    if payload["contract"] != _CORPUS_CONTRACT:
        raise HtrCorpusError("HTR corpus manifest has an unsupported contract")
    if payload["network_required"] is not False:
        raise HtrCorpusError("HTR corpus manifest must explicitly require no network")
    if payload["format_type"] != "xml":
        raise HtrCorpusError("HTR corpus manifest format_type must be xml")
    source_plan_sha256 = _require_sha256(
        payload["source_plan_sha256"],
        role="HTR corpus source plan SHA-256",
    )
    if source_plan_sha256 != _sha256_file(plan_path):
        raise HtrCorpusError("HTR corpus does not match the supplied corpus plan")

    receipts = payload["inputs"]
    if not isinstance(receipts, list) or len(receipts) != len(inputs):
        raise HtrCorpusError("HTR corpus receipt count does not match the corpus plan")
    current_directory = Path(
        tempfile.mkdtemp(prefix=".aktreader-htr-current.", dir=corpus.parent)
    )
    split_pagexml: dict[str, list[str]] = {split: [] for split in _SPLITS}
    try:
        for source, receipt in zip(inputs, receipts, strict=True):
            if not isinstance(receipt, dict):
                raise HtrCorpusError("HTR corpus input receipt must be an object")
            _required_keys(
                receipt,
                required={
                    "project",
                    "source_import",
                    "split",
                    "bundle",
                    "page_count",
                    "eligible_training_line_count",
                    "image_count",
                },
                role="HTR corpus input receipt",
            )
            expected_bundle_path = (Path("data") / source.manifest_sha256).as_posix()
            bundle = receipt["bundle"]
            if not isinstance(bundle, dict) or set(bundle) != {"path", "manifest_sha256"}:
                raise HtrCorpusError("HTR corpus bundle receipt is invalid")
            if bundle["path"] != expected_bundle_path:
                raise HtrCorpusError("HTR corpus bundle path does not match the corpus plan")
            _require_sha256(bundle["manifest_sha256"], role="HTR corpus bundle manifest SHA-256")
            bundle_directory = _bundle_path(
                corpus,
                bundle["path"],
                role="HTR corpus bundle path",
            )
            if not bundle_directory.is_dir():
                raise HtrCorpusError("HTR corpus bundle path is not a directory")
            verified = _verify_bundle(bundle_directory, source=source)
            expected_receipt = {
                "project": {
                    "project_id": verified.project_id,
                    "name": verified.project_name,
                },
                "source_import": {
                    "manifest_sha256": verified.source_manifest_sha256,
                    "source_pagexml_sha256": verified.source_pagexml_sha256,
                },
                "split": verified.split,
                "bundle": {
                    "path": expected_bundle_path,
                    "manifest_sha256": verified.bundle_manifest_sha256,
                },
                "page_count": verified.page_count,
                "eligible_training_line_count": verified.line_count,
                "image_count": verified.image_count,
            }
            if receipt != expected_receipt:
                raise HtrCorpusError("HTR corpus input receipt does not match its checked bundle")
            readiness = training_readiness(
                source.project,
                manifest_sha256=source.manifest_sha256,
            )
            if readiness["status"] != "READY_FOR_PAGEXML_TRAINING_EXPORT":
                raise HtrCorpusError(
                    "HTR corpus source lost current training eligibility during inspection"
                )
            current_pagexml = current_directory / f"{source.manifest_sha256}.page.xml"
            export_human_pagexml(
                source.project,
                current_pagexml,
                manifest_sha256=source.manifest_sha256,
            )
            try:
                current_document = ET.fromstring(current_pagexml.read_bytes())
            except (OSError, ET.ParseError) as error:
                raise HtrCorpusError(
                    "current project PAGE XML cannot be checked against the corpus"
                ) from error
            if _pagexml_content_sha256(current_document) != verified.pagexml_content_sha256:
                raise HtrCorpusError(
                    "HTR corpus PAGE XML does not match current consented project content"
                )
            split_pagexml[source.split].append(
                (Path("data") / source.manifest_sha256 / "document.page.xml").as_posix()
            )
    finally:
        shutil.rmtree(current_directory, ignore_errors=True)

    expected_splits = {
        split: {
            "manifest": f"{split}.lst",
            "pagexml_count": len(split_pagexml[split]),
        }
        for split in _SPLITS
        if split_pagexml[split]
    }
    if payload["splits"] != expected_splits:
        raise HtrCorpusError("HTR corpus split receipt does not match its input bundles")
    for split, expected in expected_splits.items():
        manifest = _bundle_path(
            corpus,
            expected["manifest"],
            role=f"HTR corpus {split} manifest path",
        )
        expected_content = "\n".join(split_pagexml[split]) + "\n"
        if manifest.read_text(encoding="utf-8") != expected_content:
            raise HtrCorpusError(f"HTR corpus {split} manifest does not match its split")
    for split in _SPLITS:
        if split not in expected_splits and (corpus / f"{split}.lst").exists():
            raise HtrCorpusError(f"HTR corpus has an unexpected {split} manifest")

    expected_kraken = {
        "working_directory": ".",
        "format_type": "xml",
        "automatic_partitioning": False,
        "train_command": [
            "ketos",
            "train",
            "-f",
            "xml",
            "-t",
            "train.lst",
            "-e",
            "validation.lst",
        ],
        "test_command": (
            [
                "ketos",
                "test",
                "-f",
                "xml",
                "-e",
                "test.lst",
                "-m",
                "<local-model-weights>",
            ]
            if "test" in expected_splits
            else None
        ),
    }
    if payload["kraken"] != expected_kraken:
        raise HtrCorpusError("HTR corpus Kraken command receipt is invalid")

    return {
        "status": "READY_FOR_LOCAL_KRAKEN_TRAINING",
        "corpus": str(corpus),
        "corpus_manifest": str(manifest_path),
        "corpus_manifest_sha256": _sha256_file(manifest_path),
        "source_plan_sha256": source_plan_sha256,
        "split_pagexml_counts": {
            split: len(split_pagexml[split])
            for split in _SPLITS
            if split_pagexml[split]
        },
        "network_required": False,
    }
