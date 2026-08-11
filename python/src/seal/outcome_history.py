"""What every run found, kept, so that a promise which keeps changing its
mind is visible as a rate rather than as something somebody remembers.

A regression loop has to tell a promise the application really has stopped
keeping from a test that fails intermittently with no change to anything it
exercises. The two are fixed in different places, by different people, and
sending an agent at the application for the second produces a change that
fixes nothing. `--confirm` (see seal.py) answers that for one failure, by
running it again; this answers it across runs, which is where the pattern
actually lives -- a test that fails one run in four looks perfectly ordinary
in any single one of them.

So each run appends what it found, one entry per outcome, and what gets read
back is how often each promise's verdict *changed*. A steady record says
nothing and is reported as nothing: what earns a line is a promise that has
been red and green in the same window without anybody deciding which it is.

The same entries are what a regression loop is read from, one run at a time
rather than one promise at a time (see outcome_loop.py). That is why each
carries the run it belongs to and what that run covered: a loop is rounds of
the whole suite, and which promises a round did not mention has to be a fact
rather than a guess.

Two things this deliberately does not do.

**It concludes nothing.** A rate is evidence. Whether a test is at fault, or
the application is genuinely intermittent, or the environment is, is a
judgement -- and the action it leads to, quarantining the outcome, is a
change to the tree that a code owner approves like any other (see
/rfcs/0009-outcome-tests.md). Nothing here quarantines anything.

**It has no threshold.** A number picked before anything has a use for one is
guidance dressed as a rule. The record says how many times a promise flipped
and over how many runs, and leaves the reading to whoever asked.

The file sits under .workspace/, where everything seal generates into a
project already goes and which a project already ignores: this is an
observation about runs on one machine, not a fact about the repository. Two
reads of the same run append the same verdict twice, which is honest -- it is
what was asked and what was answered -- and cannot manufacture a flip, since
a flip is a verdict that *changed*.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Where the record lives, relative to the project root. JSON Lines because
# the only write there is is an append: a run adds what it found without
# reading, parsing or rewriting what came before, so a run interrupted
# halfway costs the entry it was writing and nothing else.
HISTORY_FILE = Path(".workspace") / "seal" / "outcome-history.jsonl"

# How far back a reading looks. Long enough that a promise failing one run in
# several shows up, short enough that a test fixed a fortnight ago stops being
# reported as a problem -- the record is what it did lately, not its whole
# past.
RECENT_RUNS = 10

# The keys one entry carries. Named rather than spelled inline: this file
# outlives any one version of seal, and an entry a later read cannot make
# sense of is worse than no record.
OUTCOME_KEY = "outcome"
STATE_KEY = "state"
CONFIRMATION_KEY = "confirmation"
AT_KEY = "at"

# Which run this entry belongs to, and what that run covered. Together they
# are what lets a read reconstruct runs from a flat list of outcomes -- which
# is what a regression loop is made of (see outcome_loop.py).
#
# The run is carried rather than inferred from AT_KEY. Two runs sharing a
# timestamp would read as one, and a run whose entries were written either
# side of a second would read as two; neither is something a loop should
# depend on not happening.
RUN_KEY = "run"
SCOPE_KEY = "scope"

# Whether the suite had been told not to gate on this promise when the run
# happened. Carried rather than looked up later: a quarantine is a file in
# the tree that comes and goes, and a round read back through today's tree
# would say a promise that gated a fortnight ago never did.
QUARANTINE_KEY = "quarantined"

# What a run covered. The whole tree, or the outcomes somebody named on the
# command line -- and only the first is an iteration of anything. A subset
# says nothing about the promises it left out, which `seal outcomes run`
# already says in as many words, so reading one as a round of a loop would
# report every promise it skipped as having been fixed.
SCOPE_TREE = "tree"
SCOPE_SELECTION = "selection"


def history_path(seal_root: Path) -> Path:
    return seal_root / HISTORY_FILE


def record(seal_root: Path, results, whole_suite: bool) -> None:
    """Append what this run found, one entry per outcome.

    `whole_suite` is whether this run covered every promise the tree holds,
    which is what separates a round of a loop from somebody iterating on one
    translation. It is a fact about the run and so is written down rather
    than worked out later: a read cannot tell a subset that happened to name
    every outcome from a run of the suite, and the difference decides whether
    the promises absent from an entry were passing or simply not asked.

    Failure to write is not failure to run. The record is an aid to whoever
    reads it later; a read-only checkout, or a project whose .workspace is
    not writable, should still get its suite's verdict.
    """
    path = history_path(seal_root)
    at = datetime.now(timezone.utc).isoformat()
    run = uuid.uuid4().hex
    scope = SCOPE_TREE if whole_suite else SCOPE_SELECTION
    lines = [
        json.dumps(
            {
                OUTCOME_KEY: result.outcome.slug,
                STATE_KEY: result.state,
                CONFIRMATION_KEY: result.confirmation,
                AT_KEY: at,
                RUN_KEY: run,
                SCOPE_KEY: scope,
                QUARANTINE_KEY: result.outcome.quarantined,
            }
        )
        for result in results
    ]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as history:
            history.write("".join(f"{line}\n" for line in lines))
    except OSError:
        return


def _entries(seal_root: Path) -> list[dict]:
    """Every entry in the record, oldest first.

    A line that cannot be read is skipped rather than failing the read. This
    is an append-only log on somebody's own machine, which is exactly the
    kind of file that ends up with a truncated last line -- and a listing
    that refused to print because of one would be a worse tool than one that
    printed a slightly shorter history.
    """
    path = history_path(seal_root)
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []
    entries = []
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def recorded_verdicts(seal_root: Path, recent: int = RECENT_RUNS) -> dict[str, list[str]]:
    """The last few states recorded for each outcome, oldest first."""
    verdicts: dict[str, list[str]] = {}
    for entry in _entries(seal_root):
        slug, state = entry.get(OUTCOME_KEY), entry.get(STATE_KEY)
        if not isinstance(slug, str) or not isinstance(state, str):
            continue
        verdicts.setdefault(slug, []).append(state)
    return {slug: states[-recent:] for slug, states in verdicts.items()}


@dataclass(frozen=True)
class Run:
    """One run of the suite, reassembled from the entries it appended."""

    at: datetime
    states: dict[str, str]
    """What each promise's verdict was, by slug."""
    quarantined: set[str]
    """Which of them the suite had been told not to gate on, so a failure
    there did not fail this run."""


def recorded_runs(seal_root: Path) -> list[Run]:
    """Every run of the *whole* suite in the record, oldest first.

    Runs rather than entries, because what a loop is made of is rounds: a
    promise that was red last round and is green this one was fixed, and that
    comparison needs both sides to be a whole run of the suite.

    Two kinds of entry are left out, for the same reason. One naming a
    selection covered only the outcomes somebody asked for, so what it does
    not mention is unknown rather than passing. And one carrying no run and
    no scope at all -- written before the record said either -- is a run
    whose coverage nothing can establish; counted as the suite, it would
    report every promise added since as having been fixed the moment it
    passed. Both still count towards how often a promise has changed its
    mind, which asks only what that promise's own verdict was.
    """
    runs: dict[str, Run] = {}
    for entry in _entries(seal_root):
        run = entry.get(RUN_KEY)
        slug, state = entry.get(OUTCOME_KEY), entry.get(STATE_KEY)
        if entry.get(SCOPE_KEY) != SCOPE_TREE or not isinstance(run, str):
            continue
        if not isinstance(slug, str) or not isinstance(state, str):
            continue
        if run not in runs:
            at = _parsed(entry.get(AT_KEY))
            if at is None:
                continue
            runs[run] = Run(at=at, states={}, quarantined=set())
        runs[run].states[slug] = state
        if entry.get(QUARANTINE_KEY) is True:
            runs[run].quarantined.add(slug)
    # In the order they were written rather than by timestamp: the file is
    # append-only, so its own order is the order they happened, and a clock
    # that stepped backwards between two runs should not reorder them.
    return list(runs.values())


def _parsed(at: object) -> datetime | None:
    """The timestamp an entry carries, or None where it carries nothing that
    can be read as one. A run seal cannot date is one no elapsed time can be
    measured from, which is half of what a cap is read off."""
    if not isinstance(at, str):
        return None
    try:
        return datetime.fromisoformat(at)
    except ValueError:
        return None


def flips(states: list[str]) -> int:
    """How many times this promise's verdict changed across the runs given.

    Changes rather than failures, because a promise that has been failing
    every run since somebody broke it is not what this is looking for -- that
    is a regression, and the suite already says so every time. What this
    finds is the one that was red and green in the same window with nothing
    in between deciding which.
    """
    return sum(1 for before, after in zip(states, states[1:]) if before != after)
