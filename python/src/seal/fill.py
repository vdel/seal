"""Filling the objects an overlay says seal fills.

An overlay declares its own objects and annotates the ones nothing else
populates (see stubs.py). This turns each of those into the same object
with values in it, as a **strategic-merge patch** rather than a second copy.

Patches rather than resources, deliberately. The stub already arrives from
the overlay, and kustomize refuses a duplicate id outright -- the same
reason a project's own overlay patches a Deployment it inherits rather than
restating it. A patch also means one object reaches the cluster, with the
project's own name, labels and annotations intact and only `data` supplied,
so nothing depends on which of two copies happens to be applied last.

Each overlay's patches are written beside a kustomization of their own,
which names the real overlay as its single resource. That keeps every patch
path local to its own root, and it is what a session deploys instead of the
overlay directly -- so the overlay a project wrote stays exactly as written.
"""

import base64
import os
from pathlib import Path

import yaml

from seal.stubs import Stub

# What a Secret's values are written as, versus a ConfigMap's. base64 of the
# raw bytes carries anything a store can hold -- a certificate with newlines
# in it as readily as a password -- where a ConfigMap holds the string.
_SECRET_KIND = "Secret"

WORKSPACE_DIR_NAME = ".workspace"
FILLED_DIR_NAME = "seal-env"
KUSTOMIZATION_FILENAME = "kustomization.yaml"


def filled_dir(seal_root: Path, overlay_name: str) -> Path:
    """Where the filled patches for one overlay go.

    Per overlay rather than per service: which object carries a value is the
    overlay's statement, and two overlays can split the same service's keys
    differently.
    """
    return seal_root / WORKSPACE_DIR_NAME / FILLED_DIR_NAME / overlay_name


def patch_for(stub: Stub, values: dict[str, str]) -> str:
    """One stub, as a patch supplying the values it claims.

    Only `apiVersion`, `kind`, `metadata.name` and the values: those three
    are what kustomize matches the patch to its target by, and everything
    else the project wrote about this object is already in the overlay and
    stays there.
    """
    if stub.kind == _SECRET_KIND:
        data = {
            key: base64.b64encode(value.encode("utf-8")).decode("ascii")
            for key, value in sorted(values.items())
        }
    else:
        data = dict(sorted(values.items()))
    document = {
        "apiVersion": "v1",
        "kind": stub.kind,
        "metadata": {"name": stub.name},
        "data": data,
    }
    # default_flow_style=False and an explicit dump rather than hand-written
    # YAML: a resolved value is arbitrary text, and quoting it correctly by
    # hand is the kind of thing that works until a value contains a colon.
    return yaml.safe_dump(document, default_flow_style=False, sort_keys=False)


def _patch_filename(stub: Stub) -> str:
    """A filename that cannot collide within one overlay. Two kinds may
    share a name (a ConfigMap and a Secret both called `api`), which is
    legal in Kubernetes and has to stay legal here."""
    return f"{stub.kind.lower()}-{stub.name}.yaml"


def write_filled(
    seal_root: Path,
    overlay_name: str,
    overlay_path: Path,
    claimed: dict[Stub, tuple[str, ...]],
    resolved_by_service: dict[str, dict[str, str]],
) -> Path | None:
    """Write one overlay's patches and the kustomization that applies them.

    Returns where they went, or None where this overlay declares no stub at
    all -- a project running an operator in its session cluster too marks
    nothing, seal fills nothing, and what deploys is the overlay
    itself.
    """
    if not claimed:
        return None

    directory = filled_dir(seal_root, overlay_name)
    directory.mkdir(parents=True, exist_ok=True)
    # Stale patches from a previous run are worse than none: an overlay that
    # stopped declaring a stub would otherwise keep being handed the values
    # it used to claim.
    for existing in directory.glob("*.yaml"):
        existing.unlink()

    patches = []
    for stub, keys in sorted(claimed.items(), key=lambda item: _patch_filename(item[0])):
        values = {
            key: resolved_by_service[stub.service][key]
            for key in keys
            if key in resolved_by_service.get(stub.service, {})
        }
        filename = _patch_filename(stub)
        (directory / filename).write_text(patch_for(stub, values), encoding="utf-8")
        patches.append(filename)

    # The overlay is named by a path relative to this directory, the way
    # select_k8s_overlay()'s own generated kustomization names it: kustomize
    # refuses an absolute resource root outright.
    relative_overlay = _relative(directory, overlay_path)
    (directory / KUSTOMIZATION_FILENAME).write_text(
        yaml.safe_dump(
            {
                "apiVersion": "kustomize.config.k8s.io/v1beta1",
                "kind": "Kustomization",
                "resources": [relative_overlay],
                "patches": [{"path": name} for name in patches],
            },
            default_flow_style=False,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return directory


def _relative(from_dir: Path, to_path: Path) -> str:
    """`to_path` as a path relative to `from_dir`, forward-slash separated.

    Written out rather than Path.relative_to(), which refuses a target that
    is not underneath -- and the overlay never is: these land under
    `.workspace/`, beside the project's manifests rather than inside them.
    """
    return os.path.relpath(to_path, from_dir).replace(os.sep, "/")
