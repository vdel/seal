"""The cluster the checks that need one share.

Several of these promises are about what happens when an environment is
actually brought up, and each of them needs somewhere to bring one. Getting
that is expensive, which is exactly why this group's runner is started once
for the whole group: the cluster is got once, and every check that needs one
deploys into it in turn.

Two rules keep that from costing somebody their own machine:

**A cluster somebody is already using is borrowed, never replaced.** If the
machine points at one, that is the one these deploy into, and nothing here
deletes it. Only a cluster this suite created is one this suite tears down,
and it carries a name that says so.

**A fixture leaves nothing behind.** Projects are deployed one after another
into the same cluster, so what one left must not decide what the next one
sees.

And where the machine cannot host a cluster at all, a check establishes
nothing and says so, rather than passing: `cannot_run()` leaves the promise
with no verdict, which is what a run reports for a promise nothing vouched
for.
"""

import contextlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Iterator

from helpers.cli import PACKAGE_DIR, Run, seal
from helpers.verdict import cannot_run

# What a cluster this suite made is called. Distinct on purpose: teardown
# deletes this name and nothing else, so a suite run on somebody's own
# machine cannot take their cluster with it.
OUR_CLUSTER = "kind-seal-outcomes"

# Long enough for an image build and a rollout on a cold machine. A run that
# has not finished by then is not slow, it is stuck, and a check that waited
# forever would be reported as neither kept nor broken.
BRINGING_UP_SECONDS = 1800

# What making a cluster is given. Shorter, and separately: a machine that
# cannot host one at all fails somewhere inside this, and the difference
# between "this machine cannot" and "this check hangs" is how long anybody
# is prepared to wait to be told.
MAKING_A_CLUSTER_SECONDS = 420


def _runs(*argv: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def _a_cluster_answers() -> bool:
    """Whether the machine points at a cluster that is actually up. Asking
    the API server rather than reading kubeconfig: a context naming a cluster
    that is gone is the shape that turns into a confusing failure later."""
    return _runs("kubectl", "cluster-info").returncode == 0


def what_is_missing() -> str:
    """What this machine has not got, in the words of the thing that needs
    it. Empty when a fixture project can be brought up here."""
    for tool, why in (
        ("docker", "a container runtime is what images are built and run by"),
        ("kubectl", "an overlay is deployed and read back through it"),
        ("tilt", "`seal up` and `seal ci` are Tilt underneath"),
    ):
        if shutil.which(tool) is None:
            return f"{tool} is not on PATH, and {why}"
    if _runs("docker", "info").returncode != 0:
        return "the container runtime is installed but its daemon is not answering"
    if not _a_cluster_answers() and shutil.which("ctlptl") is None:
        return (
            "this machine points at no cluster, and ctlptl is not on PATH to make one"
        )
    return ""


# Where a failed attempt is remembered, for the rest of one run. Each check
# is its own process, so without this every one of them would spend the same
# several minutes discovering the same thing about the same machine. The
# group's `run` clears it, so a machine that has been fixed is asked again.
NO_CLUSTER_HERE = Path(tempfile.gettempdir()) / "seal-outcomes-no-cluster"


def a_cluster() -> None:
    """Somewhere to deploy a fixture project, or no verdict.

    Created at most once per run however many checks call this: the second
    caller finds the first one's cluster answering and uses it.
    """
    missing = what_is_missing()
    if missing:
        cannot_run(missing)
    if _a_cluster_answers():
        return
    if NO_CLUSTER_HERE.is_file():
        cannot_run(NO_CLUSTER_HERE.read_text(encoding="utf-8").strip())

    created = _runs(
        "ctlptl", "create", "cluster", "kind", f"--name={OUR_CLUSTER}",
        "--registry=ctlptl-registry",
        timeout=MAKING_A_CLUSTER_SECONDS,
    )
    if created.returncode != 0 or not _a_cluster_answers():
        # Not a promise broken: the machine could not host a cluster, which
        # says nothing about whether the library keeps this promise.
        why = (
            "no cluster could be created here:\n"
            f"{created.stdout}{created.stderr}".strip()
        )
        NO_CLUSTER_HERE.write_text(why + "\n", encoding="utf-8")
        cannot_run(why)


@contextlib.contextmanager
def deployed(fixture, *arguments: str, overlay: str = "dev") -> Iterator[Run]:
    """A fixture project brought up in the cluster, and taken away after.

    What comes back is the run that brought it up -- including a run that
    failed, because several of these promises are about what a refusal does.
    Whatever it deployed is deleted on the way out, so the next fixture
    starts from a cluster that has never heard of this one.
    """
    a_cluster()
    run = seal("ci", *arguments, cwd=fixture.root, timeout=BRINGING_UP_SECONDS)
    try:
        yield run
    finally:
        # Deleted through the same overlay that deployed it, which is the
        # one description of what this fixture put in the cluster that
        # cannot go stale.
        _runs(
            "kubectl", "delete", "-k", str(fixture.root / "k8s" / overlay),
            "--ignore-not-found",
            timeout=300,
        )


def _a_free_port() -> int:
    """A port nothing else is on, for this session's own Tilt server.

    A session serves on one port and the CLI talks to that port, so two
    sessions on one machine are two sessions competing for the same one --
    and a command aimed at the wrong one is refused with a token that is not
    its. A check that borrowed the default would be asking about whichever
    session happened to be there.
    """
    with contextlib.closing(socket.socket()) as held:
        held.bind(("127.0.0.1", 0))
        return held.getsockname()[1]


@contextlib.contextmanager
def a_session(fixture, *arguments: str, overlay: str = "dev") -> Iterator[dict[str, str]]:
    """A session somebody could be working in: brought up, left running, and
    taken away afterwards. What it yields is what a command has to be told to
    reach *this* session.

    Different from `deployed()`, which is a gating run: that one brings an
    environment up, reads the promises and exits. A session stays, which is
    what a promise about working *against* one needs -- and what lets a run
    that covers a single promise reach the environment already up rather
    than building another.
    """
    a_cluster()
    reaching_it = {"TILT_PORT": str(_a_free_port())}
    started = subprocess.Popen(
        [
            "uv", "run", "--project", str(PACKAGE_DIR), "seal", "up",
            "--port", reaching_it["TILT_PORT"], "--stream=true", *arguments,
        ],
        cwd=fixture.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, **reaching_it},
    )
    try:
        _wait_until_serving(started, reaching_it)
        yield reaching_it
    finally:
        started.terminate()
        try:
            started.wait(timeout=120)
        except subprocess.TimeoutExpired:  # pragma: no cover -- a session that will not stop
            started.kill()
        _runs(
            "kubectl", "delete", "-k", str(fixture.root / "k8s" / overlay),
            "--ignore-not-found",
            timeout=300,
        )


def _wait_until_serving(
    session: subprocess.Popen, reaching_it: dict[str, str], timeout: int = BRINGING_UP_SECONDS
) -> None:
    """Wait for the session to be one a test could be pointed at.

    Asked of the session itself rather than of the cluster: this suite runs
    fixture after fixture into one cluster, so what is running there at any
    moment includes what the last one has not finished taking away. A session
    that has not started answering yet, read through the cluster, looks
    exactly like one whose resources are all up.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if session.poll() is not None:
            cannot_run("the session exited before it was serving")
        answered = subprocess.run(
            ["tilt", "get", "uiresource", "-o", "json"],
            capture_output=True,
            text=True,
            env={**os.environ, **reaching_it},
            timeout=60,
        )
        if answered.returncode == 0 and _every_resource_is_up(answered.stdout):
            return
        time.sleep(2)
    cannot_run("the session never started serving")


def _every_resource_is_up(reported: str) -> bool:
    """Whether the session says everything it declares is up and settled.

    The Tiltfile itself is one of those resources, so a session still
    evaluating it is not one to hand a test yet.
    """
    try:
        declared = json.loads(reported) or {}
    except json.JSONDecodeError:
        return False
    items = declared.get("items") or []
    if not items:
        return False
    for item in items:
        status = item.get("status") or {}
        if status.get("updateStatus") in ("pending", "in_progress"):
            return False
        if status.get("runtimeStatus") in ("pending",):
            return False
    return True


def kubectl(*arguments: str, timeout: int = 120) -> Run:
    """kubectl, for reading back what a run put in the cluster."""
    completed = _runs("kubectl", *arguments, timeout=timeout)
    return Run(completed.returncode, completed.stdout, completed.stderr)
