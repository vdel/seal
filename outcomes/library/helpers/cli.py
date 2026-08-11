"""Invoking the application these promises are about.

The application here is the `seal` CLI in this checkout -- not whatever
`seal` happens to be installed on the machine, which would have a
promise reported kept or broken about code nobody is changing. So every
check runs the checkout, through `uv`, which is how this repository's own
Python is run everywhere else.

A run is captured rather than streamed: what a check asserts on is what the
command said, and the interesting cases here are the refusals, where the
message naming every offender *is* the promise.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from helpers.verdict import cannot_run

# This checkout: the CLI under test, and the Python project that provides it.
REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_DIR = REPO_ROOT / "python"

# Long enough that a slow machine is not a failure, short enough that a
# command waiting on something that will never arrive is reported rather
# than hanging until somebody kills the suite. Commands that bring an
# environment up pass their own.
DEFAULT_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class Run:
    """What a command did, as a check reads it."""

    status: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        """Both streams, for asserting on a message without having to know
        which one a command chose to print it on."""
        return self.stdout + self.stderr

    def __str__(self) -> str:
        return f"exit {self.status}\n--- stdout ---\n{self.stdout}--- stderr ---\n{self.stderr}"


def seal_available() -> str:
    """Why the CLI cannot be run here, or the empty string when it can."""
    if not PACKAGE_DIR.is_dir():
        # A check run from somewhere other than the tree it belongs to: the
        # checkout it means by "the application" is not above it. Said out
        # loud, because the alternative is a package manager's own error
        # about a directory nobody mentioned.
        return f"{PACKAGE_DIR} is not there, so this check is not inside the checkout it tests"
    if shutil.which("uv") is None:
        return "uv is not on PATH, and it is what runs this checkout's seal"
    return ""


def seal(
    *arguments: str,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> Run:
    """Run the CLI in a project, the way somebody working in that project
    would: from its root, with the arguments they would type.

    `env` adds to the environment rather than replacing it -- a command that
    reaches for a container runtime needs the caller's PATH and its
    configuration, and a check that stripped those would be testing a
    machine nobody has.
    """
    reason = seal_available()
    if reason:
        cannot_run(reason)
    completed = subprocess.run(
        ["uv", "run", "--project", str(PACKAGE_DIR), "seal", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, **(env or {})},
    )
    return Run(completed.returncode, completed.stdout, completed.stderr)
