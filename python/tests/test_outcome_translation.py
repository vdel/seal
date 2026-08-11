"""What `seal` hands whoever is about to translate a promise into a test.

Every tree here is one the test writes itself, so what's checked is what an
adopting project gets rather than what `examples/angular-django` happens to
hold. Pure filesystem work -- no Tilt, no cluster, and nothing that starts
an agent, which is the point: seal poses the task and checks the answer.
"""

from seal.outcomes import HELPERS_DIR_NAME, OUTCOMES_DIR_ENV_VAR
from seal.seal import main
# The tree these act on is the same shape the layout tests build, so the
# helpers that build one live there rather than being written twice.
from test_outcomes import (
    TRANSLATION,
    declare_custom_runner,
    declare_tap_group,
    outcome,
    write,
    project,  # noqa: F401 -- a fixture, used by name
)

PROMPT = """# an item I add is still on the list after a reload

Adding something is the one thing this list is for.

This promise deliberately says nothing about *where* on the list a new item
appears, only that it's on it.
"""


def brief(capsys) -> str:
    return capsys.readouterr().out


def test_the_brief_carries_the_promise_in_full(project, capsys):  # noqa: F811
    outcome(project / "outcomes", "todo-list", "an-item-survives-a-reload", prompt=PROMPT)

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    # Not merely the headline: the prose below it is where a promise says
    # what it deliberately does not claim, which is exactly what a
    # translation over-reaches on when nobody put it in front of them.
    for line in PROMPT.splitlines():
        assert line.strip() == "" or line in printed


def test_the_brief_names_the_directory_the_translation_goes_in(project, capsys):  # noqa: F811
    outcome(project / "outcomes", "todo-list", "an-item-survives-a-reload")

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 0

    assert "outcomes/ui/todo-list/an-item-survives-a-reload/" in brief(capsys)


def test_the_brief_names_where_this_groups_tests_share_things(project, capsys):  # noqa: F811
    """A translation that repeats what the outcome beside it already spells
    out is one nobody told where to put it."""
    outcome(project / "outcomes", "todo-list", "an-item-survives-a-reload")

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 0

    assert f"outcomes/ui/{HELPERS_DIR_NAME}/" in brief(capsys)


def test_the_brief_describes_seals_own_runner_where_that_is_what_runs_it(project, capsys):  # noqa: F811
    outcome(project / "outcomes", "todo-list", "an-item-survives-a-reload")

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    assert "Playwright" in printed
    # Named exactly, not summarised: a file spelled some other way is one
    # the suite will not collect, leaving the promise reported as untested.
    assert ".spec.ts" in printed and ".test.tsx" in printed


def test_the_brief_describes_the_groups_own_runner_where_it_declared_one(project, capsys):  # noqa: F811
    outcomes_dir = project / "outcomes"
    declare_custom_runner(outcomes_dir)
    outcome(outcomes_dir, "todo-list", "an-item-survives-a-reload")

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    assert "outcomes/ui/Dockerfile" in printed
    # What seal guarantees a runner it did not write: its own arguments, then
    # the outcomes to run, and where each verdict is read back from.
    assert "then the outcomes this run covers" in printed
    assert "/outcome-results/<epic>/<outcome>/passed" in printed
    # A brief describing seal's runner to a project that brought its own
    # would have somebody write a test nothing is going to start.
    assert "Playwright" not in printed


def test_the_brief_describes_a_group_run_on_the_machine_as_what_starts_it(project, capsys):  # noqa: F811
    """A group whose runner seal starts as a subprocess has no image and
    no verdict file, and a brief describing it as though it had would send
    somebody looking for a Dockerfile that is not coming."""
    outcomes_dir = project / "outcomes"
    declare_tap_group(outcomes_dir)
    outcome(outcomes_dir, "todo-list", "an-item-survives-a-reload")

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    assert "outcomes/ui/run" in printed
    assert "once for the whole" in printed
    # What it reports on is a stream, so the container contract -- a verdict
    # file, a done marker, staying up -- is not what this one has to meet.
    assert "TAP point" in printed
    assert "/outcome-results/<epic>/<outcome>/passed" not in printed
    assert "Dockerfile" not in printed
    assert "Playwright" not in printed


def test_the_brief_does_not_point_a_group_on_the_machine_at_an_address(project, capsys):  # noqa: F811
    """SEAL_BASE_URL is an address inside a cluster, and a subprocess on
    the machine has no cluster to reach until it has brought one up itself."""
    outcomes_dir = project / "outcomes"
    declare_tap_group(outcomes_dir)
    outcome(outcomes_dir, "todo-list", "an-item-survives-a-reload")

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    assert "no SEAL_BASE_URL" in printed
    assert "register_outcome_runner" not in printed


def test_a_review_names_the_kind_of_group_it_found(project, capsys):  # noqa: F811
    """What runs a test decides what a reviewer can be told has already been
    checked, so a review that named the wrong kind would be settling
    questions against the wrong contract."""
    outcomes_dir = project / "outcomes"
    declare_tap_group(outcomes_dir)
    outcome(
        outcomes_dir,
        "todo-list",
        "an-item-survives-a-reload",
        translation={"check": "#!/bin/sh\nexit 0\n"},
    )

    assert main(["outcomes", "review", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    assert "'tap'" in printed
    assert "'custom'" not in printed


def test_the_brief_says_where_the_applications_address_comes_from(project, capsys):  # noqa: F811
    outcome(project / "outcomes", "todo-list", "an-item-survives-a-reload")

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    assert "SEAL_BASE_URL" in printed
    assert "register_outcome_runner" in printed


def test_the_brief_says_how_to_check_what_comes_back(project, capsys):  # noqa: F811
    outcome(project / "outcomes", "todo-list", "an-item-survives-a-reload")

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    assert "seal check" in printed
    assert "seal outcomes run ui/todo-list/an-item-survives-a-reload" in printed


def test_a_slug_that_names_nothing_is_an_error_listing_the_ones_that_do(project, capsys):  # noqa: F811
    outcome(project / "outcomes", "todo-list", "an-item-survives-a-reload")

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-relaod"]) == 1

    errors = capsys.readouterr().err
    assert "no outcome named ui/todo-list/an-item-survives-a-relaod" in errors
    assert "ui/todo-list/an-item-survives-a-reload" in errors


def test_an_outcome_that_already_has_a_translation_is_refused(project, capsys):  # noqa: F811
    outcome(
        project / "outcomes",
        "todo-list",
        "an-item-survives-a-reload",
        translation=TRANSLATION,
    )

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "already has a translation" in captured.err
    assert "reload.spec.ts" in captured.err
    assert "--rewrite" in captured.err


def test_rewrite_briefs_a_replacement_and_says_that_is_what_it_is(project, capsys):  # noqa: F811
    outcome(
        project / "outcomes",
        "todo-list",
        "an-item-survives-a-reload",
        translation=TRANSLATION,
    )

    assert (
        main(["outcomes", "translate", "--rewrite", "ui/todo-list/an-item-survives-a-reload"])
        == 0
    )

    printed = brief(capsys)
    # The reviewer of a rewrite is answering a different question from the
    # reviewer of a first translation, so the brief has to say which of the
    # two it is asking for -- and name what is being replaced.
    assert "REPLACING A COMMITTED TRANSLATION" in printed
    assert "reload.spec.ts" in printed


def test_rewriting_a_promise_nothing_has_been_written_from_briefs_first_authorship(
    project,  # noqa: F811
    capsys,
):
    outcome(project / "outcomes", "todo-list", "an-item-survives-a-reload")

    assert (
        main(["outcomes", "translate", "--rewrite", "ui/todo-list/an-item-survives-a-reload"])
        == 0
    )

    # The flag is consent to replace something, not a description of what is
    # there. Nothing is, so the brief says so by not claiming otherwise.
    assert "REPLACING A COMMITTED TRANSLATION" not in brief(capsys)


def test_an_untranslated_outcome_is_briefed_without_any_flag(project, capsys):  # noqa: F811
    outcome(project / "outcomes", "todo-list", "an-item-survives-a-reload")

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 0
    assert "Translate one promise into a test" in brief(capsys)


def test_the_brief_reads_the_tree_a_project_says_it_keeps(project, monkeypatch, capsys):  # noqa: F811
    outcome(project / "promises", "todo-list", "an-item-survives-a-reload")
    monkeypatch.setenv(OUTCOMES_DIR_ENV_VAR, "promises")

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 0
    assert "promises/ui/todo-list/an-item-survives-a-reload/" in brief(capsys)


def test_translating_needs_a_slug(project, capsys):  # noqa: F811
    outcome(project / "outcomes", "todo-list", "an-item-survives-a-reload")

    # One promise at a time. A brief is a task somebody is about to do, and
    # a command that briefed the whole tree at once would be a document
    # nobody reads rather than a task anybody starts.
    assert main(["outcomes", "translate"]) == 1
    assert "seal outcomes translate" in capsys.readouterr().err


# --- what a reviewer of a translation is given --------------------------------

SPEC = """import { expect, test } from '@playwright/test';

// Translated from prompt.md beside this file.
test('an added item survives a reload', async ({ page }) => {
  await page.goto('/');
});
"""


def test_the_review_puts_the_promise_beside_the_translation(project, capsys):  # noqa: F811
    outcome(
        project / "outcomes",
        "todo-list",
        "an-item-survives-a-reload",
        prompt=PROMPT,
        translation={"reload.spec.ts": SPEC},
    )

    assert main(["outcomes", "review", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    # Both, and in full. A change that only adds a translation shows the
    # test and not the prompt -- the prompt did not change, so it is not in
    # the diff -- while the reviewer's whole question is whether the one
    # encodes the other.
    for line in PROMPT.splitlines() + SPEC.splitlines():
        assert line.strip() == "" or line in printed


def test_the_review_says_which_files_actually_start_a_test(project, capsys):  # noqa: F811
    outcome(
        project / "outcomes",
        "todo-list",
        "an-item-survives-a-reload",
        translation={"reload.spec.ts": SPEC, "helpers/list.ts": "export const x = 1;\n"},
    )

    assert main(["outcomes", "review", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    started = printed.split("Started by the 'playwright' runner:")[1]
    assert "reload.spec.ts" in started.split("Anything above")[0]
    # A helper is read for what it does to the assertions; a file nothing
    # collects is read for whether anything reaches it at all.
    assert "helpers/list.ts" not in started.split("Anything above")[0]


def test_the_review_reports_a_translation_that_sleeps(project, capsys):  # noqa: F811
    outcome(
        project / "outcomes",
        "todo-list",
        "an-item-survives-a-reload",
        translation={"reload.spec.ts": "await page.waitForTimeout(500);\n"},
    )

    assert main(["outcomes", "review", "ui/todo-list/an-item-survives-a-reload"]) == 0
    assert "sleeps on the clock" in brief(capsys)


def test_the_review_reports_a_translation_that_polls(project, capsys):  # noqa: F811
    outcome(
        project / "outcomes",
        "todo-list",
        "an-item-survives-a-reload",
        translation={"reload.spec.ts": SPEC},
    )

    assert main(["outcomes", "review", "ui/todo-list/an-item-survives-a-reload"]) == 0
    assert "on state, not on the clock" in brief(capsys)


def test_the_review_says_when_the_gate_does_not_reach_this_outcome(project, capsys):  # noqa: F811
    outcome(
        project / "outcomes",
        "todo-list",
        "an-item-survives-a-reload",
        translation={"reload.spec.ts": SPEC},
    )
    # A later rule with no owners takes ownership back off what it matches,
    # which is one of the two ways a CODEOWNERS rule silently stops holding.
    (project / "CODEOWNERS").write_text("* @owner\n*.ts\n", encoding="utf-8")

    assert main(["outcomes", "review", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    assert "not fully gated" in printed
    assert "reload.spec.ts" in printed.split("Who can change it")[1]


def test_the_review_names_the_helpers_the_test_may_import(project, capsys):  # noqa: F811
    """A translation is reviewed against files the diff may not carry. The
    review renders this outcome and nothing else, so it says where the rest
    of what the test reads lives."""
    outcomes_dir = project / "outcomes"
    outcome(
        outcomes_dir, "todo-list", "an-item-survives-a-reload", translation={"reload.spec.ts": SPEC}
    )
    write(outcomes_dir / "ui" / HELPERS_DIR_NAME / "todo.ts", "export const list = 1;\n")

    assert main(["outcomes", "review", "ui/todo-list/an-item-survives-a-reload"]) == 0
    assert f"outcomes/ui/{HELPERS_DIR_NAME}/" in brief(capsys)


def test_a_group_that_shares_nothing_is_not_told_it_does(project, capsys):  # noqa: F811
    outcome(
        project / "outcomes",
        "todo-list",
        "an-item-survives-a-reload",
        translation={"reload.spec.ts": SPEC},
    )

    assert main(["outcomes", "review", "ui/todo-list/an-item-survives-a-reload"]) == 0
    assert "What it may import" not in brief(capsys)


def test_the_review_says_when_the_gate_does_not_reach_a_helper(project, capsys):  # noqa: F811
    """A test is as editable as what it imports, so a review reporting only
    this outcome's own files would call a test gated that isn't."""
    outcomes_dir = project / "outcomes"
    outcome(
        outcomes_dir, "todo-list", "an-item-survives-a-reload", translation={"reload.spec.ts": SPEC}
    )
    write(outcomes_dir / "ui" / HELPERS_DIR_NAME / "todo.ts", "export const list = 1;\n")
    (project / "CODEOWNERS").write_text("* @owner\n/outcomes/ui/helpers/\n", encoding="utf-8")

    assert main(["outcomes", "review", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    assert "not fully gated" in printed
    assert f"{HELPERS_DIR_NAME}" in printed.split("Who can change it")[1]


def test_the_review_says_when_nothing_gates_anything(project, capsys):  # noqa: F811
    outcome(
        project / "outcomes",
        "todo-list",
        "an-item-survives-a-reload",
        translation={"reload.spec.ts": SPEC},
    )
    (project / "CODEOWNERS").unlink()

    assert main(["outcomes", "review", "ui/todo-list/an-item-survives-a-reload"]) == 0

    # Worth saying plainly: approving a translation the tree does not gate
    # buys less than it looks like it does.
    assert "no CODEOWNERS" in brief(capsys)


def test_the_review_leaves_a_custom_runner_alone(project, capsys):  # noqa: F811
    """seal has no reading of what a runner the project brought starts, so
    what it reaches and how it waits are the reviewer's to spot, said out
    loud rather than answered wrongly."""
    outcomes_dir = project / "outcomes"
    declare_custom_runner(outcomes_dir)
    outcome(
        outcomes_dir,
        "todo-list",
        "an-item-survives-a-reload",
        translation={"check.py": "import time; time.sleep(1)\n"},
    )

    assert main(["outcomes", "review", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    assert "a 'custom' runner this project brought" in printed
    assert "How it waits: not checked" in printed


def test_a_fixture_that_is_not_text_is_named_rather_than_rendered(project, capsys):  # noqa: F811
    """What a test seeds itself from is as much a part of what it asserts as
    the assertions are, so a reviewer is told it exists."""
    directory = outcome(
        project / "outcomes",
        "todo-list",
        "an-item-survives-a-reload",
        translation={"reload.spec.ts": SPEC},
    )
    (directory / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")

    assert main(["outcomes", "review", "ui/todo-list/an-item-survives-a-reload"]) == 0

    printed = brief(capsys)
    assert "shot.png" in printed
    assert "not text" in printed


def test_reviewing_a_promise_with_no_translation_is_refused(project, capsys):  # noqa: F811
    outcome(project / "outcomes", "todo-list", "an-item-survives-a-reload")

    assert main(["outcomes", "review", "ui/todo-list/an-item-survives-a-reload"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    # An ordinary state, not a mistake -- so what it says is what to ask for.
    assert "no translation to review" in captured.err
    assert "seal outcomes translate ui/todo-list/an-item-survives-a-reload" in captured.err


def test_reviewing_a_slug_that_names_nothing_lists_the_ones_that_do(project, capsys):  # noqa: F811
    outcome(
        project / "outcomes",
        "todo-list",
        "an-item-survives-a-reload",
        translation=TRANSLATION,
    )

    assert main(["outcomes", "review", "ui/todo-list/nope"]) == 1

    errors = capsys.readouterr().err
    assert "seal outcomes review: no outcome named ui/todo-list/nope" in errors
    assert "ui/todo-list/an-item-survives-a-reload" in errors


# --- the seam this tooling deliberately doesn't cross -------------------------


def snapshot(root):
    """Every file under a tree, with its contents -- enough to catch a write
    wherever one happened."""
    return {
        path.relative_to(root): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_neither_command_writes_into_the_tree(project, capsys):  # noqa: F811
    """seal poses the task and checks the answer; it does not produce the
    translation. A command that wrote into the outcome tree would be one
    whose output nobody had reviewed sitting where a reviewed test goes."""
    outcomes_dir = project / "outcomes"
    outcome(outcomes_dir, "todo-list", "an-item-survives-a-reload")
    outcome(outcomes_dir, "todo-list", "deleting-is-permanent", translation={"d.spec.ts": SPEC})
    before = snapshot(outcomes_dir)

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 0
    assert main(["outcomes", "--untranslated"]) == 0
    assert main(["outcomes", "review", "ui/todo-list/deleting-is-permanent"]) == 0

    assert snapshot(outcomes_dir) == before


def test_neither_command_starts_a_process(project, monkeypatch, capsys):  # noqa: F811
    """No agent, no `tilt`, nothing. What an agent session did is not
    something a checkout can verify, and seal does not claim what it cannot
    verify from one."""
    outcomes_dir = project / "outcomes"
    outcome(outcomes_dir, "todo-list", "an-item-survives-a-reload")
    outcome(outcomes_dir, "todo-list", "deleting-is-permanent", translation={"d.spec.ts": SPEC})

    def refuse(*args, **kwargs):
        raise AssertionError(f"started a process: {args!r}")

    monkeypatch.setattr("subprocess.run", refuse)
    monkeypatch.setattr("subprocess.Popen", refuse)

    assert main(["outcomes", "translate", "ui/todo-list/an-item-survives-a-reload"]) == 0
    assert main(["outcomes", "--untranslated"]) == 0
    assert main(["outcomes", "review", "ui/todo-list/deleting-is-permanent"]) == 0
