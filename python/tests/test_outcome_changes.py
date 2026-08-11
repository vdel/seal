"""Whether a change has reached the outcome tree, and what saying so is for.

Real git repositories, built by the tests in `tmp_path`: what is under test
is a reading of a repository's own state, and a stubbed `git` would only
check that this file agrees with itself.

Nothing here asserts on `examples/angular-django` -- a project adopting seal
gets this, and gets it from the same code.
"""

import json
import subprocess
from pathlib import Path

import pytest

from seal.outcomes import OUTCOMES_DIR_ENV_VAR
from seal.runners import CONFIG_FILENAME, PLAYWRIGHT, RUNNER_FIELD
from seal.seal import main

GROUP = "ui"
EPIC = "todo-list"
OUTCOME = "deleting-is-permanent"


def write(path: Path, body: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    """An seal project inside a git repository, with one promise and its
    translation committed on `main`."""
    write(tmp_path / "Tiltfile", "# root Tiltfile\n")
    (tmp_path / "services").mkdir()
    write(tmp_path / "services" / "api" / "main.py", "# the application\n")
    outcomes = tmp_path / "outcomes"
    write(
        outcomes / CONFIG_FILENAME,
        json.dumps({RUNNER_FIELD: [{"name": GROUP, "runner_type": PLAYWRIGHT}]}) + "\n",
    )
    outcome = outcomes / GROUP / EPIC / OUTCOME
    write(outcome / "prompt.md", "# deleting an item takes it off the list for good\n")
    write(outcome / f"{OUTCOME}.spec.ts", "test('it does', async () => {});\n")

    git(tmp_path, "init", "--initial-branch", "main")
    git(tmp_path, "config", "user.email", "tests@example.invalid")
    git(tmp_path, "config", "user.name", "tests")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", "the project as it stands")

    monkeypatch.delenv(OUTCOMES_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def outcome_dir(repo: Path) -> Path:
    return repo / "outcomes" / GROUP / EPIC / OUTCOME


def test_a_change_to_the_application_alone_reaches_nothing(repo, capsys):
    """The shape a regression loop is trying to produce, and the one that can
    merge on the strength of the tests."""
    write(repo / "services" / "api" / "main.py", "# the application, fixed\n")

    assert main(["outcomes", "touched"]) == 0

    assert "reaches nothing" in capsys.readouterr().out


def test_an_edited_translation_is_named(repo, capsys):
    write(outcome_dir(repo) / f"{OUTCOME}.spec.ts", "test('it does not', async () => {});\n")

    assert main(["outcomes", "touched"]) == 1

    assert f"outcomes/{GROUP}/{EPIC}/{OUTCOME}/{OUTCOME}.spec.ts" in capsys.readouterr().out


def test_an_edited_prompt_is_named(repo, capsys):
    """Changing what the project promises is as much a code owner's call as
    changing the test: an author free to rewrite the promise never has to
    touch a test to change what is being claimed."""
    write(outcome_dir(repo) / "prompt.md", "# deleting an item usually works\n")

    assert main(["outcomes", "touched"]) == 1

    assert "prompt.md" in capsys.readouterr().out


def test_an_untracked_file_is_named(repo, capsys):
    """A spec nobody has added yet is a translation nobody has reviewed just
    as much as an edited one is. 'It isn't in git yet' is not a distinction
    the gate makes."""
    write(outcome_dir(repo) / "helpers.ts", "export const seed = () => {};\n")

    assert main(["outcomes", "touched"]) == 1

    assert "helpers.ts" in capsys.readouterr().out


def test_a_staged_change_is_named_as_much_as_an_unstaged_one(repo, capsys):
    """Which of the two a file is in is a fact about somebody's next commit,
    and the question here is what the change contains."""
    write(outcome_dir(repo) / f"{OUTCOME}.spec.ts", "test('staged', async () => {});\n")
    git(repo, "add", "-A")

    assert main(["outcomes", "touched"]) == 1

    assert f"{OUTCOME}.spec.ts" in capsys.readouterr().out


def test_a_committed_change_on_this_branch_is_named(repo, capsys):
    """A change is what a branch holds, not what has not been committed yet
    -- so the default is measured from where this branch left the one it will
    merge into."""
    git(repo, "checkout", "-b", "a-fix")
    write(outcome_dir(repo) / f"{OUTCOME}.spec.ts", "test('committed', async () => {});\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "quietly weaken the test")

    assert main(["outcomes", "touched"]) == 1

    assert f"{OUTCOME}.spec.ts" in capsys.readouterr().out


def test_what_the_base_branch_did_since_is_not_this_change_s(repo, capsys):
    """The merge base rather than the base branch's tip: what a change is
    answerable for is what it added."""
    git(repo, "checkout", "-b", "a-fix")
    write(repo / "services" / "api" / "main.py", "# the application, fixed\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "fix the application")
    git(repo, "checkout", "main")
    write(outcome_dir(repo) / "another.spec.ts", "test('elsewhere', async () => {});\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "a translation somebody else had reviewed")
    git(repo, "checkout", "a-fix")

    assert main(["outcomes", "touched"]) == 0

    assert "reaches nothing" in capsys.readouterr().out


def test_a_named_ref_is_what_it_is_measured_against(repo, capsys):
    write(outcome_dir(repo) / f"{OUTCOME}.spec.ts", "test('now', async () => {});\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "edit the test")

    assert main(["outcomes", "touched", "--since", "HEAD"]) == 0
    assert main(["outcomes", "touched", "--since", "HEAD~1"]) == 1


def test_a_ref_that_is_not_one_says_so(repo, capsys):
    assert main(["outcomes", "touched", "--since", "no-such-branch"]) == 1

    assert "not a ref" in capsys.readouterr().err


def test_what_a_touched_path_costs_is_said_rather_than_refused(repo, capsys):
    """Touching the tree is legitimate -- a promise has to be able to change.
    What it costs is a human's approval, and saying so is the whole job here:
    a second mechanism refusing what CODEOWNERS allows would make a green run
    mean less rather than more."""
    write(outcome_dir(repo) / "prompt.md", "# a different promise\n")

    main(["outcomes", "touched"])

    printed = capsys.readouterr().out
    assert "not a mistake" in printed
    assert "cannot merge unattended" in printed


def test_a_project_with_no_outcome_tree_has_nothing_to_touch(repo, capsys):
    """The same non-failure every other outcome command treats an unadopted
    convention as."""
    assert main(["outcomes", "touched", "--outcomes-dir", "promises"]) == 0

    assert "no outcome tree" in capsys.readouterr().out


def test_a_checkout_that_is_not_a_repository_says_so(tmp_path, monkeypatch, capsys):
    """A message rather than a traceback: what a diff would have said is
    enforced by CODEOWNERS at the merge either way."""
    write(tmp_path / "Tiltfile", "# root Tiltfile\n")
    (tmp_path / "services").mkdir()
    write(
        tmp_path / "outcomes" / CONFIG_FILENAME,
        json.dumps({RUNNER_FIELD: [{"name": GROUP, "runner_type": PLAYWRIGHT}]}) + "\n",
    )
    monkeypatch.delenv(OUTCOMES_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)

    assert main(["outcomes", "touched"]) == 1

    assert "not inside a git repository" in capsys.readouterr().err
