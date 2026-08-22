"""Strictly local command-line interface for the P2 pipeline."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aktreader import (
    COMMAND_NAME,
    DISTRIBUTION_NAME,
    PACKAGE_NAMESPACE,
    PROJECT_NAME,
    PROJECT_ROLE,
    REPOSITORY_URL,
    __version__,
)
from aktreader.adjudication import generate_packet, ingest_answers
from aktreader.assets import inspect_packaged_runtime_assets, runtime_asset_path
from aktreader.batch import (
    BatchJob,
    BatchRunner,
    InferenceIdentity,
    atomic_write_json,
    atomic_write_text,
    load_manifest_jobs,
)
from aktreader.cli_support import (
    CliConfigurationError,
    brief_for_job,
    generation_report,
    kraken_report,
    load_json_object,
    load_kraken_config,
    load_local_reader_config,
    load_strict_json,
    local_input_path,
    local_output_path,
    model_identity,
    reader_report,
    require_keys,
    require_local_only_data,
)
from aktreader.collection import (
    add_project_to_collection,
    create_collection,
    export_public_collection,
    inspect_collection,
    list_collection_documents,
    list_collection_saved_searches,
    run_collection_saved_search,
    save_collection_search,
    search_collection,
)
from aktreader.comparison import compare_reader_labels, render_disagreements_csv
from aktreader.consensus import merge_labels
from aktreader.consensus_record import build_consensus_record, write_consensus_record
from aktreader.evaluation import (
    evaluate_predictions,
    load_prediction_records,
    render_stratified_markdown,
)
from aktreader.grounding import (
    load_grounded_reader_label,
    paired_quality_metrics,
    validate_cross_reader_grounding,
)
from aktreader.htr_corpus import (
    assemble_consented_training_corpus,
    inspect_consented_training_corpus,
)
from aktreader.installation import inspect_application_checkout
from aktreader.kraken import KrakenError, LocalKraken
from aktreader.kraken_training import (
    KrakenEvaluationError,
    KrakenTrainingError,
    run_kraken_evaluation,
    run_kraken_training,
)
from aktreader.local_reader import LocalReader, LocalReaderError
from aktreader.pagexml import import_pagexml
from aktreader.project import (
    create_project,
    evaluate_htr_suggestions,
    export_consented_training_pagexml,
    export_human_alto,
    export_human_pagexml,
    export_human_pdf,
    export_human_transcript,
    export_human_transcriptions_csv,
    export_review_package,
    grant_training_consent,
    import_htr_suggestions,
    import_images_into_project,
    import_pagexml_into_project,
    import_pdf_into_project,
    import_review_package,
    inspect_project,
    list_project_documents,
    recognize_project_with_kraken,
    resolve_review_proposal,
    revise_line_geometry,
    revise_page_reading_order,
    revise_region_geometry,
    revoke_training_consent,
    search_project_transcriptions,
    segment_project_with_kraken,
    training_readiness,
    update_project_document,
)
from aktreader.prompt import verify_reader_prompt
from aktreader.service import (
    LOOPBACK_HOST,
    ServiceError,
    activate_service_project_model,
    add_project_to_service,
    attach_service_artifact,
    create_local_account,
    create_self_hosted_service_server,
    create_service_workspace,
    grant_project_role,
    inspect_service_workspace,
    list_local_accounts,
    list_service_artifacts,
    list_service_project_model_releases,
    list_service_projects,
    queue_project_backup,
    queue_service_project_kraken_training,
    register_service_artifact,
    restore_project_backup,
    rollback_service_project_model,
    verify_project_backup,
)
from aktreader.validators.dates import validate_dates
from aktreader.validators.formula import validate_formula_positions
from aktreader.verification import CHECK_NAMES, verify_application_checkout
from aktreader.web_workbench import create_self_hosted_workbench_server
from aktreader.workbench import launch_workbench

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACT_RECORD_SCHEMA_PATH = runtime_asset_path("schemas/act-record-2.0.0.schema.json")


def _source_checkout_default(relative_path: str) -> Path | None:
    candidate = PROJECT_ROOT / relative_path
    return candidate if candidate.exists() else None


def _emit_json(payload: Mapping[str, Any], *, stream: Any = None) -> None:
    target = sys.stdout if stream is None else stream
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    encoding = getattr(target, "encoding", None)
    if encoding:
        try:
            rendered.encode(encoding)
        except UnicodeEncodeError:
            rendered = rendered.encode(encoding, errors="backslashreplace").decode(encoding)
    target.write(rendered)
    target.write("\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the local-only parser without import-time runtime execution."""
    parser = argparse.ArgumentParser(
        prog=COMMAND_NAME,
        description="AKT Reader Application: Local-only civil-register extraction (P2).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=(
            f"%(prog)s {__version__} "
            f"({PROJECT_NAME}; distribution: {DISTRIBUTION_NAME})"
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    doctor = subparsers.add_parser("doctor", help="report the local pipeline environment")
    doctor.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    doctor.add_argument(
        "--inspect-root",
        type=Path,
        help=(
            "diagnose contracts in another local checkout without reconfiguring "
            "the running Application"
        ),
    )

    checkout_verify = subparsers.add_parser(
        "checkout-verify",
        help="verify the public Application checkout without scans or model weights",
    )
    checkout_verify.add_argument("--root", type=Path, default=PROJECT_ROOT)
    checkout_verify.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    prompt = subparsers.add_parser(
        "prompt-verify", help="verify the frozen Reader prompt and source-skill bindings"
    )
    prompt.add_argument("--root", type=Path, default=PROJECT_ROOT)

    labels = subparsers.add_parser(
        "label-validate", help="validate external blind-reader label JSON files"
    )
    labels.add_argument("labels", nargs="+", type=Path)

    collection_create = subparsers.add_parser("collection-create", help="create a local collection")
    collection_create.add_argument("collection", type=Path)
    collection_create.add_argument("--name", required=True)
    collection_add = subparsers.add_parser(
        "collection-add-project", help="add or refresh a local project in a collection"
    )
    collection_add.add_argument("collection", type=Path)
    collection_add.add_argument("project", type=Path)
    collection_inspect = subparsers.add_parser(
        "collection-inspect",
        help="inspect a local collection",
    )
    collection_inspect.add_argument("collection", type=Path)
    collection_documents = subparsers.add_parser(
        "collection-list-documents",
        help="list local collection documents and search their metadata",
    )
    collection_documents.add_argument("collection", type=Path)
    collection_documents.add_argument("--query")
    collection_documents.add_argument("--limit", type=int, default=100)
    collection_search = subparsers.add_parser(
        "collection-search",
        help="search a local collection",
    )
    collection_search.add_argument("collection", type=Path)
    collection_search.add_argument("query")
    collection_search.add_argument("--limit", type=int, default=100)
    collection_save_search = subparsers.add_parser(
        "collection-save-search",
        help="create or update one private named collection search",
    )
    collection_save_search.add_argument("collection", type=Path)
    collection_save_search.add_argument("--name", required=True)
    collection_save_search.add_argument("--query", required=True)
    collection_saved_searches = subparsers.add_parser(
        "collection-list-saved-searches",
        help="list private named collection searches",
    )
    collection_saved_searches.add_argument("collection", type=Path)
    collection_run_search = subparsers.add_parser(
        "collection-run-saved-search",
        help="run one private named collection search",
    )
    collection_run_search.add_argument("collection", type=Path)
    collection_run_search.add_argument("--search-id", required=True)
    collection_run_search.add_argument("--limit", type=int, default=100)
    collection_publish = subparsers.add_parser(
        "collection-export-public",
        help="write an explicit static public collection release",
    )
    collection_publish.add_argument("collection", type=Path)
    collection_publish.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new static release directory outside the collection",
    )
    collection_publish.add_argument(
        "--license-id",
        required=True,
        help="declared license for the public collection release",
    )
    collection_publish.add_argument(
        "--confirm-public",
        action="store_true",
        help="confirm that the selected indexed text and metadata may be public",
    )

    project_create = subparsers.add_parser(
        "project-create",
        help="create an empty local AKT Reader workbench project",
    )
    project_create.add_argument("project", type=Path, help="new local .aktproj directory")
    project_create.add_argument("--name", required=True, help="human-readable project name")

    project_inspect = subparsers.add_parser(
        "project-inspect",
        help="inspect one local AKT Reader workbench project",
    )
    project_inspect.add_argument("project", type=Path, help="local .aktproj directory")

    project_documents = subparsers.add_parser(
        "project-list-documents",
        help="list local PAGE XML document records",
    )
    project_documents.add_argument("project", type=Path, help="local .aktproj directory")

    project_search = subparsers.add_parser(
        "project-search",
        help="search effective local transcription text or document metadata",
    )
    project_search.add_argument("project", type=Path, help="local .aktproj directory")
    project_search.add_argument("query", help="case-insensitive local search text")
    project_search.add_argument(
        "--field",
        choices=("text", "title", "tag"),
        default="text",
        help="field to search (default: text)",
    )
    project_search.add_argument(
        "--limit",
        type=int,
        default=50,
        help="maximum results from 1 to 100 (default: 50)",
    )

    project_document_update = subparsers.add_parser(
        "project-update-document",
        help="update title, tags, or notes for one local document",
    )
    project_document_update.add_argument("project", type=Path, help="local .aktproj directory")
    project_document_update.add_argument(
        "--manifest-sha256",
        required=True,
        help="document PAGE XML import manifest SHA-256",
    )
    project_document_update.add_argument(
        "--metadata",
        required=True,
        type=Path,
        help="strict local JSON object with title, tags, and/or notes",
    )

    project_import = subparsers.add_parser(
        "project-import-pagexml",
        help="copy local PAGE XML and page images into a local workbench project",
    )
    project_import.add_argument("project", type=Path, help="local .aktproj directory")
    project_import.add_argument("source", type=Path, help="local PAGE XML source")
    project_import.add_argument(
        "--image-root",
        type=Path,
        help="local directory containing imageFilename paths (defaults to the XML directory)",
    )

    project_import_images = subparsers.add_parser(
        "project-import-images",
        help="create one local PAGE XML document from a directory of page images",
    )
    project_import_images.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_import_images.add_argument(
        "source_directory",
        type=Path,
        help="local directory of top-level page images",
    )
    project_import_images.add_argument(
        "--title",
        help="optional document title (defaults to the image directory name)",
    )

    project_import_pdf = subparsers.add_parser(
        "project-import-pdf",
        help="render one local PDF into an editable PAGE XML document",
    )
    project_import_pdf.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_import_pdf.add_argument("source", type=Path, help="local PDF source")
    project_import_pdf.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="local render DPI from 72 to 600 (default: 300)",
    )
    project_import_pdf.add_argument(
        "--title",
        help="optional document title (defaults to the PDF filename)",
    )

    project_htr_suggestions = subparsers.add_parser(
        "project-import-htr-suggestions",
        help="store one aligned local PAGE XML recognition result as project suggestions",
    )
    project_htr_suggestions.add_argument("project", type=Path, help="local .aktproj directory")
    project_htr_suggestions.add_argument("source", type=Path, help="local recognition PAGE XML")
    project_htr_suggestions.add_argument(
        "--manifest-sha256",
        required=True,
        help="target PAGE XML project-import manifest SHA-256",
    )
    project_htr_suggestions.add_argument(
        "--engine",
        default="kraken",
        help="local recognition engine identifier (default: kraken)",
    )
    project_htr_suggestions.add_argument(
        "--runtime-fingerprint",
        required=True,
        help="SHA-256 fingerprint reported by the local recognition run",
    )
    project_htr_suggestions.add_argument(
        "--image-root",
        type=Path,
        help="local directory containing the recognition XML imageFilename paths",
    )

    project_kraken_layout = subparsers.add_parser(
        "project-kraken-segment",
        help="derive one editable PAGE XML layout document from local project images",
    )
    project_kraken_layout.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_kraken_layout.add_argument(
        "--manifest-sha256",
        required=True,
        help="source image/PAGE XML project-import manifest SHA-256",
    )
    project_kraken_layout.add_argument(
        "--config",
        required=True,
        type=Path,
        help="checksum-pinned local Kraken configuration JSON",
    )
    project_kraken_layout.add_argument(
        "--title",
        help="optional title for the derived layout document",
    )

    project_kraken = subparsers.add_parser(
        "project-kraken-recognize",
        help="recognize one imported project document with pinned local Kraken",
    )
    project_kraken.add_argument("project", type=Path, help="local .aktproj directory")
    project_kraken.add_argument(
        "--manifest-sha256",
        required=True,
        help="target PAGE XML project-import manifest SHA-256",
    )
    project_kraken.add_argument(
        "--config",
        required=True,
        type=Path,
        help="checksum-pinned local Kraken configuration JSON",
    )


    project_export = subparsers.add_parser(
        "project-export-pagexml",
        help="export latest human revisions as a new local PAGE XML document",
    )
    project_export.add_argument("project", type=Path, help="local .aktproj directory")
    project_export.add_argument(
        "--manifest-sha256",
        required=True,
        help="source PAGE XML project-import manifest SHA-256",
    )
    project_export.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new PAGE XML export path outside the project",
    )
    project_export.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly replace an existing PAGE XML export",
    )

    project_export_transcript = subparsers.add_parser(
        "project-export-transcript",
        help="export effective human text as a new local UTF-8 transcript",
    )
    project_export_transcript.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_export_transcript.add_argument(
        "--manifest-sha256",
        required=True,
        help="source PAGE XML project-import manifest SHA-256",
    )
    project_export_transcript.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new UTF-8 transcript path outside the project",
    )
    project_export_transcript.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly replace an existing transcript export",
    )

    project_export_csv = subparsers.add_parser(
        "project-export-transcriptions-csv",
        help="export effective human line text as a new local CSV",
    )
    project_export_csv.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_export_csv.add_argument(
        "--manifest-sha256",
        required=True,
        help="source PAGE XML project-import manifest SHA-256",
    )
    project_export_csv.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new transcription CSV path outside the project",
    )
    project_export_csv.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly replace an existing transcription CSV export",
    )

    project_export_alto = subparsers.add_parser(
        "project-export-alto",
        help="export current human text and layout as local ALTO XML",
    )
    project_export_alto.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_export_alto.add_argument(
        "--manifest-sha256",
        required=True,
        help="source PAGE XML project-import manifest SHA-256",
    )
    project_export_alto.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new ALTO XML export path outside the project",
    )
    project_export_alto.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly replace an existing ALTO XML export",
    )

    project_export_pdf = subparsers.add_parser(
        "project-export-pdf",
        help="render current human text and layout as a local image-only PDF",
    )
    project_export_pdf.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_export_pdf.add_argument(
        "--manifest-sha256",
        required=True,
        help="source PAGE XML project-import manifest SHA-256",
    )
    project_export_pdf.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new PDF export path outside the project",
    )
    project_export_pdf.add_argument(
        "--font",
        type=Path,
        help="optional readable local TrueType font for reproducible PDF text rendering",
    )
    project_export_pdf.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly replace an existing PDF export",
    )

    project_geometry = subparsers.add_parser(
        "project-revise-line-geometry",
        help="append one validated local line polygon/baseline revision",
    )
    project_geometry.add_argument("project", type=Path, help="local .aktproj directory")
    project_geometry.add_argument(
        "--manifest-sha256",
        required=True,
        help="source PAGE XML project-import manifest SHA-256",
    )
    project_geometry.add_argument(
        "--source-span-id",
        required=True,
        help="PAGE XML line source span ID",
    )
    project_geometry.add_argument(
        "--geometry",
        required=True,
        type=Path,
        help="strict local JSON object with polygon and baseline fields",
    )
    project_geometry.add_argument(
        "--editor",
        required=True,
        help="local editor recording the geometry revision",
    )

    project_reading_order = subparsers.add_parser(
        "project-revise-page-reading-order",
        help="append one validated local page region reading-order revision",
    )
    project_reading_order.add_argument("project", type=Path, help="local .aktproj directory")
    project_reading_order.add_argument(
        "--manifest-sha256",
        required=True,
        help="source PAGE XML project-import manifest SHA-256",
    )
    project_reading_order.add_argument(
        "--page-index",
        required=True,
        type=int,
        help="zero-based PAGE XML page index",
    )
    project_reading_order.add_argument(
        "--region-order",
        required=True,
        type=Path,
        help="strict local JSON object with a region_ids field",
    )
    project_reading_order.add_argument(
        "--editor",
        required=True,
        help="local editor recording the reading-order revision",
    )

    project_region_geometry = subparsers.add_parser(
        "project-revise-region-geometry",
        help="append one validated local TextRegion polygon revision",
    )
    project_region_geometry.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_region_geometry.add_argument(
        "--manifest-sha256",
        required=True,
        help="source PAGE XML project-import manifest SHA-256",
    )
    project_region_geometry.add_argument(
        "--page-index",
        required=True,
        type=int,
        help="zero-based PAGE XML page index",
    )
    project_region_geometry.add_argument(
        "--region-id",
        required=True,
        help="exact PAGE XML TextRegion ID",
    )
    project_region_geometry.add_argument(
        "--geometry",
        required=True,
        type=Path,
        help="strict local JSON object with a polygon field",
    )
    project_region_geometry.add_argument(
        "--editor",
        required=True,
        help="local editor recording the region geometry revision",
    )

    project_export_review = subparsers.add_parser(
        "project-export-review-package",
        help="export one contributor's current revisions as an offline review package",
    )
    project_export_review.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_export_review.add_argument(
        "--manifest-sha256",
        required=True,
        help="source PAGE XML project-import manifest SHA-256",
    )
    project_export_review.add_argument(
        "--contributor",
        required=True,
        help="editor identity whose current revisions are exported",
    )
    project_export_review.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new JSON package path outside the project",
    )
    project_export_review.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly replace an existing review package",
    )

    project_import_review = subparsers.add_parser(
        "project-import-review-package",
        help="queue one local offline review package without applying text",
    )
    project_import_review.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_import_review.add_argument(
        "package",
        type=Path,
        help="local offline review package JSON",
    )

    project_resolve_review = subparsers.add_parser(
        "project-resolve-review-proposal",
        help="explicitly accept or reject one queued offline review proposal",
    )
    project_resolve_review.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_resolve_review.add_argument(
        "--proposal-sha256",
        required=True,
        help="proposal SHA-256 emitted by project-import-review-package",
    )
    project_resolve_review.add_argument(
        "--decision",
        required=True,
        choices=("accept", "reject"),
        help="explicit owner decision",
    )
    project_resolve_review.add_argument(
        "--editor",
        required=True,
        help="local editor recording the decision",
    )


    project_evaluate_htr = subparsers.add_parser(
        "project-evaluate-htr",
        help="evaluate one imported HTR result against explicit human revisions",
    )
    project_evaluate_htr.add_argument("project", type=Path, help="local .aktproj directory")
    project_evaluate_htr.add_argument(
        "--manifest-sha256",
        required=True,
        help="source PAGE XML project-import manifest SHA-256",
    )
    project_evaluate_htr.add_argument(
        "--result-pagexml-sha256",
        required=True,
        help="imported recognition PAGE XML SHA-256",
    )
    project_evaluate_htr.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new local HTR evaluation report path outside the project",
    )
    project_evaluate_htr.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly replace an existing local evaluation report",
    )


    project_grant_training_consent = subparsers.add_parser(
        "project-grant-training-consent",
        help="append contributor consent for current human line revisions",
    )
    project_grant_training_consent.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_grant_training_consent.add_argument(
        "--manifest-sha256",
        required=True,
        help="source PAGE XML project-import manifest SHA-256",
    )
    project_grant_training_consent.add_argument(
        "--contributor",
        required=True,
        help="must exactly match the editor of each current human revision",
    )
    project_grant_training_consent.add_argument(
        "--source-span",
        action="append",
        dest="source_spans",
        help="one source span to consent (repeatable)",
    )
    project_grant_training_consent.add_argument(
        "--all-human-revised",
        action="store_true",
        help="consent every current human revision authored by this contributor",
    )

    project_revoke_training_consent = subparsers.add_parser(
        "project-revoke-training-consent",
        help="append withdrawal of one contributor's training-consent grant",
    )
    project_revoke_training_consent.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_revoke_training_consent.add_argument(
        "--grant-consent-id",
        required=True,
        help="consent ID emitted by project-grant-training-consent",
    )
    project_revoke_training_consent.add_argument(
        "--contributor",
        required=True,
        help="must exactly match the contributor who granted consent",
    )
    project_revoke_training_consent.add_argument(
        "--reason",
        required=True,
        help="short local record of the withdrawal reason",
    )

    project_training_readiness = subparsers.add_parser(
        "project-training-readiness",
        help="report consent and human-revision readiness for one PAGE XML import",
    )
    project_training_readiness.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_training_readiness.add_argument(
        "--manifest-sha256",
        required=True,
        help="source PAGE XML project-import manifest SHA-256",
    )
    project_training_readiness.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new local readiness report path outside the project",
    )
    project_training_readiness.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly replace an existing local readiness report",
    )


    project_export_training = subparsers.add_parser(
        "project-export-consented-training-pagexml",
        help="create one consent-gated local PAGE XML HTR training bundle",
    )
    project_export_training.add_argument(
        "project",
        type=Path,
        help="local .aktproj directory",
    )
    project_export_training.add_argument(
        "--manifest-sha256",
        required=True,
        help="source PAGE XML project-import manifest SHA-256",
    )
    project_export_training.add_argument(
        "--split",
        required=True,
        choices=("train", "validation", "test"),
        help="immutable split assignment for this project import",
    )
    project_export_training.add_argument(
        "--output-directory",
        required=True,
        type=Path,
        help="new local bundle directory outside the project",
    )

    htr_corpus = subparsers.add_parser(
        "htr-build-corpus",
        help="assemble current-consent local PAGE XML into explicit Kraken data splits",
    )
    htr_corpus.add_argument(
        "--plan",
        required=True,
        type=Path,
        help="local JSON plan listing project imports and their fixed splits",
    )
    htr_corpus.add_argument(
        "--output-directory",
        required=True,
        type=Path,
        help="new local corpus directory outside every source project",
    )

    htr_inspect = subparsers.add_parser(
        "htr-inspect-corpus",
        help="verify one consented local PAGE XML corpus before Kraken training",
    )
    htr_inspect.add_argument(
        "--plan",
        required=True,
        type=Path,
        help="local JSON plan used to build the corpus",
    )
    htr_inspect.add_argument(
        "--corpus-directory",
        required=True,
        type=Path,
        help="existing local corpus directory to inspect",
    )

    workbench = subparsers.add_parser(
        "workbench",
        help="open the local image-and-line transcription workbench",
    )
    workbench.add_argument("project", type=Path, help="local .aktproj directory")

    serve = subparsers.add_parser(
        "serve",
        help="serve one local project in a loopback-only browser workbench",
    )
    serve.add_argument("project", type=Path, help="local .aktproj directory")
    serve.add_argument(
        "--port",
        type=int,
        default=8765,
        help="loopback TCP port from 0 to 65535 (default: 8765)",
    )

    service_create = subparsers.add_parser(
        "service-create",
        help="create a local loopback service workspace",
    )
    service_create.add_argument("workspace", type=Path, help="new local service directory")

    service_inspect = subparsers.add_parser(
        "service-inspect",
        help="inspect a local loopback service workspace",
    )
    service_inspect.add_argument("workspace", type=Path, help="local service directory")

    service_user_create = subparsers.add_parser(
        "service-user-create",
        help="create one password-protected local service account",
    )
    service_user_create.add_argument("workspace", type=Path, help="local service directory")
    service_user_create.add_argument("--username", required=True, help="new local username")
    service_user_create.add_argument(
        "--password-file",
        required=True,
        type=Path,
        help="local UTF-8 password file; its contents are never printed",
    )

    service_users = subparsers.add_parser(
        "service-list-users",
        help="list local service account identities without credentials",
    )
    service_users.add_argument("workspace", type=Path, help="local service directory")

    service_role = subparsers.add_parser(
        "service-grant-role",
        help="grant a local account a role on one managed project",
    )
    service_role.add_argument("workspace", type=Path, help="local service directory")
    service_role.add_argument("--project-id", required=True, help="managed project UUID")
    service_role.add_argument("--username", required=True, help="local username")
    service_role.add_argument(
        "--role",
        required=True,
        choices=("VIEWER", "EDITOR", "OWNER"),
        help="project access role",
    )

    service_add = subparsers.add_parser(
        "service-add-project",
        help="copy one local project into service-managed storage",
    )
    service_add.add_argument("workspace", type=Path, help="local service directory")
    service_add.add_argument("project", type=Path, help="local .aktproj directory")
    service_add.add_argument(
        "--owner",
        help="existing local username granted OWNER when the project is copied",
    )

    service_projects = subparsers.add_parser(
        "service-list-projects",
        help="list projects owned by a local service workspace",
    )
    service_projects.add_argument("workspace", type=Path, help="local service directory")

    service_artifact_register = subparsers.add_parser(
        "service-artifact-register",
        help="copy one local model or dataset artifact into managed storage",
    )
    service_artifact_register.add_argument(
        "workspace",
        type=Path,
        help="local service directory",
    )
    service_artifact_register.add_argument(
        "source",
        type=Path,
        help="local regular model or dataset artifact file",
    )
    service_artifact_register.add_argument(
        "--kind",
        required=True,
        choices=("MODEL", "DATASET"),
        help="artifact kind",
    )
    service_artifact_register.add_argument(
        "--name",
        required=True,
        help="human-readable artifact name",
    )
    service_artifact_register.add_argument(
        "--license-id",
        required=True,
        help="declared license identifier, such as Apache-2.0",
    )
    service_artifact_register.add_argument(
        "--description",
        default="",
        help="optional local artifact description",
    )

    service_artifacts = subparsers.add_parser(
        "service-list-artifacts",
        help="list locally registered model and dataset metadata",
    )
    service_artifacts.add_argument("workspace", type=Path, help="local service directory")

    service_attach_artifact = subparsers.add_parser(
        "service-project-attach-artifact",
        help="attach a registered model or dataset to a managed project",
    )
    service_attach_artifact.add_argument(
        "workspace",
        type=Path,
        help="local service directory",
    )
    service_attach_artifact.add_argument(
        "--project-id",
        required=True,
        help="managed project UUID",
    )
    service_attach_artifact.add_argument(
        "--artifact-id",
        required=True,
        help="registered artifact UUID",
    )

    service_activate_model = subparsers.add_parser(
        "service-project-activate-model",
        help="select one attached registered model for future queued recognition",
    )
    service_activate_model.add_argument(
        "workspace",
        type=Path,
        help="local service directory",
    )
    service_activate_model.add_argument(
        "--project-id",
        required=True,
        help="managed project UUID",
    )
    service_activate_model.add_argument(
        "--artifact-id",
        required=True,
        help="attached MODEL artifact UUID",
    )

    service_model_history = subparsers.add_parser(
        "service-project-model-history",
        help="list immutable model-release and rollback history for a managed project",
    )
    service_model_history.add_argument(
        "workspace",
        type=Path,
        help="local service directory",
    )
    service_model_history.add_argument(
        "--project-id",
        required=True,
        help="managed project UUID",
    )

    service_rollback_model = subparsers.add_parser(
        "service-project-rollback-model",
        help="append a rollback to one prior project model release",
    )
    service_rollback_model.add_argument(
        "workspace",
        type=Path,
        help="local service directory",
    )
    service_rollback_model.add_argument(
        "--project-id",
        required=True,
        help="managed project UUID",
    )
    service_rollback_model.add_argument(
        "--release-id",
        required=True,
        help="prior model release UUID",
    )

    service_training = subparsers.add_parser(
        "service-queue-kraken-training",
        help="snapshot and queue one consent-checked local CPU/GPU Kraken training run",
    )
    service_training.add_argument("workspace", type=Path, help="local service directory")
    service_training.add_argument("--project-id", required=True, help="managed project UUID")
    service_training.add_argument(
        "--config",
        required=True,
        type=Path,
        help="local checksum-pinned Kraken training configuration",
    )
    service_training.add_argument(
        "--plan",
        required=True,
        type=Path,
        help="local consented HTR corpus plan",
    )
    service_training.add_argument(
        "--corpus-directory",
        required=True,
        type=Path,
        help="local inspected HTR training corpus directory",
    )
    service_training.add_argument(
        "--model-name",
        required=True,
        help="name to register for every produced model checkpoint",
    )
    service_training.add_argument(
        "--model-license-id",
        required=True,
        help="declared license identifier for the produced weights",
    )
    service_training.add_argument(
        "--model-description",
        default="",
        help="optional description attached to the produced model artifact",
    )

    service_queue = subparsers.add_parser(
        "service-queue-backup",
        help="persist a local project backup job for a running service worker",
    )
    service_queue.add_argument("workspace", type=Path, help="local service directory")
    service_queue.add_argument("--project-id", required=True, help="managed project UUID")

    service_verify = subparsers.add_parser(
        "service-backup-verify",
        help="verify every file hash in a local service backup archive",
    )
    service_verify.add_argument("backup", type=Path, help="local .aktbackup.zip file")

    service_restore = subparsers.add_parser(
        "service-backup-restore",
        help="verify then restore a local service backup archive",
    )
    service_restore.add_argument("backup", type=Path, help="local .aktbackup.zip file")
    service_restore.add_argument("project", type=Path, help="new local .aktproj directory")

    service_serve = subparsers.add_parser(
        "service-serve",
        help="run the local service and durable backup worker on loopback only",
    )
    service_serve.add_argument("workspace", type=Path, help="local service directory")
    service_serve.add_argument(
        "--port",
        type=int,
        default=8780,
        help="loopback TCP port from 0 to 65535 (default: 8780)",
    )
    service_serve.add_argument(
        "--container-listen",
        action="store_true",
        help=(
            "bind to the container interface; use only with a host-loopback Docker "
            "port mapping"
        ),
    )
    service_serve.add_argument(
        "--kraken-config",
        type=Path,
        help=(
            "optional local checksum-pinned Kraken configuration loaded by the "
            "service owner at startup"
        ),
    )

    pagexml = subparsers.add_parser(
        "pagexml-import",
        help="import local PAGE XML and its local page images into an immutable manifest",
    )
    pagexml.add_argument("source", type=Path, help="local PAGE XML source")
    pagexml.add_argument(
        "--image-root",
        type=Path,
        help="local directory containing imageFilename paths (defaults to the XML directory)",
    )
    pagexml.add_argument("--output", required=True, type=Path, help="import manifest path")
    pagexml.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly replace an existing import manifest",
    )

    consensus = subparsers.add_parser(
        "consensus-merge",
        help="merge exactly two explicitly named blind-reader labels",
    )
    consensus.add_argument("left_label", type=Path)
    consensus.add_argument("right_label", type=Path)
    consensus.add_argument("--output", required=True, type=Path)
    consensus.add_argument(
        "--schema",
        type=Path,
        default=ACT_RECORD_SCHEMA_PATH,
    )
    consensus.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly permit atomic replacement of an existing consensus output",
    )

    inspect_reader = subparsers.add_parser(
        "reader-inspect", help="verify pinned local Reader artifacts without running inference"
    )
    inspect_reader.add_argument("--config", required=True, type=Path)

    kraken_inspect = subparsers.add_parser(
        "kraken-inspect",
        help="verify pinned local Kraken artifacts without running recognition",
    )
    kraken_inspect.add_argument("--config", required=True, type=Path)

    kraken_recognize = subparsers.add_parser(
        "kraken-recognize",
        help="recognize one local pre-segmented PAGE XML document with Kraken",
    )
    kraken_recognize.add_argument("--config", required=True, type=Path)
    kraken_recognize.add_argument("--pagexml", required=True, type=Path)
    kraken_recognize.add_argument("--output", required=True, type=Path)
    kraken_recognize.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly replace an existing PAGE XML recognition result",
    )

    kraken_train = subparsers.add_parser(
        "kraken-train",
        help="run one pinned local Kraken training job from an inspected corpus",
    )
    kraken_train.add_argument("--config", required=True, type=Path)
    kraken_train.add_argument("--plan", required=True, type=Path)
    kraken_train.add_argument("--corpus-directory", required=True, type=Path)
    kraken_train.add_argument("--output-directory", required=True, type=Path)

    kraken_evaluate = subparsers.add_parser(
        "kraken-evaluate",
        help="run a pinned local Kraken model against an inspected held-out split",
    )
    kraken_evaluate.add_argument("--config", required=True, type=Path)
    kraken_evaluate.add_argument("--plan", required=True, type=Path)
    kraken_evaluate.add_argument("--corpus-directory", required=True, type=Path)
    kraken_evaluate.add_argument("--training-run-directory", required=True, type=Path)
    kraken_evaluate.add_argument("--output-directory", required=True, type=Path)

    infer = subparsers.add_parser(
        "reader-infer", help="run one explicitly configured local Reader inference"
    )
    infer.add_argument("--config", required=True, type=Path)
    infer.add_argument("--scan", required=True, type=Path)
    infer.add_argument("--brief", required=True, type=Path)
    infer.add_argument("--output", required=True, type=Path)

    batch = subparsers.add_parser(
        "batch-run", help="resume a manifest-driven local inference run"
    )
    batch.add_argument("--config", required=True, type=Path)
    batch.add_argument("--manifest", required=True, type=Path)
    batch.add_argument("--checkpoint", required=True, type=Path)
    batch.add_argument("--output-dir", required=True, type=Path)
    batch.add_argument("--as-of-year", type=int)
    batch.add_argument("--max-retries", type=int, default=2)
    batch.add_argument(
        "--rebind-failed-fingerprints",
        action="store_true",
        help=(
            "explicitly preserve FAILED retry counts while auditing a changed "
            "runtime fingerprint; changed non-FAILED rows are rejected"
        ),
    )

    adjudicate = subparsers.add_parser(
        "adjudicate",
        help="generate an offline human adjudication packet or ingest its answers",
    )
    adjudicate.add_argument("--wave", required=True)
    adjudicate.add_argument(
        "--spec",
        type=Path,
        help="wave specification; defaults to human_check/waves/wave-<id>.json",
    )
    adjudicate.add_argument(
        "--output-dir",
        type=Path,
        help="packet directory; defaults to human_check/generated/wave-<id>",
    )
    adjudicate.add_argument(
        "--answers",
        type=Path,
        help="ingest a downloaded answers JSON into an existing packet directory",
    )
    adjudicate.add_argument("--max-questions", type=int, default=10)
    adjudicate.add_argument(
        "--replace-existing",
        action="store_true",
        help="explicitly replace generation artifacts; ingested results remain immutable",
    )
    evaluate = subparsers.add_parser(
        "eval", help="generate the clerk-year-sequestered SerockBench report"
    )
    evaluate.add_argument("--predictions", required=True, type=Path)
    evaluate.add_argument(
        "--gold-dir",
        type=Path,
        default=_source_checkout_default("gold/acts"),
        help="gold records directory; required outside an Application source checkout",
    )
    evaluate.add_argument(
        "--holdout",
        type=Path,
        default=_source_checkout_default("gold/clerk_year_holdout.json"),
        help="clerk-year holdout manifest; required outside a source checkout",
    )
    evaluate.add_argument("--training-clerk-years", type=Path)
    evaluate.add_argument("--output", type=Path)
    evaluate.add_argument(
        "--strata-table",
        type=Path,
        help="optional Markdown table of count-backed field-family and language strata",
    )

    compare = subparsers.add_parser(
        "compare",
        help="compare two local reader-label collections without inference or network access",
    )
    compare.add_argument("left", type=Path, help="left label file or directory")
    compare.add_argument("right", type=Path, help="right label file or directory")
    compare.add_argument("--output", type=Path, help="optional JSON report path")
    compare.add_argument(
        "--csv",
        type=Path,
        help="optional spreadsheet-safe CSV containing every field disagreement",
    )
    compare.add_argument(
        "--max-disagreements",
        type=int,
        default=100,
        help="maximum disagreement details to include in the report (default: 100)",
    )
    compare.add_argument(
        "--require-grounded",
        action="store_true",
        help="fail closed unless every input label passes the continuous-transcription gate",
    )
    return parser


def environment_report(inspect_root: Path | str | None = None) -> dict[str, object]:
    """Return deterministic installed-runtime and checkout-readiness facts."""
    supported = sys.version_info >= (3, 11)
    runtime_root = PROJECT_ROOT.resolve()
    inspected_root = runtime_root if inspect_root is None else Path(inspect_root).resolve()
    checkout = inspect_application_checkout(inspected_root)
    runtime_checkout = (
        checkout
        if inspected_root == runtime_root
        else inspect_application_checkout(runtime_root)
    )
    runtime_assets = inspect_packaged_runtime_assets()
    inspected_root_is_runtime_root = inspected_root == runtime_root
    runtime_mode = (
        "source-checkout"
        if runtime_checkout["identity_status"] == "MATCH"
        else "installed-distribution"
    )
    source_checkout_verification_available = bool(
        supported and inspected_root_is_runtime_root and checkout["ready"]
    )
    standalone_distribution_ready = bool(
        supported and runtime_assets["runtime_assets_available"]
    )
    if inspect_root is not None:
        pipeline_available = source_checkout_verification_available
    elif runtime_mode == "source-checkout":
        pipeline_available = bool(
            source_checkout_verification_available and standalone_distribution_ready
        )
    else:
        pipeline_available = standalone_distribution_ready
    return {
        "doctor_report_version": "1.1.0",
        "aktreader_version": __version__,
        "project_name": PROJECT_NAME,
        "project_role": PROJECT_ROLE,
        "distribution_name": DISTRIBUTION_NAME,
        "package_namespace": PACKAGE_NAMESPACE,
        "command_name": COMMAND_NAME,
        "repository_url": REPOSITORY_URL,
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_supported": supported,
        "phase": "P2",
        "cli_available": True,
        "runtime_mode": runtime_mode,
        "runtime_root": str(runtime_root),
        "inspected_root": checkout["root"],
        "inspected_root_is_runtime_root": inspected_root_is_runtime_root,
        "checkout_identity_status": checkout["identity_status"],
        "observed_distribution_name": checkout["observed_distribution_name"],
        "contract_asset_count": checkout["contract_asset_count"],
        "available_contract_asset_count": checkout["available_contract_asset_count"],
        "contract_assets_available": checkout["contract_assets_available"],
        "missing_contract_assets": checkout["missing_contract_assets"],
        "contract_assets": checkout["contract_assets"],
        "inspected_checkout_ready": checkout["ready"],
        **runtime_assets,
        "source_checkout_verification_available": (
            source_checkout_verification_available
        ),
        "pipeline_available": pipeline_available,
        "source_checkout_required": False,
        "standalone_distribution_ready": standalone_distribution_ready,
        "reader_backend": "local-open-weights-only",
        "network_required": False,
    }


def _command_doctor(args: argparse.Namespace) -> int:
    inspect_root = (
        None
        if args.inspect_root is None
        else local_output_path(args.inspect_root, role="inspected application root")
    )
    report = environment_report(inspect_root)
    if args.json:
        _emit_json(report)
    else:
        print(f"{report['project_name']} {report['aktreader_version']}")
        print(f"Repository role: {report['project_role']}")
        print(
            "Runtime identity: "
            f"distribution {report['distribution_name']} | "
            f"package {report['package_namespace']} | command {report['command_name']}"
        )
        print(f"Repository: {report['repository_url']}")
        print(f"Runtime mode: {report['runtime_mode']}")
        print(f"Runtime root: {report['runtime_root']}")
        if not report["inspected_root_is_runtime_root"]:
            print(f"Inspected root: {report['inspected_root']} (diagnostic only)")
        print(
            "Checkout identity: "
            f"{report['checkout_identity_status']} "
            f"(observed: {report['observed_distribution_name'] or 'none'})"
        )
        print(
            "Checkout assets: "
            f"{report['available_contract_asset_count']}/"
            f"{report['contract_asset_count']} available"
        )
        for path in report["missing_contract_assets"]:
            print(f"  missing: {path}")
        print(
            "Packaged runtime assets: "
            f"{report['available_runtime_asset_count']}/"
            f"{report['runtime_asset_count']} available"
        )
        for path in report["missing_runtime_assets"]:
            print(f"  missing from package: {path}")
        print(
            "Full checkout verification available: "
            f"{'yes' if report['source_checkout_verification_available'] else 'no'}"
        )
        print(f"Pipeline available: {'yes' if report['pipeline_available'] else 'no'}")
        print(
            "Standalone wheel ready: "
            + (
                "yes (explicit external reader artifacts required)"
                if report["standalone_distribution_ready"]
                else "no (packaged runtime contracts are incomplete)"
            )
        )
        print(f"Pipeline phase: {report['phase']}")
        print(f"Python {report['python_version']} ({report['implementation']})")
        print(f"Python >= 3.11: {'yes' if report['python_supported'] else 'no'}")
        print("Reader backend: local open weights only")
        print("Network required: no")
    return 0 if report["pipeline_available"] else 1


def _command_prompt_verify(args: argparse.Namespace) -> int:
    root = local_input_path(args.root, role="project root")
    if not root.is_dir():
        raise CliConfigurationError(f"project root is not a directory: {root}")
    digest = verify_reader_prompt(root)
    _emit_json(
        {
            "status": "PASS",
            "prompt": str(root / "prompts" / "reader_prompt.md"),
            "sha256": digest,
            "verbatim_skill_count": 3,
        }
    )
    return 0


def _command_checkout_verify(args: argparse.Namespace) -> int:
    root = local_input_path(args.root, role="application checkout")
    if not root.is_dir():
        raise CliConfigurationError(f"application checkout is not a directory: {root}")
    report = verify_application_checkout(root)
    if args.json:
        _emit_json(report)
    else:
        print(f"{PROJECT_NAME} public checkout verification")
        print(f"Root: {report['root']}")
        for name in CHECK_NAMES:
            check = report["checks"][name]
            detail = check.get("summary") or check.get("error") or check.get("reason")
            print(f"{check['status']:>7}  {name}: {detail}")
        print(
            f"Result: {report['status']} "
            f"({report['passed_check_count']}/{report['check_count']})"
        )
        print("Requires source scans: no")
        print("Requires model/runtime files: no")
        print("Requires network access: no")
    return 0 if report["status"] == "PASS" else 1


def _command_label_validate(args: argparse.Namespace) -> int:
    results = []
    for raw_path in args.labels:
        path = local_input_path(raw_path, role="reader label")
        if not path.is_file():
            raise CliConfigurationError(f"reader label is not a file: {path}")
        label = load_grounded_reader_label(path)
        results.append(
            {
                "path": str(path),
                "label_id": label.label_id,
                "record_id": label.record_id,
                "reader_id": label.reader_id,
                "reader_family": label.reader_family,
                "schema_kind": label.schema_kind,
                "confidence_cap": label.confidence_cap,
                "source_sha256": label.source_sha256,
                "quality_metrics": paired_quality_metrics((label,)),
            }
        )
    _emit_json({"status": "PASS", "labels": results, "count": len(results)})
    return 0



def _command_collection_create(args: argparse.Namespace) -> int:
    _emit_json(create_collection(args.collection, name=args.name))
    return 0


def _command_collection_add_project(args: argparse.Namespace) -> int:
    _emit_json(add_project_to_collection(args.collection, args.project))
    return 0


def _command_collection_inspect(args: argparse.Namespace) -> int:
    _emit_json(inspect_collection(args.collection))
    return 0


def _command_collection_search(args: argparse.Namespace) -> int:
    _emit_json(search_collection(args.collection, args.query, limit=args.limit))
    return 0


def _command_collection_list_documents(args: argparse.Namespace) -> int:
    _emit_json(
        list_collection_documents(
            args.collection,
            query=args.query,
            limit=args.limit,
        )
    )
    return 0


def _command_collection_save_search(args: argparse.Namespace) -> int:
    collection = local_input_path(args.collection, role="collection")
    if not collection.is_dir():
        raise CliConfigurationError(f"collection is not a directory: {collection}")
    _emit_json(
        save_collection_search(
            collection,
            name=args.name,
            query=args.query,
        )
    )
    return 0


def _command_collection_list_saved_searches(args: argparse.Namespace) -> int:
    collection = local_input_path(args.collection, role="collection")
    if not collection.is_dir():
        raise CliConfigurationError(f"collection is not a directory: {collection}")
    _emit_json(list_collection_saved_searches(collection))
    return 0


def _command_collection_run_saved_search(args: argparse.Namespace) -> int:
    collection = local_input_path(args.collection, role="collection")
    if not collection.is_dir():
        raise CliConfigurationError(f"collection is not a directory: {collection}")
    _emit_json(
        run_collection_saved_search(
            collection,
            search_id=args.search_id,
            limit=args.limit,
        )
    )
    return 0


def _command_collection_export_public(args: argparse.Namespace) -> int:
    collection = local_input_path(args.collection, role="collection")
    if not collection.is_dir():
        raise CliConfigurationError(f"collection is not a directory: {collection}")
    output = local_output_path(args.output, role="public collection destination")
    if output.exists():
        raise CliConfigurationError(f"public collection destination already exists: {output}")
    report = export_public_collection(
        collection,
        output,
        license_id=args.license_id,
        confirm_public=args.confirm_public,
    )
    _emit_json(report)
    return 0


def _command_project_create(args: argparse.Namespace) -> int:
    project = local_output_path(args.project, role="project destination")
    report = create_project(project, name=args.name)
    _emit_json(report)
    return 0


def _command_project_inspect(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    report = inspect_project(project)
    _emit_json(report)
    return 0


def _command_project_list_documents(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    _emit_json(
        {
            "status": "READY",
            "project": str(project),
            "documents": list_project_documents(project),
            "network_required": False,
        }
    )
    return 0


def _command_project_search(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    _emit_json(
        search_project_transcriptions(
            project,
            query=args.query,
            field=args.field,
            limit=args.limit,
        )
    )
    return 0


def _command_project_update_document(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    metadata_path = local_input_path(args.metadata, role="document metadata")
    if not metadata_path.is_file():
        raise CliConfigurationError("document metadata must be a JSON file")
    metadata = load_strict_json(metadata_path, role="document metadata")
    if (
        not isinstance(metadata, dict)
        or not metadata
        or not set(metadata).issubset({"title", "tags", "notes"})
    ):
        raise CliConfigurationError(
            "document metadata must contain only title, tags, and/or notes"
        )
    _emit_json(
        update_project_document(
            project,
            manifest_sha256=args.manifest_sha256,
            title=metadata.get("title"),
            tags=metadata.get("tags"),
            notes=metadata.get("notes"),
        )
    )
    return 0


def _command_project_import_pagexml(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    source = local_input_path(args.source, role="PAGE XML source")
    image_root = None
    if args.image_root is not None:
        image_root = local_input_path(args.image_root, role="PAGE XML image root")
        if not image_root.is_dir():
            raise CliConfigurationError(f"PAGE XML image root is not a directory: {image_root}")
    report = import_pagexml_into_project(project, source, image_root=image_root)
    _emit_json(report)
    return 0


def _command_project_import_images(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    source_directory = local_input_path(
        args.source_directory,
        role="image import directory",
    )
    if not project.is_dir() or not source_directory.is_dir():
        raise CliConfigurationError(
            "image import requires an existing project and image directory"
        )
    _emit_json(
        import_images_into_project(
            project,
            source_directory,
            title=args.title,
        )
    )
    return 0


def _command_project_import_pdf(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    source = local_input_path(args.source, role="PDF source")
    if not project.is_dir() or not source.is_file():
        raise CliConfigurationError("PDF import requires an existing project and PDF source")
    _emit_json(
        import_pdf_into_project(
            project,
            source,
            dpi=args.dpi,
            title=args.title,
        )
    )
    return 0


def _command_project_import_htr_suggestions(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    source = local_input_path(args.source, role="recognition PAGE XML")
    if not source.is_file():
        raise CliConfigurationError(f"recognition PAGE XML is not a file: {source}")
    image_root = None
    if args.image_root is not None:
        image_root = local_input_path(args.image_root, role="recognition PAGE XML image root")
        if not image_root.is_dir():
            raise CliConfigurationError(
                f"recognition PAGE XML image root is not a directory: {image_root}"
            )
    report = import_htr_suggestions(
        project,
        source,
        manifest_sha256=args.manifest_sha256,
        engine=args.engine,
        runtime_fingerprint=args.runtime_fingerprint,
        image_root=image_root,
    )
    _emit_json(report)
    return 0


def _command_project_kraken_segment(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    config_path = local_input_path(args.config, role="Kraken configuration")
    if not config_path.is_file():
        raise CliConfigurationError(f"Kraken configuration is not a file: {config_path}")
    report = segment_project_with_kraken(
        project,
        manifest_sha256=args.manifest_sha256,
        kraken=LocalKraken(load_kraken_config(config_path)),
        title=args.title,
    )
    _emit_json(report)
    return 0


def _command_project_kraken_recognize(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    config_path = local_input_path(args.config, role="Kraken configuration")
    if not config_path.is_file():
        raise CliConfigurationError(f"Kraken configuration is not a file: {config_path}")
    report = recognize_project_with_kraken(
        project,
        manifest_sha256=args.manifest_sha256,
        kraken=LocalKraken(load_kraken_config(config_path)),
    )
    _emit_json(report)
    return 0


def _command_project_export_pagexml(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    output = local_output_path(args.output, role="PAGE XML export")
    if output.is_dir():
        raise CliConfigurationError(f"PAGE XML export is a directory: {output}")
    if output.exists() and not args.replace_existing:
        raise CliConfigurationError(
            "PAGE XML export already exists; pass --replace-existing to replace it atomically"
        )
    report = export_human_pagexml(
        project,
        output,
        manifest_sha256=args.manifest_sha256,
        replace_existing=args.replace_existing,
    )
    _emit_json(report)
    return 0


def _command_project_export_transcript(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    output = local_output_path(args.output, role="transcript export")
    if output.is_dir():
        raise CliConfigurationError(f"transcript export is a directory: {output}")
    if output.exists() and not args.replace_existing:
        raise CliConfigurationError(
            "transcript export already exists; pass --replace-existing to replace it atomically"
        )
    report = export_human_transcript(
        project,
        output,
        manifest_sha256=args.manifest_sha256,
        replace_existing=args.replace_existing,
    )
    _emit_json(report)
    return 0


def _command_project_export_transcriptions_csv(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    output = local_output_path(args.output, role="transcription CSV export")
    if output.is_dir():
        raise CliConfigurationError(f"transcription CSV export is a directory: {output}")
    if output.exists() and not args.replace_existing:
        raise CliConfigurationError(
            "transcription CSV export already exists; pass --replace-existing "
            "to replace it atomically"
        )
    report = export_human_transcriptions_csv(
        project,
        output,
        manifest_sha256=args.manifest_sha256,
        replace_existing=args.replace_existing,
    )
    _emit_json(report)
    return 0


def _command_project_export_alto(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    output = local_output_path(args.output, role="ALTO XML export")
    if output.is_dir():
        raise CliConfigurationError(f"ALTO XML export is a directory: {output}")
    if output.exists() and not args.replace_existing:
        raise CliConfigurationError(
            "ALTO XML export already exists; pass --replace-existing to replace it atomically"
        )
    report = export_human_alto(
        project,
        output,
        manifest_sha256=args.manifest_sha256,
        replace_existing=args.replace_existing,
    )
    _emit_json(report)
    return 0



def _command_project_export_pdf(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    output = local_output_path(args.output, role="PDF export")
    if output.is_dir():
        raise CliConfigurationError(f"PDF export is a directory: {output}")
    if output.exists() and not args.replace_existing:
        raise CliConfigurationError(
            "PDF export already exists; pass --replace-existing to replace it atomically"
        )
    font_path = None
    if args.font is not None:
        font_path = local_input_path(args.font, role="PDF font")
        if not font_path.is_file():
            raise CliConfigurationError(f"PDF font is not a file: {font_path}")
    report = export_human_pdf(
        project,
        output,
        manifest_sha256=args.manifest_sha256,
        replace_existing=args.replace_existing,
        font_path=font_path,
    )
    _emit_json(report)
    return 0


def _command_project_revise_line_geometry(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    geometry_path = local_input_path(args.geometry, role="line geometry")
    if not project.is_dir() or not geometry_path.is_file():
        raise CliConfigurationError("line geometry revision requires a project and JSON file")
    geometry = load_strict_json(geometry_path, role="line geometry")
    if not isinstance(geometry, dict) or set(geometry) != {"polygon", "baseline"}:
        raise CliConfigurationError(
            "line geometry must have exactly polygon and baseline fields"
        )
    _emit_json(
        revise_line_geometry(
            project,
            manifest_sha256=args.manifest_sha256,
            source_span_id=args.source_span_id,
            polygon=geometry["polygon"],
            baseline=geometry["baseline"],
            editor=args.editor,
        )
    )
    return 0


def _command_project_revise_page_reading_order(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    order_path = local_input_path(args.region_order, role="page region order")
    if not project.is_dir() or not order_path.is_file():
        raise CliConfigurationError(
            "page reading-order revision requires a project and JSON file"
        )
    order = load_strict_json(order_path, role="page region order")
    if not isinstance(order, dict) or set(order) != {"region_ids"}:
        raise CliConfigurationError(
            "page region order must have exactly a region_ids field"
        )
    _emit_json(
        revise_page_reading_order(
            project,
            manifest_sha256=args.manifest_sha256,
            page_index=args.page_index,
            region_ids=order["region_ids"],
            editor=args.editor,
        )
    )
    return 0


def _command_project_revise_region_geometry(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    geometry_path = local_input_path(args.geometry, role="region geometry")
    if not project.is_dir() or not geometry_path.is_file():
        raise CliConfigurationError(
            "region geometry revision requires a project and JSON file"
        )
    geometry = load_strict_json(geometry_path, role="region geometry")
    if not isinstance(geometry, dict) or set(geometry) != {"polygon"}:
        raise CliConfigurationError("region geometry must have exactly a polygon field")
    _emit_json(
        revise_region_geometry(
            project,
            manifest_sha256=args.manifest_sha256,
            page_index=args.page_index,
            region_id=args.region_id,
            polygon=geometry["polygon"],
            editor=args.editor,
        )
    )
    return 0


def _command_project_export_review_package(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    output = local_output_path(args.output, role="review package output")
    if output.is_dir():
        raise CliConfigurationError(f"review package output is a directory: {output}")
    if output == project or project in output.parents:
        raise CliConfigurationError("review package output must be outside the project")
    if output.exists() and not args.replace_existing:
        raise CliConfigurationError(
            "review package output already exists; pass --replace-existing to replace it"
        )
    report = export_review_package(
        project,
        output,
        manifest_sha256=args.manifest_sha256,
        contributor=args.contributor,
        replace_existing=args.replace_existing,
    )
    _emit_json(report)
    return 0


def _command_project_import_review_package(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    package = local_input_path(args.package, role="review package")
    if not project.is_dir() or not package.is_file():
        raise CliConfigurationError("review package import requires a project and package file")
    _emit_json(import_review_package(project, package))
    return 0


def _command_project_resolve_review_proposal(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    _emit_json(
        resolve_review_proposal(
            project,
            proposal_sha256=args.proposal_sha256,
            decision=args.decision,
            editor=args.editor,
        )
    )
    return 0


def _command_project_evaluate_htr(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    output = local_output_path(args.output, role="HTR evaluation report")
    if output.is_dir():
        raise CliConfigurationError(f"HTR evaluation report is a directory: {output}")
    if output == project or project in output.parents:
        raise CliConfigurationError(
            "HTR evaluation report must be outside the project so project storage stays immutable"
        )
    if output.exists() and not args.replace_existing:
        raise CliConfigurationError(
            "HTR evaluation report already exists; pass --replace-existing to replace it atomically"
        )
    report = evaluate_htr_suggestions(
        project,
        manifest_sha256=args.manifest_sha256,
        result_pagexml_sha256=args.result_pagexml_sha256,
    )
    report = {**report, "output": str(output)}
    atomic_write_json(output, report)
    _emit_json(report)
    return 0


def _command_project_grant_training_consent(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    report = grant_training_consent(
        project,
        manifest_sha256=args.manifest_sha256,
        contributor=args.contributor,
        source_span_ids=args.source_spans,
        all_human_revised=args.all_human_revised,
    )
    _emit_json(report)
    return 0


def _command_project_revoke_training_consent(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    report = revoke_training_consent(
        project,
        grant_consent_id=args.grant_consent_id,
        contributor=args.contributor,
        reason=args.reason,
    )
    _emit_json(report)
    return 0


def _command_project_training_readiness(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    output = local_output_path(args.output, role="training readiness report")
    if output.is_dir():
        raise CliConfigurationError(f"training readiness report is a directory: {output}")
    if output == project or project in output.parents:
        raise CliConfigurationError(
            "training readiness report must be outside the project so project storage stays "
            "immutable"
        )
    if output.exists() and not args.replace_existing:
        raise CliConfigurationError(
            "training readiness report already exists; pass --replace-existing to replace "
            "it atomically"
        )
    report = training_readiness(
        project,
        manifest_sha256=args.manifest_sha256,
    )
    report = {**report, "output": str(output)}
    atomic_write_json(output, report)
    _emit_json(report)
    return 0


def _command_project_export_consented_training_pagexml(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    output_directory = local_output_path(
        args.output_directory,
        role="consented PAGE XML training bundle directory",
    )
    if output_directory.exists():
        raise CliConfigurationError(
            f"consented PAGE XML training bundle directory already exists: {output_directory}"
        )
    report = export_consented_training_pagexml(
        project,
        output_directory,
        manifest_sha256=args.manifest_sha256,
        split=args.split,
    )
    _emit_json(report)
    return 0


def _command_htr_build_corpus(args: argparse.Namespace) -> int:
    plan = local_input_path(args.plan, role="HTR corpus plan")
    if not plan.is_file():
        raise CliConfigurationError(f"HTR corpus plan is not a file: {plan}")
    output_directory = local_output_path(
        args.output_directory,
        role="HTR training corpus directory",
    )
    if output_directory.exists():
        raise CliConfigurationError(
            f"HTR training corpus directory already exists: {output_directory}"
        )
    report = assemble_consented_training_corpus(plan, output_directory)
    _emit_json(report)
    return 0


def _command_htr_inspect_corpus(args: argparse.Namespace) -> int:
    plan = local_input_path(args.plan, role="HTR corpus plan")
    if not plan.is_file():
        raise CliConfigurationError(f"HTR corpus plan is not a file: {plan}")
    corpus_directory = local_input_path(
        args.corpus_directory,
        role="HTR training corpus directory",
    )
    if not corpus_directory.is_dir():
        raise CliConfigurationError(
            f"HTR training corpus directory is not a directory: {corpus_directory}"
        )
    report = inspect_consented_training_corpus(plan, corpus_directory)
    _emit_json(report)
    return 0


def _command_workbench(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    launch_workbench(project)
    return 0

def _command_serve(args: argparse.Namespace) -> int:
    project = local_input_path(args.project, role="project")
    if not project.is_dir():
        raise CliConfigurationError(f"project is not a directory: {project}")
    server = create_self_hosted_workbench_server(project, port=args.port)
    _emit_json(
        {
            "status": "SERVING",
            "project": str(project),
            "url": server.url,
            "bind_address": "127.0.0.1",
            "network_required": False,
        }
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    return 0


def _command_service_create(args: argparse.Namespace) -> int:
    workspace = local_output_path(args.workspace, role="service workspace destination")
    _emit_json(create_service_workspace(workspace))
    return 0


def _command_service_inspect(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    _emit_json(inspect_service_workspace(workspace))
    return 0


def _command_service_user_create(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    password_file = local_input_path(args.password_file, role="local password file")
    if not password_file.is_file():
        raise CliConfigurationError("local password file is not a regular file")
    try:
        password = password_file.read_text(encoding="utf-8").rstrip("\r\n")
    except (OSError, UnicodeError) as error:
        raise CliConfigurationError("local password file is unreadable UTF-8") from error
    _emit_json(create_local_account(workspace, username=args.username, password=password))
    return 0


def _command_service_list_users(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    _emit_json(
        {
            "status": "READY",
            "accounts": list_local_accounts(workspace),
            "network_required": False,
        }
    )
    return 0


def _command_service_grant_role(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    _emit_json(
        grant_project_role(
            workspace,
            project_id=args.project_id,
            username=args.username,
            role=args.role,
        )
    )
    return 0


def _command_service_add_project(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    project = local_input_path(args.project, role="project")
    _emit_json(add_project_to_service(workspace, project, owner_username=args.owner))
    return 0


def _command_service_list_projects(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    _emit_json(
        {
            "status": "READY",
            "projects": list_service_projects(workspace),
            "network_required": False,
        }
    )
    return 0


def _command_service_artifact_register(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    source = local_input_path(args.source, role="artifact source")
    if not source.is_file():
        raise CliConfigurationError("artifact source is not a regular file")
    _emit_json(
        register_service_artifact(
            workspace,
            source,
            kind=args.kind,
            name=args.name,
            license_id=args.license_id,
            description=args.description,
        )
    )
    return 0


def _command_service_list_artifacts(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    _emit_json(
        {
            "status": "READY",
            "artifacts": list_service_artifacts(workspace),
            "network_required": False,
        }
    )
    return 0


def _command_service_project_attach_artifact(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    _emit_json(
        attach_service_artifact(
            workspace,
            project_id=args.project_id,
            artifact_id=args.artifact_id,
        )
    )
    return 0



def _command_service_project_activate_model(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    _emit_json(
        activate_service_project_model(
            workspace,
            project_id=args.project_id,
            artifact_id=args.artifact_id,
        )
    )
    return 0


def _command_service_project_model_history(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    _emit_json(list_service_project_model_releases(workspace, project_id=args.project_id))
    return 0


def _command_service_project_rollback_model(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    _emit_json(
        rollback_service_project_model(
            workspace,
            project_id=args.project_id,
            release_id=args.release_id,
        )
    )
    return 0


def _command_service_queue_kraken_training(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    config = local_input_path(args.config, role="Kraken training configuration")
    plan = local_input_path(args.plan, role="HTR training corpus plan")
    corpus = local_input_path(args.corpus_directory, role="HTR training corpus directory")
    if not config.is_file() or not plan.is_file() or not corpus.is_dir():
        raise CliConfigurationError(
            "Kraken training requires local configuration, plan, and corpus directory"
        )
    _emit_json(
        queue_service_project_kraken_training(
            workspace,
            project_id=args.project_id,
            config_path=config,
            plan_path=plan,
            corpus_directory=corpus,
            model_name=args.model_name,
            model_license_id=args.model_license_id,
            model_description=args.model_description,
        )
    )
    return 0


def _command_service_queue_backup(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    _emit_json(queue_project_backup(workspace, args.project_id))
    return 0


def _command_service_backup_verify(args: argparse.Namespace) -> int:
    backup = local_input_path(args.backup, role="backup archive")
    _emit_json(verify_project_backup(backup))
    return 0


def _command_service_backup_restore(args: argparse.Namespace) -> int:
    backup = local_input_path(args.backup, role="backup archive")
    project = local_output_path(args.project, role="restored project destination")
    _emit_json(restore_project_backup(backup, project))
    return 0


def _command_service_serve(args: argparse.Namespace) -> int:
    workspace = local_input_path(args.workspace, role="service workspace")
    kraken = (
        None
        if args.kraken_config is None
        else LocalKraken(load_kraken_config(args.kraken_config))
    )
    bind_address = "0.0.0.0" if args.container_listen else LOOPBACK_HOST
    server = create_self_hosted_service_server(
        workspace,
        host=bind_address,
        port=args.port,
        kraken=kraken,
    )
    _emit_json(
        {
            "status": "SERVING",
            "service_workspace": str(workspace),
            "url": (
                f"http://{LOOPBACK_HOST}:{server.server_port}"
                if args.container_listen
                else server.url
            ),
            "bind_address": bind_address,
            "kraken_recognition_enabled": kraken is not None,
            "network_required": False,
        }
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    return 0


def _command_pagexml_import(args: argparse.Namespace) -> int:
    source = local_input_path(args.source, role="PAGE XML source")
    if not source.is_file():
        raise CliConfigurationError(f"PAGE XML source is not a file: {source}")
    image_root = None
    if args.image_root is not None:
        image_root = local_input_path(args.image_root, role="PAGE XML image root")
        if not image_root.is_dir():
            raise CliConfigurationError(f"PAGE XML image root is not a directory: {image_root}")
    output = local_output_path(args.output, role="PAGE XML import manifest")
    if output == source:
        raise CliConfigurationError("PAGE XML import manifest must not overwrite the XML source")
    if output.exists() and not args.replace_existing:
        raise CliConfigurationError(
            "PAGE XML import manifest already exists; pass --replace-existing to replace "
            "it atomically"
        )
    manifest = import_pagexml(source, image_root=image_root)
    atomic_write_json(output, manifest)
    _emit_json(
        {
            "status": "SUCCEEDED",
            "output": str(output),
            "pagexml_sha256": manifest["source"]["sha256"],
            "page_count": manifest["summary"]["page_count"],
            "region_count": manifest["summary"]["region_count"],
            "line_count": manifest["summary"]["line_count"],
            "network_required": False,
        }
    )
    return 0


def _command_consensus_merge(args: argparse.Namespace) -> int:
    left_path = local_input_path(args.left_label, role="left reader label")
    right_path = local_input_path(args.right_label, role="right reader label")
    if not left_path.is_file() or not right_path.is_file():
        raise CliConfigurationError("consensus inputs must both be label files")
    if left_path == right_path:
        raise CliConfigurationError("consensus requires two distinct label files")

    output = local_output_path(args.output, role="consensus output")
    if output in {left_path, right_path}:
        raise CliConfigurationError("consensus output must not overwrite either source label")
    if output.exists() and not args.replace_existing:
        raise CliConfigurationError(
            "consensus output already exists; pass --replace-existing to replace it atomically"
        )
    schema_path = local_input_path(args.schema, role="consensus schema")
    if not schema_path.is_file():
        raise CliConfigurationError(f"consensus schema is not a file: {schema_path}")
    if output == schema_path:
        raise CliConfigurationError("consensus output must not overwrite its schema")

    left = load_grounded_reader_label(left_path)
    right = load_grounded_reader_label(right_path)
    result = merge_labels(left, right)
    grounding_incidents = validate_cross_reader_grounding(left, right)
    findings = (
        validate_dates(result)
        + validate_formula_positions(left)
        + validate_formula_positions(right)
        + grounding_incidents
    )
    record = build_consensus_record(
        result,
        left,
        right,
        findings=findings,
        schema_ref=schema_path.name,
        workspace_root=PROJECT_ROOT,
    )
    write_consensus_record(output, record, schema_path=schema_path)
    summary = record["derivation"]["confidence_summary"]
    _emit_json(
        {
            "status": "SUCCEEDED",
            "record_id": record["record_id"],
            "output": str(output),
            "source_label_ids": list(result.reader_label_ids),
            "field_count": summary["field_count"],
            "dual_disagreement_count": summary["dual_disagreement_count"],
            "validator_finding_count": summary["validator_finding_count"],
            "groundedness_incident_count": len(grounding_incidents),
            "quality_metrics": paired_quality_metrics((left, right)),
            "arbitration_request_count": len(record["arbitration"]["requests"]),
        }
    )
    return 0


def _command_kraken_inspect(args: argparse.Namespace) -> int:
    config_path = local_input_path(args.config, role="kraken config")
    kraken = LocalKraken(load_kraken_config(config_path))
    _emit_json(kraken_report(kraken))
    return 0


def _command_kraken_recognize(args: argparse.Namespace) -> int:
    config_path = local_input_path(args.config, role="kraken config")
    kraken = LocalKraken(load_kraken_config(config_path))
    pagexml = local_input_path(args.pagexml, role="input PAGE XML")
    if not pagexml.is_file():
        raise CliConfigurationError(f"input PAGE XML is not a file: {pagexml}")
    output = local_output_path(args.output, role="Kraken PAGE XML output")
    if output in {config_path, pagexml}:
        raise CliConfigurationError("Kraken PAGE XML output must not overwrite any input file")
    result = kraken.recognize_pagexml(
        pagexml,
        output,
        replace_existing=args.replace_existing,
    )
    stdout_path = output.with_suffix(".kraken.stdout.txt")
    stderr_path = output.with_suffix(".kraken.stderr.txt")
    atomic_write_text(stdout_path, result.stdout)
    atomic_write_text(stderr_path, result.stderr)
    _emit_json(
        {
            "status": "SUCCEEDED",
            "input_pagexml": str(pagexml),
            "output": str(result.output_path),
            "raw_stdout": str(stdout_path),
            "raw_stderr": str(stderr_path),
            "source_sha256": result.source_sha256,
            "output_sha256": result.output_sha256,
            "runtime_fingerprint": result.runtime_fingerprint,
            "network_required": False,
        }
    )
    return 0


def _command_reader_inspect(args: argparse.Namespace) -> int:
    config_path = local_input_path(args.config, role="reader config")
    reader = LocalReader(load_local_reader_config(config_path))
    _emit_json(reader_report(reader))
    return 0


def _command_reader_infer(args: argparse.Namespace) -> int:
    config_path = local_input_path(args.config, role="reader config")
    reader = LocalReader(load_local_reader_config(config_path))
    scan = local_input_path(args.scan, role="input scan")
    if not scan.is_file():
        raise CliConfigurationError(f"input scan is not a file: {scan}")
    brief_path = local_input_path(args.brief, role="batch brief")
    brief = load_json_object(brief_path, role="batch brief")
    require_local_only_data(brief, location="batch brief")
    output = local_output_path(args.output, role="inference output")
    if output in {config_path, scan, brief_path}:
        raise CliConfigurationError("inference output must not overwrite any input file")
    result = reader.read(scan, batch_brief=brief)
    atomic_write_json(output, result.payload)
    stdout_path = output.with_suffix(".stdout.txt")
    stderr_path = output.with_suffix(".stderr.txt")
    atomic_write_text(stdout_path, result.stdout)
    atomic_write_text(stderr_path, result.stderr)
    _emit_json(
        {
            "status": "SUCCEEDED",
            "output": str(output),
            "raw_stdout": str(stdout_path),
            "raw_stderr": str(stderr_path),
            "runtime_fingerprint": reader.runtime_fingerprint,
            "inference_fingerprint": result.inference_fingerprint,
        }
    )
    return 0


def _command_kraken_train(args: argparse.Namespace) -> int:
    config = local_input_path(args.config, role="Kraken training configuration")
    plan = local_input_path(args.plan, role="HTR corpus plan")
    corpus_directory = local_input_path(
        args.corpus_directory,
        role="HTR training corpus directory",
    )
    output_directory = local_output_path(
        args.output_directory,
        role="Kraken training output directory",
    )
    if not config.is_file() or not plan.is_file() or not corpus_directory.is_dir():
        raise CliConfigurationError(
            "Kraken training requires local configuration, plan, and corpus directory"
        )
    if output_directory.exists():
        raise CliConfigurationError(
            f"Kraken training output directory already exists: {output_directory}"
        )
    report = run_kraken_training(config, plan, corpus_directory, output_directory)
    _emit_json(report)
    return 0


def _command_kraken_evaluate(args: argparse.Namespace) -> int:
    config = local_input_path(args.config, role="Kraken evaluation configuration")
    plan = local_input_path(args.plan, role="HTR corpus plan")
    corpus_directory = local_input_path(
        args.corpus_directory,
        role="HTR training corpus directory",
    )
    training_run_directory = local_input_path(
        args.training_run_directory,
        role="Kraken training run directory",
    )
    output_directory = local_output_path(
        args.output_directory,
        role="Kraken evaluation output directory",
    )
    if (
        not config.is_file()
        or not plan.is_file()
        or not corpus_directory.is_dir()
        or not training_run_directory.is_dir()
    ):
        raise CliConfigurationError(
            "Kraken evaluation requires local configuration, plan, corpus, and training run"
        )
    if output_directory.exists():
        raise CliConfigurationError(
            f"Kraken evaluation output directory already exists: {output_directory}"
        )
    report = run_kraken_evaluation(
        config,
        plan,
        corpus_directory,
        training_run_directory,
        output_directory,
    )
    _emit_json(report)
    return 0


def _command_batch_run(args: argparse.Namespace) -> int:
    config_path = local_input_path(args.config, role="reader config")
    reader = LocalReader(load_local_reader_config(config_path))
    manifest = local_input_path(args.manifest, role="batch manifest")
    manifest_payload = load_strict_json(manifest, role="batch manifest")
    require_local_only_data(manifest_payload, location="batch manifest")
    output_dir = local_output_path(args.output_dir, role="batch output directory")
    checkpoint = local_output_path(args.checkpoint, role="batch checkpoint")
    if checkpoint in {config_path, manifest}:
        raise CliConfigurationError("batch checkpoint must not overwrite config or manifest")
    jobs = load_manifest_jobs(manifest, output_root=output_dir)
    protected_inputs = {config_path, manifest, checkpoint}
    for job in jobs:
        output_path = job.output_path.resolve()
        if output_path in protected_inputs or output_path == job.scan_path.resolve():
            raise CliConfigurationError(
                f"{job.job_id}: batch output must not overwrite a scan or run-control file"
            )

    def read_job(job: BatchJob) -> Mapping[str, Any]:
        try:
            result = reader.read(job.scan_path, batch_brief=brief_for_job(job))
            atomic_write_text(job.output_path.with_suffix(".stdout.txt"), result.stdout)
            atomic_write_text(job.output_path.with_suffix(".stderr.txt"), result.stderr)
            return result.payload
        except LocalReaderError as error:
            if not error.has_process_diagnostics:
                raise
            stdout_path = job.output_path.with_suffix(".failed.stdout.txt")
            stderr_path = job.output_path.with_suffix(".failed.stderr.txt")
            atomic_write_text(stdout_path, error.stdout or "")
            atomic_write_text(stderr_path, error.stderr or "")
            raise LocalReaderError(
                f"{error}; raw_stdout={stdout_path}; raw_stderr={stderr_path}",
                stdout=error.stdout,
                stderr=error.stderr,
            ) from error

    def report_progress(progress: Any, snapshot: Any) -> None:
        payload: dict[str, Any] = {"progress": progress.as_dict()}
        if snapshot is not None:
            payload["job_id"] = snapshot.job_id
            payload["status"] = snapshot.status.value
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)

    identity = InferenceIdentity(
        model_hash=model_identity(reader),
        prompt_hash=reader.artifact_hashes["prompt"],
        schema=(
            f"label:{reader.artifact_hashes['schema']};"
            f"model:{reader.artifact_hashes.get('model_schema', reader.artifact_hashes['schema'])}"
        ),
        decoding_config={
            **generation_report(reader.config),
            "runtime_fingerprint": reader.runtime_fingerprint,
        },
    )
    runner = BatchRunner(
        jobs=jobs,
        reader=read_job,
        identity=identity,
        checkpoint_path=checkpoint,
        as_of_year=args.as_of_year,
        max_retries=args.max_retries,
        progress_callback=report_progress,
        preserve_failed_retry_history=args.rebind_failed_fingerprints,
    )
    progress = runner.run()
    report = {
        "status": (
            "COMPLETE"
            if not (progress.pending or progress.running or progress.failed or progress.interrupted)
            else "INCOMPLETE"
        ),
        "checkpoint": str(checkpoint),
        "output_dir": str(output_dir),
        "runtime_fingerprint": reader.runtime_fingerprint,
        "progress": progress.as_dict(),
        "failed_fingerprint_rebind": (
            "enabled" if args.rebind_failed_fingerprints else "disabled"
        ),
    }
    _emit_json(report)
    return 0 if report["status"] == "COMPLETE" else 1


def _command_adjudicate(args: argparse.Namespace) -> int:
    wave_id = args.wave.strip()
    if not wave_id:
        raise CliConfigurationError("--wave must be a nonblank identifier")
    wave_slug = wave_id if wave_id.casefold().startswith("wave-") else f"wave-{wave_id}"
    output_raw = args.output_dir or PROJECT_ROOT / "human_check" / "generated" / wave_slug

    if args.answers is not None:
        if args.spec is not None or args.replace_existing:
            raise CliConfigurationError(
                "--spec and --replace-existing are generation-only options"
            )
        packet_dir = local_input_path(output_raw, role="adjudication packet directory")
        if not packet_dir.is_dir():
            raise CliConfigurationError(
                f"adjudication packet directory is not a directory: {packet_dir}"
            )
        answers = local_input_path(args.answers, role="adjudication answers")
        if not answers.is_file():
            raise CliConfigurationError(f"adjudication answers is not a file: {answers}")
        report = ingest_answers(
            project_root=PROJECT_ROOT,
            packet_dir=packet_dir,
            answers_path=answers,
        )
    else:
        spec_raw = args.spec or PROJECT_ROOT / "human_check" / "waves" / f"{wave_slug}.json"
        spec = local_input_path(spec_raw, role="adjudication wave specification")
        if not spec.is_file():
            raise CliConfigurationError(
                f"adjudication wave specification is not a file: {spec}"
            )
        output_dir = local_output_path(output_raw, role="adjudication packet directory")
        if output_dir == spec or output_dir in spec.parents:
            raise CliConfigurationError(
                "adjudication output directory must not contain or overwrite its specification"
            )
        report = generate_packet(
            project_root=PROJECT_ROOT,
            spec_path=spec,
            output_dir=output_dir,
            wave_id=wave_id,
            max_questions=args.max_questions,
            replace_existing=args.replace_existing,
        )
    _emit_json(report)
    return 0

def _training_clerk_year_ids(path: Path | None) -> list[str]:
    if path is None:
        return []
    payload = load_strict_json(path, role="training clerk-year manifest")
    if isinstance(payload, dict):
        require_keys(
            payload,
            required={"clerk_year_ids"},
            location="training clerk-year manifest",
        )
        payload = payload["clerk_year_ids"]
    if not isinstance(payload, list) or not all(
        isinstance(item, str) and item.strip() for item in payload
    ):
        raise CliConfigurationError(
            "training clerk-year manifest must be a string list or "
            '{"clerk_year_ids": [...]}'
        )
    if len(payload) != len(set(payload)):
        raise CliConfigurationError("training clerk-year manifest contains duplicate IDs")
    return payload


def _command_eval(args: argparse.Namespace) -> int:
    if args.gold_dir is None or args.holdout is None:
        raise CliConfigurationError(
            "eval requires --gold-dir and --holdout outside an Application source checkout"
        )
    gold_dir = local_input_path(args.gold_dir, role="gold directory")
    if not gold_dir.is_dir():
        raise CliConfigurationError(f"gold directory is not a directory: {gold_dir}")
    gold_paths = sorted(gold_dir.glob("*.json"))
    if not gold_paths:
        raise CliConfigurationError(f"gold directory contains no JSON records: {gold_dir}")
    gold_records = [
        load_json_object(path, role=f"gold record {path.name}") for path in gold_paths
    ]
    prediction_path = local_input_path(args.predictions, role="prediction input")
    predictions = load_prediction_records(prediction_path)
    holdout_path = local_input_path(args.holdout, role="holdout manifest")
    holdout = load_json_object(holdout_path, role="holdout manifest")
    report = evaluate_predictions(
        gold_records,
        predictions,
        holdout,
        training_clerk_year_ids=_training_clerk_year_ids(args.training_clerk_years),
    )
    output = local_output_path(args.output, role="evaluation output") if args.output else None
    table_output = (
        local_output_path(args.strata_table, role="stratified table output")
        if args.strata_table
        else None
    )
    destinations = [path for path in (output, table_output) if path is not None]
    protected_inputs = {holdout_path, *gold_paths}
    if args.training_clerk_years is not None:
        protected_inputs.add(
            local_input_path(
                args.training_clerk_years,
                role="training clerk-year manifest",
            )
        )
    for destination in destinations:
        if destination in protected_inputs or _path_is_within(
            destination, prediction_path
        ) or _path_is_within(destination, gold_dir):
            raise CliConfigurationError("evaluation outputs must not overwrite any input file")
    if output is not None and output == table_output:
        raise CliConfigurationError(
            "evaluation JSON and stratified table outputs must be distinct paths"
        )
    if table_output is not None:
        atomic_write_text(table_output, render_stratified_markdown(report))
    if output is not None:
        atomic_write_json(output, report)
    _emit_json(report)
    return 0


def _path_is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _command_compare(args: argparse.Namespace) -> int:
    left_path = local_input_path(args.left, role="left comparison input")
    right_path = local_input_path(args.right, role="right comparison input")
    if left_path == right_path:
        raise CliConfigurationError("comparison requires two distinct input paths")

    if args.max_disagreements < 0:
        raise CliConfigurationError("max_disagreements must be zero or greater")

    output = local_output_path(args.output, role="comparison output") if args.output else None
    csv_output = local_output_path(args.csv, role="comparison CSV output") if args.csv else None
    destinations = [path for path in (output, csv_output) if path is not None]
    for destination in destinations:
        if _path_is_within(destination, left_path) or _path_is_within(
            destination, right_path
        ):
            raise CliConfigurationError(
                "comparison outputs must not be inside either input file or directory"
            )
    if output is not None and output == csv_output:
        raise CliConfigurationError("comparison JSON and CSV outputs must be distinct paths")

    report = compare_reader_labels(
        left_path,
        right_path,
        max_disagreements=None if csv_output is not None else args.max_disagreements,
        require_grounded=args.require_grounded,
    )
    if csv_output is not None:
        all_disagreements = report["disagreements"]["items"]
        atomic_write_text(csv_output, render_disagreements_csv(all_disagreements))
        returned = all_disagreements[: args.max_disagreements]
        report = {
            **report,
            "csv_output": str(csv_output),
            "disagreements": {
                **report["disagreements"],
                "returned": len(returned),
                "truncated": report["disagreements"]["total"] > len(returned),
                "items": returned,
            },
        }
    if output is not None:
        report = {**report, "output": str(output)}
        atomic_write_json(output, report)
    _emit_json(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run one local-only CLI command with concise, non-secret error reporting."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "doctor": _command_doctor,
        "checkout-verify": _command_checkout_verify,
        "prompt-verify": _command_prompt_verify,
        "label-validate": _command_label_validate,
        "collection-create": _command_collection_create,
        "collection-add-project": _command_collection_add_project,
        "collection-inspect": _command_collection_inspect,
        "collection-list-documents": _command_collection_list_documents,
        "collection-search": _command_collection_search,
        "collection-save-search": _command_collection_save_search,
        "collection-list-saved-searches": _command_collection_list_saved_searches,
        "collection-run-saved-search": _command_collection_run_saved_search,
        "collection-export-public": _command_collection_export_public,
        "project-create": _command_project_create,
        "project-inspect": _command_project_inspect,
        "project-list-documents": _command_project_list_documents,
        "project-search": _command_project_search,
        "project-update-document": _command_project_update_document,
        "project-import-pagexml": _command_project_import_pagexml,
        "project-import-images": _command_project_import_images,
        "project-import-pdf": _command_project_import_pdf,
        "project-import-htr-suggestions": _command_project_import_htr_suggestions,
        "project-kraken-segment": _command_project_kraken_segment,
        "project-kraken-recognize": _command_project_kraken_recognize,
        "project-export-pagexml": _command_project_export_pagexml,
        "project-export-transcript": _command_project_export_transcript,
        "project-export-transcriptions-csv": _command_project_export_transcriptions_csv,
        "project-export-alto": _command_project_export_alto,
        "project-export-pdf": _command_project_export_pdf,
        "project-revise-line-geometry": _command_project_revise_line_geometry,
        "project-revise-page-reading-order": _command_project_revise_page_reading_order,
        "project-revise-region-geometry": _command_project_revise_region_geometry,
        "project-export-review-package": _command_project_export_review_package,
        "project-import-review-package": _command_project_import_review_package,
        "project-resolve-review-proposal": _command_project_resolve_review_proposal,
        "project-evaluate-htr": _command_project_evaluate_htr,
        "project-grant-training-consent": _command_project_grant_training_consent,
        "project-revoke-training-consent": _command_project_revoke_training_consent,
        "project-training-readiness": _command_project_training_readiness,
        "project-export-consented-training-pagexml": (
            _command_project_export_consented_training_pagexml
        ),
        "htr-build-corpus": _command_htr_build_corpus,
        "htr-inspect-corpus": _command_htr_inspect_corpus,
        "workbench": _command_workbench,
        "serve": _command_serve,
        "service-create": _command_service_create,
        "service-inspect": _command_service_inspect,
        "service-user-create": _command_service_user_create,
        "service-list-users": _command_service_list_users,
        "service-grant-role": _command_service_grant_role,
        "service-add-project": _command_service_add_project,
        "service-list-projects": _command_service_list_projects,
        "service-artifact-register": _command_service_artifact_register,
        "service-list-artifacts": _command_service_list_artifacts,
        "service-project-attach-artifact": _command_service_project_attach_artifact,
        "service-project-activate-model": _command_service_project_activate_model,
        "service-project-model-history": _command_service_project_model_history,
        "service-project-rollback-model": _command_service_project_rollback_model,
        "service-queue-kraken-training": _command_service_queue_kraken_training,
        "service-queue-backup": _command_service_queue_backup,
        "service-backup-verify": _command_service_backup_verify,
        "service-backup-restore": _command_service_backup_restore,
        "service-serve": _command_service_serve,
        "pagexml-import": _command_pagexml_import,
        "consensus-merge": _command_consensus_merge,
        "reader-inspect": _command_reader_inspect,
        "reader-infer": _command_reader_infer,
        "kraken-inspect": _command_kraken_inspect,
        "kraken-recognize": _command_kraken_recognize,
        "kraken-train": _command_kraken_train,
        "kraken-evaluate": _command_kraken_evaluate,
        "batch-run": _command_batch_run,
        "adjudicate": _command_adjudicate,
        "eval": _command_eval,
        "compare": _command_compare,
    }
    if args.command is None:
        parser.print_help()
        return 0

    try:
        return handlers[args.command](args)
    except KeyboardInterrupt:
        print("aktreader: interrupted; checkpoint state was preserved", file=sys.stderr)
        return 130
    except (
        CliConfigurationError,
        KrakenError,
        KrakenTrainingError,
        KrakenEvaluationError,
        LocalReaderError,
        ServiceError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(f"aktreader: error: {error}", file=sys.stderr)
        return 2
