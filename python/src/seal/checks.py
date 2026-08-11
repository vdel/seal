"""Static checks a seal project has to pass before its tests mean anything.

`seal ci` succeeds only once Tilt reports every resource ready, which is
what lets a test suite run against a finished environment rather than a
half-built one. That guarantee rests entirely on Kubernetes knowing when a
container is actually serving -- and a container with no `readinessProbe`
is marked Ready the moment its process starts, whether or not it can answer
anything. One such Deployment is enough to make a green `seal ci` mean
less than it appears to, silently.

So: every Deployment a run can deploy declares a readinessProbe on every
container. That is the whole rule. It needs no configuration and no
per-project list -- each overlay is built and what comes out is what's
checked, so a Deployment added later is covered by having been added.

Built rather than read as written, because a manifest file is not what
reaches the cluster. A kustomize patch is a Deployment document too, and an
entry in its `containers` may be introducing a container, amending one
declared in a base, or deleting it -- three things a reader of the file
alone cannot tell apart. Requiring a probe in each of them would mean
copying a base's probe into every patch that touches a container, and a
copied probe is one that goes stale. Rendering settles it: what the check
sees is what Kubernetes would get.

Deliberately not checked here: which resources wait on which others (Tilt's
`resource_deps`). Ordering reduces crash-loop churn while an environment
comes up, but `tilt ci` waits for *all* resources regardless of the order
they started in, so it isn't what makes the signal trustworthy. Inferring
those edges would mean guessing at dependencies the manifests only imply.
"""

import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from seal.credentials import SealError

DEFAULT_K8S_DIR_NAME = "k8s"
# A project whose manifests live somewhere other than k8s/ passes that
# directory to select_k8s_overlay() in its root Tiltfile, which Starlark
# never hands back to the CLI. This is how it tells the Python side the same
# thing -- an env var rather than a flag, because `seal ci` forwards every
# argument it is given straight to `tilt ci`.
K8S_DIR_ENV_VAR = "SEAL_K8S_DIR"
_MANIFEST_SUFFIXES = (".yaml", ".yml")


def configured_k8s_dir_name(environ: Mapping[str, str]) -> str:
    """Where this project keeps its manifests, relative to its root."""
    return environ.get(K8S_DIR_ENV_VAR) or DEFAULT_K8S_DIR_NAME


@dataclass(frozen=True)
class MissingReadinessProbe:
    """One container that would be reported Ready before it can serve."""

    overlay: str
    deployment: str
    container: str

    def describe(self, relative_to: Path) -> str:
        # The overlay rather than a file: a rendered container has no one
        # manifest it came from, and which shape is broken is what a reader
        # needs to know first anyway -- the same container can be fine in
        # the shape they work in and missing a probe in the shape that ships.
        del relative_to
        return (
            f"overlay '{self.overlay}': Deployment '{self.deployment}', "
            f"container '{self.container}'"
        )


def containers_in(deployment: dict) -> list[dict]:
    """A rendered Deployment's containers.

    initContainers are deliberately not among them: one runs to completion
    before the pod's containers start, so readiness is not a question it can
    answer, and the ordering a project wants from it is what Kubernetes
    already guarantees."""
    spec = deployment.get("spec") or {}
    template = spec.get("template") or {}
    pod_spec = template.get("spec") or {}
    containers = pod_spec.get("containers") or []
    return [container for container in containers if isinstance(container, dict)]


def overlays_in(k8s_dir: Path) -> list[Path]:
    """Every overlay under `k8s_dir`, in a stable order.

    An overlay is a direct subdirectory holding a kustomization -- which is
    exactly what `select_k8s_overlay()` deploys, so this checks what a run
    can actually reach for and nothing else. A directory below one is part
    of that overlay rather than an overlay of its own, and is checked
    through whichever overlay builds it."""
    return sorted(
        path
        for path in k8s_dir.iterdir()
        if path.is_dir()
        and any((path / f"kustomization{suffix}").is_file() for suffix in _MANIFEST_SUFFIXES)
    )


def render(overlay: Path) -> list[dict]:
    """What `overlay` would put in the cluster, as Kubernetes documents.

    Through kubectl, which every seal project already needs (see
    /docs/installation.md) and which is what Tilt's own `kustomize()` shells
    out to -- so what this renders is what a run deploys, built the same
    way."""
    if shutil.which("kubectl") is None:
        raise SealError(
            "Error: 'kubectl' not found on PATH, so this project's overlays cannot be "
            "built to check them. See https://kubernetes.io/docs/tasks/tools/."
        )

    result = subprocess.run(
        ["kubectl", "kustomize", str(overlay)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # An overlay that will not build is one nothing can deploy, so this
        # is a finding in its own right rather than an obstacle to the check.
        raise SealError(
            f"Error: could not build the '{overlay.name}' overlay:\n{result.stderr.strip()}"
        )

    try:
        loaded = list(yaml.safe_load_all(result.stdout))
    except yaml.YAMLError as error:
        raise SealError(f"Error: could not parse the built '{overlay.name}' overlay: {error}")
    return [document for document in loaded if isinstance(document, dict)]


def missing_readiness_probes(k8s_dir: Path) -> list[MissingReadinessProbe]:
    """Every container that would reach a cluster from one of `k8s_dir`'s
    overlays without a readinessProbe. Empty means the project passes.

    Each overlay is checked on its own, and a container is reported once per
    overlay that deploys it: a base shared by two shapes is deployed by both,
    and a project fixing one shape has not fixed the other."""
    if not k8s_dir.is_dir():
        raise SealError(
            f"Error: no Kubernetes manifests found at {k8s_dir}. If this project keeps "
            f"them elsewhere, name that directory in {K8S_DIR_ENV_VAR} (or pass "
            "`seal check --k8s-dir <dir>`)."
        )

    overlays = overlays_in(k8s_dir)
    if not overlays:
        raise SealError(
            f"Error: no Kubernetes overlays found under {k8s_dir}. An overlay is a "
            "directory holding a kustomization.yaml, and it is what "
            "select_k8s_overlay() deploys -- see /docs/guides/project-layout.md."
        )

    missing: list[MissingReadinessProbe] = []
    for overlay in overlays:
        for document in render(overlay):
            if document.get("kind") != "Deployment":
                continue
            name = (document.get("metadata") or {}).get("name", "<unnamed>")
            for index, container in enumerate(containers_in(document)):
                if "readinessProbe" not in container:
                    missing.append(
                        MissingReadinessProbe(
                            overlay=overlay.name,
                            deployment=name,
                            container=container.get("name", f"<unnamed #{index}>"),
                        )
                    )
    return missing
