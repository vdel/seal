"""What a regression loop has been doing, read from the record its runs left
behind.

The loop is an agent's (see /rfcs/0013-regression-loop.md): fix the
application, re-run the whole suite, repeat against whatever is still red.
Coupled promises don't always resolve monotonically -- fixing A can break B,
and fixing B can re-break A -- and a loop like that has no guaranteed
termination. What this module answers is the question that loop cannot ask
about itself: what has been breaking and what has been fixed, round by round,
and whether it is going in circles.

**A loop's boundary is derived, not declared.** It is the run of consecutive
whole-suite iterations back to the last all-green one, and if the newest
iteration was all-green there is no loop in progress. Nothing starts a loop
and nothing finishes one. The alternative -- an id a session carries, or a
`loop start` it is asked to run -- makes the record depend on the bookkeeping
of the session that is thrashing, which is the same session the design gives
no say in triage precisely because it has committed to a narrative about
which promise is at fault.

**A cycle is a promise fixed and then re-broken inside one loop.** That is a
signal on its own, independent of how many rounds have gone by: two
iterations can establish it. It does not catch the other shape a stuck loop
takes -- every round breaking something never seen before, no repeat and no
convergence either -- which is what a cap is for (see runners.py).

**Nothing here concludes anything.** A sequence is evidence, exactly as a
flip rate is. Which promise is stale, and whether the application should be
able to keep all of them at once, is a judgement a fresh-context agent makes
and a code owner approves -- and neither of them is a verdict this module is
in a position to reach from a log.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from seal.outcome_history import Run
from seal.outcome_suite import FAILED, NO_VERDICT
from seal.runners import Limits

# What counts as a promise this run did not see kept -- the same pair
# OutcomeResult.is_failure treats as a reason the suite is red. A test that
# left no verdict is red rather than absent: nothing knows it ran, which is
# exactly what a green suite must never be able to claim on its behalf.
#
# A quarantined promise is not red here, which is the same answer the run
# itself gave: a failure there did not fail it. A loop is what a red suite is
# in, so a promise the suite has been told not to gate on cannot be what
# holds one open -- and a quarantine, which is a code owner's decision about
# a test whose determinism somebody is fixing, would otherwise put a project
# in a loop that no application fix can ever end.
RED_STATES = (FAILED, NO_VERDICT)


def _red(run: Run) -> frozenset[str]:
    return frozenset(
        slug
        for slug, state in run.states.items()
        if state in RED_STATES and slug not in run.quarantined
    )


@dataclass(frozen=True)
class Step:
    """One iteration of the loop, and what changed in it."""

    at: datetime
    broke: tuple[str, ...]
    """Red now, and not red at the end of the iteration before -- so, for the
    first iteration of a loop, everything that was found red."""
    fixed: tuple[str, ...]
    """Red at the end of the iteration before, and not red now."""
    red: tuple[str, ...]
    """Every promise still red when this iteration finished."""


@dataclass(frozen=True)
class Loop:
    """The loop in progress, or an empty one where the suite is green."""

    steps: tuple[Step, ...]

    @property
    def in_progress(self) -> bool:
        return bool(self.steps)

    @property
    def iterations(self) -> int:
        return len(self.steps)

    @property
    def elapsed(self) -> timedelta:
        """How long this loop has spent iterating: its first round to its
        last.

        Not "since it started", which would be the same number plus however
        long the machine has been idle. A loop nobody has run since yesterday
        has not been looping since yesterday, and a cap it tripped by being
        left alone overnight would be a cap on wall-clock rather than on the
        loop.
        """
        if not self.steps:
            return timedelta()
        return self.steps[-1].at - self.steps[0].at

    @property
    def red(self) -> tuple[str, ...]:
        """What is still red as of the last iteration."""
        return self.steps[-1].red if self.steps else ()

    @property
    def cycles(self) -> tuple[str, ...]:
        """Every promise this loop fixed and then broke again, in the order
        they were re-broken.

        Within the loop and no further. A promise re-broken either side of a
        green run belongs to two different loops, and reading that as a cycle
        would make any long enough record look like one.
        """
        fixed: set[str] = set()
        cycling: list[str] = []
        for step in self.steps:
            for slug in step.broke:
                if slug in fixed and slug not in cycling:
                    cycling.append(slug)
            fixed.update(step.fixed)
        return tuple(cycling)


def loop(runs: list[Run]) -> Loop:
    """The loop the suite is in, from every whole-suite run recorded.

    The runs after the last all-green one. A green newest run means the loop
    ended the way loops are meant to, and an empty Loop is what says so -- a
    record with nothing in it and a project whose suite is passing are the
    same state as far as thrash detection goes, which is: nothing to detect.
    """
    started = 0
    for index, run in enumerate(runs):
        if not _red(run):
            started = index + 1
    if started >= len(runs):
        return Loop(steps=())

    steps = []
    # Nothing was red before the loop's first iteration: it either follows a
    # run in which every promise held, or it is the first run in the record.
    # So everything that round found red is something that broke in it, which
    # is what makes the first step read like every other one.
    before: frozenset[str] = frozenset()
    for run in runs[started:]:
        red = _red(run)
        steps.append(
            Step(
                at=run.at,
                broke=tuple(sorted(red - before)),
                fixed=tuple(sorted(before - red)),
                red=tuple(sorted(red)),
            )
        )
        before = red
    return Loop(steps=tuple(steps))


# Why a loop should stop, where it should. Named rather than reported as a
# sentence, because two callers say it differently: a run mentions it in
# passing and `seal outcomes loop` builds a report around it.
CYCLE = "cycle"
ITERATION_CAP = "iterations"
TIME_CAP = "time"


def reached(loop: Loop, limits: Limits) -> tuple[str, ...]:
    """Which of a project's declared limits this loop has reached, in the
    order they are declared -- empty where it has reached neither.

    Both are backstops, and reaching one changes nothing about any promise's
    verdict. An unresolved loop cannot merge anyway: the suite is still red,
    and every outcome test green is already the merge's precondition. What a
    cap buys is that the state gets surfaced with a reason attached instead
    of being retried forever, which is a quality of the report rather than of
    the gate.
    """
    if not loop.in_progress:
        return ()
    return tuple(
        name
        for name, over in (
            (ITERATION_CAP, loop.iterations >= limits.max_iterations),
            (TIME_CAP, loop.elapsed >= timedelta(minutes=limits.max_minutes)),
        )
        if over
    )


def stops(current: Loop, limits: Limits) -> tuple[str, ...]:
    """Every reason this loop has to stop, empty where it has none.

    The two are not the same kind of evidence and neither subsumes the
    other. A cycle is a fact about what the loop has already done -- keeping
    one promise is breaking another, and two rounds can establish it. A cap
    is a fact about how long it has been at it, which is what catches the
    loop that repeats nothing and converges on nothing either.
    """
    return ((CYCLE,) if current.cycles else ()) + reached(current, limits)
