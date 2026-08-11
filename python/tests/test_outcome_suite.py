"""What the outcome suite reports, and what it exits with.

Every tree and every results directory here is one the test writes itself,
so what's checked is what an adopting project gets rather than what
`examples/angular-django` happens to hold. No containers and no cluster:
what runs an outcome is the Tilt resource that puts it in front of the
environment, and what's under test here is the reading of what it left
behind.
"""

import itertools
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from seal.checks import K8S_DIR_ENV_VAR
import seal.seal
from seal.outcome_suite import (
    DEFAULT_RESULTS_DIR_NAME,
    FIRST_RUN_SUFFIX,
    SELECTION_FILE,
    OUTCOMES_RESULTS_SUBDIR,
    VERDICT_FAILED,
    VERDICT_FILENAME,
    VERDICT_PASSED,
    results_dir_for,
)
from seal.outcome_history import (
    HISTORY_FILE,
    RUN_KEY,
    SCOPE_KEY,
    SCOPE_SELECTION,
    SCOPE_TREE,
    recorded_runs,
    recorded_verdicts,
)
from seal.outcomes import OUTCOMES_DIR_ENV_VAR, QUARANTINE_FILENAME
from seal.runners import (
    CONFIG_FILENAME,
    LOOP_FIELD,
    PLAYWRIGHT,
    RUNNER_FIELD,
    TAP,
    TAP_RUNNER_FILENAME,
)
from seal.seal import main


def _overlay(k8s_dir, **documents):
    """Write an overlay deploying `name=document`. The check builds what a
    project would deploy, so a fixture has to be something kustomize can
    actually build -- loose manifests no kustomization names are manifests
    no cluster ever sees."""
    for name, document in documents.items():
        write(k8s_dir / f"{name}.yaml", yaml.safe_dump(document))
    write(
        k8s_dir / "kustomization.yaml",
        yaml.safe_dump(
            {
                "apiVersion": "kustomize.config.k8s.io/v1beta1",
                "kind": "Kustomization",
                "resources": [f"{name}.yaml" for name in documents],
            }
        ),
    )


def _deployment(name, containers):
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {"containers": containers},
            },
        },
    }

def declare_loop(project: Path, **limits) -> None:
    """What this project says about where its regression loop stops, added to
    the config a promise already declares its runner in."""
    config = project / "outcomes" / CONFIG_FILENAME
    document = json.loads(config.read_text(encoding="utf-8"))
    document[LOOP_FIELD] = limits
    config.write_text(json.dumps(document), encoding="utf-8")


def recorded_entries(project: Path) -> list[dict]:
    """The record's own lines, for the few assertions about what a run wrote
    rather than about what a read makes of it."""
    return [
        json.loads(line)
        for line in (project / HISTORY_FILE).read_text(encoding="utf-8").splitlines()
    ]


GROUP = "ui"
"""The group every promise below sits in. A project's outcomes are grouped
by what runs them, and one group is the smallest tree there is."""

PROBE = {"httpGet": {"path": "/healthz", "port": 8000}}


def write(path: Path, body: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def promise(
    project: Path,
    epic: str,
    name: str,
    headline: str = "a promise",
    translated: bool = True,
    verdict: str | None = None,
    group: str = GROUP,
) -> Path:
    """One outcome, and whatever its test container left behind -- `verdict`
    None standing for a test that ran and wrote nothing, which is a different
    thing from a promise nothing has been translated from yet."""
    outcomes_dir = project / "outcomes"
    declared = (
        json.loads((outcomes_dir / CONFIG_FILENAME).read_text(encoding="utf-8"))[
            RUNNER_FIELD
        ]
        if (outcomes_dir / CONFIG_FILENAME).is_file()
        else []
    )
    if group not in [entry["name"] for entry in declared]:
        write(
            outcomes_dir / CONFIG_FILENAME,
            json.dumps(
                {RUNNER_FIELD: declared + [{"name": group, "runner_type": PLAYWRIGHT}]}
            )
            + "\n",
        )
    directory = outcomes_dir / group / epic / name
    write(directory / "prompt.md", f"# {headline}\n")
    if translated:
        write(directory / f"{name}.spec.ts", "test('a promise', async () => {});\n")
    if verdict is not None:
        write(
            project / DEFAULT_RESULTS_DIR_NAME / OUTCOMES_RESULTS_SUBDIR / group / epic
            / name / VERDICT_FILENAME,
            verdict + "\n",
        )
    return directory


# --- a group seal starts on the machine -------------------------------------

# What the fake runners below record so a test can read back exactly how they
# were started -- the arguments, and one line per time they ran.
INVOCATIONS = "invocations"


def tap_group(
    project: Path,
    *epic_and_names: tuple[str, str],
    group: str = "cli",
    says: str = "",
    exit_code: int = 0,
    runner_args: list[str] | None = None,
) -> Path:
    """A group seal starts as a subprocess, its promises, and a runner
    that prints `says` and exits `exit_code`.

    The runner records how it was invoked, so what a test asserts on is what
    seal actually started rather than a stand-in for it."""
    outcomes_dir = project / "outcomes"
    declared = (
        json.loads((outcomes_dir / CONFIG_FILENAME).read_text(encoding="utf-8"))[
            RUNNER_FIELD
        ]
        if (outcomes_dir / CONFIG_FILENAME).is_file()
        else []
    )
    entry = {"name": group, "runner_type": TAP}
    if runner_args is not None:
        entry["runner_args"] = runner_args
    write(
        outcomes_dir / CONFIG_FILENAME,
        json.dumps({RUNNER_FIELD: [e for e in declared if e["name"] != group] + [entry]})
        + "\n",
    )
    for epic, name in epic_and_names:
        directory = outcomes_dir / group / epic / name
        write(directory / "prompt.md", f"# {name}\n")
        write(directory / "check.sh", "true\n")
    runner = write(
        outcomes_dir / group / TAP_RUNNER_FILENAME,
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "$(dirname "$0")/{INVOCATIONS}"\n'
        f"cat <<'TAP_STREAM'\n{says}\nTAP_STREAM\n"
        f"exit {exit_code}\n",
    )
    runner.chmod(0o755)
    return outcomes_dir / group


def invocations(group_dir: Path) -> list[str]:
    """How the group's runner was started, once per line."""
    record = group_dir / INVOCATIONS
    if not record.is_file():
        return []
    return [line for line in record.read_text(encoding="utf-8").splitlines() if line]


def verdict_of(project: Path, group: str, epic: str, name: str) -> str | None:
    """What this run recorded about a promise, or None where it recorded
    nothing -- which is what a promise nothing tested looks like."""
    path = (
        project
        / DEFAULT_RESULTS_DIR_NAME
        / OUTCOMES_RESULTS_SUBDIR
        / group
        / epic
        / name
        / VERDICT_FILENAME
    )
    return path.read_text(encoding="utf-8") if path.is_file() else None


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A minimal seal project root -- what find_seal_root() looks for."""
    (tmp_path / "Tiltfile").write_text("# root Tiltfile\n", encoding="utf-8")
    (tmp_path / "services").mkdir()
    _overlay(
        tmp_path / "k8s" / "dev",
        web=_deployment("web", [{"name": "api", "readinessProbe": PROBE}]),
    )
    monkeypatch.delenv(K8S_DIR_ENV_VAR, raising=False)
    monkeypatch.delenv(OUTCOMES_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_a_group_run_on_the_machine_is_started_once(project, capsys):
    """The whole reason a stream is read rather than a file per outcome:
    what a run costs stops being tied to how many promises it covers."""
    group = tap_group(
        project,
        ("gating", "one"),
        ("gating", "two"),
        ("gating", "three"),
        says="1..3\nok 1 - gating/one\nok 2 - gating/two\nok 3 - gating/three",
    )

    assert main(["outcomes", "run", "--all"]) == 0
    # In the tree's own order, which is the order everything else reads it
    # in -- not the order a caller happened to write the promises down.
    assert invocations(group) == ["-- gating/one gating/three gating/two"]


def test_the_runners_own_arguments_come_before_the_outcomes(project):
    """The same shape a container runner is given: its own words, then the
    separator, then one promise per argument."""
    group = tap_group(
        project,
        ("gating", "one"),
        says="1..1\nok 1 - gating/one",
        runner_args=["--strict", "-v"],
    )

    main(["outcomes", "run", "--all"])

    assert invocations(group) == ["--strict -v -- gating/one"]


def test_naming_outcomes_narrows_what_the_runner_is_told(project):
    group = tap_group(
        project,
        ("gating", "one"),
        ("gating", "two"),
        says="1..1\nok 1 - gating/one",
    )

    main(["outcomes", "run", "cli/gating/one"])

    assert invocations(group) == ["-- gating/one"]


def test_a_stream_becomes_one_verdict_per_promise(project):
    tap_group(
        project,
        ("gating", "kept"),
        ("gating", "broken"),
        says="1..2\nok 1 - gating/kept\nnot ok 2 - gating/broken",
    )

    assert main(["outcomes", "run", "--all"]) == 1
    assert verdict_of(project, "cli", "gating", "kept") == VERDICT_PASSED
    assert verdict_of(project, "cli", "gating", "broken") == VERDICT_FAILED


def test_what_the_runner_printed_is_kept_beside_the_verdicts(project):
    tap_group(
        project,
        ("gating", "broken"),
        says="1..1\nnot ok 1 - gating/broken\n  ---\n  message: the probe never came up\n  ...",
    )

    main(["outcomes", "run", "--all"])
    results = (
        project / DEFAULT_RESULTS_DIR_NAME / OUTCOMES_RESULTS_SUBDIR / "cli"
    )

    assert "the probe never came up" in (
        results / "gating" / "broken" / "log.txt"
    ).read_text(encoding="utf-8")
    assert "not ok 1" in (results / "run.log").read_text(encoding="utf-8")


def test_a_skipped_promise_is_never_recorded_as_kept(project, capsys):
    """A skipped point is written `ok` by convention and established
    nothing, so it leaves no verdict -- which the suite already reports as a
    test that did not run rather than as a gap."""
    tap_group(
        project,
        ("gating", "one"),
        says="1..1\nok 1 - gating/one # SKIP no cluster here",
    )

    assert main(["outcomes", "run", "--all"]) == 1
    assert verdict_of(project, "cli", "gating", "one") is None
    assert "no verdict" in capsys.readouterr().out


def test_a_todo_promise_is_never_recorded_as_kept(project, capsys):
    tap_group(
        project,
        ("gating", "one"),
        says="1..1\nnot ok 1 - gating/one # TODO being written",
    )

    assert main(["outcomes", "run", "--all"]) == 1
    assert verdict_of(project, "cli", "gating", "one") is None


def test_a_point_naming_a_promise_the_run_did_not_ask_about_is_reported(project, capsys):
    """A runner and a tree that disagree. Filed under nothing, because
    inventing a directory for it would put a verdict where nothing looks."""
    tap_group(
        project,
        ("gating", "one"),
        says="1..2\nok 1 - gating/one\nok 2 - gating/somewhere-else",
    )

    main(["outcomes", "run", "--all"])
    results = project / DEFAULT_RESULTS_DIR_NAME / OUTCOMES_RESULTS_SUBDIR / "cli"

    assert "not one of the outcomes it was given" in capsys.readouterr().err
    assert not (results / "gating" / "somewhere-else").exists()


def test_a_runner_that_stops_partway_leaves_the_rest_untested(project, capsys):
    """The distinction the whole module is built around: a promise this run
    saw broken, and a promise this run never reached. Recording failures for
    the second would be inventing them."""
    tap_group(
        project,
        ("gating", "one"),
        ("gating", "two"),
        ("gating", "three"),
        says="1..3\nok 1 - gating/one\nBail out! the cluster died",
    )

    assert main(["outcomes", "run", "--all"]) == 1
    assert verdict_of(project, "cli", "gating", "one") == VERDICT_PASSED
    assert verdict_of(project, "cli", "gating", "two") is None
    assert verdict_of(project, "cli", "gating", "three") is None
    assert "stopped before it had finished" in capsys.readouterr().err


def test_a_runner_that_exits_non_zero_still_has_its_points_read(project, capsys):
    """A `tap` runner may exit however it likes -- the stream is the whole
    of what it says. Unlike a container runner, whose exit takes its own
    resource down with it."""
    tap_group(
        project,
        ("gating", "one"),
        says="1..1\nnot ok 1 - gating/one",
        exit_code=3,
    )

    assert main(["outcomes", "run", "--all"]) == 1
    assert verdict_of(project, "cli", "gating", "one") == VERDICT_FAILED
    assert "exited 3" in capsys.readouterr().err


def test_a_runner_that_says_nothing_leaves_every_promise_untested(project, capsys):
    tap_group(project, ("gating", "one"), ("gating", "two"), says="")

    assert main(["outcomes", "run", "--all"]) == 1
    assert verdict_of(project, "cli", "gating", "one") is None
    assert verdict_of(project, "cli", "gating", "two") is None
    assert "2 with no verdict" in capsys.readouterr().out


def test_a_previous_runs_verdict_is_never_read_as_this_ones(project):
    """A promise that has stopped being reported on is exactly when a stale
    file would be presented as this run's own result."""
    tap_group(
        project,
        ("gating", "one"),
        says="1..1\nok 1 - gating/one",
    )
    write(
        project / DEFAULT_RESULTS_DIR_NAME / OUTCOMES_RESULTS_SUBDIR / "cli" / "gating"
        / "one" / VERDICT_FILENAME,
        VERDICT_FAILED,
    )

    assert main(["outcomes", "run", "--all"]) == 0


def test_asking_to_reset_a_run_that_deploys_nothing_says_so(project, capsys):
    """There is no session holding a service whose state a reset would put
    back. Said rather than done silently: somebody who asked for a baseline
    and did not get one should hear so before reading the verdicts."""
    tap_group(project, ("gating", "one"), says="1..1\nok 1 - gating/one")

    assert main(["outcomes", "run", "--reset", "--all"]) == 0
    assert "no session to reset" in capsys.readouterr().out


def test_confirming_a_failure_runs_the_group_again_with_that_promise_alone(project, capsys):
    """Everything downstream reads the verdict tree and nothing else, which
    is what this is really asserting: `--confirm` gets a group run on the
    machine for free, because confirmation is another run and a run is a
    dispatch."""
    group = tap_group(
        project,
        ("gating", "one"),
        ("gating", "two"),
        says="1..2\nnot ok 1 - gating/one\nok 2 - gating/two",
    )

    assert main(["outcomes", "run", "--confirm", "--all"]) == 1
    assert invocations(group) == [
        "-- gating/one gating/two",
        # The failure alone, which is the whole point: a promise that fails
        # in the suite and holds by itself is a test that does not own the
        # data it asserts on, and that is a third thing again.
        "-- gating/one",
    ]
    assert "FAIL (confirmed)" in capsys.readouterr().out


def test_a_quarantined_promise_on_the_machine_does_not_fail_the_run(project, capsys):
    """The other half of the same claim: a `tap` group's verdicts are read
    by everything that reads a container group's."""
    tap_group(project, ("gating", "one"), says="1..1\nnot ok 1 - gating/one")
    write(project / "outcomes" / "cli" / "gating" / "one" / QUARANTINE_FILENAME,
          "Being rewritten to wait on the state.\n")

    assert main(["outcomes", "run", "--all"]) == 0
    assert "FAIL (quarantined)" in capsys.readouterr().out


def test_a_run_that_deployed_nothing_does_not_claim_a_session_was_up(project, capsys):
    """The line a reader takes as the run's own account of itself. Saying it
    went and got these verdicts is the load-bearing half -- that is what
    separates them from verdicts read off somebody else's run. Where the
    promises were checked is the other half, and a group started on the
    machine has no session to have been up."""
    tap_group(project, ("gating", "one"), says="1..1\nok 1 - gating/one")

    assert main(["outcomes", "run", "--all"]) == 0
    listing = capsys.readouterr().out

    assert "run just now: 1 passed." in listing
    assert "session" not in listing


def test_a_run_that_deployed_something_still_says_where(project, capsys, monkeypatch):
    """The clause is right for the runs it was written for, and stays."""
    promise(project, "todo-list", "one", verdict=VERDICT_PASSED)
    monkeypatch.setattr(seal.seal, "_run_outcomes", lambda *args, **kwargs: None)

    assert main(["outcomes", "run", "--all"]) == 0
    assert "run just now against the session already up" in capsys.readouterr().out


def test_reading_a_run_somebody_else_performed_is_unchanged(project, capsys):
    """This form makes no claim about where, because it did not perform the
    run it is reporting."""
    promise(project, "todo-list", "one", verdict=VERDICT_PASSED)

    assert main(["outcomes", "run"]) == 0
    listing = capsys.readouterr().out

    assert "1 outcome(s): 1 passed." in listing
    assert "just now" not in listing


def test_a_group_on_the_machine_needs_no_tilt(project, monkeypatch):
    """The point of the whole runner: a project whose groups all run here
    has no session, and asking it for one would refuse a run that was never
    going to need it."""
    tap_group(project, ("gating", "one"), says="1..1\nok 1 - gating/one")
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assert main(["outcomes", "run", "--all"]) == 0


def test_a_suite_every_promise_of_which_is_kept_is_green(project, capsys):
    promise(project, "todo-list", "one", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "two", verdict=VERDICT_PASSED)

    assert main(["outcomes", "run"]) == 0
    assert "2 outcome(s): 2 passed." in capsys.readouterr().out


def test_one_failure_makes_the_suite_red(project, capsys):
    promise(project, "todo-list", "one", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "two", verdict=VERDICT_FAILED)

    assert main(["outcomes", "run"]) == 1
    assert "1 passed, 1 failed" in capsys.readouterr().out


def test_a_failure_does_not_stop_the_rest_being_reported(project, capsys):
    """The whole reason a suite exists: a listing that leaves an outcome out
    is indistinguishable from one where it passed."""
    promise(project, "todo-list", "one", verdict=VERDICT_FAILED)
    promise(project, "todo-list", "two", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "three", verdict=VERDICT_FAILED)

    assert main(["outcomes", "run"]) == 1
    listing = capsys.readouterr().out
    assert [line.split()[0] for line in listing.splitlines() if line.startswith("ui/todo-list/")] == [
        "ui/todo-list/one",
        "ui/todo-list/three",
        "ui/todo-list/two",
    ]


def test_an_outcome_that_left_no_verdict_is_a_failure(project, capsys):
    """A test that didn't run is exactly what a green suite must not be able
    to claim on its behalf."""
    promise(project, "todo-list", "one", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "two")

    assert main(["outcomes", "run"]) == 1
    captured = capsys.readouterr()
    assert "no verdict" in captured.out
    assert "1 with no verdict" in captured.out
    assert "nothing here knows this test ran at all" in captured.err.lower()


def test_a_half_written_verdict_is_no_verdict(project, capsys):
    """A truncated write and a file nobody wrote are the same thing from
    here -- a result nothing can vouch for."""
    promise(project, "todo-list", "one", verdict="")

    assert main(["outcomes", "run"]) == 1
    assert "no verdict" in capsys.readouterr().out


def test_a_promise_with_no_test_yet_does_not_fail_the_run(project, capsys):
    """An ordinary state a project sits in: there is nothing for the
    application to satisfy."""
    promise(project, "todo-list", "one", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "two", translated=False)

    assert main(["outcomes", "run"]) == 0
    listing = capsys.readouterr().out
    assert "no test yet" in listing
    assert "2 outcome(s): 1 passed, 1 with no test yet." in listing


def test_every_outcome_is_named_by_the_promise_it_makes(project, capsys):
    """The headline is what the project promises; the slug is only how the
    tree spells it."""
    promise(
        project,
        "todo-list",
        "an-added-item-survives-a-reload",
        headline="an item I add is still on the list after a reload",
        verdict=VERDICT_PASSED,
    )

    assert main(["outcomes", "run"]) == 0
    assert "an item I add is still on the list after a reload" in capsys.readouterr().out


def test_a_failure_says_where_to_look(project, capsys):
    promise(project, "todo-list", "one", verdict=VERDICT_FAILED)

    assert main(["outcomes", "run"]) == 1
    assert "tests-results/outcomes/ui/todo-list/one" in capsys.readouterr().err


def test_a_project_with_no_outcomes_is_not_a_failure(project, capsys):
    """Outcome tests are something a project adopts, not a precondition."""
    assert main(["outcomes", "run"]) == 0
    assert "no outcomes declared" in capsys.readouterr().out


def test_the_suite_can_be_pointed_at_another_tree(project, capsys):
    promise(project, "todo-list", "one", verdict=VERDICT_FAILED)

    assert main(["outcomes", "run", "--outcomes-dir", "promises"]) == 0
    assert "no outcomes declared under promises/" in capsys.readouterr().out


def test_the_suite_can_be_pointed_at_other_results(project, capsys):
    """Where results land is the runner's own arrangement, not something a
    project should have to move its tree to change."""
    promise(project, "todo-list", "one", verdict=VERDICT_PASSED)
    write(
        project / "elsewhere" / OUTCOMES_RESULTS_SUBDIR / GROUP / "todo-list" / "one" / VERDICT_FILENAME,
        VERDICT_FAILED,
    )

    assert main(["outcomes", "run", "--results-dir", "elsewhere"]) == 1
    assert "1 failed" in capsys.readouterr().out


# --- running one outcome without running the suite ----------------------------
#
# What actually runs an outcome is Tilt, against a session that is already up.
# These stand in for it: what is under test is which outcomes a run covers and
# how it says so, not Tilt's own behaviour.


@pytest.fixture
def ran(monkeypatch) -> list[str]:
    """Records which outcomes the run covered, in place of running them."""
    ran = []

    def fake(
        tilt: str,
        seal_root: Path,
        outcomes,
        results_root: Path,
        reset: bool = False,
    ) -> None:
        ran.extend(outcome.slug for outcome in outcomes)

    monkeypatch.setattr("seal.seal._run_outcomes", fake)
    monkeypatch.setattr("seal.seal.shutil.which", lambda name: "/usr/bin/" + name)
    return ran


def test_naming_one_outcome_runs_and_reports_that_one(project, ran, capsys):
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    assert main(["outcomes", "run", "ui/todo-list/deleting-is-permanent"]) == 0

    assert ran == ["ui/todo-list/deleting-is-permanent"]
    assert "deleting-is-permanent" in capsys.readouterr().out


def test_a_subset_exits_on_its_own_verdict_alone(project, ran, capsys):
    """The point of running one outcome is iterating on it. A red promise
    elsewhere in the tree is what the suite is for, and letting it fail this
    run would make the loop useless exactly when it is needed."""
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_FAILED)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    assert main(["outcomes", "run", "ui/todo-list/deleting-is-permanent"]) == 0
    assert main(["outcomes", "run", "ui/todo-list/a-reload-keeps-it"]) == 1


def test_a_subset_run_says_so_rather_than_reading_as_a_green_suite(project, ran, capsys):
    """The one claim this command must never make by accident."""
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "the-count-is-right", verdict=VERDICT_PASSED)

    assert main(["outcomes", "run", "ui/todo-list/the-count-is-right"]) == 0
    subset = capsys.readouterr().out

    assert main(["outcomes", "run"]) == 0
    whole = capsys.readouterr().out

    assert "1 of 3 outcome(s)" in subset
    assert "did not run" in subset
    assert "3 outcome(s):" in whole
    assert "did not run" not in whole


def test_a_slug_that_names_nothing_is_an_error_listing_the_real_ones(project, ran, capsys):
    """A typo that quietly selected nothing would report a green run of no
    outcomes, which reads exactly like a run where every promise was kept."""
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)

    assert main(["outcomes", "run", "ui/todo-list/a-relaod-keeps-it"]) == 1

    error = capsys.readouterr().err
    assert "ui/todo-list/a-relaod-keeps-it" in error
    assert "ui/todo-list/a-reload-keeps-it" in error
    assert ran == []


def test_a_promise_with_no_test_yet_is_reported_rather_than_run(project, ran, capsys):
    """There is nothing to run. Naming one is not an error -- a promise
    waiting for a translation is an ordinary state for a tree to be in."""
    promise(project, "todo-list", "nothing-written-yet", translated=False)

    assert main(["outcomes", "run", "ui/todo-list/nothing-written-yet"]) == 0

    assert ran == []
    assert "no test yet" in capsys.readouterr().out


@pytest.fixture
def session_resources() -> list[str]:
    """What the running session declares, by resource name, in place of a
    session. Appended to by whichever test cares which resets exist."""
    return []


@pytest.fixture
def tilt_calls(monkeypatch, session_resources) -> list[list[str]]:
    """What was asked of `tilt`, in place of asking it."""
    calls = []

    class Completed:
        returncode = 0

        def __init__(self, stdout: str = ""):
            self.stdout = stdout

    # What a session says about one resource when it is asked. Counted, so
    # each reading is a later one than the last: a wait watches for the work
    # a trigger asked for to have happened, and a session frozen in one
    # moment would have it wait for something that never arrives.
    deploys = itertools.count()

    def fake(argv, **kwargs):
        calls.append(argv)
        if argv[1:3] == ["get", "uiresource"] and len(argv) > 3 and argv[3] != "-o":
            return Completed(
                json.dumps(
                    {
                        "metadata": {"name": argv[3]},
                        "status": {
                            "updateStatus": "ok",
                            "runtimeStatus": "ok",
                            "lastDeployTime": f"deploy-{next(deploys)}",
                        },
                    }
                )
            )
        if argv[1:3] == ["get", "uiresource"]:
            return Completed(
                json.dumps(
                    {"items": [{"metadata": {"name": name}} for name in session_resources]}
                )
            )
        return Completed()

    monkeypatch.setattr("seal.seal.subprocess.run", fake)
    monkeypatch.setattr("seal.seal.shutil.which", lambda name: "/usr/bin/" + name)
    return calls


def test_running_an_outcome_asks_tilt_for_the_run_then_its_results(project, tilt_calls):
    """Both halves, and in that order: triggering the runner is what runs the
    outcomes, and the syncback is what brings their verdicts back to be read.
    Waiting between them is what makes those verdicts this run's -- a syncback
    fired while the tests are still running copies whatever is there."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    main(["outcomes", "run", "ui/todo-list/deleting-is-permanent"])

    assert triggered(tilt_calls) == [
        "seal_outcome_tests_ui",
        "seal_outcome_syncback_trigger_ui",
    ]
    # And each was waited for before the next thing happened: what a wait
    # does is ask the session where that resource has got to.
    asked = [
        (index, argv[3])
        for index, argv in enumerate(tilt_calls)
        if argv[1:3] == ["get", "uiresource"] and len(argv) > 3 and argv[3] != "-o"
    ]
    fired = [index for index, argv in enumerate(tilt_calls) if argv[1] == "trigger"]
    assert [name for _, name in asked if name == "seal_outcome_tests_ui"]
    assert any(index < fired[1] for index, name in asked if name == "seal_outcome_tests_ui")
    assert any(index > fired[1] for index, name in asked if name == "seal_outcome_syncback_trigger_ui")


def test_the_results_are_waited_for_and_not_only_asked_for(project, tilt_calls):
    """`tilt trigger` returns as soon as the session has accepted the request,
    so the resource that asks for the copy is finished while the copy is still
    going. What a run reads is what the copy brought back, so the copy is what
    it waits for -- reading first is reading a directory this run's verdicts
    have not reached, and reporting no verdict about tests that ran."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    main(["outcomes", "run", "ui/todo-list/deleting-is-permanent"])

    fired = [index for index, argv in enumerate(tilt_calls) if argv[1] == "trigger"]
    asked = [
        index
        for index, argv in enumerate(tilt_calls)
        if argv[1:4] == ["get", "uiresource", "seal_outcome_syncback_ui"]
    ]
    assert asked, "the copy itself was never asked about"
    assert asked[-1] > fired[-1]


def test_the_run_is_told_which_outcomes_it_covers(project, tilt_calls, monkeypatch):
    """Writing the selection *is* asking for a subset: Tilt watches that file
    and re-evaluates, so the runner is told fewer outcomes to start."""
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)
    selections = []
    original = seal.seal._select_outcomes

    def record(seal_root, slugs):
        selections.append(list(slugs))
        original(seal_root, slugs)

    monkeypatch.setattr("seal.seal._select_outcomes", record)
    main(["outcomes", "run", "ui/todo-list/deleting-is-permanent"])

    assert selections[0] == ["ui/todo-list/deleting-is-permanent"]


def test_the_selection_does_not_outlive_the_run_that_asked_for_it(project, tilt_calls):
    """Left behind, it would quietly narrow the next run somebody triggered
    from the Tilt UI -- the kind of surprise that makes a green run mean less
    than it says."""
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    main(["outcomes", "run", "ui/todo-list/deleting-is-permanent"])

    assert (project / SELECTION_FILE).read_text(encoding="utf-8") == ""


def test_the_last_run_s_verdict_is_never_read_as_this_one_s(project, tilt_calls, capsys):
    """A test that has stopped running at all is exactly when a stale verdict
    left in place would be presented as this run's -- and a pass is the
    answer it would give."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    assert main(["outcomes", "run", "ui/todo-list/deleting-is-permanent"]) == 1

    assert "no verdict" in capsys.readouterr().out


def test_no_session_to_run_against_says_so(project, monkeypatch, capsys):
    """`tilt trigger` against nothing running is the ordinary mistake here,
    and its own error says nothing about what to do."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    class Failed:
        returncode = 1

    monkeypatch.setattr("seal.seal.subprocess.run", lambda argv, **kwargs: Failed())
    monkeypatch.setattr("seal.seal.shutil.which", lambda name: "/usr/bin/" + name)

    assert main(["outcomes", "run", "ui/todo-list/deleting-is-permanent"]) == 1

    assert "seal up" in capsys.readouterr().err


# --- putting a project back before a run --------------------------------------
#
# A run measures the application plus whatever the run before it left, unless
# something puts the services that own state back to their baseline first.
# That is what `--reset` asks for, and these check who gets asked and when.

RESET_ONE = "seal_reset_example_api"
RESET_TWO = "seal_reset_billing"


def triggered(calls: list[list[str]]) -> list[str]:
    """The resources a run asked Tilt to trigger, in order."""
    return [argv[2] for argv in calls if argv[1] == "trigger"]


def test_a_reset_puts_every_service_back_before_any_outcome_runs(
    project, tilt_calls, session_resources
):
    """Every service that declares one, and all of them before the run: an
    outcome started against a half-restored environment is measuring the
    reset as much as the application."""
    session_resources += [RESET_ONE, "web", RESET_TWO]
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    main(["outcomes", "run", "--reset", "ui/todo-list/deleting-is-permanent"])

    assert triggered(tilt_calls) == [
        RESET_ONE,
        RESET_TWO,
        "seal_outcome_tests_ui",
        "seal_outcome_syncback_trigger_ui",
    ]


def test_a_wait_waits_for_what_the_trigger_asked_for(project, monkeypatch):
    """The failure this is here about: a resource that was Ready when it was
    triggered is still Ready in the moment after, so a wait satisfied by
    "Ready now" returns before the run it asked for has produced anything --
    and the promise is then reported as having left no verdict, which is the
    one thing a suite must never say by accident.

    The session below is Ready for the first two readings, busy for the next
    two, and Ready again after: a wait that returns before the busy stretch
    is over has not waited for this run.
    """
    readings = [
        {"updateStatus": "ok", "runtimeStatus": "ok", "lastDeployTime": "before"},
        {"updateStatus": "ok", "runtimeStatus": "ok", "lastDeployTime": "before"},
        {"updateStatus": "in_progress", "runtimeStatus": "pending", "lastDeployTime": "after"},
        {"updateStatus": "ok", "runtimeStatus": "pending", "lastDeployTime": "after"},
        {"updateStatus": "ok", "runtimeStatus": "ok", "lastDeployTime": "after"},
    ]
    seen = []

    def status(tilt, resource):
        seen.append(resource)
        return readings[min(len(seen) - 1, len(readings) - 1)]

    monkeypatch.setattr("seal.seal._resource_status", status)
    monkeypatch.setattr("seal.seal.time.sleep", lambda _: None)

    seal.seal._wait_for_trigger("/usr/bin/tilt", "seal_outcome_tests_ui", 60.0)

    assert len(seen) >= len(readings), (
        "the wait returned before the work it asked for had finished, after "
        f"{len(seen)} reading(s)"
    )


def test_a_wait_does_not_hang_on_a_trigger_that_changed_nothing(project, monkeypatch):
    """A trigger that re-runs something already settled never looks busy, and
    that is not a failure -- so the wait takes a settled resource at its word
    rather than waiting out its whole timeout for work nobody asked for."""
    settled = {"updateStatus": "ok", "runtimeStatus": "ok", "lastDeployTime": "unchanged"}
    monkeypatch.setattr("seal.seal._resource_status", lambda *_: settled)
    monkeypatch.setattr("seal.seal.STARTING_GRACE_SECONDS", 0.05)
    monkeypatch.setattr("seal.seal.SESSION_POLL_SECONDS", 0.01)

    seal.seal._wait_for_trigger("/usr/bin/tilt", "seal_reset_api", 60.0)


def test_a_wait_that_runs_out_says_so_and_reads_what_is_there(project, monkeypatch, capsys):
    """Running out is not fatal, for the same reason the timeouts are not:
    what a run reports is what each promise actually left behind, and a wait
    that ran out has established nothing about whether anything went wrong."""
    busy = {"updateStatus": "in_progress", "runtimeStatus": "pending", "lastDeployTime": "after"}
    monkeypatch.setattr("seal.seal._resource_status", lambda *_: busy)
    monkeypatch.setattr("seal.seal.SESSION_POLL_SECONDS", 0.01)

    seal.seal._wait_for_trigger("/usr/bin/tilt", "seal_outcome_tests_ui", 0.05)

    assert "still working" in capsys.readouterr().err


def test_each_reset_is_waited_for_rather_than_only_fired(
    project, tilt_calls, session_resources
):
    """A trigger returns as soon as Tilt has accepted it. Starting the run
    then would have the tests race the reset that is still emptying the
    database underneath them."""
    session_resources.append(RESET_ONE)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    main(["outcomes", "run", "--reset", "ui/todo-list/deleting-is-permanent"])

    asked_about = [
        argv[3]
        for argv in tilt_calls
        if argv[1:3] == ["get", "uiresource"] and len(argv) > 3 and argv[3] != "-o"
    ]
    assert asked_about and asked_about[0] == RESET_ONE


def test_only_the_resets_seal_declared_are_triggered(
    project, tilt_calls, session_resources
):
    """A project is free to name a resource of its own anything at all. What
    marks a reset as one is the `seal_reset_` a project cannot plausibly
    have written itself -- not the word 'reset' appearing somewhere."""
    session_resources += ["reset-database", "api-reset", RESET_ONE]
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    main(["outcomes", "run", "--reset", "ui/todo-list/deleting-is-permanent"])

    assert triggered(tilt_calls)[0] == RESET_ONE
    assert "reset-database" not in triggered(tilt_calls)
    assert "api-reset" not in triggered(tilt_calls)


def test_without_asking_for_one_nothing_is_reset(project, tilt_calls, session_resources):
    """The local loop is a session somebody is working in, and throwing away
    the state they were looking at because they re-ran a test is exactly what
    the reset resource is manual to avoid."""
    session_resources.append(RESET_ONE)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    main(["outcomes", "run", "ui/todo-list/deleting-is-permanent"])

    assert RESET_ONE not in triggered(tilt_calls)
    assert not [
        argv for argv in tilt_calls if argv[1:3] == ["get", "uiresource"] and argv[3] == "-o"
    ]


def test_a_project_whose_services_declare_no_reset_runs_anyway(
    project, tilt_calls, session_resources, capsys
):
    """Not an error: a project can own no state worth putting back. But it is
    said out loud, because a reset that found nothing to do and one that
    worked are otherwise the same silence."""
    session_resources.append("web")
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    main(["outcomes", "run", "--reset", "ui/todo-list/deleting-is-permanent"])

    assert triggered(tilt_calls)[0] == "seal_outcome_tests_ui"
    assert "nothing to put back" in capsys.readouterr().out


def test_which_services_were_reset_is_said_out_loud(
    project, tilt_calls, session_resources, capsys
):
    session_resources += [RESET_ONE, RESET_TWO]
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    main(["outcomes", "run", "--reset", "ui/todo-list/deleting-is-permanent"])

    printed = capsys.readouterr().out
    assert RESET_ONE in printed
    assert RESET_TWO in printed


def test_a_reset_that_fails_stops_the_run(project, monkeypatch, session_resources, capsys):
    """A red outcome against a half-reset environment reports a promise as
    broken for something the application never did -- the least useful red
    there is."""
    session_resources.append(RESET_ONE)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)
    calls = []

    class Result:
        def __init__(self, returncode: int, stdout: str = ""):
            self.returncode = returncode
            self.stdout = stdout

    def fake(argv, **kwargs):
        calls.append(argv)
        if argv[1:3] == ["get", "uiresource"]:
            return Result(0, json.dumps({"items": [{"metadata": {"name": RESET_ONE}}]}))
        return Result(1 if argv[1] == "trigger" else 0)

    monkeypatch.setattr("seal.seal.subprocess.run", fake)
    monkeypatch.setattr("seal.seal.shutil.which", lambda name: "/usr/bin/" + name)

    assert main(["outcomes", "run", "--reset", "ui/todo-list/deleting-is-permanent"]) == 1

    assert RESET_ONE in capsys.readouterr().err
    assert "seal_outcome_tests_ui" not in [
        argv[2] for argv in calls if argv[1] == "trigger"
    ]


def test_no_session_to_ask_what_it_is_running_says_so(
    project, monkeypatch, capsys
):
    """The ordinary mistake: `--reset` against nothing running. `tilt get`'s
    own error says nothing about what to do instead."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    class Failed:
        returncode = 1
        stdout = ""

    monkeypatch.setattr("seal.seal.subprocess.run", lambda argv, **kwargs: Failed())
    monkeypatch.setattr("seal.seal.shutil.which", lambda name: "/usr/bin/" + name)

    assert main(["outcomes", "run", "--reset", "ui/todo-list/deleting-is-permanent"]) == 1

    assert "seal up" in capsys.readouterr().err


def test_the_gate_s_own_form_has_nothing_to_reset(project, capsys):
    """With no slugs this reads verdicts a run already left behind and starts
    nothing, so a reset would come before nothing at all. Refused rather than
    ignored: a reset somebody believes happened is one every verdict read
    afterwards inherits."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    assert main(["outcomes", "run", "--reset"]) == 1

    assert "needs outcomes to run" in capsys.readouterr().err


# --- re-running the whole suite against a live session ------------------------
#
# The loop's per-iteration step is the whole suite, never the one test that
# was red. What `seal ci` gates on is a *reading* of verdicts a run left
# behind; these check that asking for a run is a different form saying so.


def test_all_runs_every_translated_promise_the_tree_holds(project, ran, capsys):
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)
    promise(project, "counting", "the-count-is-right", verdict=VERDICT_PASSED)

    assert main(["outcomes", "run", "--all"]) == 0

    assert ran == [
        "ui/counting/the-count-is-right",
        "ui/todo-list/a-reload-keeps-it",
        "ui/todo-list/deleting-is-permanent",
    ]


def test_all_reports_every_promise_without_a_caveat(project, ran, capsys):
    """It left nothing out, so there is nothing to disclaim -- but it says the
    run happened here, which the form a merge rests on cannot say."""
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    assert main(["outcomes", "run", "--all"]) == 0
    ran_now = capsys.readouterr().out

    assert main(["outcomes", "run"]) == 0
    read = capsys.readouterr().out

    assert "did not run" not in ran_now
    assert "2 outcome(s)" in ran_now
    assert "run just now" in ran_now
    assert "run just now" not in read


def test_all_exits_on_the_suite_s_own_verdict(project, ran):
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED)

    assert main(["outcomes", "run", "--all"]) == 1


def test_all_leaves_a_promise_with_no_test_yet_alone(project, ran, capsys):
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "nothing-written-yet", translated=False)

    assert main(["outcomes", "run", "--all"]) == 0

    assert ran == ["ui/todo-list/a-reload-keeps-it"]
    assert "no test yet" in capsys.readouterr().out


def test_all_and_naming_outcomes_are_different_asks(project, ran, capsys):
    """No reading of the pair that isn't a guess, and one of the two guesses
    reports a subset under a flag that says otherwise."""
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    assert main(["outcomes", "run", "--all", "ui/todo-list/a-reload-keeps-it"]) == 1

    assert ran == []
    assert "not both" in capsys.readouterr().err


def test_the_form_a_merge_rests_on_still_starts_nothing(project, tilt_calls):
    """The regression guard on the gate's own command: `seal ci` invokes this
    after Tilt has run the suite, and a form that started containers of its
    own would make it mean something different depending on when it ran."""
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)

    assert main(["outcomes", "run"]) == 0

    assert tilt_calls == []


def test_all_goes_through_the_resources_a_full_run_uses(project, tilt_calls):
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)

    main(["outcomes", "run", "--all"])

    assert triggered(tilt_calls) == [
        "seal_outcome_tests_ui",
        "seal_outcome_syncback_trigger_ui",
    ]


def test_all_composes_with_a_reset(project, tilt_calls, session_resources):
    """What a loop iteration actually asks for: every promise, from a known
    baseline."""
    session_resources.append(RESET_ONE)
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)

    main(["outcomes", "run", "--reset", "--all"])

    assert triggered(tilt_calls)[0] == RESET_ONE


def test_all_does_not_leave_the_next_run_narrowed(project, tilt_calls):
    """Every outcome is named in the selection while the run is in flight, and
    the file is emptied afterwards like any other run's -- left behind, it
    would narrow the next run somebody triggered from the Tilt UI to a tree
    that may since have grown."""
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)

    main(["outcomes", "run", "--all"])

    assert (project / SELECTION_FILE).read_text(encoding="utf-8") == ""


# --- confirming a failure before anything acts on it --------------------------
#
# A promise that failed once has not necessarily stopped being kept: the most
# flake-prone class of test a project owns is also the one whose failures cost
# the most to chase. These check who gets re-run, from what, and what the two
# results say together.


@pytest.fixture
def again(monkeypatch):
    """Stands in for running outcomes. Records every run, and from the second
    run of a given outcome onwards leaves whatever verdict `leaves` says a
    confirmation found -- which is what `--confirm` reads back."""
    runs: list[tuple[str, bool]] = []
    leaves: dict[str, str] = {}

    def fake(tilt, seal_root, outcomes, results_root, reset=False):
        for outcome in outcomes:
            runs.append((outcome.slug, reset))
            if sum(1 for slug, _ in runs if slug == outcome.slug) < 2:
                continue  # the first run leaves whatever the test seeded
            directory = results_dir_for(results_root, outcome)
            shutil.rmtree(directory, ignore_errors=True)
            if outcome.slug in leaves:
                write(directory / VERDICT_FILENAME, leaves[outcome.slug])

    monkeypatch.setattr("seal.seal._run_outcomes", fake)
    monkeypatch.setattr("seal.seal.shutil.which", lambda name: "/usr/bin/" + name)
    return SimpleNamespace(runs=runs, leaves=leaves)


def test_a_failure_that_fails_again_alone_is_confirmed(project, again, capsys):
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED)
    again.leaves["ui/todo-list/deleting-is-permanent"] = VERDICT_FAILED

    assert main(["outcomes", "run", "--all", "--confirm"]) == 1

    assert "FAIL (confirmed)" in capsys.readouterr().out


def test_a_failure_that_holds_alone_is_not_confirmed(project, again, capsys):
    """Not a pass either. The suite did not see this promise kept, and a run
    that went green because a red test passed the second time is the
    retry-until-green this layer exists to refuse."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED)
    again.leaves["ui/todo-list/deleting-is-permanent"] = VERDICT_PASSED

    assert main(["outcomes", "run", "--all", "--confirm"]) == 1

    printed = capsys.readouterr()
    assert "FAIL (not confirmed)" in printed.out
    assert "PASS " not in printed.out
    assert "does not own the data" in printed.err


def test_a_promise_that_leaves_no_verdict_again_is_confirmed(project, again, capsys):
    """Nothing here knows the test ran, twice over. That is exactly what a
    green suite must never be able to claim on a promise's behalf."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=None)

    assert main(["outcomes", "run", "--all", "--confirm"]) == 1

    assert "no verdict (confirmed)" in capsys.readouterr().out


def test_a_confirmation_runs_the_promise_alone_from_a_reset(project, again):
    """Both halves matter. Retried in place, a failure is retried against the
    state that may have caused it; run alongside the others, it is run against
    what they are doing to the same application."""
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED)
    again.leaves["ui/todo-list/deleting-is-permanent"] = VERDICT_FAILED

    main(["outcomes", "run", "--all", "--confirm"])

    assert again.runs[-1] == ("ui/todo-list/deleting-is-permanent", True)


def test_only_what_was_red_is_run_again(project, again):
    """A confirmation costs a whole run each, and a promise that held has
    nothing to reproduce."""
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED)
    again.leaves["ui/todo-list/deleting-is-permanent"] = VERDICT_FAILED

    main(["outcomes", "run", "--all", "--confirm"])

    reran = [slug for slug, _ in again.runs[2:]]
    assert reran == ["ui/todo-list/deleting-is-permanent"]


def test_a_failure_is_run_again_once_not_until_it_passes(project, again):
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED)
    again.leaves["ui/todo-list/deleting-is-permanent"] = VERDICT_FAILED

    main(["outcomes", "run", "--all", "--confirm"])

    assert len(again.runs) == 2


def test_the_run_that_failed_is_kept_beside_the_one_that_held(project, again, capsys):
    """Answering 'did this reproduce?' by writing over what happened the first
    time leaves the interesting case with nothing to compare."""
    outcome = promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED)
    again.leaves["ui/todo-list/deleting-is-permanent"] = VERDICT_PASSED
    results = (
        project / DEFAULT_RESULTS_DIR_NAME / OUTCOMES_RESULTS_SUBDIR / GROUP
        / "todo-list" / "deleting-is-permanent"
    )
    write(results / "log.txt", "the first run's log\n")

    main(["outcomes", "run", "--all", "--confirm"])

    kept = results.with_name(results.name + FIRST_RUN_SUFFIX)
    assert kept.is_dir()
    assert (kept / "log.txt").read_text(encoding="utf-8") == "the first run's log\n"
    assert (kept / VERDICT_FILENAME).read_text(encoding="utf-8").strip() == VERDICT_FAILED
    assert str(kept.relative_to(project)) in capsys.readouterr().err
    assert outcome.is_dir()


def test_nothing_is_confirmed_where_nothing_failed(project, again, capsys):
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)

    assert main(["outcomes", "run", "--all", "--confirm"]) == 0

    assert len(again.runs) == 1
    assert "(" not in capsys.readouterr().out.splitlines()[0]


def test_confirming_one_named_outcome_works_the_same_way(project, again, capsys):
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED)
    again.leaves["ui/todo-list/deleting-is-permanent"] = VERDICT_FAILED

    assert main(["outcomes", "run", "--confirm", "ui/todo-list/deleting-is-permanent"]) == 1

    assert "FAIL (confirmed)" in capsys.readouterr().out


def test_the_gate_s_own_form_has_nothing_to_confirm(project, capsys):
    """It reads verdicts a run already left behind, so there is no run for a
    confirmation to follow."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED)

    assert main(["outcomes", "run", "--confirm"]) == 1

    assert "--confirm needs outcomes to run" in capsys.readouterr().err


# --- quarantine, and the record a flake rate is read from ---------------------
#
# A promise whose test is being made deterministic shouldn't block every merge
# in the meantime, and the pattern that says one needs to be lives across runs
# rather than in any of them.


def quarantine(outcome_dir: Path, reason: str = "the selector races the render.") -> Path:
    """Declare this outcome quarantined, and hand back its directory."""
    write(outcome_dir / QUARANTINE_FILENAME, reason + "\n")
    return outcome_dir


def test_a_quarantined_promise_that_fails_does_not_fail_the_run(project, capsys):
    quarantine(promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED))

    assert main(["outcomes", "run"]) == 0


def test_a_quarantined_failure_is_never_reported_as_passed(project, capsys):
    """The whole gate rests on a green suite being a claim about promises that
    were kept. Excusing one from failing the run is not the same as saying it
    held, and the listing has to keep those apart."""
    quarantine(promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED))

    main(["outcomes", "run"])
    printed = capsys.readouterr().out

    assert "FAIL (quarantined)" in printed
    assert "1 failed" in printed
    assert "quarantined, so a failure there did not fail this run" in printed


def test_a_quarantined_promise_says_why_it_is_one(project, capsys):
    quarantine(
        promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED),
        "the delete button races the list re-render; being made to wait on state.",
    )

    main(["outcomes", "run"])

    assert "races the list re-render" in capsys.readouterr().out


def test_a_quarantined_promise_that_holds_is_reported_as_holding(project, capsys):
    """The state is a declaration about how a failure is treated, not a claim
    about the verdict."""
    quarantine(promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED))

    assert main(["outcomes", "run"]) == 0

    assert "PASS (quarantined)" in capsys.readouterr().out


def test_quarantining_does_not_hide_a_promise_that_is_still_red_elsewhere(project):
    quarantine(promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED))
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_FAILED)

    assert main(["outcomes", "run"]) == 1


def test_a_quarantine_note_is_not_a_translation(project, capsys):
    """A note about a test is not a thing that runs. Counted as one, a promise
    carrying nothing but a quarantine would read as translated -- and be
    reported as a test that left no verdict, which is a failure."""
    quarantine(promise(project, "todo-list", "nothing-written-yet", translated=False))

    assert main(["outcomes", "run"]) == 0

    assert "no test yet" in capsys.readouterr().out


def test_a_quarantine_with_no_reason_is_refused(project, capsys):
    """Indistinguishable from a test somebody switched off, and the code owner
    approving the diff is the person who has to tell them apart."""
    quarantine(promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED), "")

    assert main(["check"]) == 1

    assert "quarantined with no reason" in capsys.readouterr().err


def test_a_quarantine_needs_no_codeowners_rule_of_its_own(project):
    """The entire reason it lives in the outcome's directory: whatever rule
    already covers the tree covers this, so an agent cannot quarantine its way
    to green any more than it can edit the test."""
    outcome = quarantine(
        promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)
    )
    write(project / "CODEOWNERS", "/outcomes/ @a-team\n")

    assert main(["check"]) == 0
    assert (outcome / QUARANTINE_FILENAME).is_file()


def test_a_run_records_what_it_found(project):
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    main(["outcomes", "run"])

    assert recorded_verdicts(project) == {"ui/todo-list/deleting-is-permanent": ["PASS"]}


def test_the_record_is_appended_to_rather_than_replaced(project):
    outcome = promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)
    main(["outcomes", "run"])
    write(
        project / DEFAULT_RESULTS_DIR_NAME / OUTCOMES_RESULTS_SUBDIR / GROUP / "todo-list"
        / "deleting-is-permanent" / VERDICT_FILENAME,
        VERDICT_FAILED,
    )

    main(["outcomes", "run"])

    assert recorded_verdicts(project) == {
        "ui/todo-list/deleting-is-permanent": ["PASS", "FAIL"]
    }
    assert outcome.is_dir()


def test_a_run_of_the_whole_suite_records_itself_as_one(project):
    """What a run covered is written down rather than worked out later: a
    read cannot tell a subset that named every outcome from a run of the
    suite, and only one of the two is a round of a regression loop."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    main(["outcomes", "run"])

    assert [entry[SCOPE_KEY] for entry in recorded_entries(project)] == [SCOPE_TREE]


def test_a_run_of_named_outcomes_records_itself_as_a_selection(project, tilt_calls):
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    main(["outcomes", "run", "ui/todo-list/deleting-is-permanent"])

    assert [entry[SCOPE_KEY] for entry in recorded_entries(project)] == [SCOPE_SELECTION]


def test_two_runs_of_the_suite_are_two_runs_in_the_record(project):
    """Every entry of one run carries the same identity, and no entry of the
    next carries it -- which is the whole of how a flat list of outcomes is
    read back as rounds."""
    promise(project, "todo-list", "a-reload-keeps-it", verdict=VERDICT_PASSED)
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)

    main(["outcomes", "run"])
    main(["outcomes", "run"])

    runs = [entry[RUN_KEY] for entry in recorded_entries(project)]
    assert len(set(runs)) == 2
    assert runs[0] == runs[1] and runs[2] == runs[3]
    assert [read.states for read in recorded_runs(project)] == [
        {"ui/todo-list/a-reload-keeps-it": "PASS", "ui/todo-list/deleting-is-permanent": "PASS"}
    ] * 2


def test_a_promise_that_keeps_changing_its_mind_is_named(project, capsys):
    """A test that fails one run in four looks perfectly ordinary in any one
    of them. The pattern lives across runs, which is what the record is for."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)
    results = (
        project / DEFAULT_RESULTS_DIR_NAME / OUTCOMES_RESULTS_SUBDIR / GROUP / "todo-list"
        / "deleting-is-permanent" / VERDICT_FILENAME
    )
    for verdict in (VERDICT_FAILED, VERDICT_PASSED, VERDICT_FAILED):
        main(["outcomes", "run"])
        write(results, verdict)
    main(["outcomes", "run"])
    capsys.readouterr()

    assert main(["outcomes"]) == 0

    printed = capsys.readouterr().out
    assert "Changing their mind" in printed
    assert "3 change(s) of verdict in 4 run(s)" in printed


def test_a_promise_with_a_steady_record_is_not_named(project, capsys):
    """Most of a tree is this. A note beside every outcome saying it is fine
    is a note nobody reads."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)
    main(["outcomes", "run"])
    main(["outcomes", "run"])
    capsys.readouterr()

    main(["outcomes"])

    assert "Changing their mind" not in capsys.readouterr().out


# --- a run that is a round of a loop that should stop -------------------------
#
# A loop is rounds of the whole suite, so this is where a run finds out it is
# part of one that has a reason to stop -- in the round it happened, rather
# than from somebody thinking to ask afterwards.


def failing_rounds(project: Path, rounds: int, **limits) -> None:
    """`rounds` runs of a suite whose one promise is red: enough to reach a
    backstop, with nothing ever fixed and so no cycle to reach it first."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_FAILED)
    if limits:
        declare_loop(project, **limits)
    for _ in range(rounds):
        main(["outcomes", "run"])


def test_a_round_of_a_loop_that_should_stop_says_so(project, capsys):
    failing_rounds(project, 1, max_iterations=2)
    capsys.readouterr()

    assert main(["outcomes", "run"]) == 1

    printed = capsys.readouterr().err
    assert "At the backstop" in printed
    assert "broke  ui/todo-list/deleting-is-permanent" in printed, (
        "the round that says to stop does not carry the sequence to stop over"
    )
    assert "seal-loop-triager" in printed


def test_a_round_of_a_loop_that_is_getting_somewhere_says_nothing_extra(project, capsys):
    """Most red runs are one of those, and a note under every one of them is
    a note people stop reading."""
    failing_rounds(project, 1)
    capsys.readouterr()

    assert main(["outcomes", "run"]) == 1

    assert "At the backstop" not in capsys.readouterr().err


def test_a_run_naming_outcomes_is_a_round_of_nothing(project, capsys, tilt_calls):
    """It says nothing about the promises it left out, so it cannot be one."""
    failing_rounds(project, 2, max_iterations=1)
    capsys.readouterr()

    main(["outcomes", "run", "ui/todo-list/deleting-is-permanent"])

    assert "At the backstop" not in capsys.readouterr().err


def test_a_green_run_is_not_part_of_a_loop_however_the_record_reads(project, capsys):
    """Green ends a loop, which is the way loops are meant to end."""
    failing_rounds(project, 2, max_iterations=1)
    write(
        project / DEFAULT_RESULTS_DIR_NAME / OUTCOMES_RESULTS_SUBDIR / GROUP / "todo-list"
        / "deleting-is-permanent" / VERDICT_FILENAME,
        VERDICT_PASSED,
    )
    capsys.readouterr()

    assert main(["outcomes", "run"]) == 0

    assert "At the backstop" not in capsys.readouterr().err


def test_the_listing_names_what_is_quarantined(project, capsys):
    quarantine(
        promise(project, "todo-list", "deleting-is-permanent"),
        "the delete button races the list re-render.",
    )

    main(["outcomes"])

    printed = capsys.readouterr().out
    assert "Quarantined" in printed
    assert "races the list re-render" in printed


def test_a_truncated_record_still_reads(project, capsys):
    """An append-only log on somebody's own machine is exactly the kind of
    file that ends up with half a last line. A listing that refused to print
    because of one would be the worse tool."""
    promise(project, "todo-list", "deleting-is-permanent", verdict=VERDICT_PASSED)
    main(["outcomes", "run"])
    history = project / HISTORY_FILE
    history.write_text(history.read_text(encoding="utf-8") + '{"outcome": "ui/', encoding="utf-8")

    assert main(["outcomes"]) == 0
    assert recorded_verdicts(project) == {"ui/todo-list/deleting-is-permanent": ["PASS"]}
