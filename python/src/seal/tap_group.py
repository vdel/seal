"""Starting a group on the machine, and writing down what it said.

A `tap` group is not deployed. seal starts the executable at the
group's root once, with the outcomes it has to cover, and reads its verdicts
off the stream it prints (see /rfcs/0014-seal-on-seal.md). That
is what lets a promise about the layer *beneath* a session be tested at all:
nothing running inside a session can answer whether `seal up` brings
that session up.

What it writes is exactly what a container runner's results syncing back
would have left -- a verdict file per outcome, under that outcome's own
directory. Everything downstream reads that tree and nothing else, so the
report, quarantine, the history, `--confirm` and the regression loop all
work on a `tap` group without knowing one exists.

The care in here is all about one distinction: a promise this run saw
broken, and a promise this run never reached. A runner that dies after the
third of twenty has said nothing about the other seventeen, and a suite that
recorded seventeen failures would be inventing them. So a verdict is written
only where a point was actually reported, and everything else is left absent
-- which is what the suite already reports as no verdict.
"""

import os
import subprocess
from pathlib import Path

from seal import tap
from seal.credentials import SealError
from seal.outcome_suite import (
    OUTCOMES_RESULTS_SUBDIR,
    VERDICT_FAILED,
    VERDICT_FILENAME,
    VERDICT_PASSED,
    results_dir_for,
)
from seal.outcomes import Outcome
from seal.runners import ARGUMENT_SEPARATOR, Runner, TAP_RUNNER_FILENAME

# What the whole run printed, kept once for the group rather than copied
# under every outcome. An outcome's own directory holds the account of that
# promise; this is the account of the run, including everything printed
# before the first point and after the last.
RUN_LOG_FILENAME = "run.log"

# What a single outcome's directory keeps of the stream: whatever the runner
# printed under that point. The same name a container runner's own loop
# writes, so a failing promise's report points somebody at the same file
# whichever kind of group it was in.
OUTCOME_LOG_FILENAME = "log.txt"


def runner_path(outcomes_dir: Path, group: str) -> Path:
    """What starts this group, wherever the tree is."""
    return outcomes_dir / group / TAP_RUNNER_FILENAME


def _arguments(runner: Runner, slugs: list[str]) -> list[str]:
    """What the runner is started with: its own words, then `--`, then one
    outcome per argument.

    The same shape a container runner is given, and for the same two reasons
    (see /rfcs/0011-outcome-runners.md). Outcomes are named from inside the
    group, because a runner is built from one group and never has to know the
    others exist. And they are named explicitly, because seal knows
    which promises have been translated and the runner does not -- one
    resolving "everything here" for itself would start promises nobody has
    written a test for and report them failed.
    """
    return [*runner.runner_args, ARGUMENT_SEPARATOR, *slugs]


def _start(executable: Path, arguments: list[str], cwd: Path) -> tuple[str, int]:
    """Run it, showing what it prints and keeping a copy.

    Shown as it arrives because it is progress on somebody's own test, and a
    slow run and a hung one are otherwise the same silence. Kept because it
    is the only account of why a promise was not kept.

    stderr is folded into stdout rather than read separately: a runner that
    interleaves the two is describing one sequence of events, and two pipes
    read at different speeds would put a failure's explanation somewhere
    other than under the failure.
    """
    process = subprocess.Popen(
        [str(executable), *arguments],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    captured: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        captured.append(line)
    return "".join(captured), process.wait()


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def run(
    runner: Runner,
    outcomes: list[Outcome],
    seal_root: Path,
    outcomes_dir: Path,
    results_root: Path,
) -> list[str]:
    """Start this group's runner once, and write a verdict for every promise
    it reported on. Returns what was wrong with the *run* -- not with the
    promises, which the verdicts carry.

    Started from the project root, with the environment it was invoked in and
    nothing added. A `tap` runner is a program on this machine: it has the
    checkout, the CLI and whatever the caller's shell had, which is the whole
    reason this kind of group exists.
    """
    executable = runner_path(outcomes_dir, runner.name)
    if not executable.is_file():
        raise SealError(
            f"Error: {runner.name} is a '{runner.runner_type}' group and there is no "
            f"{executable} to start. `seal check` refuses a tree in this state -- "
            "see /docs/guides/runners.md."
        )
    if not os.access(executable, os.X_OK):
        raise SealError(
            f"Error: {executable} is what starts this group and is not executable. "
            "`chmod +x` it, and commit that."
        )

    wanted = {f"{outcome.epic}/{outcome.name}": outcome for outcome in outcomes}
    output, exit_code = _start(
        executable, _arguments(runner, list(wanted)), seal_root
    )
    _write(
        results_root / OUTCOMES_RESULTS_SUBDIR / runner.name / RUN_LOG_FILENAME,
        output,
    )

    report = tap.read(output)
    problems: list[str] = []

    for point in report.points:
        outcome = wanted.get(point.description)
        if outcome is None:
            # Filed under nothing: a point naming a promise this run did not
            # ask about is a runner and a tree that disagree, and inventing a
            # directory for it would put a verdict where nothing looks.
            problems.append(
                f"reported '{point.description}', which is not one of the outcomes it "
                "was given. A runner is told exactly which promises to cover, and "
                "names them back as it was given them."
            )
            continue
        directory = results_dir_for(results_root, outcome)
        if point.diagnostics:
            _write(directory / OUTCOME_LOG_FILENAME, "".join(point.diagnostics))
        if not point.established_something:
            # A skipped point is written `ok` by convention and established
            # nothing. Left with no verdict rather than recorded as a pass:
            # a test that did not run is exactly what a green suite must not
            # be able to claim on a promise's behalf.
            continue
        _write(
            directory / VERDICT_FILENAME,
            VERDICT_PASSED if point.ok else VERDICT_FAILED,
        )

    for name in report.duplicated():
        problems.append(
            f"reported '{name}' more than once. One promise, one verdict -- the last "
            "of them is what this run recorded."
        )

    if report.bailed_out is not None:
        because = f": {report.bailed_out}" if report.bailed_out else ""
        problems.append(
            f"stopped before it had finished{because}. Every promise it had not "
            "reported on is left with no verdict, which is what it is -- nothing "
            "here tested them."
        )
    elif exit_code != 0:
        # Not a failure of any promise. A runner is allowed to exit however
        # it likes -- the stream is the whole of what it says -- but an exit
        # nobody asked for is worth reporting beside the verdicts it did
        # leave, since the promises it never reached have none.
        problems.append(
            f"exited {exit_code}. Its points are read either way; a promise it never "
            "reported on is left with no verdict."
        )

    return problems
