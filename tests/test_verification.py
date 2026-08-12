import json
import shutil
from pathlib import Path

from aktreader.verification import verify_application_checkout

ROOT = Path(__file__).resolve().parents[1]


def _copy_public_contracts(destination: Path) -> None:
    shutil.copy2(ROOT / "pyproject.toml", destination / "pyproject.toml")
    for name in ("schemas", "prompts", "skills", "gold"):
        shutil.copytree(ROOT / name, destination / name)


def test_repository_checkout_passes_every_public_verification() -> None:
    report = verify_application_checkout(ROOT)

    assert report["status"] == "PASS"
    assert report["project_name"] == "AKT Reader - Application"
    assert report["project_role"] == "application"
    assert report["distribution_name"] == "aktreader-app"
    assert report["repository_url"] == "https://github.com/jakegold1647/aktreader"
    assert report["passed_check_count"] == report["check_count"] == 5
    assert list(report["checks"]) == [
        "application_checkout",
        "prompt_bundle",
        "gold_corpus",
        "gold_manifest",
        "holdout",
    ]
    assert report["checks"]["application_checkout"] == {
        "status": "PASS",
        "summary": "aktreader-app identity; 25/25 contract assets",
        "identity_status": "MATCH",
        "observed_distribution_name": "aktreader-app",
        "available_contract_asset_count": 25,
        "contract_asset_count": 25,
        "missing_contract_assets": [],
    }
    gold = report["checks"]["gold_corpus"]
    assert gold["schema_validated_record_count"] == 36
    assert gold["coverage"]["total"] == 36
    assert gold["coverage"]["clerk_years"] == 21
    assert report["checks"]["gold_manifest"]["restricted_sources_used"] is False
    assert report["checks"]["holdout"]["training_overlap"] == 0


def test_prompt_drift_fails_only_the_prompt_check(tmp_path: Path) -> None:
    _copy_public_contracts(tmp_path)
    prompt = tmp_path / "prompts" / "reader_prompt.md"
    prompt.write_text(prompt.read_text(encoding="utf-8") + "\ndrift\n", encoding="utf-8")

    report = verify_application_checkout(tmp_path)

    assert report["status"] == "FAIL"
    assert report["passed_check_count"] == 4
    assert report["checks"]["application_checkout"]["status"] == "PASS"
    assert report["checks"]["prompt_bundle"] == {
        "status": "FAIL",
        "error": "reader_prompt.sha256 does not match reader_prompt.md",
    }
    assert report["checks"]["gold_corpus"]["status"] == "PASS"
    assert report["checks"]["gold_manifest"]["status"] == "PASS"
    assert report["checks"]["holdout"]["status"] == "PASS"


def test_evidence_lab_identity_cannot_pass_as_the_application(tmp_path: Path) -> None:
    _copy_public_contracts(tmp_path)
    project = tmp_path / "pyproject.toml"
    project.write_text(
        project.read_text(encoding="utf-8").replace(
            'name = "aktreader-app"', 'name = "aktreader-research"'
        ),
        encoding="utf-8",
    )

    report = verify_application_checkout(tmp_path)

    assert report["status"] == "FAIL"
    assert report["passed_check_count"] == 4
    assert report["checks"]["application_checkout"] == {
        "status": "FAIL",
        "error": (
            "expected an aktreader-app checkout with every contract asset; "
            "identity=WRONG_DISTRIBUTION, assets=25/25"
        ),
    }
    assert all(
        report["checks"][name]["status"] == "PASS"
        for name in ("prompt_bundle", "gold_corpus", "gold_manifest", "holdout")
    )


def test_invalid_gold_blocks_dependent_manifest_and_holdout_checks(tmp_path: Path) -> None:
    _copy_public_contracts(tmp_path)
    gold_path = sorted((tmp_path / "gold" / "acts").glob("*.json"))[0]
    payload = json.loads(gold_path.read_text(encoding="utf-8"))
    del payload["record_id"]
    gold_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = verify_application_checkout(tmp_path)

    assert report["status"] == "FAIL"
    assert report["checks"]["gold_corpus"]["status"] == "FAIL"
    assert "schema validation failed" in report["checks"]["gold_corpus"]["error"]
    assert report["checks"]["gold_manifest"] == {
        "status": "NOT_RUN",
        "reason": "gold_corpus did not pass",
    }
    assert report["checks"]["holdout"] == {
        "status": "NOT_RUN",
        "reason": "gold_corpus did not pass",
    }


def test_manifest_coverage_drift_fails_without_hiding_holdout_result(tmp_path: Path) -> None:
    _copy_public_contracts(tmp_path)
    manifest_path = tmp_path / "gold" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["coverage"]["total"] -= 1
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    report = verify_application_checkout(tmp_path)

    assert report["status"] == "FAIL"
    assert report["passed_check_count"] == 4
    assert report["checks"]["gold_manifest"] == {
        "status": "FAIL",
        "error": "gold manifest coverage does not match the validated corpus",
    }
    assert report["checks"]["holdout"]["status"] == "PASS"


def test_holdout_drift_fails_without_hiding_manifest_result(tmp_path: Path) -> None:
    _copy_public_contracts(tmp_path)
    holdout_path = tmp_path / "gold" / "clerk_year_holdout.json"
    holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
    holdout["record_ids"].pop()
    holdout_path.write_text(json.dumps(holdout, ensure_ascii=False), encoding="utf-8")

    report = verify_application_checkout(tmp_path)

    assert report["status"] == "FAIL"
    assert report["passed_check_count"] == 4
    assert report["checks"]["gold_manifest"]["status"] == "PASS"
    assert report["checks"]["holdout"]["status"] == "FAIL"
    assert "holdout record mismatch" in report["checks"]["holdout"]["error"]
