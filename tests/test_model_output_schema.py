import copy
from pathlib import Path

import pytest

from aktreader.schema import ContractValidationError, validate_instance

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "model-output-1.0.0.schema.json"


def _payload(evidence: dict) -> dict:
    return {
        "target_check": {
            "year": 1890,
            "act_type": "death",
            "act_no": 7,
            "language": "ru",
        },
        "transcription": {
            "original_script": ["line one"],
            "translation": ["line one"],
        },
        "observations": {"principal.name": evidence},
    }


PROBABLE = {
    "value": "Goldsztejn",
    "original_script": "Гольдштейн",
    "confidence": "PROBABLE",
    "observation_state": "PRESENT",
    "alternatives": [],
    "notes": [],
}
UNCLEAR = {
    "value": "[unclear: Goldsztejn/Goldfarb]",
    "original_script": "[unclear: Гольдштейн/Гольдфарб]",
    "confidence": "UNCLEAR",
    "observation_state": "PRESENT",
    "alternatives": [
        {"value": "Goldsztejn", "original_script": "Гольдштейн"},
        {"value": "Goldfarb", "original_script": "Гольдфарб"},
    ],
    "notes": [],
}
ILLEGIBLE = {
    "value": None,
    "original_script": None,
    "confidence": None,
    "observation_state": "ILLEGIBLE",
    "alternatives": [],
    "notes": ["inspected at 4x"],
}


@pytest.mark.parametrize("evidence", [PROBABLE, UNCLEAR, ILLEGIBLE])
def test_evidence_oneof_accepts_only_contract_valid_branches(evidence: dict) -> None:
    validate_instance(_payload(evidence), SCHEMA)


@pytest.mark.parametrize(
    ("base", "updates"),
    [
        (ILLEGIBLE, {"confidence": "PROBABLE"}),
        (ILLEGIBLE, {"value": "invented"}),
        (ILLEGIBLE, {"original_script": "invented"}),
        (PROBABLE, {"alternatives": [{"value": "x", "original_script": "x"}]}),
        (UNCLEAR, {"alternatives": []}),
        (UNCLEAR, {"value": "missing uncertainty wrapper"}),
    ],
)
def test_evidence_oneof_makes_coupling_violations_unrepresentable(
    base: dict, updates: dict
) -> None:
    evidence = copy.deepcopy(base)
    evidence.update(updates)

    with pytest.raises(ContractValidationError):
        validate_instance(_payload(evidence), SCHEMA)


@pytest.mark.parametrize("placeholder", ["unknown", "UnKnOwN", "unclear", "N/A", "none"])
def test_present_scalar_value_forbids_typed_absence_placeholders(placeholder: str) -> None:
    evidence = copy.deepcopy(PROBABLE)
    evidence["value"] = placeholder

    with pytest.raises(ContractValidationError):
        validate_instance(_payload(evidence), SCHEMA)
