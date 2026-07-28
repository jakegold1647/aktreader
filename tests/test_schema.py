import json
from pathlib import Path

import pytest

from aktreader.schema import ContractValidationError, validate_declared_document, validate_instance

ROOT = Path(__file__).resolve().parents[1]
LABEL_SCHEMA = ROOT / "schemas" / "reader-label-1.0.0.schema.json"


def test_blind_reader_b_labels_validate_against_local_schema() -> None:
    for path in sorted((ROOT / "labels" / "readerB").glob("*.json")):
        document = validate_declared_document(path, workspace_root=ROOT)
        assert document["reader"]["other_reader_output_seen"] is False


def test_single_reader_confident_grade_is_rejected() -> None:
    source = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"
    document = json.loads(source.read_text(encoding="utf-8"))
    document["observations"]["act_no"]["confidence"] = "CONFIDENT"

    with pytest.raises(ContractValidationError, match="CONFIDENT"):
        validate_instance(document, LABEL_SCHEMA)


def test_reader_label_schema_accepts_v1_1_prompt_without_changing_schema_version() -> None:
    source = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"
    document = json.loads(source.read_text(encoding="utf-8"))
    document["prompt"]["version"] = "1.1.0"

    validate_instance(document, LABEL_SCHEMA)
    assert document["schema_version"] == "1.0.0"

    document["prompt"]["version"] = "1.2.0"
    with pytest.raises(ContractValidationError, match="1.2.0"):
        validate_instance(document, LABEL_SCHEMA)


def test_remote_schema_resolution_is_forbidden(tmp_path: Path) -> None:
    path = tmp_path / "remote.json"
    path.write_text('{"$schema":"https://example.test/schema.json"}', encoding="utf-8")

    with pytest.raises(ContractValidationError, match="remote"):
        validate_declared_document(path, workspace_root=tmp_path)
