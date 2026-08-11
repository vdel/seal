"""The outcome-tree layout, as `seal` reads it.

Every tree here is one the test writes itself, so what's checked is what an
adopting project gets, not what `examples/angular-django` happens to hold.
Pure filesystem work -- no Tilt, no cluster.
"""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from seal.checks import K8S_DIR_ENV_VAR
from seal.outcomes import (
    DEFAULT_OUTCOMES_DIR_NAME,
    HELPERS_DIR_NAME,
    OUTCOMES_DIR_ENV_VAR,
    configured_outcomes_dir_name,
    discover_outcomes,
    headline_of,
    helper_files,
    is_valid_slug,
    outcome_layout_problems,
)
from seal.runners import (
    CONFIG_FILENAME,
    CUSTOM,
    DOCKERFILE_FILENAME,
    PLAYWRIGHT,
    RUNNER_FIELD,
    TAP,
    TAP_RUNNER_FILENAME,
)
from seal.seal import main




def _unreachable(*args, **kwargs):  # pragma: no cover - reaching this is the failure
    raise AssertionError("seal ci got past the outcome-layout check")


def _finds_everything_but_tilt(name):
    """Looking for tilt is the first thing `seal ci` does that the checks are
    supposed to come before, so that lookup is the tripwire. Everything else
    resolves normally -- kubectl above all, which the readiness check needs
    to build an overlay, and which a blanket stub would block instead."""
    if name == "tilt":  # pragma: no cover - reaching this is the failure
        raise AssertionError("seal ci got past the outcome-layout check")
    return _REAL_WHICH(name)

_REAL_WHICH = shutil.which

def _overlay(k8s_dir, **documents):
    """Write an overlay deploying `name=document`. The check builds what a
    project would deploy, so a fixture has to be something kustomize can
    actually build -- loose manifests no kustomization names are manifests
    no cluster ever sees."""
    for name, document in documents.items():
        write(k8s_dir / f"{name}.yaml", yaml.safe_dump(document))
    write(
        k8s_dir / "kustomization.yaml",
        yaml.safe_dump(
            {
                "apiVersion": "kustomize.config.k8s.io/v1beta1",
                "kind": "Kustomization",
                "resources": [f"{name}.yaml" for name in documents],
            }
        ),
    )


def _deployment(name, containers):
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {"containers": containers},
            },
        },
    }

def write(path: Path, body: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


GROUP = "ui"
"""The group every outcome below sits in unless a test says otherwise. A
project's outcomes are grouped by what runs them, and one group is the
smallest tree there is."""


def declared_runners(outcomes_dir: Path) -> list[dict]:
    config = outcomes_dir / CONFIG_FILENAME
    if not config.is_file():
        return []
    return json.loads(config.read_text(encoding="utf-8")).get(RUNNER_FIELD, [])


def declare_runners(outcomes_dir: Path, *runners: dict) -> Path:
    """What a project's seal-test-config.json says: one entry per group."""
    return write(
        outcomes_dir / CONFIG_FILENAME,
        json.dumps({RUNNER_FIELD: list(runners)}, indent=2) + "\n",
    )


def declare_custom_runner(outcomes_dir: Path, group: str = GROUP, **fields) -> Path:
    """What a group bringing its own runner adds: a Dockerfile, and the entry
    in the config that points at it."""
    runners = [
        entry for entry in declared_runners(outcomes_dir) if entry["name"] != group
    ]
    declare_runners(
        outcomes_dir, *runners, {"name": group, "runner_type": CUSTOM, **fields}
    )
    return write(
        outcomes_dir / fields.get("dockerfile", f"{group}/{DOCKERFILE_FILENAME}"),
        "FROM alpine:3\n",
    )


def outcome(
    outcomes_dir: Path,
    epic: str,
    name: str,
    prompt: str = "# a promise\n",
    translation: dict[str, str] | None = None,
    group: str = GROUP,
) -> Path:
    """One promise in a group, and a runner declared for that group where the
    config doesn't already name one -- what a tree these tests can otherwise
    ignore the config in looks like."""
    directory = outcomes_dir / group / epic / name
    write(directory / "prompt.md", prompt)
    for relative, body in (translation or {}).items():
        write(directory / relative, body)
    if group not in [entry["name"] for entry in declared_runners(outcomes_dir)]:
        declare_runners(
            outcomes_dir,
            *declared_runners(outcomes_dir),
            {"name": group, "runner_type": PLAYWRIGHT},
        )
    return directory


def group_dir(outcomes_dir: Path, group: str = GROUP) -> Path:
    """A group directory with a runner declared for it, for the tests that
    write into the tree by hand. A directory no runner names is its own
    problem, and one of those on top of the one under test would say nothing
    about either."""
    declare_runners(
        outcomes_dir,
        *[entry for entry in declared_runners(outcomes_dir) if entry["name"] != group],
        {"name": group, "runner_type": PLAYWRIGHT},
    )
    return outcomes_dir / group


def tap_runner(outcomes_dir: Path, group: str = GROUP) -> Path:
    """What starts a 'tap' group: an executable at the group's own root.
    Written executable, because that is what seal refuses a group
    without -- a file that is plainly there and cannot be run."""
    path = write(outcomes_dir / group / TAP_RUNNER_FILENAME, "#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return path


def declare_tap_group(outcomes_dir: Path, group: str = GROUP) -> Path:
    """What a group run on the machine adds: the entry in the config, and the
    executable at the group's root that entry implies -- declare_custom_runner()'s
    counterpart for a runner declared by structure rather than by a Dockerfile."""
    runners = [
        entry for entry in declared_runners(outcomes_dir) if entry["name"] != group
    ]
    declare_runners(outcomes_dir, *runners, {"name": group, "runner_type": TAP})
    return tap_runner(outcomes_dir, group)


TRANSLATION = {"reload.spec.ts": "test('a promise', async () => {});\n"}
"""The least a runnable translation can be: one file the 'playwright' runner
collects, and nothing else."""


def test_where_a_project_keeps_its_outcomes_defaults_to_outcomes(tmp_path):
    assert configured_outcomes_dir_name({}) == DEFAULT_OUTCOMES_DIR_NAME


def test_a_project_can_keep_its_outcomes_elsewhere(tmp_path):
    """The same escape hatch SEAL_K8S_DIR gives a project's manifests -- the
    layout is a convention, not a claim on one directory name."""
    assert configured_outcomes_dir_name({OUTCOMES_DIR_ENV_VAR: "promises"}) == "promises"
    assert configured_outcomes_dir_name({OUTCOMES_DIR_ENV_VAR: ""}) == DEFAULT_OUTCOMES_DIR_NAME


def test_every_outcome_in_the_tree_is_discovered(tmp_path):
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload")
    outcome(tmp_path, "todo-list", "deleting-an-item-is-permanent")
    outcome(tmp_path, "accounts", "signing-out-ends-the-session")

    assert [found.slug for found in discover_outcomes(tmp_path)] == [
        "ui/accounts/signing-out-ends-the-session",
        "ui/todo-list/an-item-survives-a-reload",
        "ui/todo-list/deleting-an-item-is-permanent",
    ]


def test_an_outcome_carries_its_epic_and_its_own_name(tmp_path):
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload")
    (found,) = discover_outcomes(tmp_path)

    assert (found.epic, found.name) == ("todo-list", "an-item-survives-a-reload")
    assert found.directory == tmp_path / GROUP / "todo-list" / "an-item-survives-a-reload"
    assert found.prompt == found.directory / "prompt.md"


def test_the_prompts_headline_is_what_names_the_outcome(tmp_path):
    """A per-test report needs something to call an outcome that reads as the
    promise, not as a path component."""
    outcome(
        tmp_path,
        "todo-list",
        "an-item-survives-a-reload",
        prompt="# an item I add is still on the list after a reload\n\nSome context.\n",
    )
    (found,) = discover_outcomes(tmp_path)

    assert found.headline == "an item I add is still on the list after a reload"


def test_a_headline_is_read_past_leading_blank_lines(tmp_path):
    assert headline_of(write(tmp_path / "p.md", "\n\n#  a promise  \n")) == "a promise"


def test_prose_before_the_heading_leaves_the_outcome_unnamed(tmp_path):
    """Discovery describes the tree rather than policing it, so a prompt with
    no headline is still discovered -- with nothing to call it, which is what
    `seal check` reports."""
    assert headline_of(write(tmp_path / "p.md", "an item survives a reload\n\n# later\n")) == ""


def test_an_empty_prompt_has_no_headline(tmp_path):
    assert headline_of(write(tmp_path / "p.md", "")) == ""
    assert headline_of(write(tmp_path / "p.md", "\n \n")) == ""


def test_a_deeper_heading_is_not_a_headline(tmp_path):
    """An H2 is a section of the prose, not the promise itself."""
    assert headline_of(write(tmp_path / "p.md", "## a promise\n")) == ""


def test_everything_beside_the_prompt_is_the_translation(tmp_path):
    """What runs a test is one question; what belongs to it is another. A
    test's fixtures, helpers and config are all its own, whatever the runner
    happens to collect."""
    directory = outcome(
        tmp_path,
        "todo-list",
        "an-item-survives-a-reload",
        translation={
            **TRANSLATION,
            "helpers.ts": "export const list = '/todos';\n",
            "fixtures/one-item.json": "{}\n",
        },
    )
    (found,) = discover_outcomes(tmp_path)

    assert found.translated
    assert found.translation == (
        directory / "fixtures" / "one-item.json",
        directory / "helpers.ts",
        directory / "reload.spec.ts",
    )


def test_an_outcome_with_only_a_prompt_is_untranslated(tmp_path):
    """A promise written down before anything compiles it into a test -- a
    state a project passes through, not a broken tree."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload")
    (found,) = discover_outcomes(tmp_path)

    assert not found.translated
    assert found.translation == ()


def test_a_spec_file_is_a_translation_the_default_runner_can_run(tmp_path):
    """The common case: what an outcome promises is what somebody using the
    application sees, and seal supplies the browser that looks."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)
    (found,) = discover_outcomes(tmp_path)

    assert found.translated
    assert found.runner.runner_type == PLAYWRIGHT


def test_a_spec_below_the_outcome_root_still_counts(tmp_path):
    """The default runner collects recursively, so the rule that decides
    whether a file is a test has to as well -- one that disagreed would call
    a translation untranslated for a reason nobody could see."""
    outcome(
        tmp_path,
        "todo-list",
        "an-item-survives-a-reload",
        translation={"specs/reload.spec.ts": "test('a promise', async () => {});\n"},
    )
    (found,) = discover_outcomes(tmp_path)

    assert found.runner.runner_type == PLAYWRIGHT


def test_a_project_can_bring_a_runner_of_its_own(tmp_path):
    """What keeps the tree language-agnostic rather than merely broad: a
    project whose outcomes are not browser-shaped says how they run."""
    declare_custom_runner(tmp_path)
    outcome(
        tmp_path,
        "todo-list",
        "an-item-survives-a-reload",
        translation={"check.py": "assert True\n"},
    )
    (found,) = discover_outcomes(tmp_path)

    assert found.translated
    assert found.runner.runner_type == CUSTOM


def test_one_runner_covers_every_outcome_in_its_group(tmp_path):
    """A group has one runner and it drives every epic under it -- which is
    why it is declared per group rather than inside an outcome."""
    declare_custom_runner(tmp_path)
    outcome(tmp_path, "todo-list", "a-reload-keeps-it", translation=TRANSLATION)
    outcome(tmp_path, "billing", "an-invoice-is-issued-once", translation={"check.py": ""})

    assert {found.runner.runner_type for found in discover_outcomes(tmp_path)} == {CUSTOM}


def test_each_group_runs_under_the_runner_declared_for_it(tmp_path):
    """The whole point of grouping: what an API-only service promises is not
    tested by the thing that tests what somebody sees, and a project says so
    once per group rather than once per outcome."""
    declare_runners(
        tmp_path,
        {"name": "ui", "runner_type": PLAYWRIGHT},
        {"name": "api", "runner_type": CUSTOM},
    )
    write(tmp_path / "api" / DOCKERFILE_FILENAME, "FROM alpine:3\n")
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)
    outcome(
        tmp_path,
        "billing",
        "an-invoice-is-issued-once",
        translation={"check.py": "assert True\n"},
        group="api",
    )

    assert {found.slug: found.runner.runner_type for found in discover_outcomes(tmp_path)} == {
        "api/billing/an-invoice-is-issued-once": CUSTOM,
        "ui/todo-list/an-item-survives-a-reload": PLAYWRIGHT,
    }


def test_an_outcome_is_named_by_its_group_epic_and_own_name(tmp_path):
    """Three directories spell a slug, and the runner is told only the two
    below the group -- it is built from one group and never has to know the
    others exist."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload")
    (found,) = discover_outcomes(tmp_path)

    assert found.group == "ui"
    assert found.slug == "ui/todo-list/an-item-survives-a-reload"
    assert found.slug_within_group == "todo-list/an-item-survives-a-reload"


def test_files_seal_s_own_runner_would_not_collect_are_not_a_translation(tmp_path):
    """A directory of fixtures with nothing to start them is a promise
    nothing tests, however much of a test it looks like."""
    outcome(
        tmp_path,
        "todo-list",
        "an-item-survives-a-reload",
        translation={"test_reload.py": "def test(): ...\n"},
    )
    (found,) = discover_outcomes(tmp_path)

    assert not found.translated
    assert found.runner.runner_type == PLAYWRIGHT


def test_the_same_files_are_a_translation_once_a_runner_is_declared(tmp_path):
    """seal has no reading of what somebody else's runner starts -- that is
    the whole point of declaring one -- so it takes the project at its
    word."""
    outcome(
        tmp_path,
        "todo-list",
        "an-item-survives-a-reload",
        translation={"test_reload.py": "def test(): ...\n"},
    )
    declare_custom_runner(tmp_path)
    (found,) = discover_outcomes(tmp_path)

    assert found.translated


def test_a_dockerfile_inside_an_outcome_does_not_declare_a_runner(tmp_path):
    """The runner is one fixed path at the tree's root, not whichever
    Dockerfile turns up first: a test's own directory may well build images
    of its own."""
    outcome(
        tmp_path,
        "todo-list",
        "an-item-survives-a-reload",
        translation={DOCKERFILE_FILENAME: "FROM alpine:3\n"},
    )
    (found,) = discover_outcomes(tmp_path)

    assert found.runner.runner_type == PLAYWRIGHT
    assert not found.translated


def test_a_directory_with_no_prompt_is_not_an_outcome(tmp_path):
    """Nothing traces such a directory back to a promise, so there is no
    outcome to report -- `seal check` is what refuses it."""
    write(group_dir(tmp_path) / "todo-list" / "orphan" / "test_reload.py", "def test(): ...\n")
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload")

    assert [found.name for found in discover_outcomes(tmp_path)] == [
        "an-item-survives-a-reload"
    ]


def test_files_at_the_wrong_depth_are_not_outcomes(tmp_path):
    """A prompt filed directly under a group or an epic has no outcome
    directory to be paired inside."""
    write(group_dir(tmp_path) / "prompt.md", "# stray\n")
    write(group_dir(tmp_path) / "todo-list" / "prompt.md", "# stray\n")
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload")

    assert [found.slug for found in discover_outcomes(tmp_path)] == [
        "ui/todo-list/an-item-survives-a-reload"
    ]


# --- what a group's tests share ----------------------------------------------


def test_what_a_groups_tests_share_is_not_read_as_a_promise(tmp_path):
    """`helpers/` holds no prompts, so a walk for outcomes passes over it --
    otherwise every file in it would be an outcome nothing can run."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)
    write(group_dir(tmp_path) / HELPERS_DIR_NAME / "todo.ts", "export const list = 1;\n")

    assert [found.slug for found in discover_outcomes(tmp_path)] == [
        "ui/todo-list/an-item-survives-a-reload"
    ]


def test_a_groups_helpers_are_every_file_below_that_directory(tmp_path):
    """Recursive and with no filename rule of its own: what a helper is
    called is the translation's business, since nothing starts one."""
    helpers = group_dir(tmp_path) / HELPERS_DIR_NAME
    write(helpers / "todo.ts", "export const list = 1;\n")
    write(helpers / "pages" / "sign-in.ts", "export const signIn = 1;\n")

    assert helper_files(group_dir(tmp_path)) == (
        helpers / "pages" / "sign-in.ts",
        helpers / "todo.ts",
    )


def test_a_group_that_shares_nothing_has_no_helpers(tmp_path):
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)

    assert helper_files(group_dir(tmp_path)) == ()


def test_each_group_has_its_own(tmp_path):
    """A runner is built from one group's directory, so a helper is only in
    the image of the group it sits in."""
    outcome(tmp_path, "todo-list", "one", translation=TRANSLATION, group="ui")
    outcome(tmp_path, "billing", "two", translation=TRANSLATION, group="api")
    write(tmp_path / "ui" / HELPERS_DIR_NAME / "todo.ts", "export const list = 1;\n")

    assert helper_files(tmp_path / "ui") == (
        tmp_path / "ui" / HELPERS_DIR_NAME / "todo.ts",
    )
    assert helper_files(tmp_path / "api") == ()


def test_a_project_with_no_outcome_tree_declares_no_outcomes(tmp_path):
    """Outcome tests are something a project adopts, not a precondition for
    running `seal` at all."""
    assert discover_outcomes(tmp_path / "nothing-here") == []
    assert discover_outcomes(tmp_path) == []


def test_a_slug_is_lowercase_letters_digits_and_hyphens(tmp_path):
    """A slug is a path component, a test identifier in a report and a
    CODEOWNERS pattern at once, so it's held to what all three read alike."""
    assert is_valid_slug("an-item-survives-a-reload")
    assert is_valid_slug("epic2")
    assert not is_valid_slug("An-Item")
    assert not is_valid_slug("an item")
    assert not is_valid_slug("an--item")
    assert not is_valid_slug("-leading")
    assert not is_valid_slug("trailing-")
    assert not is_valid_slug("under_score")
    assert not is_valid_slug("")


# --- what the layout refuses -------------------------------------------------


def problems_at(outcomes_dir: Path) -> list[str]:
    """Each problem as `<path relative to the tree>: <what's wrong>`, which is
    the shape `seal check` prints."""
    return [problem.describe(outcomes_dir) for problem in outcome_layout_problems(outcomes_dir)]


def test_a_well_formed_tree_has_no_problems(tmp_path):
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)
    outcome(tmp_path, "accounts", "signing-out-ends-the-session")

    assert problems_at(tmp_path) == []


def test_an_untranslated_outcome_is_not_a_problem(tmp_path):
    """A promise can land long before anything compiles it into a test --
    a rule against that would mean a prompt could only ever arrive in the
    same change as its translation."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload")

    assert problems_at(tmp_path) == []


def test_a_translation_nothing_can_start_is_refused(tmp_path):
    """The failure a suite cannot catch for itself: it reports the promise as
    untested, which reads exactly like a promise nobody has got to yet."""
    outcome(
        tmp_path,
        "todo-list",
        "an-item-survives-a-reload",
        translation={"test_reload.py": "def test(): ...\n"},
    )

    (problem,) = problems_at(tmp_path)
    assert problem.startswith("ui/todo-list/an-item-survives-a-reload: nothing here can run")


def test_a_translation_with_only_fixtures_is_refused_too(tmp_path):
    """Nothing about a directory of seed data says how to run it, and the
    rule is about what can be started rather than what looks like a test."""
    outcome(
        tmp_path,
        "todo-list",
        "an-item-survives-a-reload",
        translation={"fixtures/one-item.json": "{}\n"},
    )

    assert len(problems_at(tmp_path)) == 1


def test_a_runnable_translation_is_not_a_problem(tmp_path):
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)
    outcome(tmp_path, "todo-list", "deleting-is-permanent", translation=TRANSLATION)

    assert problems_at(tmp_path) == []


def test_a_declared_runner_settles_what_can_run(tmp_path):
    """The rule exists because seal's own runner collects by filename, so a
    translation it would pass over is a promise reported untested. A project
    that says how its outcomes run has answered the question the rule asks."""
    outcome(
        tmp_path,
        "todo-list",
        "an-item-survives-a-reload",
        translation={"check.py": "assert True\n"},
    )
    assert len(problems_at(tmp_path)) == 1

    declare_custom_runner(tmp_path)
    assert problems_at(tmp_path) == []


SLEEPS = {
    "reload.spec.ts": (
        "test('a promise', async ({ page }) => {\n"
        "  await page.goto('/');\n"
        "  await page.waitForTimeout(500);\n"
        "});\n"
    )
}
"""A translation that waits on the clock: it holds where it was written and
fails wherever the browser is slower."""


def test_a_translation_that_waits_on_the_clock_is_refused(tmp_path):
    """A sleep is how a multi-service test becomes flaky, and a flaky outcome
    test spends real time reporting a promise as broken because a browser was
    slow -- which is worse than the promise having no test at all."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=SLEEPS)

    (problem,) = problems_at(tmp_path)
    assert problem.startswith(
        "ui/todo-list/an-item-survives-a-reload/reload.spec.ts: waits on the clock"
    )


def test_a_translation_that_polls_for_state_is_not(tmp_path):
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)

    assert problems_at(tmp_path) == []


def test_a_declared_runner_settles_how_a_translation_waits_too(tmp_path):
    """The same reason a declared runner settles what can run: seal has no
    reading of what that runner starts, and a sleep-detector for every
    language a Dockerfile might run would be a lint pretending to be a rule."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=SLEEPS)
    assert len(problems_at(tmp_path)) == 1

    declare_custom_runner(tmp_path)
    assert problems_at(tmp_path) == []


def test_a_helper_beside_the_test_is_held_to_the_rule(tmp_path):
    """The whole directory is the translation, so a wait moved out of the
    spec and into something it imports is the same wait."""
    outcome(
        tmp_path,
        "todo-list",
        "an-item-survives-a-reload",
        translation={**TRANSLATION, "helpers/settle.ts": "await page.waitForTimeout(1000);\n"},
    )

    (problem,) = problems_at(tmp_path)
    assert "helpers/settle.ts" in problem


def test_every_translation_that_sleeps_is_reported_at_once(tmp_path):
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=SLEEPS)
    outcome(tmp_path, "todo-list", "deleting-is-permanent", translation=SLEEPS)

    assert len(problems_at(tmp_path)) == 2


def test_a_fixture_that_is_not_text_is_passed_over(tmp_path):
    """A translation carries its own seed data, and nothing waits inside an
    image -- so a file this cannot read is not a file it has an opinion on."""
    directory = outcome(
        tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION
    )
    (directory / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")

    assert problems_at(tmp_path) == []


def test_the_tree_root_holds_a_declared_runner_s_build_context(tmp_path):
    """The runner is built from the tree, so what sits beside its Dockerfile
    is its own -- an entrypoint, a lockfile, whatever it builds from."""
    declare_custom_runner(tmp_path)
    write(tmp_path / "run.sh", "#!/bin/sh\n")
    write(tmp_path / "requirements.txt", "pytest\n")
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)

    assert problems_at(tmp_path) == []


def test_a_file_at_the_tree_root_is_refused_without_a_custom_runner(tmp_path):
    """Nothing reads it, and a prompt misfiled here is the mistake the rule
    is for."""
    write(tmp_path / "prompt.md", "# a promise filed two levels too high\n")
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)

    (problem,) = problems_at(tmp_path)
    assert problem.startswith("prompt.md: a file where the layout has only group")


def test_what_a_groups_tests_share_is_not_held_to_the_epic_layout(tmp_path):
    """`helpers/` holds no promises, so the rules an epic is held to -- a
    directory per outcome, a prompt in each -- would read every file in it as
    an outcome gone wrong."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)
    helpers = group_dir(tmp_path) / HELPERS_DIR_NAME
    write(helpers / "todo.ts", "export const list = 1;\n")
    write(helpers / "pages" / "sign-in.ts", "export const signIn = 1;\n")

    assert problems_at(tmp_path) == []


def test_a_promise_filed_under_helpers_is_refused(tmp_path):
    """The cost of a fixed name, paid where it is noticed: an epic called
    `helpers` would have every outcome under it passed over in silence."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)
    write(
        group_dir(tmp_path) / HELPERS_DIR_NAME / "signing-in" / "prompt.md",
        "# a promise\n",
    )

    (problem,) = problems_at(tmp_path)
    assert problem.startswith("ui/helpers/signing-in/prompt.md: a promise under helpers/")


def test_a_promise_filed_under_helpers_is_refused_whatever_runs_the_group(tmp_path):
    """Which outcomes exist is the tree's business rather than the runner's,
    so this one holds where seal's reading of a test stops."""
    outcome(tmp_path, "billing", "an-invoice-is-issued-once", translation=TRANSLATION)
    declare_custom_runner(tmp_path)
    write(tmp_path / GROUP / HELPERS_DIR_NAME / "signing-in" / "prompt.md", "# a promise\n")

    (problem,) = problems_at(tmp_path)
    assert problem.startswith("ui/helpers/signing-in/prompt.md: a promise under helpers/")


def test_a_test_filed_under_helpers_is_refused(tmp_path):
    """A run is pointed at one outcome's directory at a time, so a spec here
    is collected by nothing and its failures are seen by nobody."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)
    write(
        group_dir(tmp_path) / HELPERS_DIR_NAME / "todo.spec.ts",
        "test('a promise', async () => {});\n",
    )

    (problem,) = problems_at(tmp_path)
    assert problem.startswith("ui/helpers/todo.spec.ts: a test under helpers/")


def test_a_helper_that_waits_on_the_clock_is_refused(tmp_path):
    """Worse here than in a test: every outcome importing it inherits the
    wait."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)
    write(
        group_dir(tmp_path) / HELPERS_DIR_NAME / "todo.ts",
        "export const settle = (page) => page.waitForTimeout(500);\n",
    )

    (problem,) = problems_at(tmp_path)
    assert problem.startswith("ui/helpers/todo.ts: waits on the clock")


def test_a_declared_runner_settles_what_a_helper_may_be_called(tmp_path):
    """seal has no reading of what a runner the project brought collects, so
    which of these files it starts and which it imports is not its business
    -- the same silence it keeps about a translation under that runner."""
    outcome(tmp_path, "billing", "an-invoice-is-issued-once", translation=TRANSLATION)
    declare_custom_runner(tmp_path)
    helpers = tmp_path / GROUP / HELPERS_DIR_NAME
    write(helpers / "todo.spec.ts", "test('a promise', async () => {});\n")
    write(helpers / "wait.ts", "export const settle = (page) => page.waitForTimeout(5);\n")

    assert problems_at(tmp_path) == []


def test_helpers_at_the_trees_root_are_refused_where_they_would_not_reach_a_runner(tmp_path):
    """A runner is built from one group's directory, so nothing at the tree's
    root is in the image that has to import it -- and read as an undeclared
    group, this would send somebody to declare a runner for a directory
    holding no promises."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)
    write(tmp_path / HELPERS_DIR_NAME / "todo.ts", "export const list = 1;\n")

    (problem,) = problems_at(tmp_path)
    assert problem.startswith("helpers: what a group's tests share lives at that group's root")


def test_a_project_with_no_outcome_tree_is_not_a_problem(tmp_path):
    """Outcome tests are something a project adopts, not a precondition."""
    assert outcome_layout_problems(tmp_path / "nothing-here") == []
    assert outcome_layout_problems(tmp_path) == []


def test_a_test_with_no_prompt_is_refused(tmp_path):
    """The one the merge gate rests on: a translation nobody can reach the
    promise for is a test whose intent can't be reviewed."""
    write(group_dir(tmp_path) / "todo-list" / "orphan" / "test_reload.py", "def test(): ...\n")

    (problem,) = problems_at(tmp_path)
    assert problem.startswith("ui/todo-list/orphan: no prompt.md")


def test_a_prompt_with_no_headline_is_refused(tmp_path):
    """Nothing can name the outcome in a report without one."""
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", prompt="an item survives\n")

    (problem,) = problems_at(tmp_path)
    assert problem.startswith("ui/todo-list/an-item-survives-a-reload/prompt.md: no headline")


def test_an_empty_prompt_is_refused(tmp_path):
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload", prompt="")

    (problem,) = problems_at(tmp_path)
    assert "no headline" in problem


def test_a_file_where_only_epics_belong_is_refused(tmp_path):
    """A prompt filed at a group's own level has no outcome directory to be
    paired inside, so nothing would ever discover it."""
    write(group_dir(tmp_path) / "prompt.md", "# stray\n")

    (problem,) = problems_at(tmp_path)
    assert problem.startswith("ui/prompt.md: a file where the layout has only epic directories")


def test_a_file_where_only_outcomes_belong_is_refused(tmp_path):
    write(group_dir(tmp_path) / "todo-list" / "prompt.md", "# stray\n")

    (problem,) = problems_at(tmp_path)
    assert problem.startswith(
        "ui/todo-list/prompt.md: a file where the layout has only outcome directories"
    )


def test_a_badly_formed_epic_name_is_refused(tmp_path):
    outcome(tmp_path, "Todo List", "an-item-survives-a-reload")

    (problem,) = problems_at(tmp_path)
    assert problem.startswith("ui/Todo List: epic name is not a slug")


def test_a_badly_formed_outcome_name_is_refused(tmp_path):
    outcome(tmp_path, "todo-list", "An_Item_Survives")

    (problem,) = problems_at(tmp_path)
    assert problem.startswith("ui/todo-list/An_Item_Survives: outcome name is not a slug")


def test_every_offender_is_reported_at_once(tmp_path):
    """A project should be able to put its tree right in one pass rather than
    one failed run at a time."""
    write(group_dir(tmp_path) / "stray.md", "# stray\n")
    write(group_dir(tmp_path) / "todo-list" / "orphan" / "test_reload.py", "\n")
    outcome(tmp_path, "todo-list", "no-headline-here", prompt="just prose\n")
    outcome(tmp_path, "Accounts", "signing-out-ends-the-session")

    assert len(problems_at(tmp_path)) == 4


def test_a_badly_named_outcome_is_still_checked_for_its_prompt(tmp_path):
    """A bad name shouldn't stop the tree being read -- otherwise fixing one
    problem uncovers another that was there all along."""
    (group_dir(tmp_path) / "todo-list" / "An_Item").mkdir(parents=True)

    assert len(problems_at(tmp_path)) == 2


def test_tooling_leavings_are_not_read_as_promises(tmp_path):
    """A `.gitkeep` or an editor's dotfile is neither a prompt nor a test, and
    reading one as either would flag a tree nobody got wrong."""
    write(tmp_path / ".gitkeep", "")
    write(group_dir(tmp_path) / ".gitkeep", "")
    write(group_dir(tmp_path) / "todo-list" / ".DS_Store", "")
    outcome(tmp_path, "todo-list", "an-item-survives-a-reload")

    assert problems_at(tmp_path) == []
    assert [found.slug for found in discover_outcomes(tmp_path)] == [
        "ui/todo-list/an-item-survives-a-reload"
    ]


# --- what `seal check` and `seal ci` do with it -------------------------------

PROBE = {"httpGet": {"path": "/healthz", "port": 8080}}


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A minimal seal project root -- what find_seal_root() looks for -- whose
    manifests already pass the readiness check and whose outcome tree is
    already owned, so what these assert on is the tree's layout and not either
    other check's result."""
    (tmp_path / "Tiltfile").write_text("# root Tiltfile\n", encoding="utf-8")
    (tmp_path / "services").mkdir()
    # A repository of its own, with a CODEOWNERS covering everything: the
    # merge-gate check reads whichever repository encloses the project, and
    # pinning that here keeps these tests independent of wherever they run.
    (tmp_path / ".git").mkdir()
    write(tmp_path / "CODEOWNERS", "* @owner\n")
    _overlay(
        tmp_path / "k8s" / "dev",
        web=_deployment("web", [{"name": "api", "readinessProbe": PROBE}]),
    )
    monkeypatch.delenv(K8S_DIR_ENV_VAR, raising=False)
    monkeypatch.delenv(OUTCOMES_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# --- what counts as a project ---------------------------------------------------


@pytest.fixture
def specification_only(tmp_path, monkeypatch):
    """A project that states promises and runs no cluster: a tree, a
    CODEOWNERS rule over it, and neither a Tiltfile nor a services/
    directory. A project whose groups all run on the machine has nothing to
    bring up (see /rfcs/0014-seal-on-seal.md)."""
    (tmp_path / ".git").mkdir()
    write(tmp_path / "CODEOWNERS", "* @owner\n")
    outcome(tmp_path / "outcomes", "gating", "a-promise", translation=TRANSLATION)
    monkeypatch.delenv(K8S_DIR_ENV_VAR, raising=False)
    monkeypatch.delenv(OUTCOMES_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_a_project_with_only_a_specification_can_be_asked_what_it_promises(
    specification_only, capsys
):
    assert main(["outcomes"]) == 0
    assert "ui/gating/a-promise" in capsys.readouterr().out


def test_a_project_with_only_a_specification_can_be_checked(specification_only):
    """There is no k8s directory to read, and nothing about the tree's own
    rules needs one."""
    assert main(["check"]) == 0


def test_a_project_with_only_a_specification_is_not_one_to_bring_up(
    specification_only, capsys
):
    """`seal up` needs a Tiltfile to hand to Tilt, and says so. The
    looser rule is the outcome commands' alone."""
    assert main(["up"]) == 1
    assert "not inside a seal project" in capsys.readouterr().err


def test_a_project_that_keeps_its_tree_elsewhere_is_still_found(tmp_path, monkeypatch):
    """Where a project keeps its promises is the project's to say, so the
    walk looks for whichever name is in force rather than a hardcoded one."""
    (tmp_path / ".git").mkdir()
    write(tmp_path / "CODEOWNERS", "* @owner\n")
    outcome(tmp_path / "promises", "gating", "a-promise", translation=TRANSLATION)
    monkeypatch.setenv(OUTCOMES_DIR_ENV_VAR, "promises")
    monkeypatch.chdir(tmp_path)

    assert main(["outcomes"]) == 0


def test_a_tree_under_another_name_is_not_a_project_by_default(tmp_path, monkeypatch):
    """The other half of the same rule: a directory called something else is
    only a tree because the project said so."""
    (tmp_path / ".git").mkdir()
    outcome(tmp_path / "promises", "gating", "a-promise", translation=TRANSLATION)
    monkeypatch.delenv(OUTCOMES_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)

    assert main(["outcomes"]) == 1


def test_a_project_with_both_is_found_where_both_are(project, monkeypatch, capsys):
    """A project with services and a tree is one project. The looser rule
    must not find a nearer root -- which would put the tree, the manifests
    and the services under different roots for different commands."""
    outcome(project / "outcomes", "todo-list", "a-promise", translation=TRANSLATION)
    (project / "services" / "api").mkdir(parents=True)
    monkeypatch.chdir(project / "services" / "api")

    assert main(["outcomes"]) == 0
    assert "ui/todo-list/a-promise" in capsys.readouterr().out


def test_nothing_anywhere_names_both_ways_of_being_a_project(tmp_path, monkeypatch):
    """Somebody who has one of the two shapes should not have to find out
    from somewhere else that the other would have done."""
    monkeypatch.chdir(tmp_path)

    assert main(["outcomes"]) == 1


def test_the_refusal_names_both_ways(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(["outcomes"])
    refusal = capsys.readouterr().err

    assert "services/" in refusal
    assert "outcomes/" in refusal


def test_a_command_that_needs_a_cluster_names_only_what_it_needs(tmp_path, monkeypatch, capsys):
    """`seal up` has no use for a tree, so offering one as a way out
    would be an instruction that does not work."""
    monkeypatch.chdir(tmp_path)
    main(["up"])
    refusal = capsys.readouterr().err

    assert "services/" in refusal
    assert "outcomes/" not in refusal


def test_a_project_that_deploys_nothing_has_no_container_to_check(
    specification_only, capsys
):
    """The readiness check is about what a project deploys. One with no
    manifests and no services deploys nothing, and saying so on every run is
    what trains people to read past this output."""
    assert main(["check"]) == 0
    assert "readinessProbe" not in capsys.readouterr().out


def test_a_project_with_services_and_no_manifests_still_says_so(tmp_path, monkeypatch, capsys):
    """The other half, and the one that matters: this project deploys, and
    there is nothing here saying what. The looser rule above must not turn
    that into silence."""
    (tmp_path / "Tiltfile").write_text("# root Tiltfile\n", encoding="utf-8")
    (tmp_path / "services").mkdir()
    monkeypatch.delenv(K8S_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)

    assert main(["check"]) == 1
    assert "no Kubernetes manifests found" in capsys.readouterr().err


def test_seal_check_passes_a_well_formed_tree(project, capsys):
    outcome(project / "outcomes", "todo-list", "an-item-survives-a-reload")

    assert main(["check"]) == 0
    assert "pairs a prompt with a test the suite can run" in capsys.readouterr().out


def test_seal_check_refuses_a_test_with_no_prompt(project, capsys):
    write(group_dir(project / "outcomes") / "todo-list" / "orphan" / "test_reload.py", "\n")

    assert main(["check"]) == 1
    assert "outcomes/ui/todo-list/orphan: no prompt.md" in capsys.readouterr().err


def test_seal_check_says_nothing_about_a_project_with_no_outcomes(project, capsys):
    """Reporting on a convention a project hasn't adopted, on every run, would
    train people to read past this check's output."""
    assert main(["check"]) == 0
    assert "outcome" not in capsys.readouterr().out


def test_both_checks_report_from_one_invocation(project, capsys):
    """They're independent problems in different parts of a project, so
    stopping at the first would hide the other behind another run."""
    _overlay(
        project / "k8s" / "dev",
        web=_deployment("web", [{"name": "api", "readinessProbe": PROBE}]),
        worker=_deployment("worker", [{"name": "celery"}]),
    )
    write(group_dir(project / "outcomes") / "todo-list" / "orphan" / "test_reload.py", "\n")

    assert main(["check"]) == 1
    errors = capsys.readouterr().err
    assert "no readinessProbe" in errors
    assert "no prompt.md" in errors


def test_seal_ci_refuses_to_start_on_a_broken_outcome_tree(project, monkeypatch, capsys):
    """Same reason `seal ci` already runs the readiness check first: a run
    whose outcome tests can't be traced to a promise makes its own green
    result mean less than it says, and finding out costs a directory walk."""
    write(group_dir(project / "outcomes") / "todo-list" / "orphan" / "test_reload.py", "\n")

    monkeypatch.setattr("seal.seal._fill_declared_objects", _unreachable)
    monkeypatch.setattr("seal.seal.shutil.which", _finds_everything_but_tilt)

    assert main(["ci"]) == 1
    assert "no prompt.md" in capsys.readouterr().err


def test_the_outcomes_dir_env_var_is_what_seal_ci_can_be_told(project, monkeypatch, capsys):
    """`seal ci` forwards its arguments to `tilt ci` untouched, so a project
    whose tree isn't in outcomes/ has no flag to reach for -- this is how it
    says where it is, and both commands read the same answer."""
    write(group_dir(project / "promises") / "todo-list" / "orphan" / "test_reload.py", "\n")
    monkeypatch.setenv(OUTCOMES_DIR_ENV_VAR, "promises")

    monkeypatch.setattr("seal.seal._fill_declared_objects", _unreachable)
    monkeypatch.setattr("seal.seal.shutil.which", _finds_everything_but_tilt)

    assert main(["check"]) == 1
    assert main(["ci"]) == 1
    assert "promises/ui/todo-list/orphan" in capsys.readouterr().err


def test_an_explicit_outcomes_dir_wins_over_the_env_var(project, monkeypatch):
    outcome(project / "promises", "todo-list", "an-item-survives-a-reload")
    write(group_dir(project / "other") / "todo-list" / "orphan" / "test_reload.py", "\n")
    monkeypatch.setenv(OUTCOMES_DIR_ENV_VAR, "promises")

    assert main(["check"]) == 0
    assert main(["check", "--outcomes-dir", "other"]) == 1


# --- what `seal outcomes` lists ----------------------------------------------


def test_seal_outcomes_lists_every_outcome_with_its_headline(project, capsys):
    outcome(
        project / "outcomes",
        "todo-list",
        "an-item-survives-a-reload",
        prompt="# an item I add is still on the list after a reload\n",
    )
    outcome(
        project / "outcomes",
        "accounts",
        "signing-out-ends-the-session",
        prompt="# signing out ends the session\n",
    )

    assert main(["outcomes"]) == 0
    listing = capsys.readouterr().out
    assert "ui/accounts/signing-out-ends-the-session" in listing
    assert "an item I add is still on the list after a reload" in listing
    assert "signing out ends the session" in listing


def test_seal_outcomes_marks_what_has_no_test_yet(project, capsys):
    """The question this listing opens with, for whatever is going to write
    the missing translations."""
    outcome(project / "outcomes", "todo-list", "has-a-test", translation=TRANSLATION)
    outcome(project / "outcomes", "todo-list", "has-no-test")

    assert main(["outcomes"]) == 0
    listing = capsys.readouterr().out
    has_a_test, has_no_test = (
        line for line in listing.splitlines() if line.startswith("ui/todo-list/")
    )
    assert "translated" in has_a_test
    assert "no test yet" in has_no_test
    assert "1 translated" in listing


def test_untranslated_lists_bare_slugs_and_nothing_else(project, capsys):
    """What `seal outcomes translate` is pointed at, one promise at a time.
    Anything else on stdout is something every caller has to strip, and one
    that forgot would feed a heading back as an outcome name."""
    outcomes_dir = project / "outcomes"
    outcome(outcomes_dir, "todo-list", "an-item-survives-a-reload", translation=TRANSLATION)
    outcome(outcomes_dir, "todo-list", "deleting-is-permanent")

    assert main(["outcomes", "--untranslated"]) == 0
    assert capsys.readouterr().out == "ui/todo-list/deleting-is-permanent\n"


def test_untranslated_says_nothing_where_every_promise_has_a_test(project, capsys):
    outcome(
        project / "outcomes", "todo-list", "an-item-survives-a-reload", translation=TRANSLATION
    )

    assert main(["outcomes", "--untranslated"]) == 0
    assert capsys.readouterr().out == ""


def test_untranslated_says_nothing_about_a_project_with_no_tree(project, capsys):
    """The listing's own explanatory line would be read back as a slug."""
    assert main(["outcomes", "--untranslated"]) == 0
    assert capsys.readouterr().out == ""


def test_untranslated_means_the_suite_has_nothing_to_run(project, capsys):
    """Not that the directory is empty. A translation seal's own runner will
    not collect leaves the promise as untested as an empty one does, and it is
    the same thing that has to be written before the suite covers it."""
    outcome(
        project / "outcomes",
        "todo-list",
        "an-item-survives-a-reload",
        translation={"check.py": "assert True\n"},
    )

    assert main(["outcomes", "--untranslated"]) == 0
    assert capsys.readouterr().out == "ui/todo-list/an-item-survives-a-reload\n"


def test_seal_outcomes_on_a_project_with_no_tree_is_not_a_failure(project, capsys):
    assert main(["outcomes"]) == 0
    assert "no outcomes declared" in capsys.readouterr().out


def test_seal_outcomes_says_when_a_prompt_has_no_headline(project, capsys):
    """The listing points at the command that explains it rather than
    printing a blank column that reads as a bug in the listing."""
    outcome(project / "outcomes", "todo-list", "an-item-survives-a-reload", prompt="prose\n")

    assert main(["outcomes"]) == 0
    assert "seal check" in capsys.readouterr().out


def test_seal_outcomes_reads_the_outcomes_dir_env_var(project, monkeypatch, capsys):
    outcome(project / "promises", "todo-list", "an-item-survives-a-reload")
    monkeypatch.setenv(OUTCOMES_DIR_ENV_VAR, "promises")

    assert main(["outcomes"]) == 0
    assert "ui/todo-list/an-item-survives-a-reload" in capsys.readouterr().out


def test_an_explicit_outcomes_dir_wins_over_the_env_var_when_listing(project, monkeypatch, capsys):
    outcome(project / "promises", "todo-list", "in-promises")
    outcome(project / "other", "todo-list", "in-other")
    monkeypatch.setenv(OUTCOMES_DIR_ENV_VAR, "promises")

    assert main(["outcomes", "--outcomes-dir", "other"]) == 0
    assert "ui/todo-list/in-other" in capsys.readouterr().out
