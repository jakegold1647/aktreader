import pytest

from aktreader.privacy import PrivacyOutcome, PrivacyPolicy, evaluate_privacy


@pytest.mark.parametrize(
    ("act_type", "year", "expected"),
    [
        ("birth", 1926, PrivacyOutcome.ALLOW),
        ("birth", 1927, PrivacyOutcome.PRIVACY_REFUSED),
        ("marriage", 1946, PrivacyOutcome.ALLOW),
        ("marriage", 1947, PrivacyOutcome.PRIVACY_REFUSED),
        ("death", 1946, PrivacyOutcome.ALLOW),
        ("death", 1947, PrivacyOutcome.PRIVACY_REFUSED),
    ],
)
def test_default_privacy_boundaries(
    act_type: str, year: int, expected: PrivacyOutcome
) -> None:
    assert evaluate_privacy(act_type, year, as_of_year=2026).outcome is expected


def test_privacy_fails_closed_for_unknown_year_and_reviews_unknown_type() -> None:
    missing_year = evaluate_privacy("birth", None, as_of_year=2026)
    unknown_type = evaluate_privacy("annex", 1900, as_of_year=2026)

    assert missing_year.outcome is PrivacyOutcome.PRIVACY_REFUSED
    assert "cannot be established" in missing_year.reason
    assert unknown_type.outcome is PrivacyOutcome.REVIEW_REQUIRED
    assert "human privacy review" in unknown_type.reason


def test_privacy_policy_is_configurable_but_validated() -> None:
    policy = PrivacyPolicy(birth_years=110, marriage_years=90, death_years=90)

    assert evaluate_privacy("birth", 1916, policy=policy, as_of_year=2026).allowed
    assert not evaluate_privacy("birth", 1917, policy=policy, as_of_year=2026).allowed
    with pytest.raises(ValueError):
        PrivacyPolicy(birth_years=-1)
