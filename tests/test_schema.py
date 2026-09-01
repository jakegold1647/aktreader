import json
import socket
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


def test_reader_label_schema_accepts_released_prompts_without_changing_schema_version() -> None:
    source = ROOT / "labels" / "readerB" / "serock-1890-death-1.json"
    document = json.loads(source.read_text(encoding="utf-8"))
    document["prompt"]["version"] = "1.1.0"

    validate_instance(document, LABEL_SCHEMA)
    assert document["schema_version"] == "1.0.0"

    document["prompt"]["version"] = "1.2.0"
    validate_instance(document, LABEL_SCHEMA)
    assert document["schema_version"] == "1.0.0"

    document["prompt"]["version"] = "1.3.0"
    validate_instance(document, LABEL_SCHEMA)
    assert document["schema_version"] == "1.0.0"

    document["prompt"]["version"] = "1.4.0"
    with pytest.raises(ContractValidationError, match="1.4.0"):
        validate_instance(document, LABEL_SCHEMA)


def test_remote_schema_resolution_is_forbidden(tmp_path: Path) -> None:
    path = tmp_path / "remote.json"
    path.write_text('{"$schema":"https://example.test/schema.json"}', encoding="utf-8")

    with pytest.raises(ContractValidationError, match="remote"):
        validate_declared_document(path, workspace_root=tmp_path)


def test_local_schema_references_resolve_inside_the_schema_root(tmp_path: Path) -> None:
    definitions = tmp_path / "definitions"
    definitions.mkdir()
    (definitions / "value.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "string",
            }
        ),
        encoding="utf-8",
    )
    schema = tmp_path / "schema.json"
    schema.write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"value": {"$ref": "definitions/value.json"}},
                "required": ["value"],
            }
        ),
        encoding="utf-8",
    )

    validate_instance({"value": "local"}, schema, schema_root=tmp_path)
    with pytest.raises(ContractValidationError, match="string"):
        validate_instance({"value": 12}, schema, schema_root=tmp_path)


def test_schema_reference_cannot_escape_its_local_root(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "outside.json").write_text('{"type":"object"}', encoding="utf-8")
    schema = workspace / "schema.json"
    schema.write_text('{"$ref":"../outside.json"}', encoding="utf-8")

    with pytest.raises(ContractValidationError, match="local schema root"):
        validate_instance({}, schema, schema_root=workspace)


@pytest.mark.parametrize(
    "reference",
    [
        "http://127.0.0.1:9/remote.json",
        "https://example.invalid/remote.json",
        "file://server/share/remote.json",
    ],
)
def test_external_schema_references_fail_without_network_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reference: str,
) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"$ref": reference}), encoding="utf-8")

    def fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("schema validation attempted network access")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    with pytest.raises(ContractValidationError, match="local schema root"):
        validate_instance({}, schema, schema_root=tmp_path)
