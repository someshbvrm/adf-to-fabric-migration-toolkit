import json

from adf2fabric.cli import main


def test_run_writes_reports_and_drafts(sample_path, tmp_path, capsys):
    assert main(["run", str(sample_path), "-o", str(tmp_path)]) == 0
    assert (tmp_path / "index.html").read_text().startswith("<!doctype html>")
    data = json.loads((tmp_path / "assessment.json").read_text())
    assert data["summary"]["blockers"] == 3
    assert len(list((tmp_path / "fabric_pipelines").glob("*.json"))) == 7
    assert "7 pipelines" in capsys.readouterr().out


def test_fail_on_blockers_exit_code(sample_path, tmp_path):
    code = main(["assess", str(sample_path), "-o", str(tmp_path), "--format", "json", "--fail-on-blockers"])
    assert code == 2


def test_bad_source_returns_error(tmp_path, capsys):
    assert main(["assess", str(tmp_path / "nope.json")]) == 1
    assert "error" in capsys.readouterr().err
