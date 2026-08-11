"""Whether a change has reached the outcome tree, read from the repository
it is in.

The rule a regression loop turns on is that a fix goes in the application and
never in the test: a suite passes identically whether the application was
fixed or the test rewritten, and the whole gate is the difference between
those two (see /rfcs/0009-outcome-tests.md). CODEOWNERS is what enforces it,
and that enforcement is real -- but it lands at the merge, which is many
iterations and a great deal of somebody's time after the line was crossed. A
session that spent four rounds converging on a change that cannot merge
unattended has spent four rounds, and hears about it from a review it wasn't
expecting.

This is the part of that boundary a checkout can answer for itself: which
paths under the outcome tree differ from a ref. Nothing here infers what a
session did or meant to do -- it is a diff, which is exactly the kind of
claim seal is willing to make from a repository.

**It reports; it does not enforce.** Touching the tree is an ordinary,
legitimate thing to do -- a translation has to be written, a promise has to
be able to change -- and what it costs is a human's approval rather than
correctness. A second mechanism that could refuse what CODEOWNERS allows, or
allow what it refuses, would make a green run mean less rather than more.

Untracked files count. A new spec file nobody has added yet is a translation
nobody has reviewed just as much as an edited one is, and "it isn't in git
yet" is not a distinction the gate makes.
"""

import subprocess
from pathlib import Path

from seal.credentials import SealError

# Where the default comparison comes from, in the order these are tried. The
# honest question is "has this change touched a promise?", and a change is
# what a branch holds rather than what has not been committed yet -- so the
# base is the point it diverged from the branch it will merge into.
#
# Worked out from the repository rather than configured: a project that knows
# better says so with --since, and one that doesn't shouldn't have to declare
# what git already knows.
DEFAULT_BASE_CANDIDATES = ("origin/HEAD", "origin/main", "main", "master")


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def default_base(repo_root: Path) -> str | None:
    """The ref a change is measured against when nobody named one, or None
    where the repository offers nothing to measure against -- a checkout with
    no commits, or one whose branch names this knows nothing about."""
    for candidate in DEFAULT_BASE_CANDIDATES:
        if _git(repo_root, "rev-parse", "--verify", "--quiet", candidate).returncode == 0:
            return candidate
    return None


def _merge_base(repo_root: Path, ref: str) -> str:
    """Where this branch left `ref`, or `ref` itself where they have no common
    history to speak of.

    The merge base rather than the ref's own tip: what a change is
    responsible for is what it added, not everything that has happened on the
    branch it will merge into since.
    """
    found = _git(repo_root, "merge-base", ref, "HEAD")
    return found.stdout.strip() if found.returncode == 0 else ref


def touched(repo_root: Path, outcomes_dir: Path, since: str | None) -> list[Path]:
    """Every path under the outcome tree this working tree has changed
    relative to `since`, in path order and as absolute paths.

    Staged, unstaged and untracked alike. Which of the three a file is in is
    a fact about somebody's next commit, and the question here is what the
    change contains.
    """
    base = since or default_base(repo_root)
    if base is None:
        raise SealError(
            "Error: nothing to compare against. This repository has no branch `seal "
            "outcomes touched` knows to measure a change from "
            f"({', '.join(DEFAULT_BASE_CANDIDATES)}), so name one with --since."
        )
    if _git(repo_root, "rev-parse", "--verify", "--quiet", base).returncode != 0:
        raise SealError(f"Error: '{base}' is not a ref in this repository.")

    try:
        prefix = outcomes_dir.resolve().relative_to(repo_root.resolve())
    except ValueError:
        # An outcome tree outside the repository the project sits in. Nothing
        # git can say about it, and nothing CODEOWNERS could cover either.
        return []

    changed = _git(
        repo_root, "diff", "--name-only", _merge_base(repo_root, base), "--", str(prefix)
    )
    if changed.returncode != 0:
        raise SealError(f"Error: `git diff` failed: {changed.stderr.strip()}")
    untracked = _git(
        repo_root, "ls-files", "--others", "--exclude-standard", "--", str(prefix)
    )

    named = set(changed.stdout.split("\n")) | set(untracked.stdout.split("\n"))
    return sorted(repo_root / name for name in named if name.strip())
