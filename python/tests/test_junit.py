"""What a service's JUnit report is read to mean, and what `seal ci` does
about it.

Every report here is one the test writes itself: what's under test is the
reading, not any one runner's dialect. The reports are shaped the way pytest
and karma actually write them (a bare `<testsuite>` from one, a
`<testsuites>` wrapper from the other, a coverage report sitting in the same
directory), because those are the shapes that reach a project.
"""

import json
from pathlib import Path

import pytest

from seal.junit import read_run_tests, read_service_tests
from seal.seal import MAX_RENDERED_FAILURES, main

SERVICE = "example-api"


def write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def report(*cases: str, name: str = "tests", wrapped: bool = False) -> str:
    suite = "<testsuite name='{}' tests='{}'>{}</testsuite>".format(
        name, len(cases), "".join(cases),
    )
    return "<testsuites>{}</testsuites>".format(suite) if wrapped else suite


PASSING = "<testcase classname='tests.test_todo' name='test_lists_todos'/>"
FAILING = (
    "<testcase classname='tests.test_todo' name='test_adds_a_todo'>"
    "<failure message='assert 1 == 2'/></testcase>"
)
ERRORING = (
    "<testcase classname='tests.test_todo' name='test_deletes_a_todo'>"
    "<error message='fixture not found'/></testcase>"
)
SKIPPED = (
    "<testcase classname='tests.test_todo' name='test_exports'>"
    "<skipped message='needs a licence'/></testcase>"
)


def test_a_report_where_every_case_passed_is_a_pass(tmp_path):
    write(tmp_path / "junit.xml", report(PASSING, PASSING))

    tests = read_service_tests(SERVICE, tmp_path)

    assert tests.passed
    assert tests.cases == 2


def test_a_failed_case_fails_the_service(tmp_path):
    write(tmp_path / "junit.xml", report(PASSING, FAILING))

    tests = read_service_tests(SERVICE, tmp_path)

    assert not tests.passed
    assert tests.failed == ("tests.test_todo.test_adds_a_todo (junit.xml)",)


def test_an_errored_case_fails_the_service_the_same_way(tmp_path):
    """A test that couldn't run and a test that ran and was wrong are
    different problems for whoever fixes them, but the same answer to
    whether this service's tests passed."""
    write(tmp_path / "junit.xml", report(ERRORING))

    assert not read_service_tests(SERVICE, tmp_path).passed


def test_a_skipped_case_is_neither_passed_nor_failed(tmp_path):
    """It is still counted and still reported, so a suite quietly skipping
    what somebody thinks it runs is visible in the one line CI prints."""
    write(tmp_path / "junit.xml", report(PASSING, SKIPPED))

    tests = read_service_tests(SERVICE, tmp_path)

    assert tests.passed
    assert tests.skipped == 1
    assert "1 skipped" in tests.summary()


def test_no_results_at_all_is_a_failure(tmp_path):
    """The directory is missing when nothing was ever copied back out of the
    container -- an image that never started, a container killed before the
    sync. A service whose tests nobody can find has not passed them."""
    tests = read_service_tests(SERVICE, tmp_path / "never-synced")

    assert not tests.passed
    assert tests.problems


def test_results_without_a_junit_report_are_a_failure(tmp_path):
    """The test stage's command doesn't fail the build, so a suite that
    never ran leaves a directory that looks like a successful one. The
    absent report is the only thing that says otherwise."""
    write(tmp_path / "coverage.xml", "<coverage line-rate='0.9'></coverage>")

    tests = read_service_tests(SERVICE, tmp_path)

    assert not tests.passed
    assert "no JUnit report" in tests.summary()


def test_a_report_holding_no_cases_is_a_failure(tmp_path):
    """A runner that collected nothing writes a well-formed report saying
    so, and 'zero tests, zero failures' is exactly the green a gate must not
    be able to claim."""
    write(tmp_path / "junit.xml", report())

    tests = read_service_tests(SERVICE, tmp_path)

    assert not tests.passed
    assert "nothing ran" in tests.summary()


def test_a_suite_that_errored_before_running_a_case_is_a_failure(tmp_path):
    """It has no case to hang its error on, so its own attributes are the
    only record of it -- and the passing suite beside it would otherwise
    answer for the whole service."""
    write(
        tmp_path / "junit.xml",
        "<testsuites>"
        + "<testsuite name='ok' tests='1'>{}</testsuite>".format(PASSING)
        + "<testsuite name='broken' tests='0' errors='1'/>"
        + "</testsuites>",
    )

    tests = read_service_tests(SERVICE, tmp_path)

    assert not tests.passed
    assert "broken" in tests.summary()


def test_a_report_cut_off_mid_write_is_a_failure(tmp_path):
    """What a container killed partway through its run leaves behind. The
    half of the report that arrived says nothing about the half that
    didn't."""
    write(tmp_path / "junit.xml", "<testsuite name='tests'><testcase")

    tests = read_service_tests(SERVICE, tmp_path)

    assert not tests.passed
    assert "could not be read" in tests.summary()


def test_reports_are_found_wherever_the_runner_writes_them(tmp_path):
    """Where inside its results directory a runner files its report is the
    runner's business -- karma writes one per browser into a subdirectory of
    its own, pytest one file beside the coverage report. A project shouldn't
    have to declare which."""
    write(tmp_path / "ui" / "junit.xml", report(PASSING, wrapped=True))
    write(tmp_path / "coverage.xml", "<coverage line-rate='0.9'></coverage>")

    tests = read_service_tests(SERVICE, tmp_path)

    assert tests.passed
    assert tests.cases == 1


def test_every_report_in_the_directory_counts(tmp_path):
    """One failing shard among several passing ones fails the service: a
    verdict that only read the first file would be a green one nobody could
    trust."""
    write(tmp_path / "junit-1.xml", report(PASSING))
    write(tmp_path / "junit-2.xml", report(FAILING))

    tests = read_service_tests(SERVICE, tmp_path)

    assert not tests.passed
    assert tests.cases == 2


def test_a_nested_failure_is_counted_once(tmp_path):
    """Suites report their counts to their parent as well as themselves, so
    a verdict summing what each suite declares reports one failure twice --
    and '2 of 1 failed' is not a sentence anyone should have to read."""
    write(
        tmp_path / "junit.xml",
        "<testsuites failures='1'>"
        + "<testsuite name='outer' tests='1' failures='1'>"
        + "<testsuite name='inner' tests='1' failures='1'>{}</testsuite>".format(FAILING)
        + "</testsuite></testsuites>",
    )

    tests = read_service_tests(SERVICE, tmp_path)

    assert len(tests.failed) == 1
    assert tests.cases == 1


def test_the_summary_names_the_service_and_what_ran(tmp_path):
    """It is one line in the Tilt UI and in the CI log, and 'passed' on its
    own doesn't distinguish a suite that ran from one that was emptied."""
    write(tmp_path / "junit.xml", report(PASSING, PASSING))

    assert read_service_tests(SERVICE, tmp_path).summary() == (
        "example-api: 2 tests passed"
    )


@pytest.mark.parametrize(
    "body, exit_code",
    [(report(PASSING), 0), (report(FAILING), 1), ("<coverage/>", 1)],
)
def test_the_cli_exits_on_what_the_report_says(tmp_path, capsys, body, exit_code):
    """The half of the contract Tilt holds: the
    `seal_tests_verdict_<service>` resource is a command whose exit code
    is what fails `tilt ci`, so the verdict has to reach it that way."""
    write(tmp_path / "junit.xml", body)

    assert main(["_tests-verdict", SERVICE, "--results-dir", str(tmp_path)]) == exit_code
    assert SERVICE in capsys.readouterr().out


# --- what a whole run left behind, and what a caller is handed with it ------


def test_a_run_is_read_as_the_directories_its_results_came_back_in(tmp_path):
    """Each service under its own name and the outcome suite under
    `outcomes`, because that is how they reach a project -- and nothing here
    has to tell them apart."""
    write(tmp_path / "api" / "junit.xml", report(PASSING, PASSING))
    write(tmp_path / "outcomes" / "ui" / "todo-list" / "one" / "junit.xml", report(PASSING))

    run = read_run_tests(tmp_path)

    assert [source.service for source in run.sources] == ["api", "outcomes"]
    assert run.passed
    assert run.cases == 3


def test_one_failed_source_fails_the_whole_run(tmp_path):
    """A run is what a caller reports on, and a green headline over a red
    service is the one thing it must never be able to print."""
    write(tmp_path / "api" / "junit.xml", report(FAILING))
    write(tmp_path / "ui" / "junit.xml", report(PASSING))

    run = read_run_tests(tmp_path)

    assert not run.passed
    assert run.failed == 1


def test_a_run_that_produced_nothing_is_a_failure_rather_than_an_absence(tmp_path):
    """A shape whose run died before writing anything looks exactly like one
    whose tests all passed. Which of the two it was is the whole question,
    so silence answers it here."""
    missing = read_run_tests(tmp_path / "never-ran")
    empty = read_run_tests(tmp_path)

    assert not missing.passed and missing.problems
    assert not empty.passed and empty.problems


def test_the_rendered_results_are_keyed_by_the_names_the_caller_gave(tmp_path, capsys):
    """Two shapes verified in one pipeline are two claims, and the caller is
    the only one that knows which run was which -- the results themselves say
    nothing about the overlay that produced them."""
    write(tmp_path / "dev" / "api" / "junit.xml", report(PASSING, FAILING))

    assert main([
        "_tests-results",
        "--run", "dev={}".format(tmp_path / "dev"),
        "--run", "non-dev={}".format(tmp_path / "non-dev"),
    ]) == 0

    rendered = json.loads(capsys.readouterr().out)

    assert list(rendered) == ["dev", "non-dev"]
    assert rendered["dev"]["cases"] == 2
    assert rendered["dev"]["failed"] == 1
    assert rendered["dev"]["sources"][0]["name"] == "api"
    assert "test_adds_a_todo" in rendered["dev"]["sources"][0]["failed"][0]
    # The shape that never ran says so, rather than being left out of a
    # listing where its absence would read as nothing to report.
    assert rendered["non-dev"]["problems"]


def test_the_rendering_is_one_line_a_job_output_can_carry(tmp_path, capsys):
    """It is written to $GITHUB_OUTPUT as `results=<json>`, which is a single
    line. A newline in a test's own name would end the value there and leave
    the rest of it being parsed as more output."""
    write(
        tmp_path / "api" / "junit.xml",
        "<testsuite name='tests' tests='1'>"
        "<testcase classname='t' name='a name\nwith a newline'>"
        "<failure message='no'/></testcase></testsuite>",
    )

    main(["_tests-results", "--run", "dev={}".format(tmp_path)])

    assert capsys.readouterr().out.count("\n") == 1


def test_the_failed_names_are_capped_and_say_how_many_they_left_out(tmp_path, capsys):
    """What carries the rendering has a size limit. A listing that quietly
    got shorter would say a suite failed less than it did, so the count is
    rendered whole beside the names."""
    write(tmp_path / "api" / "junit.xml", report(*[FAILING] * (MAX_RENDERED_FAILURES + 3)))

    main(["_tests-results", "--run", "dev={}".format(tmp_path)])
    source = json.loads(capsys.readouterr().out)["dev"]["sources"][0]

    assert len(source["failed"]) == MAX_RENDERED_FAILURES
    assert source["failed_omitted"] == 3


@pytest.mark.parametrize("entry", ["dev", "=/tmp/results", "dev="])
def test_a_run_that_does_not_name_both_halves_is_refused(entry, capsys):
    """A `--run` missing its directory would render a run that found nothing
    -- a failure reported against a shape whose results were never looked
    for."""
    assert main(["_tests-results", "--run", entry]) == 1
    assert "NAME=DIR" in capsys.readouterr().err


def test_the_same_name_twice_is_refused(tmp_path, capsys):
    """One run's results would replace the other's silently, and the shape
    that vanished is the one nobody would think to look for."""
    assert main([
        "_tests-results",
        "--run", "dev={}".format(tmp_path),
        "--run", "dev={}".format(tmp_path),
    ]) == 1
    assert "twice" in capsys.readouterr().err
