import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "resources" / "open_datasets.manifest.json"
FETCHER = ROOT / "tools" / "fetch_open_datasets.ps1"
README = ROOT / "README.md"
SHA256 = re.compile(r"^[a-f0-9]{64}$")
FORBIDDEN = ("yadvashem", "ushmm", "arolsen", "geneteka", "jri-poland", "jewishgen")


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_open_dataset_manifest_is_owner_only_and_license_reviewed() -> None:
    manifest = _manifest()

    assert manifest["schema_version"] == "1.0.0"
    assert manifest["owner_execution_only"] is True
    assert manifest["application_downloads_datasets"] is False
    assert manifest["destination_root"] == r"E:\DNA\BulkData\Training_Sources_Open"
    assert {item["id"] for item in manifest["datasets"]} == {
        "digital-peter",
        "cyrillic-handwriting-dataset-v5",
        "school-notebooks-ru",
    }
    assert all(item["status"] == "ELIGIBLE" for item in manifest["datasets"])
    assert all(item["recipe_role"] == "BASE_SCRIPT_ADAPTATION" for item in manifest["datasets"])
    assert {item["license"]["name"] for item in manifest["datasets"]} == {
        "MIT",
        "CC0-1.0",
    }


def test_every_eligible_artifact_has_an_immutable_verification_gate() -> None:
    for dataset in _manifest()["datasets"]:
        revision = dataset["source"]["revision"]
        assert revision
        assert dataset["artifacts"]
        for artifact in dataset["artifacts"]:
            parsed = urlparse(artifact["url"])
            assert parsed.scheme == "https"
            assert artifact["expected_size_bytes"] > 0
            assert not any(fragment in artifact["url"].lower() for fragment in FORBIDDEN)
            if artifact["verification"] == "SHA256_AND_SIZE":
                assert SHA256.fullmatch(artifact["expected_sha256"])
                assert revision in artifact["url"]
            else:
                assert artifact["verification"] == "SIZE_THEN_RECORD_SHA256"
                assert artifact["expected_sha256"] is None
                assert revision == "dataset-version-5"
                assert parse_qs(parsed.query)["datasetVersionNumber"] == ["5"]


def test_restricted_or_license_ambiguous_candidates_are_excluded() -> None:
    excluded = {item["id"]: item for item in _manifest()["excluded_candidates"]}

    assert set(excluded) == {"hkr-dataset", "ehri-multilingual-dataset", "ehri-ner"}
    assert all(item["status"] == "EXCLUDED" for item in excluded.values())
    assert "non-commercial" in excluded["hkr-dataset"]["reason"].lower()
    assert "yad vashem" in excluded["ehri-multilingual-dataset"]["reason"].lower()
    assert "eupl-1.2" in excluded["ehri-ner"]["reason"].lower()


def test_fetcher_verifies_partial_before_move_and_writes_receipts() -> None:
    script = FETCHER.read_text(encoding="utf-8")

    assert "AcceptLicenses" in script
    assert "[string]$ManifestPath," in script
    assert "$MyInvocation.MyCommand.Path" in script
    assert script.index("$MyInvocation.MyCommand.Path") > script.index(
        "$ErrorActionPreference = 'Stop'"
    )
    assert '"$destination.partial"' in script
    assert "Get-FileHash -LiteralPath" in script
    assert "expected_size_bytes" in script
    assert "expected_sha256" in script
    assert "Move-Item -LiteralPath $partial -Destination $destination" in script
    assert script.index("$observedBytes -ne $expectedBytes") < script.index(
        "Move-Item -LiteralPath $partial -Destination $destination"
    )
    assert "DOWNLOAD_RECEIPT.json" in script
    assert "LICENSE_RECEIPT.json" in script
    assert "'--proto'" in script
    assert "'=https'" in script
    assert "Expand-Archive" not in script
    assert "ExecutionPolicy Bypass" not in script


def test_readme_documents_roles_and_application_boundary() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "## Owner-only open training sources" in readme
    assert "Base-script adaptation" in readme
    assert "The application never calls" in readme
    assert "No text-side lexicon corpus currently clears every gate" in readme
