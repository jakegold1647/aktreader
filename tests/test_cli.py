import json

from aktreader import __version__
from aktreader.cli import environment_report, main


def test_environment_report_is_honest_about_phase() -> None:
    report = environment_report()

    assert report["aktreader_version"] == __version__
    assert report["phase"] == "P1"
    assert report["pipeline_available"] is False
    assert report["python_supported"] is True


def test_doctor_json_is_machine_readable(capsys) -> None:
    exit_code = main(["doctor", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["phase"] == "P1"
    assert payload["pipeline_available"] is False


def test_no_command_prints_help(capsys) -> None:
    exit_code = main([])

    assert exit_code == 0
    assert "P1 gold corpus" in capsys.readouterr().out
