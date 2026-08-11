"""This repository's own outcome tree, held to the rules it holds others to.

Seal promises things to an adopting project, and those promises live
in `/outcomes/` like any project's (see
/rfcs/0014-seal-on-seal.md). That makes this repository a
consumer of its own library, and these are the checks a consumer gets.

Not library tests. Everything else in this suite builds the project it
asserts on, so that what is checked is what an adopting project gets rather
than what this repository happens to hold (/rfcs/0001-library-boundary.md).
These deliberately do the opposite: they assert on this repository, because
this repository's specification is the thing under test. Keeping them in a
file of their own is what stops that exception from spreading.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from seal.codeowners import find_codeowners

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECIFICATION = REPO_ROOT / "outcomes"
GROUP = SPECIFICATION / "library"
HELPERS = GROUP / "helpers"
DECISION_RECORD = REPO_ROOT / "rfcs" / "0014-seal-on-seal.md"


def _seal(*args: str) -> subprocess.CompletedProcess:
    """The CLI, run against this repository the way somebody would.

    Through the interpreter running these tests rather than a console script,
    so this passes or fails on the code in the checkout rather than on
    whatever `seal` happens to be installed on the machine.
    """
    return subprocess.run(
        [sys.executable, "-m", "seal.seal", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "python" / "src")},
    )


def test_this_repositorys_specification_passes_its_own_check():
    """The whole point of adopting the tree here. Whatever `seal check`
    refuses an adopting project for, it refuses this repository for."""
    result = _seal("check")

    assert result.returncode == 0, result.stdout + result.stderr


def test_what_starts_this_groups_promises_can_be_started():
    """Git records the executable bit and a checkout onto a filesystem that
    drops it does not. `seal check` refuses that too -- this fails in
    the same run rather than waiting for somebody to try a suite."""
    runner = GROUP / "run"

    assert runner.is_file(), f"{runner} is what starts this group"
    assert os.access(runner, os.X_OK), f"{runner} is not executable"


def test_what_this_groups_checks_share_lives_in_the_tree():
    """The checks here build the projects they point a command at, and every
    one of them would otherwise spell that out again. Shared code sits in the
    group beside the epics -- and a tree holding it is still a tree
    `seal check` accepts, which the check above establishes."""
    assert HELPERS.is_dir(), f"{HELPERS} is where this group's checks share what they share"


def test_what_this_groups_checks_share_needs_a_code_owner_too():
    """An assertion moves into shared code as readily as it moves into a
    test. One a change could reach without review would defang every check
    importing it, which is the same hole an unowned test is -- so the rule
    that covers the tests has to reach here as well."""
    codeowners = find_codeowners(REPO_ROOT)

    assert codeowners is not None, "this repository has a CODEOWNERS"
    uncovered = [
        path
        for path in [HELPERS, *sorted(HELPERS.rglob("*"))]
        if not codeowners.owners_for(path, path.is_dir())
    ]

    assert uncovered == [], (
        "what this group's checks share can be changed without a code owner: "
        + ", ".join(_relative(path) for path in uncovered)
    )


def test_what_this_repository_promises_can_be_listed():
    """The question the tree exists to answer, asked the way anybody would
    ask it."""
    result = _seal("outcomes")

    assert result.returncode == 0, result.stdout + result.stderr


def _headline(text: str) -> str:
    """A promise as both documents spell it.

    Trailing periods and line wrapping are the two ways one source can
    write a promise differently from the other without meaning anything
    different, so neither counts as a disagreement.
    """
    return " ".join(text.split()).rstrip(".")


def _promised() -> set[str]:
    """Every promise RFC 0014 states.

    Read off the bullets under "The promises" rather than a list written
    here: one written in this file would agree with itself while disagreeing
    with the decision record.
    """
    record = DECISION_RECORD.read_text(encoding="utf-8")
    promises = record.split("## The promises")[1].split("## Rationale")[0]
    return {
        _headline(match.group(1))
        for match in re.finditer(r"^- \*\*(.+?)\*\*", promises, re.MULTILINE | re.DOTALL)
    }


def _written_down() -> dict[str, Path]:
    """Every promise the tree holds, by headline, and where it is."""
    written = {}
    for prompt in sorted(GROUP.rglob("prompt.md")):
        first = next(
            line for line in prompt.read_text(encoding="utf-8").splitlines() if line.strip()
        )
        written[_headline(first.removeprefix("# "))] = prompt.parent
    return written


def _relative(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def test_every_promise_the_decision_record_states_is_written_down():
    """The failure that matters. A promise stated in RFC 0014 and absent
    from the tree is one the listing does not report -- so the question the
    tree exists to answer, "what does Seal promise", gets an answer
    short of the truth, and nothing says so."""
    missing = sorted(_promised() - set(_written_down()))

    assert missing == [], (
        f"{_relative(DECISION_RECORD)} states promises the specification does not "
        f"hold, so they are promised and unreported: {missing}"
    )


def test_the_tree_promises_nothing_the_decision_record_does_not():
    """The other direction. A promise in the tree with no decision behind it
    is one nobody agreed to make -- and it would be reported, translated and
    eventually gated on."""
    written = _written_down()
    unbacked = sorted(set(written) - _promised())

    assert unbacked == [], (
        f"the specification holds promises {_relative(DECISION_RECORD)} does not "
        "state: "
        + ", ".join(f"{name!r} ({_relative(written[name])})" for name in unbacked)
    )


def test_the_two_are_matched_on_what_they_both_carry():
    """A guard that cannot fail is worse than none, so this says out loud
    what the two above compare.

    Headlines, because that is the thing both documents actually carry. A
    slug is derived from a headline, and two things derived from one source
    cannot disagree -- matching on those would be a check that always
    passes.
    """
    promised = _promised()

    assert promised, f"read no promises out of {_relative(DECISION_RECORD)}"
    assert len(_written_down()) == len(promised)
