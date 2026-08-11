"""What a project declares in `seal-test-config.json`, and what `seal check`
refuses about it.

The config is the one thing about an outcome tree that a walk cannot answer:
nothing about a directory of promises says what starts them. That makes it
the one place the tree and a declaration can drift apart, so most of what is
checked here is the two disagreeing -- a group nothing claims, a runner
claiming nothing.

Every tree here is one the test writes itself, so what's checked is what an
adopting project gets rather than what `examples/angular-django` happens to
hold. Pure filesystem work -- no Tilt, no cluster.
"""

import json
from pathlib import Path

from seal.outcomes import discover_outcomes, outcome_layout_problems
from seal.runners import (
    CONFIG_FILENAME,
    CUSTOM,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MAX_MINUTES,
    DOCKERFILE_FILENAME,
    LOOP_FIELD,
    MAX_ITERATIONS_FIELD,
    MAX_MINUTES_FIELD,
    PLAYWRIGHT,
    TAP,
    TAP_RUNNER_FILENAME,
    read_loop_limits,
    read_runner_config,
)
from test_outcomes import (
    GROUP,
    TRANSLATION,
    declare_runners,
    outcome,
    problems_at,
    tap_runner,
    write,
)


def test_a_runner_is_read_with_the_group_it_drives(tmp_path):
    declare_runners(tmp_path, {"name": "ui", "runner_type": PLAYWRIGHT})
    (runner,), problems = read_runner_config(tmp_path)

    assert problems == []
    assert (runner.name, runner.runner_type) == ("ui", PLAYWRIGHT)
    assert runner.runner_args == ()


def test_a_runner_can_be_told_what_to_say_to_itself(tmp_path):
    """What reaches the container ahead of the outcomes it has to run, and
    the one thing about a runner seal has no way to know."""
    declare_runners(
        tmp_path,
        {"name": "ui", "runner_type": PLAYWRIGHT, "runner_args": ["--timeout=60000"]},
    )
    (runner,), _ = read_runner_config(tmp_path)

    assert runner.runner_args == ("--timeout=60000",)


def test_a_custom_runner_defaults_to_the_dockerfile_in_its_own_group(tmp_path):
    """The ordinary case takes no path at all: a group brings a runner by
    keeping it beside the epics it runs."""
    declare_runners(tmp_path, {"name": "api", "runner_type": CUSTOM})
    (runner,), _ = read_runner_config(tmp_path)

    assert runner.dockerfile == f"api/{DOCKERFILE_FILENAME}"
    assert runner.dockerfile_context == "api"


def test_a_custom_runner_can_be_built_from_somewhere_else_in_the_tree(tmp_path):
    """Two groups sharing one image, or a runner kept beside the config
    rather than inside a group -- both are a project's business."""
    declare_runners(
        tmp_path,
        {
            "name": "api",
            "runner_type": CUSTOM,
            "dockerfile": "runner/Dockerfile",
            "dockerfile_context": "runner",
        },
    )
    (runner,), problems = read_runner_config(tmp_path)

    assert problems == []
    assert (runner.dockerfile, runner.dockerfile_context) == (
        "runner/Dockerfile",
        "runner",
    )


def test_a_build_path_reaching_outside_the_tree_is_refused(tmp_path):
    """An image built from a checkout's surroundings is one whose contents
    depend on where it was built, which is the reproducibility the whole
    environment layer exists to give."""
    declare_runners(
        tmp_path,
        {"name": "api", "runner_type": CUSTOM, "dockerfile_context": "../.."},
    )
    _, (problem,) = read_runner_config(tmp_path)

    assert "reaches outside the outcome tree" in problem


def test_a_runner_type_seal_has_no_runner_for_is_refused(tmp_path):
    """A misread type would fall back to some other runner, and a group
    quietly run by the wrong thing reports promises as broken for a reason
    nothing in the tree shows."""
    declare_runners(tmp_path, {"name": "api", "runner_type": "pytest"})
    _, (problem,) = read_runner_config(tmp_path)

    assert "'pytest'" in problem and CUSTOM in problem


def test_a_dockerfile_on_a_runner_seal_supplies_is_refused(tmp_path):
    """A line nothing reads is worse than a missing one: it says the image is
    the project's when the image is seal's."""
    declare_runners(
        tmp_path,
        {"name": "ui", "runner_type": PLAYWRIGHT, "dockerfile": "ui/Dockerfile"},
    )
    _, (problem,) = read_runner_config(tmp_path)

    assert "whose image is seal's" in problem


def test_a_tap_runner_is_read_with_the_group_it_drives(tmp_path):
    """seal starts a 'tap' group on the machine, so there is no image
    for a project to bring and both build fields stay empty."""
    declare_runners(tmp_path, {"name": "cli", "runner_type": TAP})
    (runner,), problems = read_runner_config(tmp_path)

    assert problems == []
    assert (runner.name, runner.runner_type) == ("cli", TAP)
    assert (runner.dockerfile, runner.dockerfile_context) == (None, None)
    assert runner.is_tap and not runner.is_custom


def test_a_tap_runner_can_be_told_what_to_say_to_itself(tmp_path):
    """The same argument shape every runner gets: its own words, then the
    outcomes it has to run."""
    declare_runners(
        tmp_path,
        {"name": "cli", "runner_type": TAP, "runner_args": ["--strict"]},
    )
    (runner,), _ = read_runner_config(tmp_path)

    assert runner.runner_args == ("--strict",)


def test_a_dockerfile_on_a_tap_runner_is_refused(tmp_path):
    """Held to the same rule as a 'playwright' one, and for the same reason:
    a build field here says the image is the project's when there is no image
    at all."""
    declare_runners(
        tmp_path,
        {"name": "cli", "runner_type": TAP, "dockerfile": "cli/Dockerfile"},
    )
    _, (problem,) = read_runner_config(tmp_path)

    assert "whose image is seal's" in problem
    assert CUSTOM in problem


def test_a_dockerfile_context_on_a_tap_runner_is_refused(tmp_path):
    declare_runners(
        tmp_path,
        {"name": "cli", "runner_type": TAP, "dockerfile_context": "cli"},
    )
    _, (problem,) = read_runner_config(tmp_path)

    assert "dockerfile_context" in problem


def test_a_misspelled_field_on_a_tap_runner_is_refused(tmp_path):
    declare_runners(tmp_path, {"name": "cli", "runner_type": TAP, "args": ["-x"]})
    _, (problem,) = read_runner_config(tmp_path)

    assert "'args'" in problem


def test_two_runners_naming_one_group_are_refused_whichever_types(tmp_path):
    declare_runners(
        tmp_path,
        {"name": "cli", "runner_type": TAP},
        {"name": "cli", "runner_type": PLAYWRIGHT},
    )
    _, problems = read_runner_config(tmp_path)

    assert any("'cli'" in problem for problem in problems)


def test_a_tap_group_keeps_its_runner_beside_its_epics(tmp_path):
    """What starts a 'tap' group lives at the group's own level, the way a
    'custom' group's build material does. A file there is the runner, not a
    promise filed at the wrong depth."""
    outcome(tmp_path, "gating", "a-promise", translation=TRANSLATION, group="cli")
    declare_runners(tmp_path, {"name": "cli", "runner_type": TAP})
    tap_runner(tmp_path, "cli")

    assert problems_at(tmp_path) == []


def test_a_tap_group_with_an_executable_runner_passes(tmp_path):
    outcome(tmp_path, "gating", "a-promise", translation=TRANSLATION, group="cli")
    declare_runners(tmp_path, {"name": "cli", "runner_type": TAP})
    tap_runner(tmp_path, "cli")

    assert problems_at(tmp_path) == []


def test_a_tap_group_with_nothing_to_start_is_refused(tmp_path):
    """The version, one level up, of the rule about a translation a runner
    cannot run: a group nothing can start reports every promise under it as
    untested, for a reason no listing explains."""
    outcome(tmp_path, "gating", "a-promise", translation=TRANSLATION, group="cli")
    declare_runners(tmp_path, {"name": "cli", "runner_type": TAP})

    (problem,) = problems_at(tmp_path)

    assert f"cli/{TAP_RUNNER_FILENAME}" in problem
    assert "untested" in problem


def test_a_runner_that_cannot_be_run_is_its_own_problem(tmp_path):
    """The one somebody actually hits: git records the executable bit, and a
    checkout onto a filesystem that drops it leaves a file plainly there and
    unable to start. Saying it is missing would send them looking for it."""
    outcome(tmp_path, "gating", "a-promise", translation=TRANSLATION, group="cli")
    declare_runners(tmp_path, {"name": "cli", "runner_type": TAP})
    write(tmp_path / "cli" / TAP_RUNNER_FILENAME, "#!/bin/sh\n").chmod(0o644)

    (problem,) = problems_at(tmp_path)

    assert "not executable" in problem
    assert "chmod +x" in problem


def test_what_a_tap_group_translates_a_promise_into_is_its_own_business(tmp_path):
    """Taken at its word, the way a 'custom' group is: seal has no
    reading of what somebody else's runner starts, which is the whole point
    of declaring one."""
    outcome(
        tmp_path,
        "gating",
        "a-promise",
        translation={"check.py": "assert True\n"},
        group="cli",
    )
    declare_runners(tmp_path, {"name": "cli", "runner_type": TAP})
    tap_runner(tmp_path, "cli")

    assert problems_at(tmp_path) == []


def test_a_group_that_cannot_start_is_reported_beside_the_trees_own_offenders(tmp_path):
    """One pass, so a project puts its tree right in one go rather than one
    failed run at a time."""
    outcome(tmp_path, "gating", "a-promise", translation=TRANSLATION, group="cli")
    declare_runners(tmp_path, {"name": "cli", "runner_type": TAP})
    write(tmp_path / "cli" / "gating" / "orphan" / "check.py", "\n")

    problems = problems_at(tmp_path)

    assert any(TAP_RUNNER_FILENAME in problem for problem in problems)
    assert any("no prompt.md" in problem for problem in problems)


def test_a_playwright_group_is_untouched_by_the_rule(tmp_path):
    """Nothing about a group seal starts in the cluster changed: it has
    no executable of its own and is not asked for one."""
    outcome(tmp_path, "todo-list", "a-promise", translation=TRANSLATION)

    assert problems_at(tmp_path) == []


def test_a_misspelled_field_is_refused(tmp_path):
    """The one config mistake a run cannot report: it reads as a default
    nobody asked for."""
    declare_runners(tmp_path, {"name": "ui", "runner_type": PLAYWRIGHT, "args": ["-x"]})
    _, (problem,) = read_runner_config(tmp_path)

    assert "'args'" in problem


def test_two_runners_naming_the_same_group_are_refused(tmp_path):
    declare_runners(
        tmp_path,
        {"name": "ui", "runner_type": PLAYWRIGHT},
        {"name": "ui", "runner_type": CUSTOM},
    )
    _, problems = read_runner_config(tmp_path)

    assert any("already runs" in problem for problem in problems)


def test_a_file_that_is_not_json_is_refused(tmp_path):
    write(tmp_path / CONFIG_FILENAME, "runner: [ui]\n")
    _, (problem,) = read_runner_config(tmp_path)

    assert "cannot be read as JSON" in problem


def test_a_tree_with_no_config_at_all_is_refused(tmp_path):
    """Nothing says what runs these promises, so nothing can start them --
    and the suite reports a promise nothing starts as untested."""
    write(tmp_path / GROUP / "todo-list" / "a-promise" / "prompt.md", "# a promise\n")

    (problem,) = problems_at(tmp_path)
    assert problem.startswith(f".: no {CONFIG_FILENAME}")


def test_a_group_no_runner_names_is_refused(tmp_path):
    """The tree and its declaration having drifted apart. Every promise under
    that directory would be reported untested, which reads exactly like a
    promise nobody has got to yet."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)
    write(tmp_path / "api" / "billing" / "an-invoice" / "prompt.md", "# a promise\n")

    (problem,) = problems_at(tmp_path)
    assert problem.startswith("api: no runner in")


def test_a_runner_naming_no_group_is_refused(tmp_path):
    """The same drift from the other side: an image built over nothing."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)
    declare_runners(
        tmp_path,
        {"name": GROUP, "runner_type": PLAYWRIGHT},
        {"name": "api", "runner_type": PLAYWRIGHT},
    )

    (problem,) = problems_at(tmp_path)
    assert "'api' has no directory in this tree" in problem


def test_a_custom_runner_whose_dockerfile_is_missing_is_refused(tmp_path):
    declare_runners(tmp_path, {"name": "api", "runner_type": CUSTOM})
    write(tmp_path / "api" / "billing" / "an-invoice" / "prompt.md", "# a promise\n")

    (problem,) = problems_at(tmp_path)
    assert f"api/{DOCKERFILE_FILENAME} is not there" in problem


def test_a_config_declaring_no_runner_at_all_is_refused(tmp_path):
    declare_runners(tmp_path)

    (problem,) = problems_at(tmp_path)
    assert problem.startswith(f"{CONFIG_FILENAME}: declares no runner")


def test_a_group_a_runner_names_holds_that_runners_build_context(tmp_path):
    """A group brings its runner, so what sits beside its epics is that
    runner's -- an entrypoint, a lockfile, whatever it builds from."""
    declare_runners(tmp_path, {"name": "api", "runner_type": CUSTOM})
    write(tmp_path / "api" / DOCKERFILE_FILENAME, "FROM alpine:3\n")
    write(tmp_path / "api" / "run.sh", "#!/bin/sh\n")
    write(tmp_path / "api" / "billing" / "an-invoice" / "prompt.md", "# a promise\n")

    assert problems_at(tmp_path) == []


def test_a_file_at_the_tree_root_belongs_to_a_custom_runner(tmp_path):
    """A runner built from the whole tree keeps what it needs beside the
    config, which is the one thing at that level that is nobody's promise."""
    declare_runners(
        tmp_path,
        {
            "name": "api",
            "runner_type": CUSTOM,
            "dockerfile": DOCKERFILE_FILENAME,
            "dockerfile_context": ".",
        },
    )
    write(tmp_path / DOCKERFILE_FILENAME, "FROM alpine:3\n")
    write(tmp_path / "run.sh", "#!/bin/sh\n")
    write(tmp_path / "api" / "billing" / "an-invoice" / "prompt.md", "# a promise\n")

    assert problems_at(tmp_path) == []


def test_an_outcome_under_an_undeclared_group_is_not_discovered(tmp_path):
    """Discovery describes a tree the config can be read against, and reports
    what it cannot through `seal check` instead."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload")
    write(tmp_path / "api" / "billing" / "an-invoice" / "prompt.md", "# a promise\n")

    assert [found.slug for found in discover_outcomes(tmp_path)] == [
        "ui/todo-list/an-item-survives-a-reload"
    ]


def test_a_project_with_no_outcome_tree_declares_no_runners(tmp_path):
    assert read_runner_config(tmp_path / "nothing-here") == ([], [])
    assert outcome_layout_problems(tmp_path / "nothing-here") == []


# --- where a project's regression loop stops ----------------------------------
#
# The second thing this file declares, and the second thing a walk of the
# tree cannot answer. Cycle detection catches a loop ping-ponging between a
# few promises; neither it nor a cap catches the other without the other, so
# both are here and both are backstops rather than measurements.


def declare_loop(tmp_path: Path, block) -> Path:
    """A config declaring a runner, as every project must, and a `loop` block
    beside it."""
    declare_runners(tmp_path, {"name": GROUP, "runner_type": PLAYWRIGHT})
    config = tmp_path / CONFIG_FILENAME
    document = json.loads(config.read_text(encoding="utf-8"))
    document[LOOP_FIELD] = block
    config.write_text(json.dumps(document), encoding="utf-8")
    return config


def test_a_project_that_declares_no_loop_gets_the_backstops(tmp_path):
    """A backstop is not something an adopting project should have to write
    down before its first loop."""
    declare_runners(tmp_path, {"name": GROUP, "runner_type": PLAYWRIGHT})

    limits, problems = read_loop_limits(tmp_path)

    assert problems == []
    assert limits.max_iterations == DEFAULT_MAX_ITERATIONS
    assert limits.max_minutes == DEFAULT_MAX_MINUTES


def test_a_project_with_no_config_at_all_gets_them_too(tmp_path):
    limits, problems = read_loop_limits(tmp_path)

    assert problems == []
    assert limits.max_iterations == DEFAULT_MAX_ITERATIONS


def test_a_declared_limit_replaces_the_backstop(tmp_path):
    declare_loop(tmp_path, {MAX_ITERATIONS_FIELD: 4, MAX_MINUTES_FIELD: 30})

    limits, problems = read_loop_limits(tmp_path)

    assert problems == []
    assert (limits.max_iterations, limits.max_minutes) == (4, 30)


def test_each_limit_is_declared_on_its_own(tmp_path):
    """A project that has measured its rounds and not its clock should not
    have to invent the other."""
    declare_loop(tmp_path, {MAX_ITERATIONS_FIELD: 4})

    limits, _ = read_loop_limits(tmp_path)

    assert (limits.max_iterations, limits.max_minutes) == (4, DEFAULT_MAX_MINUTES)


def test_a_loop_block_that_is_not_an_object_is_refused(tmp_path):
    declare_loop(tmp_path, 4)

    limits, (problem,) = read_loop_limits(tmp_path)

    assert MAX_ITERATIONS_FIELD in problem
    assert limits.max_iterations == DEFAULT_MAX_ITERATIONS


def test_a_limit_of_zero_is_refused(tmp_path):
    """A loop that stops before it starts, declared as though it were a
    policy."""
    declare_loop(tmp_path, {MAX_ITERATIONS_FIELD: 0})

    _, (problem,) = read_loop_limits(tmp_path)

    assert "above zero" in problem


def test_a_negative_limit_is_refused(tmp_path):
    declare_loop(tmp_path, {MAX_MINUTES_FIELD: -5})

    _, (problem,) = read_loop_limits(tmp_path)

    assert MAX_MINUTES_FIELD in problem


def test_a_limit_that_is_not_a_whole_number_is_refused(tmp_path):
    declare_loop(tmp_path, {MAX_MINUTES_FIELD: "an hour or so"})

    _, (problem,) = read_loop_limits(tmp_path)

    assert "whole number" in problem


def test_a_misspelled_limit_is_refused_rather_than_ignored(tmp_path):
    """It reads as a default nobody asked for, which is the one config mistake
    a run cannot report."""
    declare_loop(tmp_path, {"max_iteration": 4})

    _, (problem,) = read_loop_limits(tmp_path)

    assert "max_iteration'" in problem


def test_everything_wrong_with_a_loop_block_is_reported_in_one_pass(tmp_path):
    declare_loop(tmp_path, {MAX_ITERATIONS_FIELD: 0, MAX_MINUTES_FIELD: -1, "rounds": 3})

    _, problems = read_loop_limits(tmp_path)

    assert len(problems) == 3


def test_declaring_a_loop_is_not_declaring_something_unknown(tmp_path):
    """The file holds two fields now, and the check that refuses everything
    else has to know it."""
    declare_loop(tmp_path, {MAX_ITERATIONS_FIELD: 4})

    _, problems = read_runner_config(tmp_path)

    assert problems == []


def test_a_mis_declared_loop_fails_the_check(tmp_path):
    """The block is part of the file `seal check` already reads, so a project
    finds out where it finds out about everything else wrong with it."""
    outcome(tmp_path, "todo-list", "a-reload-keeps-it", translation=TRANSLATION)
    declare_loop(tmp_path, {MAX_ITERATIONS_FIELD: 0})

    assert [problem for problem in problems_at(tmp_path) if MAX_ITERATIONS_FIELD in problem]


def test_a_file_that_is_not_json_is_complained_about_once(tmp_path):
    """Both readers open the same file; only one of them is its reader."""
    write(tmp_path / CONFIG_FILENAME, "{oh dear")

    _, from_runners = read_runner_config(tmp_path)
    _, from_loop = read_loop_limits(tmp_path)

    assert len(from_runners) == 1
    assert from_loop == []
