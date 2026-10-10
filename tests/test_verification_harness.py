"""The fixture gate must not silently accept unexecuted checks."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / ".autoloop/scripts/verify.py"
spec = importlib.util.spec_from_file_location("fixture_verification", _SCRIPT)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


@pytest.mark.parametrize(
    "report,expected",
    [
        ('<testsuites><testsuite tests="2" skipped="0" errors="0" failures="0"/></testsuites>', 0),
        ('<testsuites><testsuite tests="2" skipped="1" errors="0" failures="0"/></testsuites>', 1),
        (None, 1),
        ("not XML", 1),
        ('<testsuites><testsuite tests="0" skipped="0"/></testsuites>', 1),
        ('<testsuites><testsuite tests="many" skipped="0"/></testsuites>', 1),
        ('<testsuites><testsuite tests="2" errors="1"/></testsuites>', 1),
    ],
)
def test_fixture_gate_requires_complete_pytest_report(tmp_path, monkeypatch, report, expected):
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    (tmp_path / ".autoloop/artifacts").mkdir(parents=True)
    monkeypatch.setattr(harness, "build_things_db", lambda path: Path(path).write_text("synthetic DB"))
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "fixture-check"])
    commands = []
    fixture_paths = []

    def run(cmd, *, cwd, env, stdout, stderr):
        commands.append(cmd)
        assert cwd == tmp_path
        assert env["THINGS_AUTH_TOKEN"] == ""
        fixture_paths.extend(Path(env[key]) for key in ("THINGS_DB", "SUUR_THINGS_CONFIG"))
        assert all(path.parent == Path(env["THINGS_DB"]).parent for path in fixture_paths)
        assert not Path(env["SUUR_THINGS_TOKEN_FILE"]).exists()
        assert Path(env["THINGS_DB"]).read_text() == "synthetic DB"
        if "pytest" in cmd and report is not None:
            (Path(env["THINGS_DB"]).parent / "pytest.xml").write_text(report)
        stdout.write("fixture subprocess completed\n")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(harness.subprocess, "run", run)
    assert harness.main() == expected
    assert len(commands) == (4 if expected == 0 else 3)
    assert (tmp_path / ".autoloop/artifacts/fixture-check.txt").exists()
    assert all(not path.exists() for path in fixture_paths)


def test_fixture_gate_stops_on_failed_check(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    (tmp_path / ".autoloop/artifacts").mkdir(parents=True)
    monkeypatch.setattr(harness, "build_things_db", lambda path: Path(path).write_text("synthetic DB"))
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "fixture-failure"])
    commands = []

    def run(cmd, **kwargs):
        commands.append(cmd)
        kwargs["stdout"].write("fixture lint failed\n")
        return subprocess.CompletedProcess(cmd, 7)

    monkeypatch.setattr(harness.subprocess, "run", run)
    assert harness.main() == 7
    assert len(commands) == 1
    assert "Exit: 7" in (tmp_path / ".autoloop/artifacts/fixture-failure.txt").read_text()
