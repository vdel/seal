"""Building the project a check points a command at.

Most of these promises are about a project's *shape* -- a container with no
readiness probe, a tree nobody owns, a service added since the last run --
and the worked example has one shape. So a check builds the project its
promise turns on, in a directory thrown away afterwards, which is also what
keeps a check from passing because of how something else in this repository
happens to be arranged (/rfcs/0001-library-boundary.md).

Everything is optional. A check asking for an outcome tree gets a project
with no services; one asking about manifests gets no outcome tree. What a
project does not have is as much a part of a shape as what it does.
"""

import contextlib
import json
import shutil
import subprocess
import stat
import tempfile
from pathlib import Path
from typing import Iterator

from helpers.cli import REPO_ROOT

# A probe that says a container is serving. Its content is not what any
# promise here is about -- what matters is whether one is declared at all --
# so every check that needs a passing manifest uses this one rather than
# inventing a different plausible probe each time.
READINESS_PROBE = {"httpGet": {"path": "/healthz", "port": 8080}}

# What makes a directory of manifests an overlay: the file kustomize reads,
# and the one Seal looks for when it asks a project which shapes it can
# deploy.
KUSTOMIZATION = "kustomization.yaml"


def _yaml(value, indent: int = 0) -> str:
    """The subset of YAML these manifests need, without a dependency.

    A check builds manifests as data and reads them back as text; pulling a
    parser in would make what this repository promises depend on what is
    installed beside it, which is the dependence a `tap` group already has
    enough of.
    """
    pad = "  " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            rendered = _yaml(item, indent + 1)
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{pad}{key}:\n{rendered}")
            else:
                lines.append(f"{pad}{key}: {rendered.strip()}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            rendered = _yaml(item, indent + 1)
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{pad}-\n{rendered}")
            else:
                lines.append(f"{pad}- {rendered.strip()}")
        return "\n".join(lines)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def container(name: str, image: str = "nginx:stable", probe: bool = True, **fields) -> dict:
    """One container of a Deployment. `probe=False` is the shape Seal
    refuses: a container reported Ready the instant its process launches."""
    body = {"name": name, "image": image, **fields}
    if probe:
        body["readinessProbe"] = READINESS_PROBE
    return body


def deployment(name: str, containers: list[dict]) -> dict:
    """A Deployment, as thin as one can be and still be one: what the checks
    here read is its containers."""
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {"containers": containers},
            },
        },
    }


class Project:
    """A throwaway project on disk, built a piece at a time."""

    def __init__(self, root: Path) -> None:
        self.root = root
        # Every service this project declares, in the order it declared
        # them: the root Tiltfile is that list, and there is nowhere else it
        # could have gone stale.
        self._services: list[str] = []
        # Where this project's outcome runner reaches the application, when
        # it has one.
        self._base_url: str | None = None
        self._outcome_deps: list[str] = []

    # --- the pieces ------------------------------------------------------

    def write(self, relative: str, body: str = "", executable: bool = False) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        if executable:
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def read(self, relative: str) -> str:
        return (self.root / relative).read_text(encoding="utf-8")

    def remove(self, relative: str) -> None:
        """Take a piece away again -- a service removed, a probe deleted.

        Several promises are about what happens on the *next* run after a
        project changed, and a check that only ever built projects from
        scratch could not ask that question.
        """
        path = self.root / relative
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        overlays = self.root / "k8s"
        for directory in sorted(overlays.iterdir()) if overlays.is_dir() else []:
            if directory.is_dir():
                self.overlay(directory.name)

    def tiltfile(self, body: str = "# a project\n") -> "Project":
        """The root Tiltfile: what makes this directory a project, and the
        only list of the services it has."""
        self.write("Tiltfile", body)
        (self.root / "services").mkdir(parents=True, exist_ok=True)
        return self

    def service(self, name: str, env: str = "", tiltfile: str | None = None) -> "Project":
        self.write(f"services/{name}/.env", env)
        if tiltfile is not None:
            self.write(f"services/{name}/Tiltfile", tiltfile)
        return self

    def manifest(self, overlay: str, name: str, body: dict) -> Path:
        path = self.write(f"k8s/{overlay}/{name}.yaml", _yaml(body) + "\n")
        self.overlay(overlay)
        return path

    def overlay(self, name: str) -> Path:
        """A deployable shape, and the kustomization that makes it one.

        Regenerated from whatever manifests the overlay holds rather than
        appended to, so a check that takes a manifest away is left with an
        overlay that still deploys -- which is what several of these promises
        ask about.
        """
        directory = self.root / "k8s" / name
        directory.mkdir(parents=True, exist_ok=True)
        resources = sorted(
            path.name for path in directory.glob("*.yaml") if path.name != KUSTOMIZATION
        )
        return self.write(
            f"k8s/{name}/{KUSTOMIZATION}",
            "resources:\n" + "".join(f"  - {resource}\n" for resource in resources),
        )

    def deployment(
        self, name: str, containers: list[dict] | None = None, overlay: str = "dev"
    ) -> Path:
        return self.manifest(
            overlay, name, deployment(name, containers or [container(name)])
        )

    def deploys(self, name: str, dockerfile: str, containers: list[dict] | None = None,
                overlay: str = "dev", **service: object) -> "Project":
        """A service this project builds and deploys: its image, its own
        Tiltfile, and the Deployment the overlay carries for it.

        Everything a promise about bringing an environment up turns on is
        here rather than in a fixed fixture project -- what a container does
        before it serves, what a service declares, how many there are -- so
        a check builds the one its promise is about.
        """
        self.write(f"services/{name}/Dockerfile", dockerfile)
        arguments = ",\n    ".join(
            f"{field}={value!r}" for field, value in sorted(service.items())
        )
        self.write(
            f"services/{name}/Tiltfile",
            "load('ext://seal', 'seal_service')\n\n"
            "seal_service(\n"
            f"    {name!r},\n"
            "    context='.',\n"
            "    dockerfile='Dockerfile',\n"
            + (f"    {arguments},\n" if arguments else "")
            + ")\n",
        )
        self.deployment(name, containers or [container(name, image=name)], overlay=overlay)
        if name not in self._services:
            self._services.append(name)
        return self.tiltfile(self._root_tiltfile(overlay))

    def stops_deploying(self, name: str, overlay: str = "dev") -> "Project":
        """Take a service away again: its directory, its Deployment, and its
        place in the list the root Tiltfile is."""
        self.remove(f"services/{name}")
        self.remove(f"k8s/{overlay}/{name}.yaml")
        if name in self._services:
            self._services.remove(name)
        return self.tiltfile(self._root_tiltfile(overlay))

    def registers_outcomes(
        self, base_url: str, waits_for: list[str] | None = None, overlay: str = "dev"
    ) -> "Project":
        """Where this project's outcome runner reaches the application, and
        what has to be serving before it looks.

        A project says both once, in its root Tiltfile. What to wait for is
        the project's own to know: seal infers no ordering from
        manifests, so a runner told nothing starts as soon as it is built.
        """
        self._base_url = base_url
        self._outcome_deps = waits_for or []
        return self.tiltfile(self._root_tiltfile(overlay))

    def _root_tiltfile(self, overlay: str) -> str:
        """The project's entry point: the extension, every service it
        declares, and which shape it deploys.

        The extension is this checkout, by path -- what these promises are
        about is the library as it is on disk right now, not a published
        release of it.
        """
        included = "".join(
            f"include('services/{name}/Tiltfile')\n" for name in self._services
        )
        outcomes = (
            f"\nregister_outcome_runner(base_url={self._base_url!r}, "
            f"resource_deps={self._outcome_deps!r})\n"
            if self._base_url
            else ""
        )
        return (
            f"v1alpha1.extension_repo(name='seal', url='file://{REPO_ROOT}')\n"
            "v1alpha1.extension(name='seal', repo_name='seal', "
            "repo_path='tilt/seal')\n\n"
            "load('ext://seal', 'select_k8s_overlay', 'register_outcome_runner')\n\n"
            f"{included}\n"
            f"select_k8s_overlay(k8s_dir='k8s', default_overlay={overlay!r})\n"
            f"{outcomes}"
        )

    def runners(self, *entries: dict) -> Path:
        return self.write(
            "outcomes/seal-test-config.json",
            json.dumps({"runner": list(entries)}, indent=2) + "\n",
        )

    def group(self, name: str, run: str | None = None) -> "Project":
        """A group run on the machine: the declaration, and the executable
        that declaration implies."""
        declared = self._declared()
        self.runners(
            *[entry for entry in declared if entry["name"] != name],
            {"name": name, "runner_type": "tap"},
        )
        self.write(
            f"outcomes/{name}/run",
            run if run is not None else DEFAULT_GROUP_RUN,
            executable=True,
        )
        return self

    def promise(
        self,
        group: str,
        epic: str,
        name: str,
        prompt: str = "# a promise\n",
        translation: dict[str, str] | None = None,
    ) -> Path:
        directory = f"outcomes/{group}/{epic}/{name}"
        self.write(f"{directory}/prompt.md", prompt)
        for relative, body in (translation or {}).items():
            self.write(f"{directory}/{relative}", body, executable=relative == "check")
        return self.root / directory

    def codeowners(self, body: str = "* @owner\n") -> Path:
        """Who has to approve a change here. A project is a repository as
        far as this rule is concerned, so the marker goes down with it."""
        (self.root / ".git").mkdir(exist_ok=True)
        return self.write("CODEOWNERS", body)

    def repository(self) -> "Project":
        """Make this a real repository with everything in it committed.

        For the promises about what a *change* reaches: a diff needs a commit
        to be a diff from. Identity and branch are passed per command rather
        than configured globally, so a check establishes nothing about the
        machine's git configuration and changes nothing about it either.
        """
        self._git("init", "--initial-branch=main")
        return self.commit("what the project looked like before the change")

    def commit(self, message: str) -> "Project":
        self._git("add", "-A")
        self._git(
            "-c",
            "user.email=checks@example.invalid",
            "-c",
            "user.name=the outcome suite",
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            message,
        )
        return self

    def _git(self, *arguments: str) -> None:
        subprocess.run(
            ["git", *arguments], cwd=self.root, check=True, capture_output=True, text=True
        )

    def _declared(self) -> list[dict]:
        config = self.root / "outcomes" / "seal-test-config.json"
        if not config.is_file():
            return []
        return json.loads(config.read_text(encoding="utf-8")).get("runner", [])


# What a group's runner does when a check has not asked for something else:
# one point per outcome, from an executable beside the promise. The same
# convention this repository's own group uses, so a fixture project reads
# like a real one.
DEFAULT_GROUP_RUN = """#!/bin/sh
set -u
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
while [ $# -gt 0 ] && [ "$1" != "--" ]; do shift; done
[ "${1:-}" = "--" ] && shift
echo "1..$#"
number=0
for slug in "$@"; do
  number=$((number + 1))
  check="$here/$slug/check"
  if [ ! -x "$check" ]; then
    echo "not ok $number - $slug # TODO no test yet"
  elif "$check"; then
    echo "ok $number - $slug"
  else
    echo "not ok $number - $slug"
  fi
done
"""


@contextlib.contextmanager
def project(name: str = "fixture") -> Iterator[Project]:
    """A project directory, gone when the check is done with it.

    Under the machine's own temporary directory rather than beside this
    checkout: a project written inside the repository would be picked up by
    whatever walks it, and a check that left one behind would change what
    the next promise sees.
    """
    with tempfile.TemporaryDirectory(prefix=f"seal-{name}-") as directory:
        yield Project(Path(directory))
