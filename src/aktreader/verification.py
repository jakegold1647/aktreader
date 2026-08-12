"""Offline integrity verification for a public Application checkout."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from aktreader import DISTRIBUTION_NAME, PROJECT_NAME, PROJECT_ROLE, REPOSITORY_URL
from aktreader.evaluation import validate_holdout_integrity
from aktreader.gold import validate_corpus
from aktreader.installation import inspect_application_checkout
from aktreader.prompt import PROMPT_VERSION, VERBATIM_SKILLS, verify_reader_prompt
from aktreader.schema import load_json, validate_declared_document

CHECK_NAMES = (
    "application_checkout",
    "prompt_bundle",
    "gold_corpus",
    "gold_manifest",
    "holdout",
)

_EXPECTED_EXCEPTIONS = (OSError, ValueError, TypeError, KeyError, AttributeError)


class CheckoutVerificationError(ValueError):
    """Raised when one public checkout invariant is false."""


def _passed(summary: str, **details: Any) -> dict[str, Any]:
    return {"status": "PASS", "summary": summary, **details}


def _failed(error: BaseException) -> dict[str, Any]:
    return {
        "status": "FAIL",
        "error": str(error) or type(error).__name__,
    }


def _not_run(reason: str) -> dict[str, Any]:
    return {"status": "NOT_RUN", "reason": reason}


def _attempt(check: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return check()
    except _EXPECTED_EXCEPTIONS as error:
        return _failed(error)


def _verify_checkout(root: Path) -> dict[str, Any]:
    checkout = inspect_application_checkout(root)
    available = checkout["available_contract_asset_count"]
    expected = checkout["contract_asset_count"]
    if not checkout["ready"]:
        raise CheckoutVerificationError(
            "expected an aktreader-app checkout with every contract asset; "
            f"identity={checkout['identity_status']}, assets={available}/{expected}"
        )
    return _passed(
        f"aktreader-app identity; {available}/{expected} contract assets",
        identity_status=checkout["identity_status"],
        observed_distribution_name=checkout["observed_distribution_name"],
        available_contract_asset_count=available,
        contract_asset_count=expected,
        missing_contract_assets=checkout["missing_contract_assets"],
    )


def _verify_prompt(root: Path) -> dict[str, Any]:
    digest = verify_reader_prompt(root)
    return _passed(
        f"frozen prompt {PROMPT_VERSION}; {len(VERBATIM_SKILLS)} source skills",
        prompt_version=PROMPT_VERSION,
        prompt_sha256=digest,
        verbatim_skill_count=len(VERBATIM_SKILLS),
    )


def _verify_gold(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    records: list[dict[str, Any]] = []

    def check() -> dict[str, Any]:
        paths = sorted((root / "gold" / "acts").glob("*.json"))
        if not paths:
            raise CheckoutVerificationError("gold/acts contains no JSON records")
        records.extend(
            validate_declared_document(path, workspace_root=root) for path in paths
        )
        coverage = validate_corpus(records)
        return _passed(
            (
                f"{coverage['total']} schema-valid records across "
                f"{coverage['clerk_years']} clerk-year IDs"
            ),
            schema_validated_record_count=len(paths),
            coverage=coverage,
        )

    result = _attempt(check)
    return result, records if result["status"] == "PASS" else None


def _verify_manifest(root: Path, coverage: dict[str, Any]) -> dict[str, Any]:
    manifest = load_json(root / "gold" / "manifest.json")
    if manifest.get("coverage") != coverage:
        raise CheckoutVerificationError(
            "gold manifest coverage does not match the validated corpus"
        )
    if manifest.get("restricted_sources_used") is not False:
        raise CheckoutVerificationError(
            "gold manifest must explicitly declare restricted_sources_used=false"
        )
    return _passed(
        "coverage and restricted-source declaration match the corpus",
        schema_version=manifest.get("schema_version"),
        restricted_sources_used=False,
        known_gap_count=len(manifest.get("known_gaps", [])),
        quarantine_count=len(manifest.get("quarantine", [])),
    )


def _verify_holdout(root: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    holdout = load_json(root / "gold" / "clerk_year_holdout.json")
    details = validate_holdout_integrity(records, holdout)
    details.pop("status", None)
    return _passed(
        (
            f"{details['records']} records / {details['clerk_years']} clerk-year IDs; "
            "no training overlap"
        ),
        **details,
    )


def verify_application_checkout(root: Path) -> dict[str, Any]:
    """Verify public, scan-free Application contracts and return one stable report."""
    resolved_root = root.resolve()
    checks: dict[str, dict[str, Any]] = {
        "application_checkout": _attempt(lambda: _verify_checkout(resolved_root)),
        "prompt_bundle": _attempt(lambda: _verify_prompt(resolved_root)),
    }

    gold_check, records = _verify_gold(resolved_root)
    checks["gold_corpus"] = gold_check
    if records is None:
        checks["gold_manifest"] = _not_run("gold_corpus did not pass")
        checks["holdout"] = _not_run("gold_corpus did not pass")
    else:
        coverage = gold_check["coverage"]
        checks["gold_manifest"] = _attempt(
            lambda: _verify_manifest(resolved_root, coverage)
        )
        checks["holdout"] = _attempt(lambda: _verify_holdout(resolved_root, records))

    passed = sum(check["status"] == "PASS" for check in checks.values())
    return {
        "verification_report_version": "1.0.0",
        "verification_scope": "public-source-checkout",
        "project_name": PROJECT_NAME,
        "project_role": PROJECT_ROLE,
        "distribution_name": DISTRIBUTION_NAME,
        "repository_url": REPOSITORY_URL,
        "root": str(resolved_root),
        "status": "PASS" if passed == len(CHECK_NAMES) else "FAIL",
        "passed_check_count": passed,
        "check_count": len(CHECK_NAMES),
        "checks": checks,
        "source_scans_required": False,
        "model_runtime_required": False,
        "network_required": False,
    }
