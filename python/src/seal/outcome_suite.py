"""Running a project's outcome suite, and saying what it found.

An outcome test is a container (see outcomes.py): it drives the running
environment from inside the cluster and leaves a verdict behind in its own
results directory, which reaches the project as `tests-results/outcomes/
<epic>/<outcome>/` -- beside where each service's own test results already
land (see /rfcs/0005-service-tests.md).

This module reads every one of those verdicts at once, which is the whole
point of the suite existing. A fix scoped to the one test somebody was
looking at can break another that nobody re-ran, so what has to be reportable
is "every promise this project has translated still holds", not "the test I
was looking at passed". That distinction is the merge gate's precondition:
see /rfcs/0009-outcome-tests.md.

Three consequences shape what is below.

Every outcome is reported, always. A listing that leaves one out is
indistinguishable from one where it passed.

A translated outcome that left no verdict is a failure, not a gap. A test
that did not run is exactly what a green suite must not be able to claim,
and the ways one silently fails to run -- an image that never started, a
container killed before it wrote anything -- all look like an absent file
from here.

A promise with no test yet is neither. It is an ordinary state a project
sits in (see /rfcs/0010-outcome-tree.md), so it appears in the listing and in the
summary and does not fail the run: there is nothing to satisfy.

Selecting outcomes by name is the one thing that reports fewer than all of
them, and it exists for the person iterating on a translation rather than
for the gate -- paying for the other twenty on every edit is how a local
loop stops being used. What it must never produce is output readable as the
suite's own, so a subset counts what ran against how many the tree declares
and says what it left out (see summary() below, and `seal outcomes run` in
seal.py).
"""

from dataclasses import dataclass
from pathlib import Path

from seal.outcomes import Outcome, discover_outcomes

# Where results reach the project from the cluster. The same directory each
# service's own junit/coverage output already syncs back to, so one artifact
# carries both and neither has a second convention to learn.
DEFAULT_RESULTS_DIR_NAME = "tests-results"

# Outcome results are filed under their own subdirectory of it, by slug: an
# outcome is not a service, and its results have to be reachable by the same
# `<group>/<epic>/<outcome>` identifier the tree, the reports and CODEOWNERS
# all use.
OUTCOMES_RESULTS_SUBDIR = "outcomes"

# What an outcome's container writes its verdict to, and the two values it
# can hold. One container answers for several promises, so each verdict is a
# file of its own rather than a report of the whole run -- which is what
# separates this from how a service's own tests are read (see junit.py).
VERDICT_FILENAME = "passed"
VERDICT_PASSED = "1"
VERDICT_FAILED = "0"

# What each state is called in a report. These are the strings a person
# reads, so they say what happened rather than encoding it: "no verdict" is
# not a kind of failure to skim past, it is a test that did not run.
PASSED = "PASS"
FAILED = "FAIL"
NO_VERDICT = "no verdict"
UNTRANSLATED = "no test yet"

# What a second run of a failing promise found, where one was asked for. A
# failure re-run on its own from a reset environment either reproduces or it
# doesn't, and the difference is what separates a promise the application has
# stopped keeping from a test that isn't deterministic -- which are fixed in
# different places, by different people, and only one of them is worth an
# agent session against the application.
#
# "not confirmed" rather than "flaky": what a single non-reproduction
# establishes is that it didn't reproduce, and calling that flakiness is a
# conclusion about a cause nobody has looked for. A test that doesn't own the
# data it asserts on fails in the suite and passes alone every single time,
# which is not flaky at all.
CONFIRMED = "confirmed"
UNCONFIRMED = "not confirmed"

# What a quarantined outcome's line says about itself. The verdict stays what
# it was -- a quarantine is a declaration about how a failure is treated, not
# a claim about whether the promise held -- so this qualifies the state
# alongside a confirmation rather than replacing it.
QUARANTINED = "quarantined"

# Where the first run's results are kept while a confirmation re-run writes
# its own. An outcome's own directory is what a report points somebody at, and
# a confirmation that overwrote it would answer "did this reproduce?" by
# destroying the evidence of what happened the first time. A slug is lowercase
# letters, digits and single hyphens (see /rfcs/0010-outcome-tree.md), so a
# suffix with a dot in it can never collide with a real outcome's directory.
FIRST_RUN_SUFFIX = ".first-run"

# The Tilt resources a run goes through, spelled the way
# tilt/seal/outcomes.Tiltfile spells them (see
# tilt/seal/resources.Tiltfile).
# One set per group, because one image and one container answer for a
# group's promises and a project has as many of those as it has runners.
#
# The trigger and the copy are separate resources because they do separate
# things: `tilt trigger` returns once the session has accepted the request,
# so the resource that asks for the copy is finished while the copy is still
# going. A run reads what the copy brought back, so it is the copy it has to
# see finish.
#
# Nothing checks a resource name before triggering it, and Tilt is content to
# be asked about one that does not exist. A name here that disagreed with the
# Tiltfile's would run nothing, wait for nothing, and leave the last run's
# verdicts to be read as this one's -- so one test pins every one of them
# against a real evaluated project
# (python/tests/test_seal_tilt_resources.py).
RUN_PURPOSE = "outcome_tests"
SYNCBACK_TRIGGER_PURPOSE = "outcome_syncback_trigger"
SYNCBACK_PURPOSE = "outcome_syncback"


# What marks a resource as seal's, in the flat namespace it shares with a
# project's own -- tilt/seal/resources.Tiltfile's SEAL_RESOURCE_PREFIX.
SEAL_RESOURCE_PREFIX = "seal_"


def resource_name(purpose: str, subject: str) -> str:
    """One of seal's Tilt resources, named the way
    tilt/seal/resources.Tiltfile names everything seal declares: the marker,
    the purpose, then what it belongs to. Underscores throughout, hyphens in
    a group or service name included -- these are Tilt resources rather than
    Kubernetes objects, and one separator makes the whole name read as a
    single token."""
    return f"{SEAL_RESOURCE_PREFIX}{purpose}_{subject.replace('-', '_')}"


# A service's reset, as tilt/seal/build.Tiltfile registers it: the resource
# that puts that service's data back to its baseline. The name is the whole
# contract (see /rfcs/0002-declaration-by-structure.md) -- which is what lets a run find
# every reset a session declares without a registry of them to consult, and
# without seal knowing a project's services at all.
RESET_PURPOSE = "reset"
RESET_RESOURCE_PREFIX = f"{SEAL_RESOURCE_PREFIX}{RESET_PURPOSE}_"


def reset_resources(declared: list[str]) -> list[str]:
    """Every reset among the resources a session declares, in that session's
    own order.

    Matched by prefix rather than derived from a list of services, because
    which services declared a reset is something only the evaluated Tiltfile
    knows: `seal_service(reset=...)` registers one and a service without the
    argument gets none, so a name built from a service list would name
    resources that are not there.
    """
    return [name for name in declared if name.startswith(RESET_RESOURCE_PREFIX)]

# Where `seal outcomes run <slug>...` says which outcomes a run covers. Tilt
# watches this file and re-evaluates when it changes, which is what narrows a
# run without restarting the session; the same path is spelled in
# tilt/seal/outcomes.Tiltfile, and the test above pins them together.
#
# An empty file is the whole tree, which is what `seal ci` runs.
SELECTION_FILE = Path(".workspace") / "seal" / "outcomes-selection"


def results_dir_for(results_root: Path, outcome: Outcome) -> Path:
    """Where this outcome's container's results land, named by the same slug
    the tree spells out.

    The group is seal's half of that path rather than the runner's. A runner
    is built from one group and reports into `<epic>/<outcome>`, knowing
    nothing about the others; what keeps two groups' results apart is that
    each group's syncback lands under its own directory here.
    """
    return (
        results_root
        / OUTCOMES_RESULTS_SUBDIR
        / outcome.group
        / outcome.epic
        / outcome.name
    )


def read_verdict(results_dir: Path) -> str | None:
    """This outcome's verdict, or None where there isn't one to read.

    Anything other than the two values the contract defines is None rather
    than a guess: a truncated write and a file that was never written are the
    same thing from here -- a test whose result nobody can vouch for -- and
    reading a half-written verdict as either answer is the one mistake that
    would let the suite claim something it doesn't know.
    """
    verdict = results_dir / VERDICT_FILENAME
    if not verdict.is_file():
        return None
    written = verdict.read_text(encoding="utf-8").strip()
    return written if written in (VERDICT_PASSED, VERDICT_FAILED) else None


@dataclass(frozen=True)
class OutcomeResult:
    """One promise, and what this run of the suite found out about it."""

    outcome: Outcome
    state: str
    results_dir: Path
    confirmation: str | None = None
    """What a second run of this promise found, where one was asked for --
    CONFIRMED, UNCONFIRMED, or None where nothing re-ran it. It qualifies the
    state rather than replacing it: an unconfirmed failure is still a promise
    this run did not see kept."""

    @property
    def is_failure(self) -> bool:
        """Whether this outcome is a reason the suite is red. A promise with
        no test yet is not: there is nothing for the application to satisfy.
        A test that left no verdict is: nothing here knows that it ran.

        A failure that didn't reproduce is still one. The suite did not see
        every promise kept, and confirmation says why that was rather than
        making it not so -- a run that went green because a red test passed
        the second time is the retry-until-green this whole layer exists to
        refuse.

        A quarantined one is not, which is the entire point of the state: a
        test whose determinism somebody is fixing shouldn't block every merge
        in the meantime. It is still reported, and still not reported as
        passed -- the listing says it failed and says it is quarantined, so a
        green suite never becomes a claim about a promise nobody saw kept."""
        return self.state in (FAILED, NO_VERDICT) and not self.outcome.quarantined

    @property
    def reported_state(self) -> str:
        """How this result reads in a listing: the state, and whatever
        qualifies it -- what a second run made of it, and whether the suite
        has been told not to gate on it."""
        notes = [note for note in (self.confirmation, self.quarantine_note) if note]
        if not notes:
            return self.state
        return f"{self.state} ({', '.join(notes)})"

    @property
    def quarantine_note(self) -> str | None:
        return QUARANTINED if self.outcome.quarantined else None

    @property
    def first_run_dir(self) -> Path:
        """Where this outcome's first results were kept, if a confirmation
        re-run has since written over its own directory."""
        return self.results_dir.with_name(self.results_dir.name + FIRST_RUN_SUFFIX)


def result_for(outcome: Outcome, results_root: Path) -> OutcomeResult:
    """What this run found out about one promise."""
    results_dir = results_dir_for(results_root, outcome)
    if not outcome.translated:
        state = UNTRANSLATED
    else:
        verdict = read_verdict(results_dir)
        state = {
            VERDICT_PASSED: PASSED,
            VERDICT_FAILED: FAILED,
            None: NO_VERDICT,
        }[verdict]
    return OutcomeResult(outcome=outcome, state=state, results_dir=results_dir)


def suite_results(outcomes_dir: Path, results_root: Path) -> list[OutcomeResult]:
    """Every outcome the tree declares, with its verdict -- in the tree's own
    order, so the same suite reads the same way run to run."""
    return [
        result_for(outcome, results_root) for outcome in discover_outcomes(outcomes_dir)
    ]


def select(outcomes: list[Outcome], slugs: list[str]) -> tuple[list[Outcome], list[str]]:
    """The outcomes these slugs name, and the slugs that name nothing.

    Selected in the tree's own order rather than the order they were typed:
    outcome tests run one at a time against one application, so which order
    they run in is part of what a run means, and it should not depend on how
    somebody happened to spell the command.

    A slug matching nothing comes back rather than being dropped. A run that
    reports nothing looks exactly like a run where everything passed, which
    is the one thing a typo must not be able to produce."""
    declared = {outcome.slug: outcome for outcome in outcomes}
    wanted = set(slugs)
    return (
        [outcome for outcome in outcomes if outcome.slug in wanted],
        [slug for slug in slugs if slug not in declared],
    )


def report(results: list[OutcomeResult]) -> list[str]:
    """The listing, one line per outcome, named by the prompt's headline
    rather than its slug -- the headline is what the project actually
    promises, and the slug is only how the tree spells it."""
    slug_width = max(len(result.outcome.slug) for result in results)
    state_width = max(
        [len(state) for state in (PASSED, FAILED, NO_VERDICT, UNTRANSLATED)]
        + [len(result.reported_state) for result in results]
    )
    lines = []
    for result in results:
        headline = result.outcome.headline or "(no headline -- see `seal check`)"
        lines.append(
            f"{result.outcome.slug:<{slug_width}}  "
            f"{result.reported_state:<{state_width}}  {headline}"
        )
    return lines


def summary(
    results: list[OutcomeResult],
    declared: int | None = None,
    ran_now: bool = False,
    drove_a_session: bool = True,
) -> str:
    """One line saying what this run found. Counted by state, so a run with
    nothing to say still says how many promises it covered.

    `declared` is how many outcomes the tree holds, and is given when only
    some of them ran. Then the count is of what ran and the line says so:
    the whole suite's verdict is a claim about every promise a project makes,
    and a subset's must never be readable as one.

    `ran_now` says the tests ran during this command rather than before it.
    Both forms cover every promise, so neither carries a caveat -- but one is
    read from what a run left behind and the other started that run, and
    somebody reading a suite's verdict should be able to tell which they are
    holding."""
    counted = [
        (sum(1 for result in results if result.state == state), label)
        for state, label in (
            (PASSED, "passed"),
            (FAILED, "failed"),
            (NO_VERDICT, "with no verdict"),
            (UNTRANSLATED, "with no test yet"),
        )
    ]
    parts = ", ".join(f"{count} {label}" for count, label in counted if count)
    # Counted on top of the states above rather than instead of them: a
    # quarantined promise that failed did fail, and a line that reported it
    # only as quarantined would leave a reader unable to tell it from one
    # that held.
    quarantined = sum(1 for result in results if result.outcome.quarantined)
    if quarantined:
        parts += (
            f" -- {quarantined} of them quarantined, so a failure there did not fail "
            "this run"
        )
    if declared is None:
        if ran_now:
            # Saying a run went and got these verdicts is the load-bearing
            # half: a verdict this command performed and one it read off a
            # run somebody else performed are different claims. Where those
            # promises were checked is the other half, and only true of a
            # run that deployed something -- a group started on the machine
            # has no session to have been up.
            against = " against the session already up" if drove_a_session else ""
            return f"{len(results)} outcome(s), run just now{against}: {parts}."
        return f"{len(results)} outcome(s): {parts}."
    return (
        f"{len(results)} of {declared} outcome(s), named on the command line: {parts}. "
        f"The other {declared - len(results)} did not run, so nothing here says whether "
        "they still hold -- only the whole suite does that."
    )
