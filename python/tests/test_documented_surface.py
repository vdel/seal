"""What `docs/reference/tilt-extensions.md` says a project can reach for, read
off the extension itself.

A reference page is the one place a reader looks to find out what exists, and
its failure mode is quiet: an export the page omits is a capability nobody
finds, and a name in its `load()` line that the extension doesn't export is a
root Tiltfile that dies at parse time with `name ... not found in module
ext://seal` -- for a reader who did exactly what the page told them to.

Neither is something a human notices while reviewing a change to Starlark.
"""

import re
from pathlib import Path

from seal.runners import RUNNER_TYPES

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_TILTFILE = REPO_ROOT / "tilt" / "seal" / "Tiltfile"
CONFIG_TILTFILE = REPO_ROOT / "tilt" / "seal" / "config.Tiltfile"
REFERENCE = REPO_ROOT / "docs" / "reference" / "tilt-extensions.md"
RUNNERS_GUIDE = REPO_ROOT / "docs" / "guides" / "runners.md"


def _exported_names() -> set[str]:
    """Every name `ext://seal` re-exports.

    A module-level binding in tilt/seal/Tiltfile is exactly what Starlark
    makes importable, so this reads the assignments rather than restating a
    list here -- one written out in this file would agree with itself while
    disagreeing with the extension. Leading-underscore names are the
    load_dynamic() handles the file pulls its exports out of, which Starlark
    treats as private.
    """
    return {
        name
        for name in re.findall(
            r"^([A-Za-z_][A-Za-z0-9_]*) = ",
            EXTENSION_TILTFILE.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if not name.startswith("_")
    }


def _documented_names() -> set[str]:
    """The names the reference's own `load('ext://seal', ...)` line tells a
    project to import -- the line a reader copies."""
    text = REFERENCE.read_text(encoding="utf-8")
    match = re.search(r"load\('ext://seal',(.*?)\)", text, re.DOTALL)
    assert match, f"no load('ext://seal', ...) line in {REFERENCE}"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def _defined_flags() -> set[str]:
    """The Tilt config flags the extension declares, read from the Starlark
    for the same reason as the exports above."""
    return set(
        re.findall(
            r"config\.define_(?:string|bool|string_list)\('([^']+)'\)",
            CONFIG_TILTFILE.read_text(encoding="utf-8"),
        )
    )


def test_every_export_is_in_the_reference_s_load_line():
    undocumented = sorted(_exported_names() - _documented_names())
    assert undocumented == [], (
        "ext://seal exports these and the reference's load() line does not"
        " name them: {}".format(undocumented)
    )


def test_the_reference_s_load_line_names_nothing_that_is_not_exported():
    unexported = sorted(_documented_names() - _exported_names())
    assert unexported == [], (
        "the reference tells a project to load these and ext://seal does not"
        " export them, so a root Tiltfile copying that line fails at parse"
        " time: {}".format(unexported)
    )


def test_the_reference_s_count_of_the_exports_matches_how_many_there_are():
    """The prose under that line says how many there are. A reader who counts
    is checking whether the list is complete, so a stale number quietly
    answers that question wrong."""
    spelled = {
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    match = re.search(
        r"Those (\w+) are everything `ext://seal` exports",
        REFERENCE.read_text(encoding="utf-8"),
    )
    assert match, f"no 'Those N are everything ext://seal exports' in {REFERENCE}"
    counted = spelled.get(match.group(1))
    assert counted == len(_exported_names()), (
        "the reference says '{}' exports and ext://seal has {}".format(
            match.group(1), len(_exported_names()),
        )
    )


def test_every_config_flag_is_in_the_reference_s_flag_table():
    text = REFERENCE.read_text(encoding="utf-8")
    missing = sorted(
        flag for flag in _defined_flags() if f"`--{flag}`" not in text
    )
    assert missing == [], (
        "the extension defines these flags and the reference does not list"
        " them: {}".format(missing)
    )


def test_every_runner_a_project_can_declare_is_documented():
    """A runner type nobody can find is one nobody uses.

    The failure this catches is the quiet half of adding one: the code
    accepts a new `runner_type`, `seal check` stops refusing it, and
    the one page a reader looks at to find out what exists never mentions
    it. Read off RUNNER_TYPES rather than listed here, since a list written
    in this file would agree with itself while disagreeing with what ships.
    """
    guide = RUNNERS_GUIDE.read_text(encoding="utf-8")

    undocumented = [
        runner_type
        for runner_type in RUNNER_TYPES
        if f"`{runner_type}`" not in guide
    ]

    assert undocumented == [], (
        f"{RUNNERS_GUIDE.name} does not mention {undocumented}, so a project "
        "declaring one would be following code nothing tells it about."
    )


def test_every_runner_has_a_section_of_its_own():
    """Mentioned in passing is not documented. Each runner is a different
    thing to write -- spec files, a Dockerfile, an executable printing a
    stream -- so each needs the section that says which."""
    headings = re.findall(r"^## .*$", RUNNERS_GUIDE.read_text(encoding="utf-8"), re.MULTILINE)

    for runner_type in RUNNER_TYPES:
        assert any(f"`{runner_type}`" in heading for heading in headings), (
            f"no section of {RUNNERS_GUIDE.name} is about the '{runner_type}' runner"
        )
