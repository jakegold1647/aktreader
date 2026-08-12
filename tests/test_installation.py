from pathlib import Path

from aktreader import DISTRIBUTION_NAME
from aktreader.cli import PROJECT_ROOT
from aktreader.installation import CONTRACT_ASSETS, inspect_application_checkout


def test_real_application_checkout_has_every_declared_contract() -> None:
    report = inspect_application_checkout(PROJECT_ROOT)

    assert report["identity_status"] == "MATCH"
    assert report["observed_distribution_name"] == DISTRIBUTION_NAME
    assert report["contract_asset_count"] == 25
    assert report["available_contract_asset_count"] == 25
    assert report["contract_assets_available"] is True
    assert report["missing_contract_assets"] == []
    assert report["contract_assets"]["gold_records"]["file_count"] == 36
    assert report["ready"] is True


def test_matching_distribution_without_contracts_is_not_ready(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "aktreader-app"\nversion = "0"\n',
        encoding="utf-8",
    )

    report = inspect_application_checkout(tmp_path)

    assert report["identity_status"] == "MATCH"
    assert report["contract_assets_available"] is False
    assert report["available_contract_asset_count"] == 0
    assert report["missing_contract_assets"] == [
        asset.relative_path for asset in CONTRACT_ASSETS
    ]
    assert report["ready"] is False


def test_evidence_lab_metadata_is_rejected_even_if_a_contract_exists(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "aktreader-research"\nversion = "0"\n',
        encoding="utf-8",
    )
    contract = tmp_path / CONTRACT_ASSETS[0].relative_path
    contract.parent.mkdir(parents=True)
    contract.write_text("{}\n", encoding="utf-8")

    report = inspect_application_checkout(tmp_path)

    assert report["identity_status"] == "WRONG_DISTRIBUTION"
    assert report["observed_distribution_name"] == "aktreader-research"
    assert report["available_contract_asset_count"] == 1
    assert report["ready"] is False


def test_malformed_project_metadata_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project\n", encoding="utf-8")

    report = inspect_application_checkout(tmp_path)

    assert report["identity_status"] == "MALFORMED"
    assert report["observed_distribution_name"] is None
    assert report["ready"] is False
