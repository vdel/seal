"""What `seal check` refuses when a change to an outcome would need nobody's
approval.

Every project here is one the test writes itself, so what's checked is what
an adopting project gets rather than what `examples/angular-django` happens
to hold. Pure filesystem work -- no Tilt, no cluster, no GitHub.
"""

import json
from pathlib import Path

import pytest
import yaml

from seal.checks import K8S_DIR_ENV_VAR
from seal.codeowners import CODEOWNERS_FILENAME, parse_codeowners
from seal.outcomes import (
    HELPERS_DIR_NAME,
    OUTCOMES_DIR_ENV_VAR,
    QUARANTINE_FILENAME,
    unowned_outcomes,
)
from seal.runners import CONFIG_FILENAME, PLAYWRIGHT, RUNNER_FIELD
from seal.seal import main

GROUP = "ui"
"""The group every outcome below sits in. A project's outcomes are grouped
by what runs them, and one group is the smallest tree there is."""

PROBE = {"httpGet": {"path": "/healthz", "port": 8000}}



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


def outcome(
    outcomes_dir: Path,
    epic: str = "todo-list",
    name: str = "an-item-survives-a-reload",
    translation: dict[str, str] | None = None,
    group: str = GROUP,
) -> Path:
    """One outcome, whose tree the layout check would also accept -- these
    tests are about who owns it, and a tree `seal check` would reject for a
    second reason would leave that ambiguous. So the group has a runner
    declared for it, and a translation comes with a spec file that runner
    collects (see `seal.outcomes`)."""
    write(
        outcomes_dir / CONFIG_FILENAME,
        json.dumps({RUNNER_FIELD: [{"name": group, "runner_type": PLAYWRIGHT}]}) + "\n",
    )
    directory = outcomes_dir / group / epic / name
    write(directory / "prompt.md", "# a promise\n")
    if translation:
        write(directory / f"{name}.spec.ts", "test('a promise', async () => {});\n")
    for relative, body in (translation or {}).items():
        write(directory / relative, body)
    return directory


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A minimal seal project that is its own repository, with manifests that
    already pass the readiness check -- so what these assert on is who owns
    the outcome tree and not another check's result."""
    (tmp_path / "Tiltfile").write_text("# root Tiltfile\n", encoding="utf-8")
    (tmp_path / "services").mkdir()
    (tmp_path / ".git").mkdir()
    _overlay(
        tmp_path / "k8s" / "dev",
        web=_deployment("web", [{"name": "api", "readinessProbe": PROBE}]),
    )
    monkeypatch.delenv(K8S_DIR_ENV_VAR, raising=False)
    monkeypatch.delenv(OUTCOMES_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _unowned(outcomes_dir: Path, contents: str, root: Path) -> list[str]:
    codeowners = parse_codeowners(contents, source=root / CODEOWNERS_FILENAME, root=root)
    return [
        problem.path.relative_to(root).as_posix()
        for problem in unowned_outcomes(outcomes_dir, codeowners)
    ]


# --- the rule ----------------------------------------------------------------


def test_a_tree_one_rule_covers_is_owned(tmp_path):
    outcome(tmp_path / "outcomes", translation={"test_reload.py": "\n"})

    assert _unowned(tmp_path / "outcomes", "/outcomes/ @owner\n", tmp_path) == []


def test_an_outcome_no_rule_reaches_is_reported(tmp_path):
    outcome(tmp_path / "outcomes")

    assert _unowned(tmp_path / "outcomes", "/services/ @owner\n", tmp_path) == [
        "outcomes/ui/todo-list/an-item-survives-a-reload"
    ]


def test_a_later_ownerless_rule_leaves_a_test_unowned(tmp_path):
    """The case the whole check turns on: ownership is not granted once and
    kept, it is decided by the last rule to match."""
    outcome(tmp_path / "outcomes", translation={"test_reload.py": "\n"})

    assert _unowned(tmp_path / "outcomes", "/outcomes/ @owner\n*.py\n", tmp_path) == [
        "outcomes/ui/todo-list/an-item-survives-a-reload/test_reload.py"
    ]


def test_a_prompt_is_held_to_the_same_rule_as_a_test(tmp_path):
    """An agent free to rewrite the promise never has to touch a test to
    change what the project claims."""
    outcome(tmp_path / "outcomes")

    assert _unowned(tmp_path / "outcomes", "/outcomes/ @owner\nprompt.md\n", tmp_path) == [
        "outcomes/ui/todo-list/an-item-survives-a-reload/prompt.md"
    ]


def test_a_fixture_beside_a_test_is_covered_too(tmp_path):
    outcome(tmp_path / "outcomes", translation={"fixtures/seed.json": "{}\n"})

    assert _unowned(
        tmp_path / "outcomes", "/outcomes/ @owner\n/outcomes/**/fixtures/\n", tmp_path
    ) == ["outcomes/ui/todo-list/an-item-survives-a-reload/fixtures/seed.json"]


def test_an_unowned_directory_is_reported_once_not_per_file(tmp_path):
    """One rule fixes every file inside it, so listing them all would add
    length rather than information."""
    outcome(
        tmp_path / "outcomes",
        translation={"test_reload.py": "\n", "fixtures/seed.json": "{}\n"},
    )

    assert _unowned(tmp_path / "outcomes", "* @owner\n/outcomes/\n", tmp_path) == [
        "outcomes/ui/todo-list/an-item-survives-a-reload"
    ]


def test_every_unowned_outcome_is_reported_in_one_pass(tmp_path):
    outcome(tmp_path / "outcomes", epic="todo-list", name="one")
    outcome(tmp_path / "outcomes", epic="accounts", name="two")

    assert _unowned(tmp_path / "outcomes", "/services/ @owner\n", tmp_path) == [
        "outcomes/ui/accounts/two",
        "outcomes/ui/todo-list/one",
    ]


def test_what_a_groups_tests_share_is_owned_too(tmp_path):
    """A helper holds whatever several translations share, which is as likely
    to be the assertion as the navigation -- so one a change could reach
    without review defangs every test importing it, without touching a test."""
    outcome(tmp_path / "outcomes", translation={"test_reload.py": "\n"})
    write(
        tmp_path / "outcomes" / GROUP / HELPERS_DIR_NAME / "todo.ts",
        "export const list = 1;\n",
    )

    assert _unowned(tmp_path / "outcomes", "/outcomes/ @owner\n", tmp_path) == []
    assert _unowned(
        tmp_path / "outcomes", "/outcomes/ @owner\n/outcomes/**/helpers/\n", tmp_path
    ) == ["outcomes/ui/helpers"]


def test_a_later_ownerless_rule_leaves_a_helper_unowned(tmp_path):
    """Ownership is decided by the last rule to match, here as anywhere."""
    outcome(tmp_path / "outcomes", translation={"test_reload.py": "\n"})
    write(
        tmp_path / "outcomes" / GROUP / HELPERS_DIR_NAME / "todo.ts",
        "export const list = 1;\n",
    )

    assert _unowned(
        tmp_path / "outcomes", "/outcomes/ @owner\n/outcomes/ui/helpers/todo.ts\n", tmp_path
    ) == ["outcomes/ui/helpers/todo.ts"]


def test_a_group_that_shares_nothing_has_no_helpers_to_own(tmp_path):
    outcome(tmp_path / "outcomes", translation={"test_reload.py": "\n"})

    assert _unowned(tmp_path / "outcomes", "/outcomes/ @owner\n", tmp_path) == []


def test_a_tree_with_no_outcomes_has_nothing_to_own(tmp_path):
    (tmp_path / "outcomes").mkdir()

    assert _unowned(tmp_path / "outcomes", "", tmp_path) == []


# --- what `seal check` does with it -------------------------------------------


def test_seal_check_passes_an_owned_tree(project, capsys):
    outcome(project / "outcomes", translation={"test_reload.py": "\n"})
    write(project / CODEOWNERS_FILENAME, "/outcomes/ @owner\n")

    assert main(["check"]) == 0
    assert "needs a code owner's review to change" in capsys.readouterr().out


def test_seal_check_refuses_an_unowned_tree(project, capsys):
    outcome(project / "outcomes", translation={"test_reload.py": "\n"})
    write(project / CODEOWNERS_FILENAME, "/outcomes/ @owner\n*.py\n")

    assert main(["check"]) == 1

    error = capsys.readouterr().err
    assert "outcomes/ui/todo-list/an-item-survives-a-reload/test_reload.py" in error
    assert "'*.py' (line 2), names no owner" in error
    assert "/rfcs/0009-outcome-tests.md" in error


def test_seal_check_names_the_rule_that_would_cover_the_tree(project, capsys):
    outcome(project / "outcomes")
    write(project / CODEOWNERS_FILENAME, "/services/ @owner\n")

    assert main(["check"]) == 1
    assert "/outcomes/ @your-team" in capsys.readouterr().err


def test_seal_check_refuses_a_project_with_promises_and_no_codeowners(project, capsys):
    """A project that has written promises down and left them ungated is the
    state this check exists to surface, not one that hasn't opted in yet."""
    outcome(project / "outcomes")

    assert main(["check"]) == 1

    error = capsys.readouterr().err
    assert "has no CODEOWNERS" in error
    assert f".github/{CODEOWNERS_FILENAME}" in error
    assert "/outcomes/ @your-team" in error


def test_seal_check_says_nothing_about_a_project_with_no_outcomes(project, capsys):
    """Outcome tests are something a project adopts. Demanding a CODEOWNERS
    from one that declares no promises would be demanding a gate over nothing."""
    assert main(["check"]) == 0
    assert "CODEOWNERS" not in capsys.readouterr().err


def test_a_readiness_failure_does_not_hide_an_ownership_failure(project, capsys):
    """Independent problems in different parts of a project, so fixing them
    shouldn't take as many runs as there are checks."""
    _overlay(
        project / "k8s" / "dev",
        web=_deployment("web", [{"name": "api", "readinessProbe": PROBE}]),
        worker=_deployment("worker", [{"name": "celery"}]),
    )
    outcome(project / "outcomes")

    assert main(["check"]) == 1

    error = capsys.readouterr().err
    assert "no readinessProbe" in error
    assert "has no CODEOWNERS" in error


def test_seal_check_reads_the_codeowners_github_would(project, capsys):
    """A file under .github/ is read; one somewhere GitHub never looks isn't,
    however sensible its contents."""
    outcome(project / "outcomes")
    write(project / "config" / CODEOWNERS_FILENAME, "/outcomes/ @owner\n")

    assert main(["check"]) == 1

    write(project / ".github" / CODEOWNERS_FILENAME, "/outcomes/ @owner\n")
    capsys.readouterr()

    assert main(["check"]) == 0


def test_a_nested_project_is_checked_against_its_repositorys_codeowners(
    project, monkeypatch, capsys
):
    """A project inside a larger repository is governed by that repository's
    file, at paths carrying the project's own prefix -- not by one beside its
    own Tiltfile."""
    repo = project.parent / "repo"
    nested = repo / "examples" / "app"
    nested.mkdir(parents=True)
    (repo / ".git").mkdir()
    write(nested / "Tiltfile", "# root Tiltfile\n")
    (nested / "services").mkdir()
    _overlay(nested / "k8s" / "dev", web={"apiVersion": "v1", "kind": "Namespace",
                                           "metadata": {"name": "web"}})
    outcome(nested / "outcomes")

    # The pattern a project-rooted reading would need, in the place GitHub
    # actually reads from: it owns nothing, because the paths it is matched
    # against carry the project's own prefix.
    write(repo / CODEOWNERS_FILENAME, "/outcomes/ @owner\n")
    monkeypatch.chdir(nested)

    assert main(["check"]) == 1
    assert "/examples/app/outcomes/ @your-team" in capsys.readouterr().err

    write(repo / CODEOWNERS_FILENAME, "/examples/app/outcomes/ @owner\n")
    assert main(["check"]) == 0


def test_an_explicit_outcomes_dir_is_the_tree_that_has_to_be_owned(project, capsys):
    outcome(project / "promises")
    write(project / CODEOWNERS_FILENAME, "/outcomes/ @owner\n")

    assert main(["check", "--outcomes-dir", "promises"]) == 1
    assert "/promises/ @your-team" in capsys.readouterr().err


def test_a_quarantine_note_a_later_rule_uncovers_is_reported(tmp_path):
    """A promise can be excused from failing a run without its test changing
    at all -- a way to a green suite that never went near the application, so
    the note is held to the same rule as the prompt and the test."""
    outcomes = tmp_path / "outcomes"
    write(
        outcomes / CONFIG_FILENAME,
        json.dumps({RUNNER_FIELD: [{"name": "ui", "runner_type": PLAYWRIGHT}]}) + "\n",
    )
    outcome = outcomes / "ui" / "todo-list" / "deleting-is-permanent"
    write(outcome / "prompt.md", "# deleting an item takes it off the list\n")
    write(outcome / "deleting-is-permanent.spec.ts", "test('x', async () => {});\n")
    write(outcome / QUARANTINE_FILENAME, "the delete button races the re-render.\n")
    # A later, owner-less rule: it wins, and clears ownership of the note.
    unowned = _unowned(outcomes, "/outcomes/ @a-team\nquarantine.md\n", tmp_path)

    assert unowned == [
        (outcome / QUARANTINE_FILENAME).relative_to(tmp_path).as_posix()
    ]
