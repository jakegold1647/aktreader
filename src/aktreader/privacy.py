"""Fail-closed privacy decisions for civil-register acts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class PrivacyOutcome(str, Enum):
    """A preflight outcome suitable for mapping to batch checkpoint states."""

    ALLOW = "ALLOW"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PRIVACY_REFUSED = "PRIVACY_REFUSED"


@dataclass(frozen=True)
class PrivacyPolicy:
    """Year-level retention periods used by the local batch pipeline."""

    birth_years: int = 100
    marriage_years: int = 80
    death_years: int = 80

    def __post_init__(self) -> None:
        for name, value in (
            ("birth_years", self.birth_years),
            ("marriage_years", self.marriage_years),
            ("death_years", self.death_years),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    def threshold_for(self, act_type: str) -> int | None:
        """Return the retention period for a normalized schema act type."""
        return {
            "birth": self.birth_years,
            "marriage": self.marriage_years,
            "death": self.death_years,
        }.get(act_type)


DEFAULT_PRIVACY_POLICY = PrivacyPolicy()


@dataclass(frozen=True)
class PrivacyDecision:
    """The machine-readable privacy outcome and its audit explanation."""

    outcome: PrivacyOutcome
    reason: str
    act_type: str | None
    act_year: int | None
    as_of_year: int
    required_age_years: int | None

    @property
    def allowed(self) -> bool:
        """Return whether local inference may proceed."""
        return self.outcome is PrivacyOutcome.ALLOW


def evaluate_privacy(
    act_type: str | None,
    act_year: int | None,
    *,
    policy: PrivacyPolicy = DEFAULT_PRIVACY_POLICY,
    as_of_year: int | None = None,
) -> PrivacyDecision:
    """Evaluate an act using year-level, fail-closed privacy rules.

    Unknown act types need human review because their retention period is unknown.
    Missing, malformed, or future years are refused because the act's age cannot be
    established. Boundaries are inclusive: in 2035, a 1935 birth reaches 100 years.
    """

    check_year = date.today().year if as_of_year is None else as_of_year
    if isinstance(check_year, bool) or not isinstance(check_year, int) or check_year < 1:
        raise ValueError("as_of_year must be a positive integer")

    normalized_type = act_type.strip().lower() if isinstance(act_type, str) else None
    if not normalized_type:
        return PrivacyDecision(
            outcome=PrivacyOutcome.REVIEW_REQUIRED,
            reason="act type is unknown; privacy threshold cannot be selected",
            act_type=normalized_type,
            act_year=(
                act_year
                if isinstance(act_year, int) and not isinstance(act_year, bool)
                else None
            ),
            as_of_year=check_year,
            required_age_years=None,
        )

    threshold = policy.threshold_for(normalized_type)
    if threshold is None:
        return PrivacyDecision(
            outcome=PrivacyOutcome.REVIEW_REQUIRED,
            reason=f"unsupported act type {normalized_type!r}; human privacy review required",
            act_type=normalized_type,
            act_year=(
                act_year
                if isinstance(act_year, int) and not isinstance(act_year, bool)
                else None
            ),
            as_of_year=check_year,
            required_age_years=None,
        )

    if isinstance(act_year, bool) or not isinstance(act_year, int):
        return PrivacyDecision(
            outcome=PrivacyOutcome.PRIVACY_REFUSED,
            reason="act year is unknown; age cannot be established",
            act_type=normalized_type,
            act_year=None,
            as_of_year=check_year,
            required_age_years=threshold,
        )
    if act_year < 1 or act_year > check_year:
        return PrivacyDecision(
            outcome=PrivacyOutcome.PRIVACY_REFUSED,
            reason=f"act year {act_year} is invalid or in the future",
            act_type=normalized_type,
            act_year=act_year,
            as_of_year=check_year,
            required_age_years=threshold,
        )

    age = check_year - act_year
    if age < threshold:
        return PrivacyDecision(
            outcome=PrivacyOutcome.PRIVACY_REFUSED,
            reason=(
                f"{normalized_type} act is {age} years old; "
                f"policy requires at least {threshold}"
            ),
            act_type=normalized_type,
            act_year=act_year,
            as_of_year=check_year,
            required_age_years=threshold,
        )

    return PrivacyDecision(
        outcome=PrivacyOutcome.ALLOW,
        reason=f"{normalized_type} act is {age} years old; threshold is {threshold}",
        act_type=normalized_type,
        act_year=act_year,
        as_of_year=check_year,
        required_age_years=threshold,
    )
