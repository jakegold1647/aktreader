from pathlib import Path

import pytest

from aktreader.schema import ContractValidationError, validate_instance

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "adapter-identity-1.0.0.schema.json"


def _identity() -> dict[str, object]:
    pin = {"path": "artifact.bin", "sha256": "a" * 64}
    return {
        "$schema": "../schemas/adapter-identity-1.0.0.schema.json",
        "schema_version": "1.0.0",
        "adapter_id": "qwen35-serock-r01",
        "base_model": pin,
        "training_export": pin,
        "training_recipe": pin,
        "trainer_runtime": {
            "implementation": "trainer",
            "version": "1.0.0",
            "container_image_digest": f"sha256:{'b' * 64}",
        },
        "adapter": pin,
        "verification": {
            "base_model_sha256_match": True,
            "adapter_sha256_match": True,
            "load_test": "PASS",
            "held_out_probe": "PASS",
            "verified_at": "2026-07-28T22:00:00-04:00",
        },
    }


def test_adapter_identity_binds_every_input_and_output_hash() -> None:
    validate_instance(_identity(), SCHEMA)


def test_adapter_identity_fails_closed_on_unverified_base_model() -> None:
    identity = _identity()
    identity["verification"]["base_model_sha256_match"] = False

    with pytest.raises(ContractValidationError, match="True"):
        validate_instance(identity, SCHEMA)
