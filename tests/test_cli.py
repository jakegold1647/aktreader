import json
from pathlib import Path

from aktreader import __version__
from aktreader.cli import PROJECT_ROOT, build_parser, environment_report, main


def test_environment_report_is_honest_about_phase() -> None:
    report = environment_report()

    assert report["aktreader_version"] == __version__
    assert report["phase"] == "P2"
    assert report["pipeline_available"] is True
    assert report["python_supported"] is True
    assert report["reader_backend"] == "local-open-weights-only"
    assert report["network_required"] is False


def test_doctor_json_is_machine_readable(capsys) -> None:
    exit_code = main(["doctor", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["phase"] == "P2"
    assert payload["pipeline_available"] is True
    assert payload["network_required"] is False


def test_no_command_prints_help(capsys) -> None:
    exit_code = main([])

    assert exit_code == 0
    assert "Local-only" in capsys.readouterr().out


def test_parser_exposes_no_api_key_or_network_backend_options() -> None:
    help_text = build_parser().format_help().lower()

    assert "--api" not in help_text
    assert "--url" not in help_text
    assert "hosted" not in help_text


def test_prompt_verify_and_canonical_label_validation_are_machine_readable(capsys) -> None:
    prompt_exit = main(["prompt-verify", "--root", str(PROJECT_ROOT)])
    prompt = json.loads(capsys.readouterr().out)
    label_path = PROJECT_ROOT / "labels" / "readerB" / "serock-1890-death-1.json"
    label_exit = main(["label-validate", str(label_path)])
    labels = json.loads(capsys.readouterr().out)

    assert prompt_exit == label_exit == 0
    assert prompt["status"] == "PASS"
    assert len(prompt["sha256"]) == 64
    assert labels["count"] == 1
    assert labels["labels"][0]["schema_kind"] == "canonical"
    assert Path(labels["labels"][0]["path"]) == label_path
