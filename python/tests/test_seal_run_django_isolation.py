"""`seal run`'s whole reason to exist, not just `seal up`'s dev-Secret
generation: let a developer work on one service in isolation, without ever
starting Tilt/Kubernetes -- see
examples/angular-django/services/api/README.md's "Running in isolation"
section and /rfcs/0006-credential-resolution.md at the repo root.

This proves that promise end-to-end for the example Django service: from
inside services/api/, `seal run -- uv run python src/manage.py
showmigrations --plan` should resolve .env (see credentials.py) and run a
real Django management command against a real Postgres -- the same
`localhost:5432` a developer's own local Postgres would need to be
listening on, with the same credentials as the bundled dev Postgres (see
examples/angular-django/k8s/dev/postgres/secret.yaml and
services/api/src/config/env_utils.py's DATABASE_URL fallback).

A throwaway Postgres container stands in for "a developer's own local
Postgres" here. Skipped if Docker isn't usable, if its image can't be
obtained, or if something is already listening on 5432 -- this test doesn't
try to commandeer a developer's own database.

Nothing here needs a password manager. services/api's `.env` holds
literals and `k8s://` markers, and `seal run` reaches for a provider only
when a value names one (see providers_needed() in credentials.py) -- so
this runs wherever Docker does, rather than only where a session happens
to be available. A project like that needs no declarations at all.
"""

import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
API_SERVICE_DIR = REPO_ROOT / "examples" / "angular-django" / "services" / "api"

# Must match examples/angular-django/k8s/dev/postgres/secret.yaml (the dev/CI
# Secret the bundled Postgres Deployment actually uses) and the DATABASE_URL
# fallback in services/api/src/config/env_utils.py -- both are the "local
# database" this test's container stands in for.
POSTGRES_USER = "app"
POSTGRES_PASSWORD = "app-dev-password"
POSTGRES_DB = "app"
POSTGRES_PORT = 5432
POSTGRES_IMAGE = "postgres:16-alpine"  # matches k8s/dev/postgres/deployment.yaml

READY_TIMEOUT_SECONDS = 30
PULL_TIMEOUT_SECONDS = 300
COMMAND_TIMEOUT_SECONDS = 300  # first run also resolves services/api's own uv venv


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def _unobtainable_image_reason(image: str) -> str | None:
    """None if `image` is on this machine or can be pulled onto it, else why not.

    A daemon that answers `docker info` says nothing about whether it can
    reach a registry, and the two failures are different things: no daemon
    is a machine that can't run containers, an unreachable registry is a
    machine that can't get this one's image. Both mean this test can't run,
    so both skip -- but only by asking for the image itself, because a
    registry's API and its blob storage are usually different hosts and an
    allowlist covering the first but not the second fails only once layers
    start downloading.

    The returned text is the failing line, so the skip names the host that
    refused: that hostname is what anyone changing an allowlist needs, and
    it is not the registry the pull was aimed at.
    """
    on_machine = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
    if on_machine.returncode == 0:
        return None
    try:
        pull = subprocess.run(
            ["docker", "pull", image],
            capture_output=True,
            text=True,
            timeout=PULL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return f"pull did not finish within {PULL_TIMEOUT_SECONDS}s"
    if pull.returncode == 0:
        return None
    lines = [line.strip() for line in (pull.stderr or pull.stdout).splitlines() if line.strip()]
    return lines[-1] if lines else f"docker pull exited {pull.returncode}"


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _wait_until_ready(container_name: str) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "exec", container_name, "pg_isready", "-U", POSTGRES_USER],
            capture_output=True,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise TimeoutError(f"Postgres container '{container_name}' never became ready in time")


@pytest.fixture(scope="module")
def local_postgres():
    """Starts a throwaway Postgres container bound to localhost:5432 with
    the dev/CI credentials (see module docstring), torn down afterwards."""
    if not _docker_available():
        pytest.skip("docker not available -- can't start a throwaway Postgres for this test")
    unobtainable = _unobtainable_image_reason(POSTGRES_IMAGE)
    if unobtainable is not None:
        pytest.skip(f"can't obtain {POSTGRES_IMAGE} -- {unobtainable}")
    if not _port_free(POSTGRES_PORT):
        pytest.skip(f"port {POSTGRES_PORT} already in use -- can't start a throwaway Postgres for this test")

    container_name = f"seal-test-postgres-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        [
            "docker", "run", "--rm", "-d",
            "--name", container_name,
            "-e", f"POSTGRES_USER={POSTGRES_USER}",
            "-e", f"POSTGRES_PASSWORD={POSTGRES_PASSWORD}",
            "-e", f"POSTGRES_DB={POSTGRES_DB}",
            "-p", f"127.0.0.1:{POSTGRES_PORT}:5432",
            POSTGRES_IMAGE,
        ],
        check=True,
        capture_output=True,
    )
    try:
        _wait_until_ready(container_name)
        yield
    finally:
        subprocess.run(["docker", "stop", container_name], capture_output=True)


def test_seal_run_against_a_real_django_management_command(local_postgres):
    """Equivalent to `seal run -- uv run python manage.py show migrations`,
    run from inside services/api/ exactly as a developer working on this
    service in isolation would (see the module docstring)."""
    result = subprocess.run(
        [
            sys.executable, "-m", "seal.seal", "run", "--",
            "uv", "run", "python", "src/manage.py", "showmigrations", "--plan",
        ],
        cwd=API_SERVICE_DIR,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )

    assert result.returncode == 0, (
        f"seal run failed (exit {result.returncode}):\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    # A handful of this service's own migrations showing up in the plan
    # confirms the command actually reached a real database, rather than
    # e.g. silently falling back to the build/unit-test scope's in-memory
    # SQLite (see config.settings / config.env_utils).
    assert "core.0001_initial" in result.stdout
