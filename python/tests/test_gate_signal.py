"""Whether a run's result is a verdict, and how the Tilt session finds out.

`seal ci` is a gate; `seal up` is a session somebody is about to work in.
That difference is what decides whether the outcome suite runs on its own
(see tilt/seal/outcomes.Tiltfile), and it reaches Starlark through the
environment the CLI hands Tilt -- which is what these assert on.
"""

import os
from pathlib import Path

import pytest

from seal import seal


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    """The smallest thing find_seal_root() accepts, with the expensive parts
    of a real run stubbed: what is under test is the environment handed to
    Tilt, not the checks and credential resolution that precede it."""
    (tmp_path / "Tiltfile").write_text("", encoding="utf-8")
    (tmp_path / "services").mkdir()

    monkeypatch.setattr(seal, "_run_checks", lambda *args, **kwargs: 0)
    monkeypatch.setattr(seal, "_fill_declared_objects", lambda *args, **kwargs: None)
    monkeypatch.setattr(seal.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(seal.SEAL_CI_ENV_VAR, raising=False)
    return tmp_path


def _env_handed_to_tilt(monkeypatch, command) -> dict:
    """`seal up`/`seal ci` hand off with execvpe and never return, so the
    environment they pass is the last thing either says."""
    captured = {}

    def _capture(binary, argv, env):
        captured.update(env)

    monkeypatch.setattr(seal.os, "execvpe", _capture)
    command([])
    return captured


def test_seal_ci_tells_the_session_its_result_is_a_verdict(project, monkeypatch):
    assert _env_handed_to_tilt(monkeypatch, seal.cmd_ci)[seal.SEAL_CI_ENV_VAR] == "1"


def test_seal_up_does_not(project, monkeypatch):
    """A session somebody is about to work in is not a gate. Spending a whole
    outcome suite on every start of one is how a local loop stops being
    used."""
    assert seal.SEAL_CI_ENV_VAR not in _env_handed_to_tilt(monkeypatch, seal.cmd_up)


def test_both_still_announce_how_to_run_the_cli_again(project, monkeypatch):
    """The gate signal rides alongside that one rather than replacing it."""
    for command in (seal.cmd_up, seal.cmd_ci):
        monkeypatch.delenv(seal.SEAL_CLI_ENV_VAR, raising=False)
        assert seal.SEAL_CLI_ENV_VAR in _env_handed_to_tilt(monkeypatch, command)
