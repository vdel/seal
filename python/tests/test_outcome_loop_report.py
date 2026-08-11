"""What `seal outcomes loop` says about a loop, and what it exits with.

The record every run appends is written here by hand rather than by running
a suite: what is under test is the report, and a fixture that had to thrash
a real application to produce a cycle would be a test of something else.
`test_outcome_loop.py` covers the reading underneath it, and
`test_outcome_suite.py` the note a failing run prints.
"""

import json
from pathlib import Path

import pytest

from seal.outcomes import OUTCOMES_DIR_ENV_VAR
from seal.runners import (
    CONFIG_FILENAME,
    LOOP_FIELD,
    MAX_ITERATIONS_FIELD,
    MAX_MINUTES_FIELD,
    PLAYWRIGHT,
    RUNNER_FIELD,
)
from seal.seal import main
from test_outcome_loop import run


@pytest.fixture
def project(tmp_path, monkeypatch) -> Path:
    """An seal project with one group declared, and no promises: what a loop
    is read from is the record, not the tree."""
    (tmp_path / "Tiltfile").write_text("# root Tiltfile\n", encoding="utf-8")
    (tmp_path / "services").mkdir()
    config = tmp_path / "outcomes" / CONFIG_FILENAME
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps({RUNNER_FIELD: [{"name": "ui", "runner_type": PLAYWRIGHT}]}),
        encoding="utf-8",
    )
    monkeypatch.delenv(OUTCOMES_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def declare_loop(project: Path, **limits) -> None:
    config = project / "outcomes" / CONFIG_FILENAME
    document = json.loads(config.read_text(encoding="utf-8"))
    document[LOOP_FIELD] = limits
    config.write_text(json.dumps(document), encoding="utf-8")


def test_a_project_that_has_never_run_its_suite_is_in_no_loop(project, capsys):
    assert main(["outcomes", "loop"]) == 0

    assert "no loop in progress" in capsys.readouterr().out


def test_a_green_suite_is_in_no_loop(project, capsys):
    run(project, {"ui/a/one": "PASS"})

    assert main(["outcomes", "loop"]) == 0

    assert "no loop in progress" in capsys.readouterr().out


def test_a_loop_that_is_getting_somewhere_has_no_reason_to_stop(project, capsys):
    run(project, {"ui/a/one": "FAIL", "ui/a/two": "FAIL"}, minute=0)
    run(project, {"ui/a/one": "PASS", "ui/a/two": "FAIL"}, minute=10)

    assert main(["outcomes", "loop"]) == 0

    printed = capsys.readouterr().out
    assert "2 round(s)" in printed
    assert "No reason to stop yet" in printed


def test_the_sequence_is_reported_oldest_round_first(project, capsys):
    run(project, {"ui/a/one": "FAIL", "ui/a/two": "PASS"}, minute=0)
    run(project, {"ui/a/one": "PASS", "ui/a/two": "FAIL"}, minute=10)

    main(["outcomes", "loop"])

    printed = capsys.readouterr().out
    assert printed.index("broke  ui/a/one") < printed.index("broke  ui/a/two")
    assert "fixed  ui/a/one" in printed


def test_what_is_still_red_is_named(project, capsys):
    run(project, {"ui/a/one": "FAIL", "ui/a/two": "PASS"}, minute=0)

    main(["outcomes", "loop"])

    assert "Still red after the last round:\n  ui/a/one" in capsys.readouterr().out


def test_a_promise_fixed_and_broken_again_is_a_reason_to_stop(project, capsys):
    run(project, {"ui/a/one": "FAIL", "ui/a/two": "PASS"}, minute=0)
    run(project, {"ui/a/one": "PASS", "ui/a/two": "FAIL"}, minute=10)
    run(project, {"ui/a/one": "FAIL", "ui/a/two": "PASS"}, minute=20)

    assert main(["outcomes", "loop"]) == 1

    printed = capsys.readouterr().out
    assert "Going in circles" in printed
    assert "ui/a/one" in printed


def test_a_loop_at_its_round_backstop_is_a_reason_to_stop(project, capsys):
    declare_loop(project, **{MAX_ITERATIONS_FIELD: 2})
    run(project, {"ui/a/one": "FAIL"}, minute=0)
    run(project, {"ui/a/one": "FAIL"}, minute=1)

    assert main(["outcomes", "loop"]) == 1

    printed = capsys.readouterr().out
    assert MAX_ITERATIONS_FIELD in printed
    assert CONFIG_FILENAME in printed


def test_a_loop_at_its_clock_backstop_is_a_reason_to_stop(project, capsys):
    declare_loop(project, **{MAX_MINUTES_FIELD: 30})
    run(project, {"ui/a/one": "FAIL"}, minute=0)
    run(project, {"ui/a/one": "FAIL"}, minute=45)

    assert main(["outcomes", "loop"]) == 1

    assert MAX_MINUTES_FIELD in capsys.readouterr().out


def test_a_loop_with_a_reason_to_stop_says_who_settles_it(project, capsys):
    """Not the session that has been looping, which is the one that has
    already decided which promise is at fault."""
    declare_loop(project, **{MAX_ITERATIONS_FIELD: 1})
    run(project, {"ui/a/one": "FAIL"}, minute=0)

    main(["outcomes", "loop"])

    printed = capsys.readouterr().out
    assert "has not been in this loop" in printed
    assert "code owner" in printed


def test_a_mis_declared_backstop_still_reports_the_loop(project, capsys):
    """`seal check` is where a project is told its config is wrong. A loop
    that reported nothing because of a typo in a number is a loop nobody
    hears about."""
    declare_loop(project, **{MAX_ITERATIONS_FIELD: 0})
    run(project, {"ui/a/one": "FAIL"}, minute=0)

    assert main(["outcomes", "loop"]) == 0

    assert "1 round(s)" in capsys.readouterr().out


def test_a_flag_this_command_does_not_take_says_so(project, capsys):
    assert main(["outcomes", "loop", "--max-iterations", "20"]) == 1

    assert "Usage: seal" in capsys.readouterr().err


def test_the_command_is_named_in_the_usage(project, capsys):
    main(["bogus"])

    assert "seal outcomes loop" in capsys.readouterr().err
