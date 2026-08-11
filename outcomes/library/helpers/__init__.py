"""What this group's checks share.

Every promise here is about Seal itself, so a check points a command
at a project and reads what happened. Three things are the same in all of
them and live here rather than in fifteen copies: building the project to
point at, invoking the CLI, and saying what the check found.

What a check must never do is pass because it could not run. A machine
without what a promise needs -- a container runtime, a cluster -- leaves no
verdict, which the group's `run` reports as a promise nothing established
(/rfcs/0011-outcome-runners.md). `cannot_run()` is how a check says that,
and it is the only way out of one besides a verdict.
"""

from helpers.cli import seal, seal_available
from helpers.cluster import a_cluster, a_session, deployed, kubectl, what_is_missing
from helpers.projects import Project, project
from helpers.verdict import CANNOT_RUN, Failed, cannot_run, check, expect

__all__ = [
    "CANNOT_RUN",
    "a_cluster",
    "a_session",
    "deployed",
    "kubectl",
    "what_is_missing",
    "Failed",
    "Project",
    "seal",
    "seal_available",
    "cannot_run",
    "check",
    "expect",
    "project",
]
