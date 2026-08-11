"""Where a project's outcome prompts live, and how anything finds them.

An outcome prompt is a promise the application makes, written the way
somebody using it would put it -- "an item I add is still on the list after
a reload". A low-level test is one agent's translation of that promise
against the implementation as it stands, and translating is lossy: the same
prompt yields different tests in different hands, each encoding
implementation choices the prompt never specified. So the prompt is the
source of truth, and a reviewer of a test has to be able to reach the
prompt it came from -- otherwise there is nothing to check the test's
intent against, only whether it happens to pass.

That traceability is what shapes the layout: a prompt and its translation
share a directory.

    outcomes/
      seal-test-config.json
      <group>/
        helpers/           -- what this group's tests share
        <epic>/
          <outcome>/
            prompt.md      -- the promise
            ...            -- the test translated from it

An outcome is a directory, so the pairing is the filesystem's own rather
than something a registry has to be kept in agreement with -- the same
spirit as a project's root Tiltfile being its service list. Walking the
tree is the whole of discovery.

Everything in an outcome's directory besides `prompt.md` is part of the
translation. What makes that runnable rather than merely findable is a
*runner*: an image built from the tree, which drives the running
environment from inside the cluster -- reaching services by name rather
than through a port-forward that only exists while a Tilt session is up.

A project's promises are not all of one kind, and neither are the things
that test them: a promise about what somebody sees is tested through a
browser, and a promise an API-only service makes is tested by talking to
the API. So outcomes are grouped, one group per runner, and the group is
the directory above an epic. `seal-test-config.json` at the tree's root
says what runs each one (see runners.py).

That is the one thing a walk cannot answer -- nothing about a directory of
promises says what starts them -- and it is the only thing the config
declares. Which outcomes exist is still the tree's own business.

Within a group the runner is seal's or the project's. seal's supplies
everything a kind of test needs: `playwright` gives a browser, a pinned
framework and the reporting, so a translation is spec files and nothing
else. `custom` builds a Dockerfile the project brings, which is what keeps
the tree language-agnostic rather than merely broad -- a worker, a
command-line tool, anything with no page to open says how it runs and seal
stays out of the way.

One runner per group, not one per outcome, because a run is one container
either way: it is told which outcomes to run, and every outcome it is told
about is one it knows how to start.

`helpers/` at a group's root is what that group's tests share: signing in,
reaching a page, whatever several translations would otherwise each spell
out. Its own directory rather than an epic, because epics hold promises and
this holds none -- one named `helpers` would have every outcome under it
reported as a promise nothing tests.

At the group's root and nowhere higher, because that is the runner's build
context: what a group's image is made of is that directory, so a helper any
higher would not reach the container that has to import it. Two groups with
something genuinely in common share it the way they share anything else --
a `custom` runner whose `dockerfile_context` names a directory holding both.

The tree sits at the project root, not under `services/<name>/`. An outcome
test drives several services at once -- that is what makes it an outcome
test rather than a unit test -- so there is no one service it belongs to.

An outcome directory holding only its prompt is *untranslated*: a promise
written down before anything has compiled it into a test. That is a state a
project legitimately sits in, not an error. What is not: a test with no
prompt to trace it back to, whose intent nobody can review; a group of
outcomes no runner claims, or a runner claiming a group that is not there,
which is the tree and the config having drifted apart; a translation the
group's runner would not collect, which the suite can only report as a
promise nothing tests while a test sits right there in the tree; a promise
filed under `helpers/`, which nothing walks for outcomes; and, under a
runner whose API seal knows, a translation that waits on the clock rather
than on the state it wants, whose red says nothing about whether the
promise held. `seal check` refuses all of them.

The tree carries one more property the layout alone cannot give it: every
outcome in it has to need a human's review to change, which on GitHub means
CODEOWNERS covers it (see codeowners.py, and /rfcs/0009-outcome-tests.md for what
that buys and what a repository still has to be configured to do). A test an
agent can edit to make its own failure go away is not a gate, so
`seal check` refuses an unowned tree the same way it refuses a malformed
one. Helpers are held to it as hard as the outcomes are: assertions move
into a helper as readily as anything else, so one a change could reach
without review is a way to defang a test from outside the test.
"""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from seal.codeowners import CodeOwners, Rule
from seal.runners import (
    CONFIG_FILENAME,
    CUSTOM,
    PLAYWRIGHT,
    RUNNER_FIELD,
    TAP,
    TAP_RUNNER_FILENAME,
    Runner,
    config_path,
    read_loop_limits,
    read_runner_config,
)

DEFAULT_OUTCOMES_DIR_NAME = "outcomes"
# A project that keeps its outcome tree somewhere else names it here, the
# same way SEAL_K8S_DIR names a manifests directory (see checks.py): an
# environment variable rather than a flag, because `seal ci` forwards every
# argument it is given straight through to `tilt ci`.
OUTCOMES_DIR_ENV_VAR = "SEAL_OUTCOMES_DIR"

PROMPT_FILENAME = "prompt.md"

# What a group's tests share, at the group's root: the directory a runner's
# image is built from, so a helper here is in the container beside every
# outcome that imports it.
#
# A fixed name rather than a declared one. Everything else about the layout
# is read off the tree, and a directory that means something has to be
# recognisable from the tree alone -- by the CLI, by the extension building
# the image, and by whoever opens the repository. The cost is one name an
# epic cannot have, which is why an outcome filed below it is refused rather
# than passed over.
HELPERS_DIR_NAME = "helpers"

# Where an outcome says it is quarantined, and why. In the outcome's own
# directory, which is what makes changing one a code owner's call without a
# separate governance path: whatever rule already covers the tree covers this
# (see /rfcs/0009-outcome-tests.md). A quarantine an agent could add for itself
# would be a way to a green suite that never touched the application.
#
# The reason is the file's whole content, and a quarantine without one is
# refused. A test switched off and a test whose determinism somebody is
# fixing look identical from the tree, and the reviewer approving the diff is
# the person who has to tell them apart.
QUARANTINE_FILENAME = "quarantine.md"

# What the `playwright` runner collects, which is Playwright's own default
# testMatch. Spelled out rather than approximated: this rule decides whether
# a file in the tree is a test, and one that disagreed with the runner would
# call a translation untranslated -- or the reverse -- for a reason nobody
# could see from the tree.
SPEC_SUFFIXES = tuple(
    ".{}.{}".format(kind, extension)
    for kind in ("spec", "test")
    for extension in ("ts", "js", "mjs", "cjs", "mts", "cts", "tsx", "jsx")
)

# The one fixed-duration wait Playwright offers, and therefore the whole of
# what sleeping is spelled as under that runner. A translation that waits on
# the clock instead of on the state it wants passes on the machine it was
# written on and fails on a loaded runner -- where the promise reads as
# broken because a browser was slow.
FIXED_WAIT = "waitForTimeout"

# Lowercase letters, digits and single hyphens. A slug is a path component,
# a test identifier in a report, and a CODEOWNERS pattern all at once, so it
# is held to what all three read the same way.
SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def configured_outcomes_dir_name(environ: Mapping[str, str]) -> str:
    """Where this project keeps its outcome tree, relative to its root."""
    return environ.get(OUTCOMES_DIR_ENV_VAR) or DEFAULT_OUTCOMES_DIR_NAME


def is_valid_slug(name: str) -> bool:
    return SLUG_PATTERN.match(name) is not None


@dataclass(frozen=True)
class Outcome:
    """One promise, and whatever has been translated from it so far."""

    epic: str
    name: str
    directory: Path
    prompt: Path
    # The prompt's own headline -- what a per-test report calls this outcome.
    # Empty when the prompt declares none, which `seal check` reports; keeping
    # it out of band here would mean discovery could not describe a tree it
    # does not police.
    headline: str
    # Every file of the translation, prompt and quarantine note excluded, in
    # a stable order. Recursive: a test that needs fixtures of its own keeps
    # them beside itself rather than somewhere this would not look.
    translation: tuple[Path, ...]
    # Why this outcome is quarantined, or the empty string where it isn't.
    # Not part of the translation: a note about a test is not a thing that
    # runs, and counting it as one would have a promise with nothing but a
    # quarantine read as translated.
    quarantine: str
    # What will run this outcome. The same for every outcome in a group,
    # since that is what a group is; carried per outcome so what a listing
    # says about one is answerable from the outcome alone.
    runner: Runner

    @property
    def group(self) -> str:
        """The directory this outcome's epic sits in, which is also the name
        of the runner that starts it."""
        return self.runner.name

    @property
    def translated(self) -> bool:
        """Whether a test exists here that the run can actually start.

        Files alone do not make one under a runner seal supplies: a
        directory of fixtures with nothing the `playwright` runner collects
        is a promise nothing tests, however much of a test it looks like,
        and `seal check` refuses that shape rather than letting a suite
        report it as green.

        A group whose runner the project brought is taken at its word. seal
        has no reading of what a `custom` runner starts -- that is the whole
        point of declaring one -- so anything written here is a test as far
        as this can tell.
        """
        if not self.translation:
            return False
        if self.runner.runner_type == PLAYWRIGHT:
            return any(path.name.endswith(SPEC_SUFFIXES) for path in self.translation)
        return True

    @property
    def quarantined(self) -> bool:
        """Whether a failure here is one the suite has been told not to gate
        on while somebody fixes the test's determinism."""
        return bool(self.quarantine)

    @property
    def slug(self) -> str:
        """This outcome's full identifier, the same string its directory
        spells out relative to the outcome tree."""
        return f"{self.group}/{self.epic}/{self.name}"

    @property
    def slug_within_group(self) -> str:
        """How the runner itself names this outcome. A runner is built from
        one group and told what to run, so the group is seal's side of the
        identifier and never something the container has to know about."""
        return f"{self.epic}/{self.name}"


def headline_of(prompt: Path) -> str:
    """A prompt's first non-blank line, when that line is an ATX H1, else the
    empty string. One heading, not a whole document parse: the headline is
    the single thing anything downstream reads mechanically, and the rest of
    the file is prose for whoever translates it."""
    for line in prompt.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            return stripped[2:].strip()
        return ""
    return ""


def _entries(directory: Path) -> list[Path]:
    """What the layout considers declared, at each level above an outcome.
    Dot-entries are tooling's, not the project's -- an editor's leavings or a
    `.gitkeep` are neither a promise nor a test, and reading them as one
    would flag a tree nobody got wrong. Inside an outcome no such filter
    applies: everything there is part of the translation."""
    return sorted(path for path in directory.iterdir() if not path.name.startswith("."))


def _is_epic(path: Path) -> bool:
    """Whether this entry of a group directory holds promises. Every
    directory in a group does, save the one holding what its tests share."""
    return path.is_dir() and path.name != HELPERS_DIR_NAME


def _translation_files(outcome_dir: Path) -> tuple[Path, ...]:
    seal_s_own = {outcome_dir / PROMPT_FILENAME, outcome_dir / QUARANTINE_FILENAME}
    return tuple(
        sorted(
            path
            for path in outcome_dir.rglob("*")
            if path.is_file() and path not in seal_s_own
        )
    )


def helper_files(group_dir: Path) -> tuple[Path, ...]:
    """Everything this group's tests share, in a stable order, and empty
    where the group shares nothing.

    Recursive, and with no filename rule of its own: what a helper is called
    is the translation's business, since nothing here starts one. What makes
    it part of the run is the runner's build context holding it, which is
    the group directory either way.
    """
    directory = group_dir / HELPERS_DIR_NAME
    if not directory.is_dir():
        return ()
    return tuple(sorted(path for path in directory.rglob("*") if path.is_file()))


def quarantine_reason(outcome_dir: Path) -> str:
    """Why this outcome is quarantined, or the empty string where it isn't.

    A file that is there but says nothing comes back empty, which reads the
    same way as no file at all -- so a quarantine nobody wrote a reason for
    does not take effect, and `seal check` says why. A promise excused from
    the gate for a reason nobody recorded is exactly what a reviewer has
    nothing to approve.
    """
    note = outcome_dir / QUARANTINE_FILENAME
    if not note.is_file():
        return ""
    try:
        return note.read_text(encoding="utf-8").strip()
    except (UnicodeDecodeError, OSError):
        return ""


def waits_on_the_clock(path: Path) -> bool:
    """Whether this file of a translation sleeps rather than polls.

    A plain read of the spelling, deliberately: parsing TypeScript to work
    out whether a given `waitForTimeout` is reached, or sits in a comment,
    would be a lint pretending to be a rule. A translation that means to
    sleep is having a conversation with a reviewer, which is the outcome the
    gate wants anyway.

    Only what can be read as text is looked at. A translation carries its
    own fixtures, and nothing waits inside an image.
    """
    try:
        return FIXED_WAIT in path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False


def runners_by_group(outcomes_dir: Path) -> dict[str, Runner]:
    """Every runner the tree declares, by the group directory it drives.

    A config that names the same group twice keeps the last of them here and
    is reported by `seal check`: this has to answer with one runner per
    group, and which one a broken config meant is not something to guess at.
    """
    runners, _ = read_runner_config(outcomes_dir)
    return {runner.name: runner for runner in runners}


def discover_outcomes(outcomes_dir: Path) -> list[Outcome]:
    """Every outcome the tree declares, group by group, in path order.

    This describes a well-formed tree rather than policing one: an entry
    that cannot be an outcome (a directory with no prompt, a file where the
    layout allows only directories, a group no runner claims) is passed over
    here and reported by `seal check` instead -- so a project with a broken
    tree still gets a useful listing of the outcomes it does have, alongside
    the errors.

    A project with no outcome tree at all declares no outcomes. That is not
    an error either: outcome tests are something a project adopts, not
    something it is required to have before `seal` will run.
    """
    if not outcomes_dir.is_dir():
        return []

    runners = runners_by_group(outcomes_dir)
    outcomes: list[Outcome] = []
    for group in sorted(runners):
        group_dir = outcomes_dir / group
        if not group_dir.is_dir():
            continue
        for epic_dir in [path for path in _entries(group_dir) if _is_epic(path)]:
            for outcome_dir in [path for path in _entries(epic_dir) if path.is_dir()]:
                prompt = outcome_dir / PROMPT_FILENAME
                if not prompt.is_file():
                    continue
                outcomes.append(
                    Outcome(
                        epic=epic_dir.name,
                        name=outcome_dir.name,
                        directory=outcome_dir,
                        prompt=prompt,
                        headline=headline_of(prompt),
                        translation=_translation_files(outcome_dir),
                        quarantine=quarantine_reason(outcome_dir),
                        runner=runners[group],
                    )
                )
    return outcomes


@dataclass(frozen=True)
class OutcomeProblem:
    """One thing in the tree that the layout has no reading for."""

    path: Path
    problem: str

    def describe(self, relative_to: Path) -> str:
        try:
            where = self.path.relative_to(relative_to)
        except ValueError:
            where = self.path
        return f"{where}: {self.problem}"


_NOT_A_SLUG = (
    "not a slug -- lowercase letters, digits and single hyphens. The name is a "
    "path component, a test identifier in a report and a CODEOWNERS pattern at "
    "once, so it has to read the same way in all three."
)


def _tap_runner_problems(
    outcomes_dir: Path, runner: Runner, problems: list["OutcomeProblem"]
) -> None:
    """What stops a 'tap' group from being startable at all.

    RFC 0011's rule about a translation the runner cannot run has a version
    one level up here: a group nothing can *start* reports every promise
    under it as untested, for a reason no listing explains. Both failures
    are silent, which is what makes them worth a rule.

    Nothing here asks whether the executable emits TAP, or a point per
    outcome. That is knowable only by running it, and a check that ran the
    suite to find out would be the suite.
    """
    executable = outcomes_dir / runner.name / TAP_RUNNER_FILENAME
    if not executable.is_file():
        problems.append(
            OutcomeProblem(
                config_path(outcomes_dir),
                f"'{runner.name}' is a '{TAP}' runner and there is no "
                f"{runner.name}/{TAP_RUNNER_FILENAME} to start. seal runs that "
                "file once for the whole group and reads the verdicts off what it "
                "prints, so without it every promise here is reported untested.",
            )
        )
        return
    if not os.access(executable, os.X_OK):
        # Its own problem rather than the one above, because it is the one
        # somebody actually hits: git records the executable bit, and a
        # checkout onto a filesystem that drops it leaves a file that is
        # plainly there and cannot be run.
        problems.append(
            OutcomeProblem(
                executable,
                "is what starts this group and is not executable. seal runs it "
                "directly rather than through a shell, so the bit is what decides "
                "whether it can start at all -- `chmod +x` it, and commit that.",
            )
        )


def _config_problems(
    outcomes_dir: Path, runners: list[Runner], malformed: list[str]
) -> list[OutcomeProblem]:
    """What the declaration itself gets wrong, and where it disagrees with
    the tree beside it.

    The disagreements are the reason this file is worth checking at all. A
    group nothing claims is a directory of promises that never runs, and the
    suite would report every one of them as untested; a runner claiming a
    directory that is not there builds an image over nothing. Both are the
    cost of a declaration living outside the tree, and both are cheap to
    catch here and expensive to notice from a run.
    """
    config = config_path(outcomes_dir)
    problems = [OutcomeProblem(config, problem) for problem in malformed]

    if not config.is_file():
        if not _entries(outcomes_dir):
            # An empty directory declares nothing, and outcome tests are
            # something a project adopts: saying so on every run would train
            # people to read past this check's output.
            return problems
        problems.append(
            OutcomeProblem(
                outcomes_dir,
                f"no {CONFIG_FILENAME} -- nothing here says what runs these outcomes, so "
                "none of them can be started. It holds one field, "
                f"'{RUNNER_FIELD}', a list with an entry per group directory in this "
                "tree.",
            )
        )
        return problems

    if not malformed and not runners:
        problems.append(
            OutcomeProblem(
                config,
                "declares no runner. A group of outcomes runs as the image its runner "
                "builds, so a tree with none has nothing to start.",
            )
        )

    declared = set()
    for runner in runners:
        declared.add(runner.name)
        if not is_valid_slug(runner.name):
            problems.append(
                OutcomeProblem(config, f"the group name '{runner.name}' is {_NOT_A_SLUG}")
            )
        group_dir = outcomes_dir / runner.name
        if not group_dir.is_dir():
            problems.append(
                OutcomeProblem(
                    config,
                    f"'{runner.name}' has no directory in this tree. A runner drives the "
                    "epics under the directory it names, and there is nothing here for "
                    "this one to run.",
                )
            )
        if runner.is_tap:
            _tap_runner_problems(outcomes_dir, runner, problems)
            continue
        if not runner.is_custom:
            continue
        dockerfile = outcomes_dir / runner.dockerfile
        if not dockerfile.is_file():
            problems.append(
                OutcomeProblem(
                    config,
                    f"'{runner.name}' is a '{CUSTOM}' runner and its "
                    f"{runner.dockerfile} is not there. That file is the whole of what "
                    "seal builds for this group.",
                )
            )
        context = outcomes_dir / runner.dockerfile_context
        if not context.is_dir():
            problems.append(
                OutcomeProblem(
                    config,
                    f"'{runner.name}' builds from {runner.dockerfile_context}/, which is "
                    "not a directory in this tree.",
                )
            )

    for path in _entries(outcomes_dir):
        if path.is_dir():
            if path.name in declared:
                continue
            if path.name == HELPERS_DIR_NAME:
                # Said plainly, because the reading this would otherwise get
                # -- an undeclared group -- sends somebody to declare a
                # runner for a directory holding no promises at all.
                problems.append(
                    OutcomeProblem(
                        path,
                        "what a group's tests share lives at that group's root, not at "
                        "the tree's. A runner is built from one group's directory, so "
                        "nothing here is in the image that has to import it -- move it "
                        f"to <group>/{HELPERS_DIR_NAME}/, one copy per group that needs "
                        "it, or into a directory a 'custom' runner names as its build "
                        "context where two groups genuinely share one image.",
                    )
                )
                continue
            problems.append(
                OutcomeProblem(
                    path,
                    f"no runner in {CONFIG_FILENAME} names this group, so nothing "
                    "would start the outcomes under it -- and the suite reports a "
                    "promise nothing starts as untested. Add an entry naming "
                    f"'{path.name}', or move these epics under a group that has one.",
                )
            )
        elif path.name != CONFIG_FILENAME and not any(
            runner.is_custom for runner in runners
        ):
            problems.append(
                OutcomeProblem(
                    path,
                    "a file where the layout has only group directories -- a prompt or a "
                    "test filed here has no outcome directory to be paired inside. Files "
                    f"at this level are build material for a '{CUSTOM}' runner, and this "
                    "tree declares none.",
                )
            )
    return problems


def _outcome_problems(outcome_dir: Path, runner: Runner) -> list[OutcomeProblem]:
    """What one outcome directory gets wrong, under the runner that would
    start it."""
    problems: list[OutcomeProblem] = []
    prompt = outcome_dir / PROMPT_FILENAME
    if not prompt.is_file():
        # Reported on its own: a directory with no prompt is not an outcome
        # at all, and what is or isn't runnable inside one that doesn't exist
        # is a second opinion about the same mistake.
        return [
            OutcomeProblem(
                outcome_dir,
                f"no {PROMPT_FILENAME} -- nothing here traces back to a promise, so "
                "there is no intent to review this outcome's test against.",
            )
        ]

    if not headline_of(prompt):
        problems.append(
            OutcomeProblem(
                prompt,
                "no headline -- the first non-blank line has to be an ATX H1 "
                "('# the promise'), which is what names this outcome wherever it "
                "is reported.",
            )
        )

    note = outcome_dir / QUARANTINE_FILENAME
    if note.is_file() and not quarantine_reason(outcome_dir):
        problems.append(
            OutcomeProblem(
                note,
                "quarantined with no reason -- a quarantine is a promise the suite has "
                "been told not to gate on, and one nobody wrote a motivation for is "
                "indistinguishable from a test somebody switched off. Say what is being "
                "fixed and what would let this come back.",
            )
        )

    translation = _translation_files(outcome_dir)
    if runner.runner_type != PLAYWRIGHT:
        # seal has no reading of what a runner the project brought starts,
        # which is the whole point of bringing one -- so neither what
        # counts as a test here nor how it waits is something to police.
        return problems

    # Anything written here at all, against anything the runner would
    # collect: the first separates "a promise nobody has translated yet" --
    # an ordinary state -- from "a translation nothing can start", which is
    # not.
    if translation and not any(
        path.name.endswith(SPEC_SUFFIXES) for path in translation
    ):
        problems.append(
            OutcomeProblem(
                outcome_dir,
                f"nothing here can run -- no test the '{PLAYWRIGHT}' runner collects "
                f"({', '.join(SPEC_SUFFIXES[:2])}, ...), so the suite reports this "
                "promise as untested while a test sits in the tree. Either name the "
                f"file the way that runner reads, or put this group behind a "
                f"'{CUSTOM}' runner of the project's own.",
            )
        )
    # How a translation waits, which is the difference between a promise
    # being tested and a browser being raced.
    problems.extend(
        OutcomeProblem(
            path,
            f"waits on the clock -- `{FIXED_WAIT}` sleeps for a fixed duration "
            "instead of polling for the state it is waiting for, so it passes "
            "on the machine it was written on and fails on a loaded runner, "
            "where a promise reads as broken because a browser was slow. Wait "
            "on the thing itself: a web-first assertion "
            "(`expect(locator).toBeVisible()`) or `locator.waitFor()` retries "
            "until it holds.",
        )
        for path in translation
        if waits_on_the_clock(path)
    )
    return problems


def _helpers_problems(group_dir: Path, runner: Runner) -> list[OutcomeProblem]:
    """What a group's shared translation material gets wrong, under the
    runner that would build it.

    Almost nothing is asked of it: a helper is imported by a test rather than
    started by a runner, so what it is called and what it holds are the
    translation's own business. Refused are the two ways a file here reads as
    something it cannot be -- a promise, and (under a runner whose API seal
    knows) a test -- and, for the reason a translation is held to it, a wait
    on the clock.
    """
    directory = group_dir / HELPERS_DIR_NAME
    if not directory.is_dir():
        return []

    problems = [
        OutcomeProblem(
            path,
            f"a promise under {HELPERS_DIR_NAME}/, which holds what this group's "
            "tests share rather than the promises they test. Nothing walks it for "
            "outcomes, so this one would run nowhere and be reported by nothing. "
            f"An epic cannot be named '{HELPERS_DIR_NAME}' -- move these outcomes "
            "under one of their own.",
        )
        for path in helper_files(group_dir)
        if path.name == PROMPT_FILENAME
    ]

    if runner.runner_type != PLAYWRIGHT:
        # seal has no reading of what a runner the project brought collects,
        # so which of these files it starts and which it merely imports is
        # not something to police -- the same silence _outcome_problems keeps.
        return problems

    for path in helper_files(group_dir):
        if path.name.endswith(SPEC_SUFFIXES):
            problems.append(
                OutcomeProblem(
                    path,
                    f"a test under {HELPERS_DIR_NAME}/, where a run never looks: the "
                    f"'{PLAYWRIGHT}' runner is pointed at one outcome's directory at a "
                    "time, so this file is collected by nothing and its failures are "
                    "seen by nobody. Move it into the outcome it tests, or name it "
                    "for what it is if the tests import it.",
                )
            )
        if waits_on_the_clock(path):
            problems.append(
                OutcomeProblem(
                    path,
                    f"waits on the clock -- `{FIXED_WAIT}` sleeps for a fixed duration "
                    "instead of polling for the state it is waiting for, so it passes "
                    "on the machine it was written on and fails on a loaded runner, "
                    "where a promise reads as broken because a browser was slow. A "
                    "helper is worse than a test for it: every outcome that imports "
                    "this one inherits the wait. Wait on the thing itself -- a "
                    "web-first assertion (`expect(locator).toBeVisible()`) or "
                    "`locator.waitFor()` retries until it holds.",
                )
            )
    return problems


def outcome_layout_problems(outcomes_dir: Path) -> list[OutcomeProblem]:
    """Everything in the tree that breaks the layout. Empty means the project
    passes; a project with no outcome tree at all passes too, since outcome
    tests are something a project adopts rather than a precondition for
    running `seal`.

    Every offender is returned, not the first: a project should be able to
    put its tree right once instead of a failed run at a time.

    What is deliberately *not* a problem is an outcome that has a prompt and
    no translation at all. A promise can be written down long before
    anything compiles it into a test, and a rule against that would mean a
    prompt could only ever land in the same change as its test.

    Five shapes are refused instead. A test with no prompt to trace it back
    to is the one the merge gate rests on: a translation nobody can reach
    the promise for is a test whose intent cannot be reviewed. A group and
    a runner that do not correspond is the tree and its declaration having
    drifted apart, which nothing downstream can tell from a project that
    means it. A translation nothing can start is the one a suite cannot
    catch for itself -- it reports the promise as untested, which reads
    exactly like a promise nobody has got to yet. A promise or a test filed
    under a group's `helpers/` is the same failure reached from the other
    side: that directory is what the group's tests share, nothing walks it,
    and a run would pass over both in silence. And a translation that waits
    on the clock is one whose red says nothing about the promise, which
    costs whoever inherits it more than an untranslated promise does -- a
    helper that does it costs every outcome importing it.
    """
    if not outcomes_dir.is_dir():
        return []

    runners, malformed = read_runner_config(outcomes_dir)
    _, mis_declared_loop = read_loop_limits(outcomes_dir)
    problems = _config_problems(outcomes_dir, runners, malformed + mis_declared_loop)

    # By group name rather than in the config's order, which is the order
    # everything else reads a tree in -- and one group at a time even where
    # two entries name it, since a group walked twice reports every outcome
    # under it twice for one mistake already reported above.
    for name, runner in sorted(runners_by_group(outcomes_dir).items()):
        group_dir = outcomes_dir / name
        if not group_dir.is_dir():
            continue
        problems.extend(_helpers_problems(group_dir, runner))
        for epic_dir in _entries(group_dir):
            if epic_dir.is_dir() and not _is_epic(epic_dir):
                # What this group's tests share, checked above as itself: it
                # holds no promises, so the rules an epic is held to would
                # read every file in it as an outcome gone wrong.
                continue
            if not epic_dir.is_dir():
                if runner.keeps_files_beside_its_epics:
                    # This group's runner lives here: the build context a
                    # `custom` runner's Dockerfile is read from -- an
                    # entrypoint, a lockfile, whatever it builds from -- or
                    # the executable a `tap` group is started through.
                    continue
                problems.append(
                    OutcomeProblem(
                        epic_dir,
                        "a file where the layout has only epic directories -- a prompt or a "
                        "test filed here has no outcome directory to be paired inside. Only "
                        f"a group run by a '{CUSTOM}' or '{TAP}' runner keeps files at this "
                        "level, where that runner itself lives.",
                    )
                )
                continue
            if not is_valid_slug(epic_dir.name):
                problems.append(OutcomeProblem(epic_dir, f"epic name is {_NOT_A_SLUG}"))

            for outcome_dir in _entries(epic_dir):
                if not outcome_dir.is_dir():
                    problems.append(
                        OutcomeProblem(
                            outcome_dir,
                            "a file where the layout has only outcome directories -- a prompt "
                            "belongs inside the outcome it describes, beside its translation.",
                        )
                    )
                    continue
                if not is_valid_slug(outcome_dir.name):
                    problems.append(
                        OutcomeProblem(outcome_dir, f"outcome name is {_NOT_A_SLUG}")
                    )
                problems.extend(_outcome_problems(outcome_dir, runner))
    return problems


@dataclass(frozen=True)
class UnownedOutcome:
    """One path in the outcome tree that a change could reach without a
    human being asked. `rule` is the CODEOWNERS rule that decided it, or
    None where nothing in the file matched at all -- the two are different
    mistakes and the fix differs, so the report says which."""

    path: Path
    rule: Rule | None

    def describe(self, relative_to: Path) -> str:
        try:
            where = self.path.relative_to(relative_to)
        except ValueError:
            where = self.path
        if self.rule is None:
            return f"{where}: no CODEOWNERS rule matches it."
        return (
            f"{where}: the last rule matching it, '{self.rule.pattern}' "
            f"(line {self.rule.line}), names no owner."
        )


def unowned_outcomes(outcomes_dir: Path, codeowners: CodeOwners) -> list[UnownedOutcome]:
    """Everything in the tree a change could reach without human review.
    Empty means the merge gate covers the whole tree.

    Each outcome is checked twice over, because the two halves catch
    different things and neither implies the other. The outcome *directory*
    is what covers files that do not exist yet: a translation written next
    week is owned by the rule already covering the directory it lands in,
    rather than by an entry somebody has to remember to add alongside it.
    The *files* are what catch a narrower later rule quietly taking
    ownership back off something already in the tree.

    `prompt.md` is held to the same rule as the rest. The prompt is what an
    epic promises; an agent free to rewrite the promise never has to touch a
    test to change what the project claims. So is a quarantine note, for the
    same reason turned round: a promise can be excused from failing a run
    without its test changing at all, which is a way to a green suite that
    never went near the application.

    So is a group's `helpers/`, checked the same two ways. A helper holds
    whatever several translations share, which is as likely to be the
    assertion as the navigation -- so one a change could reach without
    review is a way to defang every test importing it, without touching a
    test at all. It is the outcome directory's own argument made once for a
    group, and it is the reason this walks the tree's groups rather than
    only its outcomes.

    An outcome whose directory is unowned is reported at the directory and
    left there: every file inside it is unowned for that same reason, and
    one rule fixes all of them, so listing them adds length rather than
    information. A group's helpers are reported the same way.
    """
    unowned: list[UnownedOutcome] = []
    for group in sorted(runners_by_group(outcomes_dir)):
        directory = outcomes_dir / group / HELPERS_DIR_NAME
        if not directory.is_dir():
            continue
        directory_rule = codeowners.deciding_rule(directory, is_dir=True)
        if directory_rule is None or not directory_rule.owns_anything:
            unowned.append(UnownedOutcome(directory, directory_rule))
            continue
        for path in helper_files(outcomes_dir / group):
            rule = codeowners.deciding_rule(path, is_dir=False)
            if rule is None or not rule.owns_anything:
                unowned.append(UnownedOutcome(path, rule))

    for outcome in discover_outcomes(outcomes_dir):
        directory_rule = codeowners.deciding_rule(outcome.directory, is_dir=True)
        if directory_rule is None or not directory_rule.owns_anything:
            unowned.append(UnownedOutcome(outcome.directory, directory_rule))
            continue
        note = outcome.directory / QUARANTINE_FILENAME
        governed = [outcome.prompt, *outcome.translation]
        if note.is_file():
            governed.append(note)
        for path in governed:
            rule = codeowners.deciding_rule(path, is_dir=False)
            if rule is None or not rule.owns_anything:
                unowned.append(UnownedOutcome(path, rule))
    return unowned
