"""The deliverable names no password manager.

`tilt/`, `python/`, the CI action and the agent skills are what an
adopting project gets. Which store a project keeps its secrets in is that
project's own declaration (`seal-credentials-config.json`, see
providers.py), so a product name appearing anywhere in the deliverable is a
project having to change seal to use a store seal happened not
to think of.

This is a grep, deliberately. A rule is worth exactly as much as something
that fails when it stops holding; stated only in prose it is an intention,
and prose does not fail.

`.claude/` is covered because it ships: an adopting project installs those
skills, and a skill naming one product teaches every reader of that project
to reach for it.

The example is not covered: `examples/angular-django/` is a consumer, and a
project naming the store it actually uses is the whole point. Nor is
`/docs/` or `/rfcs/`, which have to be able to name a product to explain
one.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# What the deliverable is: the two directories a project consumes, plus the
# action it uses. `internal-*.yml` are this repository's own CI -- a caller,
# like any adopting project's would be -- and are free to name whatever
# store this repository uses.
DELIVERABLE = (
    "python/src/seal",
    "tilt",
    "actions/ci/action.yml",
    ".claude/skills",
    ".claude/agents",
)

# Products, their CLIs, their URI schemes and their domains. Not a complete
# list of password managers and never could be -- it is the set already
# surveyed in /rfcs/0006-credential-resolution.md, which is what a regression
# would most likely reintroduce.
FORBIDDEN = (
    r"proton\.me",
    r"protonpass",
    r"pass-cli",
    r"pass://",
    r"\bProton\b",
    r"\bbws\b",
    r"BWS_ACCESS_TOKEN",
    r"bitwarden",
    r"infisical",
    r"INFISICAL_TOKEN",
    r"BW_SESSION",
    r"\bop://",
    r"1[Pp]assword",
)

_FORBIDDEN = re.compile("|".join(FORBIDDEN), re.IGNORECASE)


def deliverable_files():
    for entry in DELIVERABLE:
        path = REPO_ROOT / entry
        if path.is_file():
            yield path
            continue
        for candidate in sorted(path.rglob("*")):
            if candidate.is_file() and "__pycache__" not in candidate.parts:
                yield candidate


@pytest.mark.parametrize(
    "path", list(deliverable_files()), ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_no_product_is_named(path):
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return  # not text; nothing to name a product in

    found = sorted({match.group(0) for match in _FORBIDDEN.finditer(text)})

    assert not found, (
        f"{path.relative_to(REPO_ROOT)} names {', '.join(repr(f) for f in found)}. "
        "Which store a project uses is its own declaration in "
        "seal-credentials-config.json -- see providers.py, and "
        "/rfcs/0006-credential-resolution.md for why."
    )


def test_the_guard_would_actually_catch_something(tmp_path):
    """A guard that matches nothing passes forever."""
    assert _FORBIDDEN.search("DJANGO_SECRET_KEY=pass://vault/item/password")
    assert _FORBIDDEN.search("curl -fsSL https://proton.me/download/pass-cli")
    assert _FORBIDDEN.search("bws run --project_id")
    assert not _FORBIDDEN.search("DJANGO_SECRET_KEY=store://item/field")
