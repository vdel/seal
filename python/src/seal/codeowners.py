"""Who has to review a change to a given path, read the way GitHub reads it.

The merge gate the outcome-test design rests on is a claim about GitHub's
behaviour: a diff touching an outcome test cannot merge without a human
approving it, because CODEOWNERS says so. A check that verifies that claim
is only worth as much as its agreement with GitHub -- resolve ownership
differently and the check passes on a tree GitHub leaves unguarded, which
is worse than having no check, since it reports a gate that isn't there.

So this reads CODEOWNERS on GitHub's terms:

- **Three locations.** The repository root, `.github/` and `docs/`, in that
  precedence order. Nowhere else counts: a file GitHub never reads owns
  nothing, however sensible its contents.
- **Relative to the repository, not the project.** Patterns are anchored at
  the repo root, and the repo is what has a `.git`. An seal project nested
  inside a larger repository is governed by that repository's CODEOWNERS,
  at paths that include the project's own directory prefix.
- **Last matching rule wins.** Not the most specific, and not the union:
  the final rule to match a path decides it alone. Which is why a rule with
  a pattern and no owners is a rule like any other here rather than a line
  to skip -- it is how ownership gets *cleared*, and clearing it is exactly
  what a gate has to notice.
- **Gitignore-style patterns, minus what GitHub drops.** No `!` negation
  and no `[a-z]` character ranges, both of which GitHub rejects; a `[` is a
  literal. `*` and `?` stop at a `/`, `**` spans directories, a leading `/`
  or an interior one anchors the pattern to the repo root, and a pattern
  with no `/` at all matches a name at any depth. A pattern that matches a
  directory matches everything beneath it, whether or not it is written
  with a trailing `/`.

Section headers (`[Name]`, `^[Name]`) are read as section headers and own
nothing. GitHub's sectioned CODEOWNERS resolves ownership as the union
across sections rather than by last match, so a rule read out of its
section could claim more than GitHub grants; skipping the header keeps the
reading here to the last-match semantics the rest of the file has.

Nothing here reaches the network. Whether an owner handle names a real
account, a real team, or somebody with write access is not answerable from
a checkout, and every static check seal runs has to work without one.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CODEOWNERS_FILENAME = "CODEOWNERS"
# GitHub's own precedence order: the first of these that exists is the one
# it reads, and the others are ignored entirely rather than merged.
CODEOWNERS_LOCATIONS = (".", ".github", "docs")

_GIT_DIR_NAME = ".git"


def find_repository_root(start: Path) -> Path | None:
    """The git repository `start` is inside, or None if it isn't in one.

    `.git` is matched as either a directory or a file, since a worktree or a
    submodule keeps a file there pointing at the real one."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / _GIT_DIR_NAME).exists():
            return candidate
    return None


@lru_cache(maxsize=None)
def _compile(pattern: str) -> tuple[re.Pattern[str], bool, bool]:
    """One CODEOWNERS pattern, as the three things matching it needs: the
    regex for the name (or path) it spells out, whether that is anchored at
    the repository root, and whether it matches directories only."""
    body = pattern[1:] if pattern.startswith("/") else pattern
    directories_only = body.endswith("/")
    body = body.rstrip("/")
    # A pattern with a `/` anywhere but its end is a path from the
    # repository root; one without is a name matched at any depth.
    anchored = pattern.startswith("/") or "/" in body

    parts: list[str] = []
    index = 0
    length = len(body)
    while index < length:
        character = body[index]
        if character == "*":
            run = index
            while run < length and body[run] == "*":
                run += 1
            if run - index >= 2:
                if run < length and body[run] == "/":
                    # `**/` -- any number of leading directories, none included.
                    parts.append("(?:[^/]+/)*")
                    index = run + 1
                    continue
                parts.append(".*")
                index = run
                continue
            parts.append("[^/]*")
            index += 1
        elif character == "?":
            parts.append("[^/]")
            index += 1
        else:
            # `[` is escaped rather than opening a character range: GitHub
            # doesn't support ranges, so a project that writes one gets a
            # literal bracket matched, the same as GitHub gives it.
            parts.append(re.escape(character))
            index += 1
    return re.compile("".join(parts)), anchored, directories_only


@dataclass(frozen=True)
class Rule:
    """One `pattern owner...` line. `owners` is empty for a line that names a
    pattern and nobody, which is how a file takes ownership back off a path
    an earlier rule granted."""

    pattern: str
    owners: tuple[str, ...]
    line: int

    @property
    def owns_anything(self) -> bool:
        return bool(self.owners)

    def matches(self, relative_path: str, is_dir: bool) -> bool:
        """Whether this rule decides `relative_path`, given relative to the
        repository root and written with `/` separators.

        A pattern matching a directory matches everything under it, so each
        of the path's ancestors is tried as well as the path itself. The
        `is_dir` flag only settles the path's own case: a `foo/` pattern
        matches the file `foo/bar` through its ancestor `foo`, but never a
        *file* named `foo`."""
        regex, anchored, directories_only = _compile(self.pattern)
        components = [part for part in relative_path.split("/") if part]
        if not components:
            return False

        if anchored:
            candidates = [
                ("/".join(components[:depth]), depth == len(components))
                for depth in range(1, len(components) + 1)
            ]
        else:
            candidates = [
                (component, index == len(components) - 1)
                for index, component in enumerate(components)
            ]

        for candidate, is_the_path_itself in candidates:
            if not regex.fullmatch(candidate):
                continue
            if is_the_path_itself and directories_only and not is_dir:
                continue
            return True
        return False


def _is_section_header(token: str) -> bool:
    return token.startswith("[") or token.startswith("^[")


def parse_codeowners(text: str, *, source: Path, root: Path) -> "CodeOwners":
    """Every rule in a CODEOWNERS file, in file order -- which is the order
    that decides ownership, so it is preserved rather than indexed."""
    rules: list[Rule] = []
    for number, line in enumerate(text.splitlines(), start=1):
        tokens = line.split()
        if not tokens or tokens[0].startswith("#") or _is_section_header(tokens[0]):
            continue
        pattern, rest = tokens[0], tokens[1:]
        owners: list[str] = []
        for token in rest:
            if token.startswith("#"):
                break  # a trailing comment, not an owner
            owners.append(token)
        rules.append(Rule(pattern=pattern, owners=tuple(owners), line=number))
    return CodeOwners(source=source, root=root, rules=tuple(rules))


@dataclass(frozen=True)
class CodeOwners:
    """A repository's CODEOWNERS: the file that was read, the root its
    patterns are anchored at, and its rules in file order."""

    source: Path
    root: Path
    rules: tuple[Rule, ...]

    def _relative(self, path: Path) -> str:
        """`path` as CODEOWNERS sees it: relative to the repository root,
        `/`-separated. A path already relative is taken as given; one outside
        the repository entirely resolves to nothing, since no pattern in the
        file can reach a path GitHub would never be asked about."""
        if not path.is_absolute():
            return path.as_posix()
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return ""

    def deciding_rule(self, path: Path, is_dir: bool) -> Rule | None:
        """The rule that settles this path, or None if none matches it.

        The rule is returned rather than just its owners because a report
        that says *which* line left a path unowned is the difference between
        a fixable failure and a puzzle."""
        relative_path = self._relative(path)
        if not relative_path:
            return None
        for rule in reversed(self.rules):
            if rule.matches(relative_path, is_dir):
                return rule
        return None

    def owners_for(self, path: Path, is_dir: bool) -> tuple[str, ...]:
        """Who has to review a change to this path. Empty means nobody --
        whether because no rule matched it or because the one that did names
        no owners."""
        rule = self.deciding_rule(path, is_dir)
        return rule.owners if rule else ()


def find_codeowners(repo_root: Path) -> CodeOwners | None:
    """The repository's CODEOWNERS, read from the first of GitHub's three
    locations that has one. None means the repository has no CODEOWNERS at
    all, which is a different thing from one that owns nothing."""
    for location in CODEOWNERS_LOCATIONS:
        candidate = repo_root / location / CODEOWNERS_FILENAME
        if candidate.is_file():
            return parse_codeowners(
                candidate.read_text(encoding="utf-8"), source=candidate, root=repo_root
            )
    return None
