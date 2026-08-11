"""How a check says what it found.

A check is an ordinary program: it exits 0 for a promise it saw kept, and
non-zero for one it saw broken. The third answer is the one worth writing
down carefully -- a check that could not run at all has established nothing,
and reporting that as either of the first two would be an invention. So it
exits CANNOT_RUN, and the group's `run` turns that into a test point with no
verdict.

Why a check prints its reason on stderr: seal folds a `tap` runner's
stderr into the stream it keeps, so whatever a check says lands beside the
point it failed, which is what somebody reads when a promise goes red.
"""

import sys
import traceback
from typing import Callable, NoReturn

# What a check exits when it could not establish anything -- the machine is
# missing something the promise needs, not the application. Chosen well clear
# of the codes a program is likely to exit by accident: an assertion failure
# is 1, a Python traceback is 1, and a signal is 128+n.
CANNOT_RUN = 99


class Failed(Exception):
    """A promise this check saw broken. Carries what was expected and what
    happened, because a bare `not ok` sends somebody to read the check to
    find out what it even asked."""


def expect(condition: bool, what: str) -> None:
    """Assert, in the check's own words.

    `what` reads as the thing that should have been true -- "the run was
    refused before anything was built" -- so the failure says which promise
    was not kept rather than which line of Python was surprised.
    """
    if not condition:
        raise Failed(what)


def cannot_run(reason: str) -> NoReturn:
    """Stop, having established nothing.

    For a machine missing what this check needs. Never for a promise that
    looks hard to test: the whole point of the specification is that a
    promise nothing checks is reported as unchecked, and a check that
    reached for this to avoid an awkward assertion would be hiding in the
    one place designed to be honest about gaps.
    """
    print(f"cannot run: {reason}", file=sys.stderr)
    sys.exit(CANNOT_RUN)


def check(body: Callable[[], None]) -> NoReturn:
    """Run a check's body and exit the way its verdict says.

    Every failure ends here rather than as a traceback: a promise seen
    broken and a check that crashed are both `not ok`, and the difference
    between them is in the output, where somebody can read it.
    """
    try:
        body()
    except Failed as failure:
        print(f"promise not kept: {failure}", file=sys.stderr)
        sys.exit(1)
    except Exception:  # noqa: BLE001 -- a check that crashed is a check that failed
        traceback.print_exc()
        print("the check itself raised -- no promise was established", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)
