"""Reading a runner's TAP stream.

A `tap` group is started once and says what it found on stdout, one test
point per outcome (see /rfcs/0014-seal-on-seal.md). This module
turns that stream into what it said, and nothing more: it does not know what
a description means, that one might be a slug, or what any of it does to a
verdict. That is the caller's, and keeping it there is what lets everything
below be checked against strings.

The subset read here is the one runners actually emit -- a plan, a point per
result, directives, and a bail-out -- rather than all of TAP 13. Two shapes
are deliberately not read: subtests, which nest a stream inside a point and
would give one outcome several verdicts, and TAP 14's pragmas, which change
how a producer behaves rather than what it found.

Everything unrecognised is ignored rather than refused. A runner is a
program somebody wrote, and it prints: progress, a stack trace, whatever its
own framework says on the way past. A parser that failed on the first line
it did not recognise would turn a promise that was kept into a run that
could not be read.
"""

import re
from dataclasses import dataclass

# A test point: `ok`/`not ok`, an optional number, and an optional
# description after a `-`. The number and the dash are both optional in TAP,
# and a producer that omits them is still saying a result held.
_POINT = re.compile(
    r"""^(?P<outcome>not\ ok|ok)\b     # what it found
        (?:\s+(?P<number>\d+))?       # which point, if it says
        (?:\s*-)?                     # the separator, if it uses one
        \s*(?P<rest>.*)$              # the description, and any directive
    """,
    re.VERBOSE,
)

# `1..N`, which says how many points to expect. Anywhere in the stream: a
# producer that knows its count up front puts it first, and one that only
# knows it at the end puts it there.
_PLAN = re.compile(r"^1\.\.(?P<count>\d+)\s*(?:#.*)?$")

# A run that stopped. Everything after it is untrustworthy by the producer's
# own account, which is exactly what a caller needs to tell a promise that
# failed from one nothing reached.
_BAIL_OUT = re.compile(r"^Bail out!\s*(?P<reason>.*)$", re.IGNORECASE)

# `# SKIP` / `# TODO`, with an optional reason. Split off the description
# rather than parsed out of it, so a `#` inside a description survives: only
# a directive keyword right after the `#` counts as one.
_DIRECTIVE = re.compile(r"#\s*(?P<directive>skip|todo)\b\s*(?P<reason>.*)$", re.IGNORECASE)

SKIP = "skip"
TODO = "todo"


@dataclass(frozen=True)
class Point:
    """One result a runner reported."""

    # What it was called. The empty string where the producer named nothing,
    # which is legal TAP and useless to a caller matching on names -- so it
    # is preserved as what it is rather than invented.
    description: str
    # Whether the producer said `ok`. Meaningless on its own where
    # `directive` is set: a skipped point is written `ok` by convention and
    # established nothing.
    ok: bool
    # 'skip', 'todo', or None. The caller decides what a directive means;
    # RFC 0014 says it means no verdict, and this module does not.
    directive: str | None = None
    reason: str = ""
    # Everything the producer printed under this point -- a YAML diagnostic
    # block, comment lines, anything it wrote before the next one. Kept in
    # the order it arrived, because it is the only account of why a promise
    # was not kept.
    diagnostics: tuple[str, ...] = ()

    @property
    def established_something(self) -> bool:
        """Did this point report a result at all? A directive says it did
        not: the producer is recording that it got here and went no
        further."""
        return self.directive is None


@dataclass(frozen=True)
class Report:
    """What a stream said, and what it did not."""

    points: tuple[Point, ...]
    # How many points the producer promised, or None where it never said.
    # A plan is the only way a stream can be short rather than simply over.
    planned: int | None = None
    # Why the producer stopped, where it said it was stopping. The empty
    # string is a bail-out with no reason; None is a run that did not bail.
    bailed_out: str | None = None

    @property
    def is_short(self) -> bool:
        """Did the producer promise more points than it delivered?

        A run that bailed is short by definition and says so itself, so
        both are worth telling apart from one that simply ended -- they are
        the two ways a promise ends up with nothing said about it.
        """
        return self.planned is not None and len(self.points) < self.planned

    def by_description(self) -> dict[str, Point]:
        """Points keyed by what the producer called them.

        The last of a repeated name wins, which is the same rule a reader
        following the stream would apply -- and a duplicate is a producer
        bug the caller reports rather than a reading this can settle.
        """
        return {point.description: point for point in self.points}

    def duplicated(self) -> tuple[str, ...]:
        """Names the producer used more than once, in the order they were
        first seen. A caller matching points to what it asked for needs to
        know one answer covered two questions."""
        seen: dict[str, int] = {}
        for point in self.points:
            seen[point.description] = seen.get(point.description, 0) + 1
        return tuple(name for name, count in seen.items() if count > 1)


def _split_directive(rest: str) -> tuple[str, str | None, str]:
    """A point's description, its directive and that directive's reason.

    The directive is looked for from the right, so a `#` inside a
    description does not start one -- `ok 1 - the # in a name` is a point
    called `the # in a name`, not a skipped one.
    """
    match = None
    for candidate in _DIRECTIVE.finditer(rest):
        match = candidate
    if match is None:
        return rest.strip(), None, ""
    return (
        rest[: match.start()].strip(),
        match.group("directive").lower(),
        match.group("reason").strip(),
    )


def read(stream: str) -> Report:
    """What this TAP stream said.

    Lines are read in order and nothing is looked ahead to: a producer that
    dies mid-stream leaves a report of everything up to where it stopped,
    which is the whole reason a stream is read rather than a file waited
    for.
    """
    points: list[Point] = []
    diagnostics: list[list[str]] = []
    planned: int | None = None
    bailed_out: str | None = None

    for line in stream.splitlines():
        stripped = line.strip()

        bail = _BAIL_OUT.match(stripped)
        if bail is not None:
            # Everything after this is the producer's own admission that it
            # is no longer reporting, so reading on would be reading noise.
            bailed_out = bail.group("reason").strip()
            break

        plan = _PLAN.match(stripped)
        if plan is not None:
            planned = int(plan.group("count"))
            continue

        point = _POINT.match(stripped)
        if point is not None:
            description, directive, reason = _split_directive(point.group("rest"))
            points.append(
                Point(
                    description=description,
                    ok=point.group("outcome") == "ok",
                    directive=directive,
                    reason=reason,
                )
            )
            diagnostics.append([])
            continue

        if diagnostics:
            # Anything between one point and the next belongs to the point
            # it followed -- a YAML block, a comment, a line the runner's own
            # framework printed. Attributed rather than dropped: it is the
            # only account of why a promise was not kept.
            diagnostics[-1].append(line)

    return Report(
        points=tuple(
            Point(
                description=point.description,
                ok=point.ok,
                directive=point.directive,
                reason=point.reason,
                diagnostics=tuple(lines),
            )
            for point, lines in zip(points, diagnostics)
        ),
        planned=planned,
        bailed_out=bailed_out,
    )
