import json
from pathlib import Path

import pytest

from aktreader import (
    COMMAND_NAME,
    DISTRIBUTION_NAME,
    PACKAGE_NAMESPACE,
    PROJECT_NAME,
    PROJECT_ROLE,
    REPOSITORY_URL,
    __version__,
)
from aktreader.cli import PROJECT_ROOT, build_parser, environment_report, main


def test_environment_report_is_honest_about_phase() -> None:
    report = environment_report()

    assert report["doctor_report_version"] == "1.0.0"
    assert report["aktreader_version"] == __version__
    assert report["project_name"] == PROJECT_NAME == "AKT Reader - Application"
    assert report["project_role"] == PROJECT_ROLE == "application"
    assert report["distribution_name"] == DISTRIBUTION_NAME == "aktreader-app"
    assert report["package_namespace"] == PACKAGE_NAMESPACE == "aktreader"
    assert report["command_name"] == COMMAND_NAME == "aktreader"
    assert report["repository_url"] == REPOSITORY_URL
    assert report["phase"] == "P2"
    assert report["cli_available"] is True
    assert report["checkout_identity_status"] == "MATCH"
    assert report["observed_distribution_name"] == "aktreader-app"
    assert report["contract_assets_available"] is True
    assert report["available_contract_asset_count"] == report["contract_asset_count"] == 25
    assert report["missing_contract_assets"] == []
    assert report["inspected_checkout_ready"] is True
    assert report["inspected_root_is_runtime_root"] is True
    assert report["pipeline_available"] is True
    assert report["source_checkout_required"] is True
    assert report["standalone_distribution_ready"] is False
    assert report["python_supported"] is True
    assert report["reader_backend"] == "local-open-weights-only"
    assert report["network_required"] is False


def test_doctor_json_is_machine_readable(capsys) -> None:
    exit_code = main(["doctor", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["phase"] == "P2"
    assert payload["project_role"] == "application"
    assert payload["distribution_name"] == "aktreader-app"
    assert payload["checkout_identity_status"] == "MATCH"
    assert payload["contract_assets_available"] is True
    assert payload["inspected_checkout_ready"] is True
    assert payload["pipeline_available"] is True
    assert payload["network_required"] is False


def test_doctor_human_output_names_the_application(capsys) -> None:
    exit_code = main(["doctor"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert output.startswith("AKT Reader - Application 0.0.1\n")
    assert "Repository role: application\n" in output
    assert "distribution aktreader-app | package aktreader | command aktreader" in output
    assert f"Repository: {REPOSITORY_URL}\n" in output
    assert "Checkout identity: MATCH (observed: aktreader-app)\n" in output
    assert "Contract assets: 25/25 available\n" in output
    assert "Pipeline available: yes\n" in output
    assert "Standalone wheel ready: no" in output


def test_doctor_fails_closed_for_an_alternate_incomplete_root(tmp_path, capsys) -> None:
    exit_code = main(["doctor", "--json", "--inspect-root", str(tmp_path)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["inspected_root"] == str(tmp_path.resolve())
    assert payload["inspected_root_is_runtime_root"] is False
    assert payload["checkout_identity_status"] == "MISSING"
    assert payload["available_contract_asset_count"] == 0
    assert payload["contract_assets_available"] is False
    assert payload["inspected_checkout_ready"] is False
    assert payload["pipeline_available"] is False


def test_version_names_the_application_distribution(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--version"])

    assert raised.value.code == 0
    assert capsys.readouterr().out == (
        "aktreader 0.0.1 (AKT Reader - Application; distribution: aktreader-app)\n"
    )


def test_no_command_prints_help(capsys) -> None:
    exit_code = main([])

    assert exit_code == 0
    assert "Local-only" in capsys.readouterr().out


def test_parser_exposes_no_api_key_or_network_backend_options() -> None:
    help_text = build_parser().format_help().lower()

    assert "--api" not in help_text
    assert "--url" not in help_text
    assert "hosted" not in help_text


def test_prompt_verify_and_canonical_label_validation_are_machine_readable(
    tmp_path: Path, capsys
) -> None:
    prompt_exit = main(["prompt-verify", "--root", str(PROJECT_ROOT)])
    prompt = json.loads(capsys.readouterr().out)
    source_path = PROJECT_ROOT / "labels" / "readerB" / "serock-1890-death-1.json"
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    payload["observations"] = {
        "principal.age": payload["observations"]["principal.age"]
    }
    label_path = tmp_path / "grounded-label.json"
    label_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    label_exit = main(["label-validate", str(label_path)])
    labels = json.loads(capsys.readouterr().out)

    assert prompt_exit == label_exit == 0
    assert prompt["status"] == "PASS"
    assert len(prompt["sha256"]) == 64
    assert labels["count"] == 1
    assert labels["labels"][0]["schema_kind"] == "canonical"
    assert labels["labels"][0]["quality_metrics"]["groundedness"]["violation_count"] == 0
    assert Path(labels["labels"][0]["path"]) == label_path
