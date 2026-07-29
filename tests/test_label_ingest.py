import copy
import hashlib
import json
from pathlib import Path

import pytest

from aktreader.labels import (
    CANONICAL_READER_PROMPT_V1_SHA256,
    KNOWN_STALE_READER_A_PROMPT_SHA256,
    LabelValidationError,
    load_reader_label,
    parse_canonical_reader_label,
    parse_legacy_reader_a,
)

ROOT = Path(__file__).resolve().parents[1]
READER_A = ROOT / "labels" / "readerA" / "serock-1890-death-1.json"
READER_A_NEW = ROOT / "labels" / "readerA" / "serock-1890-death-3.json"
READER_B = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"


def _canonical_payload() -> dict:
    return json.loads(READER_B.read_text(encoding="utf-8"))


def test_supplied_canonical_reader_b_loads_immutably() -> None:
    before = hashlib.sha256(READER_B.read_bytes()).hexdigest()

    label = load_reader_label(READER_B)

    assert label.schema_kind == "canonical"
    assert label.record_id == "serock-1890-death-1"
    assert label.reader_family == "gpt"
    assert label.prompt_binding_verified is True
    assert label.artifact_binding_verified is True
    assert label.confidence_cap == "CONFIDENT_ELIGIBLE"
    assert label.source_sha256 == before
    with pytest.raises(TypeError):
        label.observations["principal.name"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        label.observations["principal.name"]["value"] = "invented"  # type: ignore[index]
    assert hashlib.sha256(READER_B.read_bytes()).hexdigest() == before


def test_supplied_legacy_reader_a_is_honestly_adapted() -> None:
    label = load_reader_label(READER_A)

    assert label.schema_kind == "legacy_reader_a"
    assert label.reader_family == "claude"
    assert label.record_id == "serock-1890-death-1"
    assert label.prompt_sha256 is None
    assert label.prompt_binding_verified is False
    assert label.provenance_errata[0]["claimed_hash_field_status"] == "ABSENT_IN_FILE"
    assert label.provenance_errata[0]["claimed_sha256"] is None
    assert (
        label.provenance_errata[0]["coordinator_reported_sha256"]
        == KNOWN_STALE_READER_A_PROMPT_SHA256
    )
    assert label.provenance_errata[0]["canonical_sha256"] == CANONICAL_READER_PROMPT_V1_SHA256
    assert label.artifact_sha256 is None
    assert label.artifact_binding_verified is False
    assert label.clerk_year_id is None
    assert label.source_spans == {}
    assert label.confidence_cap == "PROBABLE"
    assert "prompt hash" in " ".join(label.binding_notes)

    age = label.observations["principal.age"]
    assert age["value"] == 61
    assert age["confidence"] == "PROBABLE"
    assert any("downgraded" in note for note in age["notes"])
    assert label.observations["act_no"]["value"] == 1
    assert "explicit legacy register metadata" in label.observations["act_no"]["notes"][0]
    assert "declarants.0.original_script" not in label.observations
    assert label.observations["declarants.0.name"]["original_script"] == "Израель Іосковичъ"


def test_canonical_loader_rejects_single_reader_confident() -> None:
    payload = _canonical_payload()
    payload["observations"]["principal.age"]["confidence"] = "CONFIDENT"

    with pytest.raises(LabelValidationError, match="single reader"):
        parse_canonical_reader_label(payload)


def test_canonical_loader_rejects_unbound_or_dangling_spans() -> None:
    payload = _canonical_payload()
    payload["observations"]["principal.age"]["source_span_ids"] = ["not-a-real-span"]

    with pytest.raises(LabelValidationError, match="unknown source span"):
        parse_canonical_reader_label(payload)


def test_canonical_loader_rejects_nonblind_and_extra_data() -> None:
    nonblind = _canonical_payload()
    nonblind["reader"]["other_reader_output_seen"] = True
    with pytest.raises(LabelValidationError, match="blind pass"):
        parse_canonical_reader_label(nonblind)

    extra = _canonical_payload()
    extra["api_key"] = "must-never-exist"
    with pytest.raises(LabelValidationError, match="unexpected"):
        parse_canonical_reader_label(extra)


def test_canonical_loader_rejects_invalid_datetime() -> None:
    payload = _canonical_payload()
    payload["created_at"] = "not-a-date"

    with pytest.raises(LabelValidationError, match="ISO date-time"):
        parse_canonical_reader_label(payload)


def test_parser_does_not_mutate_caller_payload() -> None:
    payload = _canonical_payload()
    before = copy.deepcopy(payload)

    parse_canonical_reader_label(payload)

    assert payload == before


def test_canonical_loader_accepts_only_supported_prompt_versions() -> None:
    v1_1 = _canonical_payload()
    v1_1["prompt"]["version"] = "1.1.0"
    assert parse_canonical_reader_label(v1_1).prompt_binding_verified is True

    v1_2 = _canonical_payload()
    v1_2["prompt"]["version"] = "1.2.0"
    assert parse_canonical_reader_label(v1_2).prompt_binding_verified is True

    v1_3 = _canonical_payload()
    v1_3["prompt"]["version"] = "1.3.0"
    assert parse_canonical_reader_label(v1_3).prompt_binding_verified is True

    unsupported = _canonical_payload()
    unsupported["prompt"]["version"] = "1.4.0"
    with pytest.raises(LabelValidationError, match="unsupported prompt"):
        parse_canonical_reader_label(unsupported)


def test_new_legacy_reader_a_metadata_is_preserved_without_binding_invention() -> None:
    label = load_reader_label(READER_A_NEW)

    assert label.prompt_sha256 == KNOWN_STALE_READER_A_PROMPT_SHA256
    assert label.prompt_binding_verified is False
    assert len(label.provenance_errata) == 1
    erratum = label.provenance_errata[0]
    assert erratum["code"] == "PROVENANCE_ERRATA"
    assert erratum["claimed_hash_field_status"] == "PRESENT_STALE"
    assert erratum["claimed_sha256"] == KNOWN_STALE_READER_A_PROMPT_SHA256
    assert erratum["coordinator_reported_sha256"] == KNOWN_STALE_READER_A_PROMPT_SHA256
    assert erratum["canonical_sha256"] == CANONICAL_READER_PROMPT_V1_SHA256
    assert erratum["prompt_version"] == "1.0.0"
    assert erratum["effect"] == "CONTENT_STANDS_PROMPT_BINDING_UNVERIFIED"
    assert any("PROVENANCE_ERRATA" in note for note in label.binding_notes)
    assert label.raw["provenance_errata"][0]["claimed_sha256"] == label.prompt_sha256
    assert label.clerk_year_id is None
    assert any("clerk-year proxy" in note for note in label.binding_notes)
    mother = label.observations["mother.name"]
    assert mother["observation_state"] == "STATED_UNKNOWN"
    assert mother["value"] is None
    assert any("stated unknown" in note for note in mother["notes"])


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("reader", "identity", "unrelated subscription Reader A"),
        ("reader", "date", "2026-07-27"),
        ("register", "town", "PuÅ‚tusk"),
        ("register", "act_no", 7),
    ],
)
def test_unrelated_missing_hash_legacy_labels_receive_no_external_erratum(
    section: str,
    key: str,
    value: object,
) -> None:
    payload = json.loads(READER_A.read_text(encoding="utf-8"))
    payload[section][key] = value

    label = parse_legacy_reader_a(payload)

    assert label.prompt_sha256 is None
    assert label.provenance_errata == ()
    assert all("PROVENANCE_ERRATA" not in note for note in label.binding_notes)
