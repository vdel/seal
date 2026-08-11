"""Invoking `bin/install-seal-skills`, which both outcomes in
`working-with-an-agent/` need and neither owns on its own.

The first promise is that an agent finds Seal the same way in any
project that adopted it; the second is that a project can tell when what it
installed has fallen behind what ships. Both are the installer's business
end-to-end -- what it writes into a project, and what its own `--check`
reports about that project -- so both checks run the same script the same
way rather than each re-implementing the invocation.

This runs the installer from *this checkout*, not whatever copy of it might
already be on the machine's PATH: what these promises are about is
Seal as it is on disk right now, not a previously published version of
it.
"""

import subprocess
from pathlib import Path

from helpers.cli import REPO_ROOT, Run
from helpers.verdict import cannot_run

INSTALLER = REPO_ROOT / "bin" / "install-seal-skills"


def installer_available() -> str:
    """Why the installer cannot be run here, or the empty string when it can."""
    if not INSTALLER.is_file():
        return f"{INSTALLER} is not there, so this check is not inside the checkout it tests"
    return ""


def install_skills(target: Path, *arguments: str) -> Run:
    """Run the installer against `target`, sourcing from this checkout's own
    `.claude/` -- the deliverable being checked, not a clone of some ref."""
    reason = installer_available()
    if reason:
        cannot_run(reason)
    completed = subprocess.run(
        [str(INSTALLER), "--target", str(target), "--from", str(REPO_ROOT), *arguments],
        capture_output=True,
        text=True,
    )
    return Run(completed.returncode, completed.stdout, completed.stderr)
