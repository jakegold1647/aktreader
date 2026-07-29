import copy
import json
from pathlib import Path

import pytest
from tools.build_consensus import _complete_pair_paths, _parse_args, _selected_pair_paths

from aktreader.consensus import merge_labels
from aktreader.consensus_record import (
    ConsensusRecordError,
    ThirdReaderVote,
    apply_third_reader_vote,
    build_consensus_record,
    record_sha256,
    write_consensus_record,
)
from aktreader.labels import load_reader_label
from aktreader.schema import ContractValidationError, validate_instance
from aktreader.validators.dates import validate_dates
from aktreader.validators.formula import validate_formula_positions

ROOT = Path(__file__).resolve().parents[1]
READER_A = ROOT / "labels" / "readerA" / "serock-1890-death-1.json"
READER_B = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"
READER_A_ERRATUM = ROOT / "labels" / "readerA" / "serock-1890-death-3.json"
READER_B_ERRATUM = ROOT / "labels" / "readerB" / "serock-1890-death-3.json"
ACT_SCHEMA = ROOT / "schemas" / "act-record-2.0.0.schema.json"


def _first_record():
    reader_a = load_reader_label(READER_A)
    reader_b = load_reader_label(READER_B)
    result = merge_labels(reader_a, reader_b)
    findings = (
        validate_dates(result)
        + validate_formula_positions(reader_a)
        + validate_formula_positions(reader_b)
    )
    record = build_consensus_record(
        result,
        reader_a,
        reader_b,
        findings=findings,
        workspace_root=ROOT,
    )
    return reader_a, reader_b, record


def _vote(
    field_path,
    *,
    selected_candidate_id=None,
    novel_candidate=None,
    identities_seen=False,
):
    return ThirdReaderVote(
        field_path=field_path,
        reader_id="independent-local-arbiter",
        reader_family="local-vlm",
        reader_version="test-model-v1",
        session_id="fresh-session-001",
        independence_basis="DIFFERENT_MODEL",
        occurred_at="2026-07-28T18:00:00-04:00",
        selected_candidate_id=selected_candidate_id,
        novel_candidate=novel_candidate,
        reader_identities_seen=identities_seen,
    )


def test_first_consensus_record_validates_and_is_deterministic() -> None:
    _, _, first = _first_record()
    _, _, second = _first_record()

    validate_instance(first, ACT_SCHEMA)
    assert first == second
    assert record_sha256(first) == record_sha256(second)
    assert first["schema_version"] == "2.0.0"
    assert first["record_kind"] == "DUAL_READER_CONSENSUS"
    assert first["clerk_year"]["binding_status"] == "SINGLE_READER_METADATA"
    assert first["artifact"]["binding_status"] == "SINGLE_READER_HASH"
    assert first["derivation"]["pair_assessment"]["fully_verified"] is False
    assert first["compliance"]["training_eligible"] is False


def test_disagreements_and_legacy_caveats_survive_serialization() -> None:
    reader_a, _, record = _first_record()

    assert any("prompt hash" in note for note in reader_a.binding_notes)
    source = next(
        item
        for item in record["derivation"]["source_labels"]
        if item["label_id"] == reader_a.label_id
    )
    assert source["prompt_sha256"] is None
    assert source["provenance_errata"][0]["claimed_hash_field_status"] == "ABSENT_IN_FILE"
    assert source["provenance_errata"][0]["claimed_sha256"] is None
    field = record["fields"]["principal.name"]
    assert field["resolution"]["status"] == "DUAL_DISAGREEMENT"
    assert field["confidence"] == "UNCLEAR"
    assert field["value"].startswith("[unclear: ")
    assert {candidate["reader_family"] for candidate in field["candidates"]} == {
        "claude",
        "gpt",
    }
    assert field["resolution"]["confidence_eligible"] is False
    request = next(
        item for item in record["arbitration"]["requests"] if item["field_path"] == "principal.name"
    )
    assert request["status"] == "PENDING"
    assert request["context_policy"] == {
        "span_and_candidates_only": True,
        "reader_identities_hidden": True,
        "full_labels_hidden": True,
    }
    assert all("reader_id" not in candidate for candidate in request["candidates"])
    assert record["arbitration"]["events"] == []


def test_known_prompt_erratum_is_machine_readable_in_source_provenance() -> None:
    reader_a = load_reader_label(READER_A_ERRATUM)
    reader_b = load_reader_label(READER_B_ERRATUM)
    result = merge_labels(reader_a, reader_b)
    record = build_consensus_record(
        result,
        reader_a,
        reader_b,
        workspace_root=ROOT,
    )

    validate_instance(record, ACT_SCHEMA)
    source = next(
        item
        for item in record["derivation"]["source_labels"]
        if item["label_id"] == reader_a.label_id
    )
    assert source["prompt_sha256"] == reader_a.prompt_sha256
    assert source["prompt_binding_verified"] is False
    assert source["provenance_errata"] == [
        {
            "code": "PROVENANCE_ERRATA",
            "kind": "STALE_INTERMEDIATE_PROMPT_HASH",
            "claimed_hash_field_status": "PRESENT_STALE",
            "claimed_sha256": reader_a.prompt_sha256,
            "coordinator_reported_sha256": reader_a.prompt_sha256,
            "canonical_sha256": reader_b.prompt_sha256,
            "prompt_version": "1.0.0",
            "status": "KNOWN_ERRATUM",
            "effect": "CONTENT_STANDS_PROMPT_BINDING_UNVERIFIED",
            "source": ("labels/consensus/FOR_SOL_wave002_brief.md#1-prompt-hash-drift-resolved"),
        }
    ]
    assert any(
        "PROVENANCE_ERRATA" in note for note in record["derivation"]["pair_assessment"]["notes"]
    )


def test_dual_agreement_is_not_silently_promoted() -> None:
    _, _, record = _first_record()
    field = record["fields"]["principal.sex"]

    assert field["resolution"]["status"] == "EXACT_AGREEMENT"
    assert field["confidence"] == "PROBABLE"
    assert field["resolution"]["confidence_cap"] == "PROBABLE"
    assert field["resolution"]["confidence_eligible"] is False


def test_third_reader_2_of_3_creates_probable_new_revision() -> None:
    _, _, record = _first_record()
    before = copy.deepcopy(record)
    request = next(
        item for item in record["arbitration"]["requests"] if item["field_path"] == "principal.name"
    )

    updated = apply_third_reader_vote(
        record,
        _vote(
            "principal.name",
            selected_candidate_id=request["candidates"][0]["candidate_id"],
        ),
    )

    validate_instance(updated, ACT_SCHEMA)
    assert record == before
    assert updated["revision"] == 2
    assert updated["parent_record_sha256"] == record_sha256(record)
    field = updated["fields"]["principal.name"]
    assert field["resolution"]["status"] == "ARBITRATED_2_OF_3"
    assert field["confidence"] == "PROBABLE"
    assert field["resolution"]["confidence_cap"] == "PROBABLE"
    assert field["resolution"]["confidence_eligible"] is False
    assert len(field["candidates"]) == 3
    assert updated["arbitration"]["events"][0]["outcome"] == "RESOLVED_2_OF_3"


def test_third_distinct_reading_stays_unclear() -> None:
    _, _, record = _first_record()

    updated = apply_third_reader_vote(
        record,
        _vote(
            "principal.name",
            novel_candidate={
                "observation_state": "PRESENT",
                "value": "Third distinct reading",
                "original_script": "Третье отличное чтение",
                "reported_alternatives": [],
            },
        ),
    )

    validate_instance(updated, ACT_SCHEMA)
    field = updated["fields"]["principal.name"]
    assert field["resolution"]["status"] == "ARBITRATION_ALL_DIVERGE"
    assert field["confidence"] == "UNCLEAR"
    assert field["value"].startswith("[unclear: ")
    assert len(field["candidates"]) == 3
    assert updated["arbitration"]["events"][0]["outcome"] == "ALL_DIVERGE"


def test_arbiter_context_and_independence_are_enforced() -> None:
    _, _, record = _first_record()
    request = next(
        item for item in record["arbitration"]["requests"] if item["field_path"] == "principal.name"
    )
    with pytest.raises(ConsensusRecordError, match="span and pooled candidates"):
        apply_third_reader_vote(
            record,
            _vote(
                "principal.name",
                selected_candidate_id=request["candidates"][0]["candidate_id"],
                identities_seen=True,
            ),
        )


def test_schema_rejects_lost_candidate_provenance() -> None:
    _, _, record = _first_record()
    record["fields"]["principal.name"]["candidates"] = []

    with pytest.raises(ContractValidationError, match="too short"):
        validate_instance(record, ACT_SCHEMA)


def test_atomic_writer_emits_schema_valid_json(tmp_path: Path) -> None:
    _, _, record = _first_record()
    output = tmp_path / "record.consensus.json"

    write_consensus_record(output, record, schema_path=ACT_SCHEMA)

    loaded = json.loads(output.read_text(encoding="utf-8"))
    validate_instance(loaded, ACT_SCHEMA)
    assert loaded == record
    assert not (tmp_path / ".record.consensus.json.tmp").exists()


def test_all_complete_reader_filename_pairs_are_selected() -> None:
    names = [reader_a.name for reader_a, _ in _complete_pair_paths()]

    expected_acts = (*range(1, 7), *range(30, 50))
    expected_names = sorted(
        [
            *(f"serock-1890-death-{act_no}.json" for act_no in expected_acts),
            "serock-1890-skz-index.json",
        ]
    )
    assert names == expected_names


def test_build_tool_requires_explicit_safe_record_ids() -> None:
    with pytest.raises(SystemExit):
        _parse_args([])
    with pytest.raises(ValueError, match="invalid record IDs"):
        _selected_pair_paths(["../wave002"])

    selected = _selected_pair_paths(["serock-1890-death-2", "serock-1890-death-1"])
    assert [reader_a.stem for reader_a, _ in selected] == [
        "serock-1890-death-1",
        "serock-1890-death-2",
    ]
