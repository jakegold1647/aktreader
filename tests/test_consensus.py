import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from aktreader.consensus import ConsensusError, merge_labels, strictly_equal
from aktreader.labels import load_reader_label, parse_canonical_reader_label

ROOT = Path(__file__).resolve().parents[1]
READER_A = ROOT / "labels" / "readerA" / "serock-1890-death-1.json"
READER_B = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"
READER_A_ERRATUM = ROOT / "labels" / "readerA" / "serock-1890-death-3.json"
READER_B_ERRATUM = ROOT / "labels" / "readerB" / "serock-1890-death-3.json"


def _canonical_pair(left_field: dict | None = None, right_field: dict | None = None):
    base = json.loads(READER_B.read_text(encoding="utf-8"))
    left = copy.deepcopy(base)
    right = copy.deepcopy(base)
    left["label_id"] = "synthetic.reader-claude"
    left["reader"]["reader_id"] = "reader-claude"
    left["reader"]["reader_family"] = "claude"
    left["reader"]["reader_version"] = "test-claude"
    right["label_id"] = "synthetic.reader-gpt"
    right["reader"]["reader_id"] = "reader-gpt"
    right["reader"]["reader_family"] = "gpt"
    right["reader"]["reader_version"] = "test-gpt"
    if left_field is not None:
        left["observations"]["principal.sex"] = left_field
    if right_field is not None:
        right["observations"]["principal.sex"] = right_field
    return parse_canonical_reader_label(left), parse_canonical_reader_label(right)


def _evidence(
    value,
    *,
    original_script="умерла",
    state="PRESENT",
    confidence="PROBABLE",
):
    return {
        "value": value,
        "original_script": original_script,
        "confidence": confidence,
        "observation_state": state,
        "alternatives": [],
        "source_span_ids": ["principal"],
        "notes": [],
    }


def test_supplied_first_pair_merges_but_legacy_binding_caps_agreement() -> None:
    reader_a = load_reader_label(READER_A)
    reader_b = load_reader_label(READER_B)

    result = merge_labels(reader_a, reader_b)

    assert result.record_id == "serock-1890-death-1"
    assert result.pair.prompt_binding_verified is False
    assert any("ABSENT_IN_FILE" in note for note in result.pair.notes)
    assert result.pair.artifact_binding_verified is False
    assert result.pair.fully_verified is False
    sex = result.field("principal.sex")
    assert sex["agreement"] == "EXACT"
    assert sex["confidence"] == "PROBABLE"
    assert sex["confidence_eligible"] is False
    assert sex["confidence_cap"] == "PROBABLE"

    principal = result.field("principal.name")
    assert principal["confidence"] == "UNCLEAR"
    assert principal["value"].startswith("[unclear: ")
    assert {item["reader_family"] for item in principal["alternatives"]} == {
        "claude",
        "gpt",
    }


def test_verified_agreement_is_only_confident_eligible() -> None:
    left, right = _canonical_pair(
        _evidence("female", original_script="умерла  "),
        _evidence("female", original_script="умерла\n"),
    )

    result = merge_labels(left, right)
    field = result.field("principal.sex")

    assert result.pair.fully_verified is True
    assert field["agreement"] == "EXACT"
    assert field["confidence"] == "PROBABLE"
    assert field["confidence_eligible"] is True
    assert field["confidence_cap"] == "CONFIDENT_ELIGIBLE"


def test_only_nfc_and_whitespace_normalization_are_used() -> None:
    assert strictly_equal("Z\u0307aneta   Kowalska", "Żaneta\nKowalska")
    assert not strictly_equal("Jankiel", "Jankel")
    assert not strictly_equal(61, "61 years")
    assert not strictly_equal("Goldsztejn", "Goldstein")


def test_value_disagreement_becomes_reader_attributed_unclear() -> None:
    left, right = _canonical_pair(_evidence("female"), _evidence("male"))

    field = merge_labels(left, right).field("principal.sex")

    assert field["value"] == "[unclear: female/male]"
    assert field["confidence"] == "UNCLEAR"
    assert field["observation_state"] == "PRESENT"
    assert [item["reader_id"] for item in field["alternatives"]] == [
        "reader-claude",
        "reader-gpt",
    ]


def test_typed_state_disagreement_is_not_collapsed_to_null() -> None:
    blank = _evidence(None, original_script=None, state="BLANK", confidence=None)
    present = _evidence("female")
    left, right = _canonical_pair(blank, present)

    field = merge_labels(left, right).field("principal.sex")

    assert field["observation_state"] == "UNRESOLVED"
    assert field["value"] == "[unclear: BLANK/female]"
    assert field["alternatives"][0]["observation_state"] == "BLANK"
    assert field["alternatives"][1]["observation_state"] == "PRESENT"


def test_unreported_field_is_not_treated_as_blank() -> None:
    left, right = _canonical_pair()
    observations = dict(left.observations)
    observations.pop("principal.sex")
    left = replace(left, observations=observations)

    field = merge_labels(left, right).field("principal.sex")

    assert field["observation_state"] == "UNRESOLVED"
    assert "UNREPORTED" in field["value"]
    assert field["alternatives"][0]["reported"] is False


def test_pair_rejects_same_reader_family_target_and_prompt_mismatches() -> None:
    left, right = _canonical_pair()
    with pytest.raises(ConsensusError, match="families"):
        merge_labels(left, replace(right, reader_family=left.reader_family))

    bad_target = dict(right.target)
    bad_target["act_no"] = 99
    with pytest.raises(ConsensusError, match="target mismatch"):
        merge_labels(left, replace(right, target=bad_target))

    with pytest.raises(ConsensusError, match="prompt"):
        merge_labels(left, replace(right, prompt_sha256="f" * 64))


def test_pair_rejects_missing_blind_attestation_and_artifact_mismatch() -> None:
    left, right = _canonical_pair()
    with pytest.raises(ConsensusError, match="attest"):
        merge_labels(left, replace(right, blind_attested=False))

    with pytest.raises(ConsensusError, match="artifact"):
        merge_labels(left, replace(right, artifact_sha256="0" * 64))


def test_known_reader_a_prompt_erratum_merges_but_never_verifies_binding() -> None:
    left = load_reader_label(READER_A_ERRATUM)
    right = load_reader_label(READER_B_ERRATUM)

    result = merge_labels(left, right)

    assert result.pair.prompt_binding_verified is False
    assert any("PROVENANCE_ERRATA" in note for note in result.pair.notes)
    exact_field = next(field for field in result.fields.values() if field["agreement"] == "EXACT")
    assert exact_field["confidence_cap"] == "PROBABLE"
    assert exact_field["confidence_eligible"] is False


def test_arbitrary_legacy_prompt_mismatch_is_still_rejected() -> None:
    left = load_reader_label(READER_A_ERRATUM)
    right = load_reader_label(READER_B_ERRATUM)

    with pytest.raises(ConsensusError, match="prompt SHA-256 mismatch"):
        merge_labels(
            replace(left, prompt_sha256="f" * 64, provenance_errata=()),
            right,
        )


def test_wave001_absent_hash_erratum_rejects_conflicting_canonical_hash() -> None:
    left = load_reader_label(READER_A)
    right = load_reader_label(READER_B)

    assert left.prompt_sha256 is None
    with pytest.raises(ConsensusError, match="conflicts with PROVENANCE_ERRATA"):
        merge_labels(left, replace(right, prompt_sha256="f" * 64))
