"""What a regression loop looks like from the record its runs leave behind.

Every record here is one the test writes itself, entry by entry, rather than
one produced by running the suite: what is under test is the reading, and a
fixture that had to run a suite to produce a four-round loop would be a test
of the runner instead. `python/tests/test_outcome_suite.py` covers the
writing.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from seal.outcome_history import (
    AT_KEY,
    CONFIRMATION_KEY,
    HISTORY_FILE,
    OUTCOME_KEY,
    QUARANTINE_KEY,
    RUN_KEY,
    SCOPE_KEY,
    SCOPE_SELECTION,
    SCOPE_TREE,
    STATE_KEY,
    recorded_runs,
    recorded_verdicts,
)
from seal.outcome_loop import ITERATION_CAP, TIME_CAP, loop, reached
from seal.outcome_suite import FAILED, NO_VERDICT, PASSED, UNTRANSLATED
from seal.runners import Limits

START = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def run(
    project: Path,
    states: dict[str, str],
    *,
    scope: str = SCOPE_TREE,
    minute: int = 0,
    quarantined: tuple[str, ...] = (),
):
    """One run of the suite, appended the way `seal outcomes run` appends it."""
    history = project / HISTORY_FILE
    history.parent.mkdir(parents=True, exist_ok=True)
    identity = f"run-{len(history.read_text(encoding='utf-8').splitlines()) if history.is_file() else 0}"
    with history.open("a", encoding="utf-8") as record:
        for slug, state in states.items():
            record.write(
                json.dumps(
                    {
                        OUTCOME_KEY: slug,
                        STATE_KEY: state,
                        CONFIRMATION_KEY: None,
                        AT_KEY: (START + timedelta(minutes=minute)).isoformat(),
                        RUN_KEY: identity,
                        SCOPE_KEY: scope,
                        QUARANTINE_KEY: slug in quarantined,
                    }
                )
                + "\n"
            )


def loop_of(project: Path):
    return loop(recorded_runs(project))


def test_a_run_of_the_suite_is_read_back_whole(tmp_path):
    run(tmp_path, {"ui/a/one": PASSED, "ui/a/two": FAILED})

    assert [read.states for read in recorded_runs(tmp_path)] == [
        {"ui/a/one": PASSED, "ui/a/two": FAILED}
    ]


def test_a_subset_is_not_an_iteration_of_anything(tmp_path):
    """It says nothing about the promises it left out, so read as a round it
    would report every one of them as having been fixed."""
    run(tmp_path, {"ui/a/one": FAILED, "ui/a/two": FAILED})
    run(tmp_path, {"ui/a/one": PASSED}, scope=SCOPE_SELECTION, minute=1)

    assert loop_of(tmp_path).iterations == 1
    assert loop_of(tmp_path).red == ("ui/a/one", "ui/a/two")


def test_a_record_written_before_runs_said_what_they_covered_is_not_read_as_one(tmp_path):
    """An entry carrying no run and no scope is a run whose coverage nothing
    can establish. It still counts towards how often that promise has changed
    its mind, which asks only about the promise."""
    history = tmp_path / HISTORY_FILE
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(
        json.dumps({OUTCOME_KEY: "ui/a/one", STATE_KEY: FAILED, AT_KEY: START.isoformat()})
        + "\n",
        encoding="utf-8",
    )

    assert recorded_runs(tmp_path) == []
    assert not loop_of(tmp_path).in_progress
    assert recorded_verdicts(tmp_path) == {"ui/a/one": [FAILED]}


def test_a_green_suite_is_not_a_loop(tmp_path):
    run(tmp_path, {"ui/a/one": PASSED, "ui/a/two": PASSED})

    assert not loop_of(tmp_path).in_progress
    assert loop_of(tmp_path).iterations == 0


def test_a_promise_with_no_test_yet_does_not_hold_a_loop_open(tmp_path):
    """There is nothing for the application to satisfy, which is why the suite
    doesn't fail on one either."""
    run(tmp_path, {"ui/a/one": PASSED, "ui/a/two": UNTRANSLATED})

    assert not loop_of(tmp_path).in_progress


def test_a_loop_starts_after_the_last_green_run(tmp_path):
    run(tmp_path, {"ui/a/one": FAILED}, minute=0)
    run(tmp_path, {"ui/a/one": PASSED}, minute=1)
    run(tmp_path, {"ui/a/one": FAILED}, minute=2)
    run(tmp_path, {"ui/a/one": FAILED}, minute=3)

    assert loop_of(tmp_path).iterations == 2


def test_a_record_that_has_never_been_green_is_one_loop_from_the_start(tmp_path):
    run(tmp_path, {"ui/a/one": FAILED}, minute=0)
    run(tmp_path, {"ui/a/one": FAILED}, minute=1)

    assert loop_of(tmp_path).iterations == 2


def test_a_run_that_ends_green_ends_the_loop(tmp_path):
    run(tmp_path, {"ui/a/one": FAILED}, minute=0)
    run(tmp_path, {"ui/a/one": PASSED}, minute=1)

    assert not loop_of(tmp_path).in_progress


def test_the_sequence_says_what_broke_and_what_was_fixed(tmp_path):
    run(tmp_path, {"ui/a/one": FAILED, "ui/a/two": PASSED}, minute=0)
    run(tmp_path, {"ui/a/one": PASSED, "ui/a/two": FAILED}, minute=5)

    steps = loop_of(tmp_path).steps
    assert [step.broke for step in steps] == [("ui/a/one",), ("ui/a/two",)]
    assert [step.fixed for step in steps] == [(), ("ui/a/one",)]
    assert [step.red for step in steps] == [("ui/a/one",), ("ui/a/two",)]


def test_a_test_that_left_no_verdict_is_red_like_a_failure(tmp_path):
    """Nothing knows it ran, which is exactly what a green suite must never be
    able to claim on its behalf."""
    run(tmp_path, {"ui/a/one": NO_VERDICT}, minute=0)

    assert loop_of(tmp_path).red == ("ui/a/one",)


def test_a_promise_fixed_and_broken_again_is_a_cycle(tmp_path):
    run(tmp_path, {"ui/a/one": FAILED, "ui/a/two": PASSED}, minute=0)
    run(tmp_path, {"ui/a/one": PASSED, "ui/a/two": FAILED}, minute=5)
    run(tmp_path, {"ui/a/one": FAILED, "ui/a/two": PASSED}, minute=10)

    assert loop_of(tmp_path).cycles == ("ui/a/one",)


def test_a_promise_red_every_round_since_it_broke_is_not_a_cycle(tmp_path):
    """That is a regression nobody has fixed yet, which the suite already says
    every time it runs."""
    run(tmp_path, {"ui/a/one": FAILED}, minute=0)
    run(tmp_path, {"ui/a/one": FAILED}, minute=5)
    run(tmp_path, {"ui/a/one": FAILED}, minute=10)

    assert loop_of(tmp_path).cycles == ()


def test_a_promise_re_broken_in_a_later_loop_is_not_this_loop_going_in_circles(tmp_path):
    """Either side of a green run is two loops, and reading that as a cycle
    would make any long enough record look like one."""
    run(tmp_path, {"ui/a/one": FAILED}, minute=0)
    run(tmp_path, {"ui/a/one": PASSED}, minute=5)
    run(tmp_path, {"ui/a/one": FAILED}, minute=10)

    assert loop_of(tmp_path).cycles == ()
    assert loop_of(tmp_path).iterations == 1


def test_every_promise_in_a_cycle_is_named(tmp_path):
    run(tmp_path, {"ui/a/one": FAILED, "ui/a/two": PASSED}, minute=0)
    run(tmp_path, {"ui/a/one": PASSED, "ui/a/two": FAILED}, minute=5)
    run(tmp_path, {"ui/a/one": FAILED, "ui/a/two": PASSED}, minute=10)
    run(tmp_path, {"ui/a/one": PASSED, "ui/a/two": FAILED}, minute=15)

    assert loop_of(tmp_path).cycles == ("ui/a/one", "ui/a/two")


def test_a_loop_says_how_many_rounds_it_has_run_and_over_how_long(tmp_path):
    run(tmp_path, {"ui/a/one": FAILED}, minute=0)
    run(tmp_path, {"ui/a/one": FAILED}, minute=12)
    run(tmp_path, {"ui/a/one": FAILED}, minute=30)

    assert loop_of(tmp_path).iterations == 3
    assert loop_of(tmp_path).elapsed == timedelta(minutes=30)


def test_the_time_counted_is_the_looping_rather_than_the_calendar(tmp_path):
    """A loop nobody has run since yesterday has not been looping since
    yesterday."""
    run(tmp_path, {"ui/a/one": FAILED}, minute=0)
    run(tmp_path, {"ui/a/one": FAILED}, minute=2)

    assert loop_of(tmp_path).elapsed == timedelta(minutes=2)


def test_a_truncated_record_still_reads_as_a_loop(tmp_path):
    run(tmp_path, {"ui/a/one": FAILED}, minute=0)
    history = tmp_path / HISTORY_FILE
    history.write_text(history.read_text(encoding="utf-8") + '{"outcome": "ui/', encoding="utf-8")

    assert loop_of(tmp_path).iterations == 1


def test_a_run_with_no_timestamp_to_read_is_not_a_round(tmp_path):
    """Elapsed time is half of what a cap is read off, and a round nothing can
    date is one no loop can be measured from."""
    history = tmp_path / HISTORY_FILE
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(
        json.dumps(
            {
                OUTCOME_KEY: "ui/a/one",
                STATE_KEY: FAILED,
                AT_KEY: "the other day",
                RUN_KEY: "run-0",
                SCOPE_KEY: SCOPE_TREE,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert recorded_runs(tmp_path) == []


def test_no_record_at_all_is_no_loop(tmp_path):
    assert recorded_runs(tmp_path) == []
    assert not loop_of(tmp_path).in_progress


# --- the backstop -------------------------------------------------------------
#
# Cycle detection catches a loop ping-ponging between a few promises. It does
# not catch a chain where every round breaks something never seen before --
# no repeat, and no convergence either. That is the cap's one job, and
# reaching it changes no verdict.

LIMITS = Limits(max_iterations=3, max_minutes=60)


def test_a_loop_within_both_limits_has_reached_neither(tmp_path):
    run(tmp_path, {"ui/a/one": FAILED}, minute=0)
    run(tmp_path, {"ui/a/one": FAILED}, minute=5)

    assert reached(loop_of(tmp_path), LIMITS) == ()


def test_a_loop_at_its_round_limit_says_so(tmp_path):
    for minute in (0, 1, 2):
        run(tmp_path, {"ui/a/one": FAILED}, minute=minute)

    assert reached(loop_of(tmp_path), LIMITS) == (ITERATION_CAP,)


def test_a_loop_at_its_clock_limit_says_so(tmp_path):
    run(tmp_path, {"ui/a/one": FAILED}, minute=0)
    run(tmp_path, {"ui/a/one": FAILED}, minute=60)

    assert reached(loop_of(tmp_path), LIMITS) == (TIME_CAP,)


def test_a_loop_past_both_names_both(tmp_path):
    for minute in (0, 30, 90):
        run(tmp_path, {"ui/a/one": FAILED}, minute=minute)

    assert reached(loop_of(tmp_path), LIMITS) == (ITERATION_CAP, TIME_CAP)


def test_a_green_suite_reaches_no_cap_however_long_the_record(tmp_path):
    """There is no loop to cap. A cap counted against a record rather than
    against a loop would trip on a project that has simply been running its
    suite for a while."""
    for minute in (0, 100, 200, 300):
        run(tmp_path, {"ui/a/one": PASSED}, minute=minute)

    assert reached(loop_of(tmp_path), LIMITS) == ()


def test_a_quarantined_promise_does_not_hold_a_loop_open(tmp_path):
    """The run itself did not fail on it, and a loop is what a red suite is
    in. Held open by one, a project would be looping over a decision a code
    owner took deliberately, and no application fix could ever end it."""
    run(tmp_path, {"ui/a/one": FAILED, "ui/a/two": PASSED}, quarantined=("ui/a/one",))

    assert not loop_of(tmp_path).in_progress


def test_quarantining_a_promise_mid_loop_reads_as_the_loop_ending(tmp_path):
    run(tmp_path, {"ui/a/one": FAILED}, minute=0)
    run(tmp_path, {"ui/a/one": FAILED}, minute=5, quarantined=("ui/a/one",))

    assert not loop_of(tmp_path).in_progress


def test_a_quarantine_lifted_later_does_not_rewrite_what_a_round_gated_on(tmp_path):
    """What each round gated on is recorded when it ran. Read back through
    today's tree instead, a promise quarantined this morning would look as
    though it never gated at all."""
    run(tmp_path, {"ui/a/one": FAILED}, minute=0)
    run(tmp_path, {"ui/a/one": FAILED}, minute=5)

    assert loop_of(tmp_path).iterations == 2
