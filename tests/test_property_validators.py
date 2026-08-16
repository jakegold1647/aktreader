from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from aktreader.gold import GoldValidationError, validate_gold_record
from aktreader.labels import EVIDENCE_KEYS as LABEL_EVIDENCE_KEYS
from aktreader.labels import OBSERVATION_STATES as LABEL_OBSERVATION_STATES
from aktreader.labels import LabelValidationError, parse_canonical_reader_label

ROOT = Path(__file__).resolve().parents[1]
READER_B = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"
GOLD_RECORD = ROOT / "gold" / "acts" / "pultusk-1877-death-13.json"


def _canonical_payload() -> dict[str, Any]:
    return json.loads(READER_B.read_text(encoding="utf-8"))


def _gold_record() -> dict[str, Any]:
    return json.loads(GOLD_RECORD.read_text(encoding="utf-8"))


def _first_evidence(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and {"value", "confidence", "observation_state"}.issubset(value):
        return value
    if isinstance(value, dict):
        for child in value.values():
            try:
                return _first_evidence(child)
            except LookupError:
                pass
    if isinstance(value, list):
        for child in value:
            try:
                return _first_evidence(child)
            except LookupError:
                pass
    raise LookupError("no evidence field found")


@settings(max_examples=16, derandomize=True)
@given(st.text(min_size=1, max_size=24).filter(lambda value: value not in LABEL_OBSERVATION_STATES))
def test_canonical_labels_reject_generated_unknown_observation_states(state: str) -> None:
    payload = _canonical_payload()
    payload["observations"]["principal.age"]["observation_state"] = state

    with pytest.raises(LabelValidationError, match="invalid state"):
        parse_canonical_reader_label(payload)


@settings(max_examples=len(LABEL_EVIDENCE_KEYS), derandomize=True)
@given(st.sampled_from(sorted(LABEL_EVIDENCE_KEYS)))
def test_canonical_labels_reject_each_missing_evidence_key(key: str) -> None:
    payload = _canonical_payload()
    del payload["observations"]["principal.age"][key]

    with pytest.raises(LabelValidationError, match="missing"):
        parse_canonical_reader_label(payload)


@settings(max_examples=8, derandomize=True)
@given(st.sampled_from(["ABSENT_ON_FORM", "BLANK", "STATED_UNKNOWN", "ILLEGIBLE"]))
def test_gold_rejects_generated_nonpresent_values(state: str) -> None:
    record = _gold_record()
    evidence = _first_evidence(record["fields"])
    evidence["observation_state"] = state
    evidence["value"] = "invented value"

    with pytest.raises(GoldValidationError, match=state):
        validate_gold_record(record)


@settings(max_examples=16, derandomize=True)
@given(st.text(min_size=1, max_size=32).filter(lambda value: not value.startswith("[unclear: ")))
def test_gold_rejects_generated_unclear_values_without_marker(value: str) -> None:
    record = _gold_record()
    evidence = _first_evidence(record["fields"])
    evidence["confidence"] = "UNCLEAR"
    evidence["value"] = value
    evidence["alternatives"] = [{"value": "other", "source": "synthetic"}]

    with pytest.raises(GoldValidationError, match=r"UNCLEAR.*\[unclear"):
        validate_gold_record(record)


def test_generated_mutations_do_not_modify_fixture_payloads() -> None:
    canonical = _canonical_payload()
    gold = _gold_record()
    canonical_before = copy.deepcopy(canonical)
    gold_before = copy.deepcopy(gold)

    with pytest.raises(LabelValidationError):
        mutated = copy.deepcopy(canonical)
        mutated["observations"]["principal.age"]["confidence"] = "CONFIDENT"
        parse_canonical_reader_label(mutated)

    with pytest.raises(GoldValidationError):
        mutated_gold = copy.deepcopy(gold)
        evidence = _first_evidence(mutated_gold["fields"])
        evidence["observation_state"] = "PRESENT"
        evidence["value"] = None
        validate_gold_record(mutated_gold)

    assert canonical == canonical_before
    assert gold == gold_before
