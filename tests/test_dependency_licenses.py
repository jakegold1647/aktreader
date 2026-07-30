from tools.check_dependency_licenses import check_dependency_licenses


def test_every_declared_dependency_has_an_approved_license_review() -> None:
    report = check_dependency_licenses()

    assert report["status"] == "PASS"
    assert report["declared_dependency_count"] == 5
    assert report["reviewed_package_count"] == 14
