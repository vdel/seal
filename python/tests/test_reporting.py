"""What a pipeline hands back about its promises, and what a person reads.

Two layers, and the seam between them is the point. `seal _tests-results`
*reads* -- through the same modules the gate's own verdicts came from, so it
cannot disagree with the run it describes. `seal _report` *renders* -- a page
and a comment, from what the reading printed and from nothing else.

Every tree and every results directory here is one the test writes itself, so
what is checked is what an adopting project gets rather than what
`examples/angular-django` happens to hold.
"""

import json
from pathlib import Path

import pytest

from seal import reporting
from seal.outcome_suite import (
    DEFAULT_RESULTS_DIR_NAME,
    FAILED,
    NO_VERDICT,
    OUTCOMES_RESULTS_SUBDIR,
    PASSED,
    UNTRANSLATED,
    VERDICT_FAILED,
    VERDICT_FILENAME,
    VERDICT_PASSED,
)
from seal.outcome_suite import evidence_in
from seal.outcomes import QUARANTINE_FILENAME
from seal.runners import CONFIG_FILENAME, PLAYWRIGHT, RUNNER_FIELD, TAP
from seal.seal import MAX_PUBLISHED_RECORDINGS, MAX_RENDERED_FAILURES, main

GROUP = "ui"


def write(path: Path, body: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def tree(project: Path, group: str = GROUP, runner_type: str = PLAYWRIGHT) -> Path:
    """An outcome tree with one group, which is the smallest there is."""
    outcomes = project / "outcomes"
    write(
        outcomes / CONFIG_FILENAME,
        json.dumps({RUNNER_FIELD: [{"name": group, "runner_type": runner_type}]}) + "\n",
    )
    return outcomes


def promise(
    project: Path,
    name: str,
    epic: str = "todo-list",
    headline: str | None = None,
    translated: bool = True,
    verdict: str | None = None,
    quarantine: str = "",
    group: str = GROUP,
    junit: str | None = None,
    recorded: tuple[str, ...] = (),
) -> Path:
    """One promise, and whatever its container left behind.

    `verdict` None stands for a test that ran and wrote nothing, which is a
    different thing from a promise nothing has been translated from yet --
    telling those two apart is most of what the reading below is for.
    """
    directory = (project / "outcomes" / group / epic / name)
    write(directory / "prompt.md", "# {}\n".format(headline if headline is not None else name))
    if translated:
        write(directory / "{}.spec.ts".format(name), "test('a promise', () => {});\n")
    if quarantine:
        write(directory / QUARANTINE_FILENAME, quarantine + "\n")
    results = (
        project / DEFAULT_RESULTS_DIR_NAME / OUTCOMES_RESULTS_SUBDIR / group / epic / name
    )
    if verdict is not None:
        write(results / VERDICT_FILENAME, verdict + "\n")
    if junit is not None:
        write(results / "junit.xml", junit)
    # What a runner left behind: paths relative to this promise's own
    # results, since where inside them a runner writes a recording is the
    # runner's business.
    for relative in recorded:
        write(results / relative, "")
    return directory


FAILING_CASE = (
    "<testsuite name='outcome' tests='1' failures='1'>"
    "<testcase classname='deleted' name='stays deleted'><failure message='no'/></testcase>"
    "</testsuite>"
)


def service_report(*cases: str, name: str = "api") -> str:
    return "<testsuite name='{}' tests='{}'>{}</testsuite>".format(
        name, len(cases), "".join(cases)
    )


PASSING = "<testcase classname='api.tests' name='it_works'/>"
FAILING = "<testcase classname='api.tests' name='it_does_not'><failure message='no'/></testcase>"


def read(project: Path, capsys, *extra: str) -> dict:
    """`seal _tests-results` against one run of this project."""
    assert (
        main(
            [
                "_tests-results",
                "--run",
                "dev={}".format(project / DEFAULT_RESULTS_DIR_NAME),
                "--outcomes-dir",
                str(project / "outcomes"),
                *extra,
            ]
        )
        == 0
    )
    return json.loads(capsys.readouterr().out)["dev"]


# --- what the reading says about a promise ----------------------------------


def test_every_promise_is_in_what_the_caller_is_handed(tmp_path, capsys):
    """The whole tree, whatever happened to it. A promise left out of the
    results is indistinguishable from one that passed, and from one the tree
    never declared -- which is the claim the outcome tree exists to make
    impossible."""
    tree(tmp_path)
    promise(tmp_path, "kept", verdict=VERDICT_PASSED)
    promise(tmp_path, "broken", verdict=VERDICT_FAILED)
    promise(tmp_path, "silent", verdict=None)
    promise(tmp_path, "untranslated", translated=False)

    run = read(tmp_path, capsys)

    assert {promise["slug"]: promise["state"] for promise in run["outcomes"]["promises"]} == {
        "ui/todo-list/kept": PASSED,
        "ui/todo-list/broken": FAILED,
        "ui/todo-list/silent": NO_VERDICT,
        "ui/todo-list/untranslated": UNTRANSLATED,
    }
    assert run["outcomes"]["counts"] == {PASSED: 1, FAILED: 1, NO_VERDICT: 1, UNTRANSLATED: 1}


def test_a_promise_is_named_by_what_it_promises_and_not_only_by_its_slug(tmp_path, capsys):
    """A reader deciding whether to merge has not necessarily opened the
    tree. The headline is what the project actually promises; the slug is
    only how the tree spells it."""
    tree(tmp_path)
    promise(tmp_path, "one", headline="a deleted item stays deleted", verdict=VERDICT_FAILED)

    [promised] = read(tmp_path, capsys)["outcomes"]["promises"]

    assert promised["headline"] == "a deleted item stays deleted"


def test_a_promise_whose_runner_writes_no_report_still_has_a_verdict(tmp_path, capsys):
    """A `tap` or `custom` runner writes a verdict file and no JUnit XML at
    all. Read as a service's own tests would be, that is a suite that came
    back silent -- a failure. It is not: the verdict file is the contract
    (see /rfcs/0011-outcome-runners.md), and a project whose promises all
    hold must not be told its gate is red."""
    tree(tmp_path, runner_type=TAP)
    write(tmp_path / "outcomes" / GROUP / "run", "#!/bin/sh\nexit 0\n")
    promise(tmp_path, "kept", verdict=VERDICT_PASSED)

    run = read(tmp_path, capsys)

    assert run["outcomes"]["passed"]
    assert run["passed"]
    assert run["outcomes"]["problems"] == []


def test_a_failing_promise_carries_which_case_failed_where_there_is_one(tmp_path, capsys):
    """Detail rather than verdict: the verdict is the file the suite read,
    and this is what a runner that also wrote a report says about which part
    of the test gave way. Somebody reading a report wants both."""
    tree(tmp_path)
    promise(tmp_path, "broken", verdict=VERDICT_FAILED, junit=FAILING_CASE)

    [promised] = read(tmp_path, capsys)["outcomes"]["promises"]

    assert promised["failed"] == ["deleted.stays deleted (junit.xml)"]


def test_a_broken_promise_fails_the_run_even_where_every_service_passed(tmp_path, capsys):
    """The two halves of what a green run claims. A service suite that passed
    says nothing about whether the application still keeps its promises, and
    a headline over the two of them must never be green while either is
    red."""
    tree(tmp_path)
    promise(tmp_path, "broken", verdict=VERDICT_FAILED)
    write(tmp_path / DEFAULT_RESULTS_DIR_NAME / "api" / "junit.xml", service_report(PASSING))

    run = read(tmp_path, capsys)

    assert run["sources"][0]["passed"]
    assert not run["passed"]


def test_a_quarantined_failure_is_reported_and_does_not_fail_the_run(tmp_path, capsys):
    """The entire point of the state: a test whose determinism somebody is
    fixing shouldn't block every merge meanwhile. It is still reported, and
    still not reported as passed."""
    tree(tmp_path)
    promise(
        tmp_path, "flaky", verdict=VERDICT_FAILED, quarantine="its fixture races the API"
    )

    run = read(tmp_path, capsys)

    assert run["passed"]
    assert run["outcomes"]["quarantined"] == 1
    [promised] = run["outcomes"]["promises"]
    assert promised["state"] == FAILED and promised["quarantined"] is True


def test_results_from_a_suite_no_tree_declares_are_a_problem(tmp_path, capsys):
    """Verdicts came back and the tree read here declares no promise, so the
    two are not describing the same run. Reported, because the alternative
    renders as a project that promises nothing -- and a suite nobody declared
    is exactly what a green gate must not claim on a project's behalf."""
    tree(tmp_path)
    write(
        tmp_path / DEFAULT_RESULTS_DIR_NAME / OUTCOMES_RESULTS_SUBDIR / "ui" / "e" / "o"
        / VERDICT_FILENAME,
        VERDICT_PASSED,
    )

    run = read(tmp_path, capsys)

    assert run["outcomes"]["problems"]
    assert not run["outcomes"]["passed"]
    assert not run["passed"]


def test_a_run_that_never_read_the_promises_says_so_rather_than_failing(tmp_path, capsys):
    """A run can be asked for the faster half of the gate: each service's own
    tests, and the readiness every run gates on. Every promise then has no
    verdict -- which from the results alone is exactly what a suite whose
    tests all failed to write one looks like, and that is a failure. Only the
    caller knows which of the two it is, so it says rather than being guessed
    at from an empty directory."""
    tree(tmp_path)
    promise(tmp_path, "one", verdict=None)
    write(tmp_path / DEFAULT_RESULTS_DIR_NAME / "api" / "junit.xml", service_report(PASSING))

    run = read(tmp_path, capsys, "--no-outcomes")

    assert run["passed"]
    assert run["outcomes"]["read"] is False
    assert run["outcomes"]["promises"] == []


def test_a_run_that_was_asked_and_got_nothing_back_is_still_a_failure(tmp_path, capsys):
    """The other side of the same switch, and the reason it has to be a
    switch: with the promises read, a translated promise that left no verdict
    is a test nothing knows ran."""
    tree(tmp_path)
    promise(tmp_path, "one", verdict=None)
    write(tmp_path / DEFAULT_RESULTS_DIR_NAME / "api" / "junit.xml", service_report(PASSING))

    run = read(tmp_path, capsys)

    assert not run["passed"]
    assert run["outcomes"]["read"] is True
    assert [p["state"] for p in run["outcomes"]["promises"]] == [NO_VERDICT]


def test_a_rendering_of_an_unread_suite_claims_nothing_about_it(tmp_path, capsys):
    """The page and the comment have to be readable as "this says nothing
    about the promises" rather than as "the promises held" -- a green run
    that quietly stopped covering them is the one thing the gate exists to
    refuse."""
    tree(tmp_path)
    promise(tmp_path, "one", headline="a deleted item stays deleted", verdict=None)
    write(tmp_path / DEFAULT_RESULTS_DIR_NAME / "api" / "junit.xml", service_report(PASSING))
    runs = {"dev": read(tmp_path, capsys, "--no-outcomes")}

    page = reporting.render_html(runs)
    comment = reporting.render_markdown(runs)

    for text in (page, comment):
        assert "not asked to read them" in text or "not read by this run" in text
        assert "a deleted item stays deleted" not in text


def test_a_project_with_no_outcome_tree_is_not_a_project_with_a_broken_one(tmp_path, capsys):
    """Outcome tests are something a project adopts, not something it has to
    have before `seal` will report on it."""
    write(tmp_path / DEFAULT_RESULTS_DIR_NAME / "api" / "junit.xml", service_report(PASSING))

    run = read(tmp_path, capsys)

    assert run["passed"]
    assert run["outcomes"]["promises"] == []
    assert run["outcomes"]["problems"] == []


def test_the_reading_is_still_one_line_a_job_output_can_carry(tmp_path, capsys):
    """It is written to $GITHUB_OUTPUT as `results=<json>`, which is a single
    line. A newline in a promise's own headline would end the value there and
    leave the rest being parsed as more output."""
    tree(tmp_path)
    promise(tmp_path, "one", headline="a headline", verdict=VERDICT_PASSED)

    main(
        [
            "_tests-results",
            "--run",
            "dev={}".format(tmp_path / DEFAULT_RESULTS_DIR_NAME),
            "--outcomes-dir",
            str(tmp_path / "outcomes"),
        ]
    )

    assert capsys.readouterr().out.count("\n") == 1


# --- and what a person reads ------------------------------------------------


def rendered(project: Path, capsys, **kwargs) -> tuple[str, str]:
    """The page and the comment, rendered from one reading of this project."""
    runs = {"dev": read(project, capsys)}
    return (
        reporting.render_html(runs, **kwargs),
        reporting.render_markdown(runs, **{k: v for k, v in kwargs.items() if k != "source"}),
    )


def test_both_renderings_say_a_red_run_is_red(tmp_path, capsys):
    """The one thing a report is for. A reviewer scrolling a pull request has
    to be able to tell a green gate from a red one without expanding
    anything, and a page whose headline disagreed with the gate would be
    worse than no page."""
    tree(tmp_path)
    promise(tmp_path, "broken", headline="a deleted item stays deleted", verdict=VERDICT_FAILED)

    page, comment = rendered(tmp_path, capsys)

    assert "FAILED" in page and "FAILED" in comment
    for text in (page, comment):
        assert "ui/todo-list/broken" in text
        assert "a deleted item stays deleted" in text


def test_the_page_holds_every_promise_and_the_comment_leads_with_what_broke(tmp_path, capsys):
    """Two audiences, one source. The page is read from an artifact and has
    room for the whole tree -- "these promises still hold" is the claim a
    green gate makes, and a page that only listed failures would never show
    it being made. The comment has a hard size limit, so it leads with the
    failures and counts the rest."""
    tree(tmp_path)
    promise(tmp_path, "kept", headline="an added item shows up", verdict=VERDICT_PASSED)
    promise(tmp_path, "broken", headline="a deleted item stays deleted", verdict=VERDICT_FAILED)

    page, comment = rendered(tmp_path, capsys)

    assert "an added item shows up" in page
    assert "a deleted item stays deleted" in page
    # The comment names what broke, and says how many held without listing
    # them.
    assert "a deleted item stays deleted" in comment
    assert "an added item shows up" not in comment
    assert "1 passed" in comment


def test_a_promise_that_left_no_verdict_reads_as_one_nobody_can_vouch_for(tmp_path, capsys):
    """Not as a kind of failure to skim past, and never as a pass: a test
    that did not run is what a green suite must not be able to claim (see
    /rfcs/0009-outcome-tests.md)."""
    tree(tmp_path)
    promise(tmp_path, "silent", verdict=None)

    page, comment = rendered(tmp_path, capsys)

    assert NO_VERDICT in page
    assert NO_VERDICT in comment


def test_an_untranslated_promise_is_reported_and_does_not_read_as_a_failure(tmp_path, capsys):
    """An ordinary state a project sits in. It appears in the report because
    a promise nobody can see is a promise nobody translates, and it is not
    news about the application."""
    tree(tmp_path)
    promise(tmp_path, "not-yet", translated=False)
    write(tmp_path / DEFAULT_RESULTS_DIR_NAME / "api" / "junit.xml", service_report(PASSING))

    page, comment = rendered(tmp_path, capsys)

    assert UNTRANSLATED in page
    assert "1 with no test yet" in comment
    assert "All 1 run passed." in comment


def test_nothing_somebody_else_wrote_reaches_the_page_as_markup(tmp_path, capsys):
    """A promise's headline and a test's name are whatever somebody typed,
    and a report's text can come from the service under test. A page that
    interpolated them unescaped would execute what a test was named."""
    tree(tmp_path)
    promise(
        tmp_path,
        "injected",
        headline="<script>alert('x')</script> & <b>bold</b>",
        verdict=VERDICT_FAILED,
    )

    page, _ = rendered(tmp_path, capsys)

    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_the_page_fetches_nothing(tmp_path, capsys):
    """It is read from an artifact download -- often offline, often long
    after the run. A stylesheet or a font from somewhere else is a page that
    renders wrong exactly when somebody needs it."""
    tree(tmp_path)
    promise(tmp_path, "one", verdict=VERDICT_PASSED)

    page, _ = rendered(tmp_path, capsys)

    for reach in ("http://", "https://", "<script", "<link", "<img"):
        assert reach not in page, reach


def test_a_run_that_produced_nothing_is_rendered_as_exactly_that(tmp_path, capsys):
    """The shape whose run died before writing a single report. It looks from
    the reports exactly like a shape nobody asked for, so the rendering has
    to say which it was -- which is the whole reason a reading is handed back
    alongside them."""
    runs = {"dev": {"passed": False, "cases": 0, "skipped": 0, "failed": 0,
                    "problems": ["no results came back from this run"], "sources": [],
                    "outcomes": {}}}

    page = reporting.render_html(runs)
    comment = reporting.render_markdown(runs)

    assert "no results came back from this run" in page
    assert "no results came back from this run" in comment


def test_no_runs_at_all_is_not_rendered_as_nothing_wrong(tmp_path):
    """A pipeline that handed back an empty reading. An empty page reads as a
    clean run, which is the one thing it must never read as."""
    page = reporting.render_html({})
    comment = reporting.render_markdown({})

    assert "no runs" in page
    assert "No runs" in comment


def test_a_capped_listing_says_how_much_it_left_out(tmp_path, capsys):
    """A listing that quietly got shorter would say a suite failed less than
    it did."""
    tree(tmp_path)
    cases = "".join(
        "<testcase classname='c' name='case{}'><failure message='no'/></testcase>".format(index)
        for index in range(MAX_RENDERED_FAILURES + 3)
    )
    write(
        tmp_path / DEFAULT_RESULTS_DIR_NAME / "api" / "junit.xml",
        "<testsuite name='api' tests='{}'>{}</testsuite>".format(
            MAX_RENDERED_FAILURES + 3, cases
        ),
    )

    page, comment = rendered(tmp_path, capsys)

    assert "and 3 more" in page
    assert "{} of {} tests failed".format(
        MAX_RENDERED_FAILURES + 3, MAX_RENDERED_FAILURES + 3
    ) in comment
    assert "and {} more".format(MAX_RENDERED_FAILURES + 3 - reporting.MAX_LISTED_CASES) in comment


def test_the_comment_stays_inside_what_a_comment_can_hold(tmp_path, capsys):
    """GitHub truncates an issue comment past 65536 characters, with nothing
    to say it did. A big tree and a big failure together are what would find
    that out on somebody's pull request."""
    tree(tmp_path)
    for index in range(200):
        promise(
            tmp_path,
            "promise-{}".format(index),
            headline="a promise with a headline of some length " * 3,
            verdict=VERDICT_FAILED,
        )

    _, comment = rendered(tmp_path, capsys)

    assert len(comment) < 65536
    # And says what it left out, so the cap can never be read as a shorter
    # suite.
    assert "and {} more".format(200 - reporting.MAX_LISTED_PROMISES) in comment


def test_what_names_the_run_is_the_callers_to_say(tmp_path, capsys):
    """Only the caller knows what identifies a run in whatever performed it
    -- a commit, a branch, a URL -- so it is rendered verbatim rather than
    reconstructed."""
    tree(tmp_path)
    promise(tmp_path, "one", verdict=VERDICT_PASSED)

    page, _ = rendered(tmp_path, capsys, title="Nightly", source="acme/app@deadbee")

    assert "Nightly" in page
    assert "acme/app@deadbee" in page


# --- the command that writes them -------------------------------------------


def test_the_report_command_writes_what_it_was_asked_for(tmp_path, capsys):
    """Files, and nothing else. Where a rendering goes -- an artifact, a job
    summary, a comment -- is the project's decision, so this writes and never
    sends."""
    reading = tmp_path / "results.json"
    reading.write_text(
        json.dumps({"dev": {"passed": True, "cases": 1, "skipped": 0, "failed": 0,
                            "problems": [], "sources": [], "outcomes": {}}}),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "_report",
                "--results",
                str(reading),
                "--html",
                str(tmp_path / "index.html"),
                "--markdown",
                str(tmp_path / "report.md"),
            ]
        )
        == 0
    )

    assert "<!DOCTYPE html>" in (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "dev" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_rendering_nowhere_is_refused(tmp_path, capsys):
    """A command that read the results and wrote nothing would exit zero
    having done nothing, and the pipeline that called it would upload an
    artifact with no report in it."""
    reading = tmp_path / "results.json"
    reading.write_text("{}", encoding="utf-8")

    assert main(["_report", "--results", str(reading)]) == 1
    assert "--html" in capsys.readouterr().err


@pytest.mark.parametrize("body", ["not json at all", "[1, 2]"])
def test_results_that_are_not_a_reading_are_refused(body, tmp_path, capsys):
    """What this renders is what `seal _tests-results` printed. Anything else
    is a pipeline wired up wrong, and rendering an empty page from it would
    hide that behind a report saying nothing is wrong."""
    reading = tmp_path / "results.json"
    reading.write_text(body, encoding="utf-8")

    assert main(["_report", "--results", str(reading), "--markdown", str(tmp_path / "r.md")]) == 1
    assert "Error" in capsys.readouterr().err


# --- what a failure left behind to look at ---------------------------------


def test_a_failure_reports_where_its_recording_is(tmp_path, capsys):
    """What a red browser test costs somebody is working out what the browser
    actually did. A recording answers that, and a report that did not say
    where one was would leave it sitting in an artifact nobody opens."""
    tree(tmp_path)
    promise(
        tmp_path,
        "broken",
        verdict=VERDICT_FAILED,
        recorded=("artifacts/broken-chromium/video.webm", "log.txt"),
    )

    [promised] = read(tmp_path, capsys)["outcomes"]["promises"]

    assert [(item["kind"], item["path"]) for item in promised["evidence"]] == [
        ("video", "outcomes/ui/todo-list/broken/artifacts/broken-chromium/video.webm"),
        ("log", "outcomes/ui/todo-list/broken/log.txt"),
    ]


def test_a_promise_that_held_is_not_a_listing_of_its_own_files(tmp_path, capsys):
    """Every runner seal supplies records on failure, so a promise that held
    has nothing to show -- and a log listed per passing promise would bury
    the one recording somebody opened the report for."""
    tree(tmp_path)
    promise(tmp_path, "kept", verdict=VERDICT_PASSED, recorded=("log.txt",))

    [promised] = read(tmp_path, capsys)["outcomes"]["promises"]

    assert "evidence" not in promised


def test_a_promise_that_left_no_verdict_still_reports_what_it_wrote(tmp_path, capsys):
    """The state where a recording is worth most: nothing knows whether the
    test ran, and whatever it managed to write before dying is the only thing
    that can say why."""
    tree(tmp_path)
    promise(tmp_path, "silent", verdict=None, recorded=("log.txt",))

    [promised] = read(tmp_path, capsys)["outcomes"]["promises"]

    assert [item["kind"] for item in promised["evidence"]] == ["log"]


def test_the_verdict_and_the_report_are_not_listed_as_things_to_open(tmp_path, capsys):
    """One is the answer the suite already read and the other is where its
    detail already came from, both reported in their own right. Listing them
    again as "something to open" buries what is actually new."""
    tree(tmp_path)
    promise(
        tmp_path,
        "broken",
        verdict=VERDICT_FAILED,
        junit=FAILING_CASE,
        recorded=("artifacts/x/video.webm",),
    )

    [promised] = read(tmp_path, capsys)["outcomes"]["promises"]

    listed = [item["path"] for item in promised["evidence"]]
    assert not any("junit.xml" in path or path.endswith(VERDICT_FILENAME) for path in listed)


def test_the_page_plays_the_recording_where_it_sits(tmp_path, capsys):
    """The page is read from an extracted artifact with the recording beside
    it, so the video is embedded rather than described. Relative, because an
    absolute path would name a directory on whichever machine produced it."""
    tree(tmp_path)
    promise(
        tmp_path,
        "broken",
        verdict=VERDICT_FAILED,
        recorded=("artifacts/broken-chromium/video.webm", "artifacts/broken-chromium/shot.png"),
    )

    page, _ = rendered(tmp_path, capsys)

    assert (
        '<video class="recording" controls preload="none" '
        'src="dev/outcomes/ui/todo-list/broken/artifacts/broken-chromium/video.webm"'
    ) in page
    # The screenshot is a link, and the video is not also listed beneath its
    # own player -- a reader should be offered each file once.
    assert '<li><span class="kind">video' not in page
    assert '<li><span class="kind">image' in page
    assert 'href="dev/outcomes/ui/todo-list/broken/artifacts/broken-chromium/shot.png"' in page


def test_the_comment_names_the_path_because_a_file_in_an_artifact_has_no_url(
    tmp_path, capsys
):
    """A CI artifact is one archive, fetched whole: nothing inside it has an
    address. So the comment names the path and links the archive, which is
    the whole of what a comment can do -- and the page inside it opens the
    file."""
    tree(tmp_path)
    promise(
        tmp_path, "broken", verdict=VERDICT_FAILED, recorded=("artifacts/x/video.webm",)
    )
    runs = {"dev": read(tmp_path, capsys)}

    comment = reporting.render_markdown(runs, artifact_url="https://ci.invalid/artifacts/7")

    assert "video: `dev/outcomes/ui/todo-list/broken/artifacts/x/video.webm`" in comment
    assert "[results artifact](https://ci.invalid/artifacts/7)" in comment


def test_a_comment_with_nowhere_to_fetch_from_still_names_the_paths(tmp_path, capsys):
    """A caller that passed no artifact URL -- or a run that uploaded
    nothing, which reports one as empty. The paths are still what somebody
    needs to find the files, so they are still there."""
    tree(tmp_path)
    promise(
        tmp_path, "broken", verdict=VERDICT_FAILED, recorded=("artifacts/x/video.webm",)
    )
    runs = {"dev": read(tmp_path, capsys)}

    comment = reporting.render_markdown(runs)

    assert "artifacts/x/video.webm" in comment
    assert "results artifact" not in comment


def test_a_green_run_is_not_told_where_to_download_nothing(tmp_path, capsys):
    """The line pointing at the archive is there to reach a recording. With
    no failure there is none, and a comment inviting a download that holds
    nothing worth opening is noise on every passing pull request."""
    tree(tmp_path)
    promise(tmp_path, "kept", verdict=VERDICT_PASSED)
    write(tmp_path / DEFAULT_RESULTS_DIR_NAME / "api" / "junit.xml", service_report(PASSING))
    runs = {"dev": read(tmp_path, capsys)}

    comment = reporting.render_markdown(runs, artifact_url="https://ci.invalid/artifacts/7")

    assert "results artifact" not in comment


def test_what_came_back_is_classified_by_what_opening_it_does(tmp_path):
    """A runner writes whatever it writes -- seal has no reading of it beyond
    the verdict -- so this is a classification of file types rather than a
    list of names any runner was told to produce. Ordered so the recording
    comes first: a reader opening one thing wants that."""
    for relative in (
        "log.txt",
        "report/index.html",
        "artifacts/x/trace.zip",
        "artifacts/x/shot.png",
        "artifacts/x/video.webm",
        "artifacts/x/notes.md",
    ):
        write(tmp_path / relative, "")

    assert [kind for kind, _ in evidence_in(tmp_path)] == [
        "video",
        "image",
        "trace",
        "page",
        "log",
    ]


# --- what a pipeline publishes on its own -----------------------------------


def _publish_list(project: Path, capsys, tmp_path: Path) -> list[dict]:
    """What `seal _report --recordings-list` says a pipeline should give an
    address of its own."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    reading = tmp_path / "results.json"
    reading.write_text(json.dumps({"dev": read(project, capsys)}), encoding="utf-8")
    listed = tmp_path / "list.json"
    assert (
        main(["_report", "--results", str(reading), "--recordings-list", str(listed)]) == 0
    )
    return json.loads(listed.read_text(encoding="utf-8"))


def test_a_broken_promises_recording_is_named_for_publishing(tmp_path, capsys):
    """A file inside an artifact has no address, so a recording worth
    watching gets an upload of its own. The name is built from the run and
    the promise because every runner calls its recording `video.webm` -- two
    artifacts in one run cannot share a name, and a reader looking at a list
    of them needs to know which promise broke."""
    tree(tmp_path)
    promise(
        tmp_path,
        "a-deleted-item-stays-deleted",
        verdict=VERDICT_FAILED,
        recorded=("artifacts/x/video.webm", "artifacts/x/shot.png"),
    )

    [entry] = _publish_list(tmp_path, capsys, tmp_path / "out")

    assert entry["key"] == "dev/ui/todo-list/a-deleted-item-stays-deleted"
    assert entry["name"] == "dev--ui--todo-list--a-deleted-item-stays-deleted.webm"
    assert entry["path"].startswith("dev/outcomes/ui/todo-list/")
    assert entry["path"].endswith("video.webm")


def test_only_a_recording_is_published_and_only_one_per_promise(tmp_path, capsys):
    """A screenshot and a log belong beside the report, not under an address
    of their own -- and a second angle on the same failure is not what
    somebody is missing. Every published file costs an upload."""
    tree(tmp_path)
    promise(
        tmp_path,
        "broken",
        verdict=VERDICT_FAILED,
        recorded=(
            "artifacts/x/video.webm",
            "artifacts/y/video.webm",
            "artifacts/x/shot.png",
            "log.txt",
        ),
    )

    published = _publish_list(tmp_path, capsys, tmp_path / "out")

    assert len(published) == 1
    assert published[0]["path"].endswith("video.webm")


def test_a_promise_that_held_publishes_nothing(tmp_path, capsys):
    """Nothing broke, so there is nothing to watch -- and an upload per green
    promise is a cost paid on every passing pull request."""
    tree(tmp_path)
    promise(tmp_path, "kept", verdict=VERDICT_PASSED, recorded=("artifacts/x/video.webm",))
    write(tmp_path / DEFAULT_RESULTS_DIR_NAME / "api" / "junit.xml", service_report(PASSING))

    assert _publish_list(tmp_path, capsys, tmp_path / "out") == []


def test_no_more_are_named_than_a_pipeline_can_publish(tmp_path, capsys):
    """A pipeline declares its uploads before it knows how many promises
    broke, so the number it can hand out is fixed. Naming more would name
    recordings nothing ever publishes, and a report linking one would link
    nowhere."""
    tree(tmp_path)
    for index in range(MAX_PUBLISHED_RECORDINGS + 3):
        promise(
            tmp_path,
            "broken-{}".format(index),
            verdict=VERDICT_FAILED,
            recorded=("artifacts/x/video.webm",),
        )

    published = _publish_list(tmp_path, capsys, tmp_path / "out")

    assert len(published) == MAX_PUBLISHED_RECORDINGS


def test_a_published_recording_is_linked_from_the_failure_it_belongs_to(tmp_path, capsys):
    """The line the whole arrangement exists for: one click from the comment
    to the video, rather than a download to go looking through."""
    tree(tmp_path)
    promise(tmp_path, "broken", verdict=VERDICT_FAILED, recorded=("artifacts/x/video.webm",))
    runs = {"dev": read(tmp_path, capsys)}

    comment = reporting.render_markdown(
        runs,
        recordings={"dev/ui/todo-list/broken": "https://ci.invalid/artifacts/9001"},
    )

    assert "▶ [watch this failure](https://ci.invalid/artifacts/9001)" in comment
    # And the path to the same file drops out: naming it under a link
    # somebody was just offered in one click is noise.
    assert "video.webm" not in comment


def test_a_recording_is_never_shown_under_the_wrong_shapes_failure(tmp_path, capsys):
    """Two overlays verified in one pipeline can break the same promise. A
    recording keyed by slug alone would show one shape's video under the
    other's failure, which is worse than showing none."""
    tree(tmp_path)
    promise(tmp_path, "broken", verdict=VERDICT_FAILED, recorded=("artifacts/x/video.webm",))
    one = read(tmp_path, capsys)
    runs = {"dev": one, "non-dev": one}

    comment = reporting.render_markdown(
        runs, recordings={"dev/ui/todo-list/broken": "https://ci.invalid/a/1"}
    )

    # One link, under the shape it was recorded on; the other shape names the
    # path instead.
    assert comment.count("watch this failure") == 1
    assert "non-dev/outcomes/ui/todo-list/broken" in comment


def test_a_comment_with_nothing_published_still_says_where_to_look(tmp_path, capsys):
    """A project that turned publishing off, or a pipeline that could not.
    The paths are still what gets somebody to the file."""
    tree(tmp_path)
    promise(tmp_path, "broken", verdict=VERDICT_FAILED, recorded=("artifacts/x/video.webm",))
    runs = {"dev": read(tmp_path, capsys)}

    comment = reporting.render_markdown(runs, recordings={})

    assert "watch this failure" not in comment
    assert "video: `dev/outcomes/ui/todo-list/broken/artifacts/x/video.webm`" in comment
