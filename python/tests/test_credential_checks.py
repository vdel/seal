"""Wiring for the checks `seal check` grew for credentials: that each
runs alongside the others, and that both `seal check` and `seal
ci` give the declaration check the same environment selection
`--credentials_env` gives the rest of the run.

Whichever checks a case is not about are stubbed out, the way
test_gate_signal.py stubs `_run_checks` itself: what's under test is
composition and argument plumbing, not readiness probes, overlays, outcome
layout or CODEOWNERS -- so nothing here needs kubectl or Tilt. See
test_checks.py, test_pod_environment.py and test_merge_gate.py for those
checks' own coverage.
"""

import json
from pathlib import Path

import pytest

from seal import seal, providers


@pytest.fixture
def stub_other_checks(monkeypatch):
    """Every check `_check_credentials` doesn't touch, all passing."""
    monkeypatch.setattr(seal, "_check_readiness", lambda *a, **k: 0)
    monkeypatch.setattr(seal, "_check_pod_environment", lambda *a, **k: 0)
    monkeypatch.setattr(seal, "_check_outcome_layout", lambda *a, **k: 0)
    monkeypatch.setattr(seal, "_check_outcome_ownership", lambda *a, **k: 0)


def test_run_checks_ors_in_a_failing_credentials_check(tmp_path, stub_other_checks, monkeypatch):
    monkeypatch.setattr(seal, "_check_credentials", lambda *a, **k: 1)

    assert seal._run_checks(tmp_path, "k8s", "outcomes", "seal check") == 1


def test_run_checks_passes_when_credentials_does_too(tmp_path, stub_other_checks, monkeypatch):
    monkeypatch.setattr(seal, "_check_credentials", lambda *a, **k: 0)

    assert seal._run_checks(tmp_path, "k8s", "outcomes", "seal check") == 0


def test_run_checks_gives_credentials_env_to_the_credentials_check(
    tmp_path, stub_other_checks, monkeypatch
):
    seen = {}

    def _capture(seal_root, label, credentials_env):
        seen["credentials_env"] = credentials_env
        return 0

    monkeypatch.setattr(seal, "_check_credentials", _capture)

    seal._run_checks(tmp_path, "k8s", "outcomes", "seal check", "prod")

    assert seen["credentials_env"] == "prod"


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    (tmp_path / "Tiltfile").write_text("", encoding="utf-8")
    (tmp_path / "services").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _captured_run_checks(monkeypatch):
    captured = {}

    def _capture(seal_root, k8s_dir, outcomes_dir, label, credentials_env=None):
        captured["credentials_env"] = credentials_env
        return 0

    monkeypatch.setattr(seal, "_run_checks", _capture)
    return captured


def test_cmd_check_takes_the_flag(project, monkeypatch):
    captured = _captured_run_checks(monkeypatch)

    assert seal.cmd_check(["--credentials_env", "prod"]) == 0
    assert captured["credentials_env"] == "prod"


def test_cmd_check_with_no_flag_gives_none(project, monkeypatch):
    captured = _captured_run_checks(monkeypatch)

    assert seal.cmd_check([]) == 0
    assert captured["credentials_env"] is None


def test_cmd_ci_passes_its_own_credentials_env_to_run_checks(project, monkeypatch):
    """A regression test for the gap this closes: before, `cmd_ci` extracted
    `credentials_env` for its own `_fill_declared_objects()` call but had
    no way to hand it to `_run_checks()` at all."""
    captured = _captured_run_checks(monkeypatch)
    monkeypatch.setattr(seal, "_fill_declared_objects", lambda *a, **k: None)
    monkeypatch.setattr(seal.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(seal.os, "execvpe", lambda *a, **k: None)

    seal.cmd_ci(["--credentials_env", "prod"])

    assert captured["credentials_env"] == "prod"


# -- _check_credentials() itself -------------------------------------------


def test_check_credentials_passes_silently_with_nothing_declared(tmp_path, capsys):
    (tmp_path / "services").mkdir()

    assert seal._check_credentials(tmp_path, "seal check", None) == 0
    assert "matches what" in capsys.readouterr().out


def test_check_credentials_reports_each_problem(tmp_path, capsys):
    (tmp_path / providers.CONFIG_FILENAME).write_text(
        json.dumps({"provider": []}), encoding="utf-8"
    )
    service_dir = tmp_path / "services" / "api"
    service_dir.mkdir(parents=True)
    (service_dir / ".env").write_text("SECRET=other://item\n", encoding="utf-8")

    code = seal._check_credentials(tmp_path, "seal check", None)

    err = capsys.readouterr().err
    assert code == 1
    assert "1 problem" in err
    assert "api/.env: SECRET" in err


def test_check_credentials_reports_a_malformed_config_without_a_traceback(tmp_path, capsys):
    (tmp_path / providers.CONFIG_FILENAME).write_text("{not json", encoding="utf-8")
    (tmp_path / "services").mkdir()

    code = seal._check_credentials(tmp_path, "seal check", None)

    assert code == 1
    assert "cannot be read as JSON" in capsys.readouterr().err


# -- the pod-environment check's own wiring --------------------------------


def test_run_checks_ors_in_a_failing_pod_environment_check(tmp_path, monkeypatch):
    """The fifth check composes like the other four -- see
    _check_pod_environment() and pod_environment.py."""
    monkeypatch.setattr(seal, "_check_readiness", lambda *a, **k: 0)
    monkeypatch.setattr(seal, "_check_credentials", lambda *a, **k: 0)
    monkeypatch.setattr(seal, "_check_outcome_layout", lambda *a, **k: 0)
    monkeypatch.setattr(seal, "_check_outcome_ownership", lambda *a, **k: 0)
    monkeypatch.setattr(seal, "_check_pod_environment", lambda *a, **k: 1)

    assert seal._run_checks(tmp_path, "k8s", "outcomes", "seal check") == 1


def test_check_pod_environment_passes_silently_with_no_env_files(tmp_path, capsys):
    (tmp_path / "services").mkdir()

    assert seal._check_pod_environment(tmp_path, "k8s", "seal check") == 0
    assert "has a source in every overlay" in capsys.readouterr().out
