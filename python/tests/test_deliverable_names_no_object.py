"""The deliverable names no Kubernetes object of a project's.

Which object carries a service's values into a pod is the overlay's
statement -- it is already in the Deployment's own `envFrom`, and it
differs per environment. A name built inside a library beside it is the
same mistake as a built-in `dev`: it works until a project needs a
ConfigMap of settings beside one Secret per credential group, and then it
is a convention nothing can opt out of.

So `<service>-secrets` is gone, and this is what keeps it gone. A grep,
for the same reason the vendor guard is one: a rule is worth what fails
when it stops holding, and this one is easy to reintroduce by hand the
next time something needs a name to write into a manifest.

The example is not covered. `examples/angular-django/` is a consumer, and
its overlay naming its own object `example-api-secrets` is exactly what
this design asks a project to do.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The two directories a project consumes. The CI action is not here: it
# runs `seal ci` and names no Kubernetes object at all.
DELIVERABLE = ("python/src/seal", "tilt")

# A name seal would be choosing on a project's behalf. `-secrets` is
# the one it used to build; the others are the shapes the same instinct
# reaches for next.
FORBIDDEN = (
    r"-secrets\b",
    r"-config\b(?!urationRef)",
    r"\{\}-secret",
    r"_secret_manifest",
)

_FORBIDDEN = re.compile("|".join(FORBIDDEN))

# What a filename is allowed to be called: `seal-credentials-config.json`
# and `seal-test-config.json` are seal's own config files, named by
# seal because they are seal's, and they are not Kubernetes objects.
_ALLOWED = re.compile(r"seal-(credentials|test)-config")


def deliverable_files():
    for entry in DELIVERABLE:
        path = REPO_ROOT / entry
        for candidate in sorted(path.rglob("*")):
            if candidate.is_file() and "__pycache__" not in candidate.parts:
                yield candidate


@pytest.mark.parametrize(
    "path", list(deliverable_files()), ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_no_kubernetes_object_name_is_built(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    found = [
        match.group(0)
        for match in _FORBIDDEN.finditer(text)
        if not _ALLOWED.search(text[max(0, match.start() - 40) : match.end()])
    ]

    assert not found, (
        f"{path.relative_to(REPO_ROOT)} names {', '.join(repr(f) for f in found)}. "
        "Which object carries a service's values is the overlay's own "
        "statement, annotated seal-test.dev/fill-from -- see stubs.py, and "
        "/rfcs/0007-credential-delivery.md for why."
    )


def test_the_guard_would_actually_catch_something():
    """A guard whose pattern matches nothing passes for the wrong reason."""
    assert _FORBIDDEN.search('secret_name = "{}-secrets".format(service)')
    assert not _FORBIDDEN.search("the overlay names the object it fills")
