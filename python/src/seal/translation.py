"""Turning one promise into a task somebody can actually do.

An outcome prompt is what an epic promises; a low-level test is one
reading of that promise against the implementation as it stands. Getting
from the first to the second is the lossy step the whole design is built
around -- two translators produce different tests from the same prompt,
each encoding implementation choices the prompt never made -- which is why
a human has to approve the result (see /rfcs/0009-outcome-tests.md).

seal's half of that is not writing the test. It is making the task
well-posed and the answer checkable: the brief below gathers everything a
translation needs, read off the project it is invoked in, and `seal check`
plus `seal outcomes run` say whether what came back holds up. Nothing here
starts an agent. seal cannot verify from a checkout what an agent session
did, and a capability that cannot be verified is one this repo does not
claim -- the same boundary it draws around clusters, registries and a
repository's own settings.

The brief is prose on stdout rather than a structured document. Its reader
is whatever is writing the test -- an agent session, or a person -- and both
read the same thing, which is also what stops the brief drifting into
something only a machine consumes and nobody proofreads.

The review is the same material turned round for the other audience. A
change that only adds a translation shows the test and not the prompt --
the prompt did not change, so it is not in the diff -- while the question
in front of the reviewer is precisely whether the one encodes the other. So
this puts them side by side, says what has already been settled
mechanically, and stops where judgement starts.
"""

import textwrap
from pathlib import Path

from seal.outcomes import (
    HELPERS_DIR_NAME,
    SPEC_SUFFIXES,
    Outcome,
    waits_on_the_clock,
)
from seal.runners import (
    ARGUMENT_SEPARATOR,
    CONFIG_FILENAME,
    CUSTOM,
    PLAYWRIGHT,
    TAP,
    TAP_RUNNER_FILENAME,
)
from seal.tap_group import runner_path


def _relative(path: Path, root: Path) -> str:
    """A path as the project's own root spells it, which is how a brief has
    to name one: the reader's working directory is that root, not wherever
    this happened to be invoked from."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _block(text: str, indent: str = "  ") -> list[str]:
    """A file's contents, indented into the brief without being reflowed.
    A prompt's own line breaks are the author's, and rewrapping them would
    quietly edit the promise on its way to being translated."""
    return [f"{indent}{line}".rstrip() for line in text.splitlines()]


def _promise(outcome: Outcome, root: Path, note: list[str]) -> list[str]:
    """The promise as its author wrote it, under whichever nudge the reader
    of this needs -- which is not the same one for somebody about to write a
    translation and somebody about to approve one."""
    return [
        "THE PROMISE",
        f"  {_relative(outcome.prompt, root)}",
        "",
        *_block(outcome.prompt.read_text(encoding="utf-8"), indent="    "),
        "",
        *note,
    ]


TO_TRANSLATE = [
    "  All of it, not just the headline. The prose is where the promise says",
    "  which cases it covers and -- just as binding -- what it deliberately",
    "  does not claim.",
]

TO_REVIEW = [
    "  The paragraphs saying what this promise does *not* claim are the ones to",
    "  read against the test hardest. A translation that asserts more than the",
    "  promise makes is a requirement nobody agreed to, enforced from now on by",
    "  a gate that blocks merges.",
]


def _where(outcome: Outcome, outcomes_dir: Path, root: Path) -> list[str]:
    helpers = outcomes_dir / outcome.group / HELPERS_DIR_NAME
    return [
        "WHERE THE TRANSLATION GOES",
        f"  {_relative(outcome.directory, root)}/",
        "",
        "  Beside the prompt. Fixtures and anything this test alone needs live",
        "  there too, in it or below it. That pairing is the whole of the",
        "  traceability this rests on: a reviewer reaches the promise from the",
        "  test by looking next to it.",
        "",
        "  What this group's tests share is the one exception, and it has a",
        "  directory of its own:",
        "",
        f"    {_relative(helpers, root)}/",
        "",
        "  Import from it what several outcomes would otherwise each spell out --",
        "  signing in, reaching a page, reading a value back. Read what is there",
        "  before writing your own. A helper is reviewed as hard as a test is, so",
        "  keep what this promise asserts in the test itself: a reviewer checking",
        "  it against the prompt should not have to open another file to find out",
        "  what it claims.",
    ]


def _playwright_runner_section() -> list[str]:
    # Spelled out from the constant the runner itself is generated from,
    # rather than summarised. A brief that described a slightly different
    # set would have somebody name a file the suite then does not collect,
    # and the tree reports that promise as one nobody has translated.
    collected = textwrap.wrap(
        ", ".join(SPEC_SUFFIXES), width=72, initial_indent="    ", subsequent_indent="    "
    )
    return [
        "WHAT WILL RUN IT",
        f"  The '{PLAYWRIGHT}' runner, which is seal's: Playwright, pinned to one",
        "  version together with the Chromium that version drives, and the config",
        "  generated for you.",
        "",
        "  So write spec files. What it collects is Playwright's own default, at",
        "  any depth under the outcome:",
        "",
        *collected,
        "",
        "  Everything else in the directory belongs to the translation too --",
        "  helpers, fixtures, data -- it just is not what starts it.",
        "",
        "  A Dockerfile here changes nothing: a runner belongs to the group and is",
        f"  declared once in {CONFIG_FILENAME} at the outcome tree's root, so one",
        "  inside an outcome is an ordinary file (/rfcs/0011-outcome-runners.md).",
    ]


def _tap_runner_section(outcome: Outcome, outcomes_dir: Path, root: Path) -> list[str]:
    runner = outcome.runner
    return [
        "WHAT WILL RUN IT",
        f"  This group's executable, which seal starts on the machine because",
        f"  '{runner.name}' is declared a '{TAP}' runner in "
        f"{_relative(outcomes_dir / CONFIG_FILENAME, root)}:",
        "",
        f"    {_relative(runner_path(outcomes_dir, runner.name), root)}",
        "",
        "  Read that file before writing anything. It is started once for the whole",
        f"  group -- not once per promise -- with its own arguments, then `{ARGUMENT_SEPARATOR}`,",
        "  then the outcomes this run covers, named from inside the group. This one",
        "  arrives as:",
        "",
        f"    {outcome.slug_within_group}",
        "",
        "  What it does with a slug is that file's business rather than seal's,",
        "  so what your test has to be called, and what language it is in, is decided",
        "  there.",
        "",
        "  What seal reads back is the stream, not a file: one TAP point per",
        "  outcome on stdout -- `ok` or `not ok`, then the slug exactly as it was",
        "  given. There is no verdict to write, no `done` marker, and nothing to stay",
        "  up for.",
        "",
        "  A point that never arrives, one marked `# SKIP` or `# TODO`, and a run",
        "  that dies before reaching yours are all the same thing here: no verdict.",
        "  A promise nothing established is never reported as kept, so a check that",
        "  cannot run says so rather than passing (/rfcs/0011-outcome-runners.md).",
    ]


def _custom_runner_section(outcome: Outcome, outcomes_dir: Path, root: Path) -> list[str]:
    runner = outcome.runner
    return [
        "WHAT WILL RUN IT",
        f"  This group's own runner, declared as the '{CUSTOM}' runner for",
        f"  '{runner.name}' in {_relative(outcomes_dir / CONFIG_FILENAME, root)}:",
        "",
        f"    {_relative(outcomes_dir / runner.dockerfile, root)}",
        "",
        "  Read that file before writing anything. seal has no reading of what a",
        f"  '{CUSTOM}' runner starts -- that is exactly what declaring one buys -- so",
        "  what a test has to be called, and what language it is in, is that",
        "  Dockerfile's business rather than seal's.",
        "",
        "  What seal guarantees it either way: the container is started with that",
        "  runner's own arguments, then `--`, then the outcomes this run covers,",
        f"  named from inside the group -- '{outcome.slug_within_group}' for this",
        "  one. Each verdict is read back from",
        "  /outcome-results/<epic>/<outcome>/passed (/rfcs/0011-outcome-runners.md).",
    ]


def _runner_section(outcome: Outcome, outcomes_dir: Path, root: Path) -> list[str]:
    """Whichever runner this tree actually declares. A brief describing the
    wrong one has somebody write a test nothing will start, so this reads the
    declaration rather than assuming the common case."""
    if outcome.runner.runner_type == PLAYWRIGHT:
        return _playwright_runner_section()
    if outcome.runner.runner_type == TAP:
        return _tap_runner_section(outcome, outcomes_dir, root)
    return _custom_runner_section(outcome, outcomes_dir, root)


def _reaching_the_application(runner_type: str) -> list[str]:
    if runner_type == TAP:
        return [
            "HOW THE TEST REACHES THE APPLICATION",
            "  Whatever it brings up itself. This group runs on the machine, as a",
            "  subprocess of the run, with the environment the run was invoked in and",
            "  nothing added -- no SEAL_BASE_URL, because there is no cluster to",
            "  address until something here has brought one up.",
            "",
            f"  That is what a '{TAP}' group is for: a promise about the layer beneath a",
            "  session, which nothing running inside a session can answer. So a test",
            "  here points a command at a project -- one it builds for the purpose, or",
            "  the checkout it is in -- and reads what that command did.",
            "",
            "  A project it builds is the honest fixture wherever the promise turns on",
            "  a shape the repository does not have. Asserting on a project that",
            "  happens to be lying around tests that project.",
        ]
    lines = [
        "HOW THE TEST REACHES THE APPLICATION",
        "  SEAL_BASE_URL, in the runner's environment. That is where the",
        "  application answers as a test reaches it from inside the cluster,",
        "  declared by the project in register_outcome_runner(base_url=...) in its",
        "  root Tiltfile.",
        "",
        "  Read it rather than hardcoding an address. seal knows nothing about an",
        "  application's own service names or ports, and a second copy of one is a",
        "  second thing to keep in agreement with the manifests.",
    ]
    if runner_type == PLAYWRIGHT:
        lines += [
            "",
            f"  Under the '{PLAYWRIGHT}' runner it is already Playwright's baseURL, so",
            "  a spec navigates with page.goto('/').",
        ]
    lines += [
        "",
        "  Nothing else is injected. An outcome test drives the application from",
        "  outside, the way a person does, so it does not get the application's own",
        "  credentials.",
    ]
    return lines


def _constraints() -> list[str]:
    return [
        "WHAT THE TRANSLATION HAS TO DO",
        "  Assert the promise, not the implementation. The prompt is deliberately",
        "  written in the application's own terms; the specifics are yours to",
        "  choose, and a test that pins one that could change without the promise",
        "  changing will fail for something that was never promised.",
        "",
        "  Leave withheld whatever the prompt withholds. Where it says it claims",
        "  nothing about something, asserting on that anyway is not thoroughness --",
        "  it is a promise the project never made, enforced as though it had.",
        "",
        "  Wait by polling for state, never on a fixed duration. A sleep holds on",
        "  the machine it was written on and fails wherever things are slower,",
        "  reporting a promise as broken because something was slow. Under the",
        f"  '{PLAYWRIGHT}' runner `seal check` refuses one outright.",
        "",
        "  Own the data it asserts on. Outcomes run one at a time against the same",
        "  application, and each starts from whatever the one before it left -- so a",
        "  test that adds what it is going to look for holds however the tree grows",
        "  around it.",
        "",
        "  Say where it came from, in the file itself: which prompt it was",
        "  translated from, and which choices the prompt left open were made here",
        "  and why. That paragraph is what the reviewer reads first, and it is what",
        "  separates a test somebody can check from one they can only run.",
    ]


def _verifying(outcome: Outcome) -> list[str]:
    return [
        "HOW TO CHECK IT",
        "  seal check",
        "  seal up                       # in another terminal, if nothing is up yet",
        f"  seal outcomes run {outcome.slug}",
        "",
        "  Green is necessary and not sufficient. The review is on what the test",
        "  asserts, and a test that asserts the wrong thing passes exactly as",
        "  convincingly as one that asserts the right thing. What that reviewer",
        "  will be reading is:",
        "",
        f"  seal outcomes review {outcome.slug}",
    ]


def _replacing(outcome: Outcome, root: Path) -> list[str]:
    return [
        "REPLACING A COMMITTED TRANSLATION",
        "  This outcome already has one:",
        *[f"    {_relative(path, root)}" for path in outcome.translation],
        "",
        "  Read it first. A rewrite reaches a human the same way first authorship",
        "  does, but the question in front of that reviewer is a different one:",
        "  what does this reading assert that the committed one did not, and is",
        "  that a better reading of the same promise or a different promise? If it",
        "  is the second, the prompt is what should be changing, and that is a",
        "  conversation to have before writing the test rather than after.",
    ]


def translation_brief(
    outcome: Outcome, outcomes_dir: Path, root: Path, rewrite: bool = False
) -> list[str]:
    """Everything needed to compile this promise into a test, as lines.

    Assembled from the project rather than from anything seal assumes: the
    prompt as its author wrote it, the directory the pairing requires, and
    whichever runner this tree actually declares -- a brief describing
    seal's Playwright runner to a project that brought its own would have
    somebody write a test nothing will start.
    """
    lines = [
        f"Translate one promise into a test: {outcome.slug}",
        "",
        "  A low-level test is one reading of a promise against the implementation",
        "  as it stands. Because the reading is yours and the promise is the",
        "  project's, a code owner approves the result before it can merge -- so",
        "  write it to be checked against the promise, not merely to pass",
        "  (/rfcs/0009-outcome-tests.md).",
        "",
    ]
    if rewrite:
        lines += _replacing(outcome, root) + [""]
    sections = [
        _promise(outcome, root, TO_TRANSLATE),
        _where(outcome, outcomes_dir, root),
        _runner_section(outcome, outcomes_dir, root),
        _reaching_the_application(outcome.runner.runner_type),
        _constraints(),
        _verifying(outcome),
    ]
    for section in sections:
        lines += section + [""]
    return lines[:-1]


def already_translated(outcome: Outcome, root: Path) -> list[str]:
    """Why a brief was refused, for an outcome that already has one.

    Not a warning to read past. First authorship and a full rewrite are the
    two cases the design routes through a human, and they are different
    asks -- so which one this is has to be said out loud by whoever wants
    the brief, rather than inferred later from a diff by the reviewer who
    is trying to work out what changed.
    """
    return [
        f"seal outcomes translate: {outcome.slug} already has a translation.",
        *[f"  {_relative(path, root)}" for path in outcome.translation],
        "",
        "Pass --rewrite to brief a replacement of it. Writing a second reading of "
        "a promise over a committed one, without having said that is what is "
        "happening, leaves the reviewer to work out from the diff alone whether "
        "the test changed or the promise did.",
    ]


NOT_TEXT = "(not text -- {size} bytes, part of the translation but nothing to read here)"


def _file(path: Path, root: Path) -> list[str]:
    lines = [f"  {_relative(path, root)}", ""]
    try:
        return lines + _block(path.read_text(encoding="utf-8"), indent="    ")
    except (UnicodeDecodeError, OSError):
        # A fixture the translation carries -- an image, an archive. Named
        # rather than skipped: what a test seeds itself from is as much a
        # part of what it asserts as the assertions are, so a reviewer has
        # to be told it exists even where its contents mean nothing here.
        return lines + [f"    {NOT_TEXT.format(size=path.stat().st_size)}"]


def _translation(outcome: Outcome, root: Path) -> list[str]:
    lines = ["THE TRANSLATION", ""]
    for path in outcome.translation:
        lines += _file(path, root) + [""]
    return lines[:-1]


def _collected(outcome: Outcome, root: Path) -> list[str]:
    """Which files of the translation actually start a test, where seal is
    what starts it. The distinction matters to a reviewer: a helper is read
    for what it does to the assertions, and a file nothing collects is read
    for whether anything reaches it at all."""
    if outcome.runner.runner_type != PLAYWRIGHT:
        starts = (
            f"this group's own {TAP_RUNNER_FILENAME}, which seal starts on the machine"
            if outcome.runner.runner_type == TAP
            else "this group's own runner"
        )
        return [
            f"  What starts a test here is {starts}, so which of the",
            "  files above it reaches is that runner's business rather than something",
            "  seal can tell you.",
        ]
    collected = [
        path for path in outcome.translation if path.name.endswith(SPEC_SUFFIXES)
    ]
    if not collected:
        return [
            f"  Started by the '{PLAYWRIGHT}' runner: nothing. No file here is named",
            "  the way that runner collects, so the suite reports this promise as",
            "  untested while a test sits in the tree -- `seal check` refuses it.",
        ]
    return [
        f"  Started by the '{PLAYWRIGHT}' runner:",
        *[f"    {_relative(path, root)}" for path in collected],
        "",
        "  Anything above that isn't in that list is read by something that is,",
        "  or by nothing at all.",
    ]


def _shared(outcome: Outcome, outcomes_dir: Path, root: Path) -> list[str]:
    """That this group keeps helpers, where a reviewer will not have seen
    them.

    A translation that imports one is reviewed against a file the diff may
    not carry and this deliberately does not render -- the outcome's own
    directory is what a review is of. Naming the directory is what stops a
    reviewer reading an import as something out of scope: it is inside the
    tree, covered by the same rule, and held to the same check.
    """
    helpers = outcomes_dir / outcome.group / HELPERS_DIR_NAME
    if not helpers.is_dir():
        return []
    return [
        "",
        f"  What it may import: {_relative(helpers, root)}/, what this group's tests",
        "  share. A review is of one outcome, so what is rendered above is this",
        "  outcome's own directory -- open that one where an import points into it.",
        "  It is inside the tree: checked like the rest of it, and covered by what",
        "  is said below about who can change this test.",
    ]


def _already_checked(
    outcome: Outcome, outcomes_dir: Path, root: Path, unowned: tuple[Path, ...] | None
) -> list[str]:
    """What a machine has already settled about this translation.

    Every line of it is read from the code `seal check` runs, rather than
    restated here. A rule that meant one thing to the check and another to a
    review would be worse than no summary at all: it would spend a
    reviewer's attention on re-deriving what they had just been told.
    """
    if outcome.runner.runner_type == PLAYWRIGHT:
        runner = f"the '{PLAYWRIGHT}' runner, which is seal's -- Playwright"
    elif outcome.runner.runner_type == TAP:
        runner = (
            f"'{outcome.runner.name}', a '{TAP}' group: its own {TAP_RUNNER_FILENAME}, started "
            "on the machine, reporting on a stream"
        )
    else:
        runner = f"'{outcome.runner.name}', a '{CUSTOM}' runner this project brought"
    sleeps = [path for path in outcome.translation if waits_on_the_clock(path)]
    if outcome.runner.runner_type != PLAYWRIGHT:
        waiting = [
            "  How it waits: not checked. seal has no reading of what a "
            f"'{outcome.runner.runner_type}'",
            "  group starts, so a sleep in it is yours to spot.",
        ]
    elif sleeps:
        waiting = [
            f"  How it waits: sleeps on the clock, in {len(sleeps)} file(s). `seal check`",
            "  refuses this, so it has not been run against the tree it is in.",
        ]
    else:
        waiting = ["  How it waits: on state, not on the clock. `seal check` agrees."]

    if unowned is None:
        ownership = [
            "  Who can change it: anyone. The repository has no CODEOWNERS, so this",
            "  test can be edited to agree with whatever it was failing about, and",
            "  approving it now buys less than it looks like it does.",
        ]
    elif unowned:
        ownership = [
            "  Who can change it: not fully gated -- CODEOWNERS leaves these uncovered:",
            *[f"    {_relative(path, root)}" for path in unowned],
        ]
    else:
        ownership = ["  Who can change it: a code owner, for every file above."]

    if outcome.quarantined:
        quarantine = [
            "",
            "  QUARANTINED. A failure here does not fail a run, so this promise is",
            "  not being enforced while that stands. The reason given:",
            *[f"    {line}" for line in outcome.quarantine.splitlines()],
        ]
    else:
        quarantine = []

    return [
        "ALREADY CHECKED",
        f"  What runs it: {runner}.",
        "",
        *_collected(outcome, root),
        *_shared(outcome, outcomes_dir, root),
        "",
        *waiting,
        "",
        *ownership,
        *quarantine,
    ]


def _left_to_you() -> list[str]:
    return [
        "LEFT TO YOU",
        "  Nothing above says whether this test encodes the promise, which is the",
        "  whole of what this review is for. Four questions a machine cannot ask:",
        "",
        "  Does it assert the promise, or an implementation detail that happens to",
        "  be true today? The second passes just as convincingly, and fails later",
        "  for something that was never promised.",
        "",
        "  Does it leave withheld what the prompt withholds? Asserting on what a",
        "  promise says it claims nothing about turns a non-promise into one, and",
        "  from then on the gate enforces it.",
        "",
        "  Would a promise-breaking change actually make this red? A test that",
        "  holds either way is a promise nothing is keeping.",
        "",
        "  Does the file say which choices the prompt left open were made here,",
        "  and why? That is what the next reader has instead of this conversation.",
    ]


def review(
    outcome: Outcome, outcomes_dir: Path, root: Path, unowned: tuple[Path, ...] | None
) -> list[str]:
    """A translation and the promise it claims to encode, side by side.

    The counterpart to the brief: the same material, turned round for the
    other audience. A translation-only change shows the test and not the
    prompt -- the prompt did not change, so it is not in the diff at all --
    while the question in front of the reviewer is precisely whether the one
    encodes the other.

    What is rendered stops where judgement starts. Summarising "what the
    test asserts" would hand the reviewer a second thing to check rather
    than less to check, and a summary that read the test more generously
    than the test reads is the one failure this cannot afford.
    """
    return [
        f"Review a translation: {outcome.slug}",
        "",
        "  A test is one reading of a promise. Whether it is the right reading is",
        "  what a code owner is for, and it is the only place review happens on",
        "  the everything-is-green path (/rfcs/0009-outcome-tests.md) -- so it",
        "  is worth spending on intent rather than on what is checked below.",
        "",
        *_promise(outcome, root, TO_REVIEW),
        "",
        *_translation(outcome, root),
        "",
        *_already_checked(outcome, outcomes_dir, root, unowned),
        "",
        *_left_to_you(),
    ]


def nothing_to_review(outcome: Outcome) -> list[str]:
    """Why a review was refused, for a promise nothing has been written from.

    An ordinary state rather than a mistake -- a promise can be written down
    long before anything compiles it into a test -- so what this says is
    what to ask for instead."""
    return [
        f"seal outcomes review: {outcome.slug} has no translation to review.",
        "",
        "A promise can be written down long before anything compiles it into a "
        "test, and this one has not been yet. What to ask for is the brief:",
        f"  seal outcomes translate {outcome.slug}",
    ]
