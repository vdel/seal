"""What a service's own test run left behind, and whether it says the tests
passed.

A service's test stage runs its suite while the image is built and writes a
JUnit report into the directory its `seal_service(junit_tests_directory=...)`
names; `register_syncback()` (tilt/seal/tests.Tiltfile) copies that directory
back to the project as `tests-results/<service_name>/`. This module reads it,
and `seal ci` fails on what it says.

The report is the only thing consulted, and that is the point. A test stage
that also wrote a pass/fail flag of its own would be a second answer to the
same question, free to disagree with the first -- and the one a person opens
to find out *which* test failed is the report. So a test stage lets its suite
fail without failing the build (`make unit-tests || true`): the build has to
finish for anything to be copied out of the image at all, and the report says
everything an exit code would have, in more detail.

What that costs is that a service which never ran its tests looks exactly
like one whose tests all passed, unless this module insists otherwise -- and
a suite that never ran is precisely what a green gate must not be able to
claim on a service's behalf (the same rule outcome_suite.py holds for a
promise). So silence is a failure here, not an absence: no report, a report
that does not parse, a report holding no test cases, and a suite that
recorded an error before it could run a case are each a failed service.

Which files hold the report is not something a project has to declare. Test
runners disagree about what to call it and where to put it -- one writes
`junit.xml` beside the coverage report, another a `TESTS-<browser>.xml` per
browser in a subdirectory of its own -- so every `.xml` under the results
directory is examined and the ones whose root element is a JUnit one are the
report. A coverage report sitting in the same directory is not one, and is
passed over rather than configured away.

read_run_tests() reads a whole run's results directory the same way, and is
what lets something outside the run -- a pipeline handing its results to
whoever called it (see `seal _tests-results` in seal.py) -- say what a run
found without parsing a single XML file of its own. It goes through this
module rather than around it precisely because a second reader is free to
disagree with the one the gate's verdict came from.
"""

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

# The two root elements a JUnit report can have: a single suite, or a
# document wrapping several. Anything else in the results directory (a
# coverage report, most often) is some other artifact of the same run.
JUNIT_ROOT_TAGS = ("testsuite", "testsuites")

# What a test case carries when it did not pass. Read as elements rather
# than from the enclosing suite's `failures`/`errors` attributes: nested
# suites report their counts to their parent as well as themselves, so
# summing attributes counts the same failure twice, and a runner is free to
# omit an attribute entirely.
FAILURE_TAGS = ("failure", "error")
SKIPPED_TAG = "skipped"

# What a suite that holds no test cases still says about itself. A suite
# that died before running anything reports its own error and has no case to
# hang it on, so this is the only place that failure is written down.
SUITE_PROBLEM_ATTRIBUTES = ("failures", "errors")


@dataclass(frozen=True)
class ServiceTests:
    """One service's test run, as its report describes it.

    `problems` are the reasons the report cannot be believed rather than
    tests that failed -- they are kept apart because they say something
    different to whoever reads the run: a failed case is the application's
    (or the test's) problem, and a missing report is the service's test
    setup not having done its job.
    """

    service: str
    cases: int
    skipped: int
    failed: tuple[str, ...]
    problems: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failed and not self.problems

    def summary(self) -> str:
        """One line for the Tilt UI and the CI log, then a line per reason.

        A passing service says how much it ran, not just that it passed: "1
        test passed" and "312 tests passed" are the same verdict and very
        different news about a suite somebody thought they had.
        """
        if self.passed:
            skipped = ", {} skipped".format(self.skipped) if self.skipped else ""
            return "{}: {} test{} passed{}".format(
                self.service, self.cases, "" if self.cases == 1 else "s", skipped,
            )

        headline = "{}: tests failed".format(self.service)
        if self.failed:
            headline = "{}: {} of {} test{} failed".format(
                self.service, len(self.failed), self.cases, "" if self.cases == 1 else "s",
            )
        return "\n".join([headline] + ["  " + line for line in self.problems + self.failed])


@dataclass(frozen=True)
class RunTests:
    """Every report one run left behind, grouped by where it came back.

    A run's results directory holds one subdirectory per source of reports:
    each service's own under its service name, and the outcome suite's under
    `outcomes` (see outcome_suite.OUTCOMES_RESULTS_SUBDIR). A caller reading
    the suite through outcome_suite.py -- which is what the gate's own
    per-promise verdict comes from -- excludes that one here, so the same
    results are never read twice by two modules free to disagree about them.

    `problems` are the run's own rather than any source's: a results
    directory that isn't there at all is a run that produced nothing, which
    no source can report on its own behalf because no source exists to.
    """

    sources: tuple[ServiceTests, ...]
    problems: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.problems and all(source.passed for source in self.sources)

    @property
    def cases(self) -> int:
        return sum(source.cases for source in self.sources)

    @property
    def skipped(self) -> int:
        return sum(source.skipped for source in self.sources)

    @property
    def failed(self) -> int:
        return sum(len(source.failed) for source in self.sources)


def read_run_tests(results_dir: Path, exclude: tuple[str, ...] = ()) -> RunTests:
    """Read every JUnit report one run left behind under `results_dir`.

    Silence is a failure here for the same reason it is in
    read_service_tests(): a run that produced nothing looks exactly like one
    whose tests all passed, and that is the claim a gate's results must never
    be readable as.

    `exclude` names subdirectories somebody else reads -- the outcome
    suite's, for a caller reading it through outcome_suite.py. Whether the
    run produced anything is still decided before the exclusion, so a
    project whose only results are its promises' is not reported as a run
    that produced nothing.
    """
    if not results_dir.is_dir():
        return RunTests(
            sources=(),
            problems=(
                "no results came back from this run ({} does not exist)".format(
                    results_dir,
                ),
            ),
        )

    came_back = [child for child in sorted(results_dir.iterdir()) if child.is_dir()]
    sources = tuple(
        read_service_tests(child.name, child)
        for child in came_back
        if child.name not in exclude
    )
    if not came_back:
        return RunTests(
            sources=(),
            problems=("no results came back from this run ({} is empty)".format(results_dir),),
        )
    return RunTests(sources=sources, problems=())


def read_service_tests(service: str, results_dir: Path) -> ServiceTests:
    """Read every JUnit report under `results_dir` and say what they add up
    to for `service`.

    `results_dir` is where that service's results reached the project --
    `tests-results/<service_name>/` -- and it is searched recursively,
    because where inside it a runner writes its report is the runner's
    business (see this module's docstring).
    """
    cases = 0
    skipped = 0
    failed: list[str] = []
    problems: list[str] = []
    reports = 0

    if not results_dir.is_dir():
        return ServiceTests(
            service=service,
            cases=0,
            skipped=0,
            failed=(),
            problems=(
                "no results came back from the test container ({} does not exist)".format(
                    results_dir,
                ),
            ),
        )

    for path in sorted(results_dir.rglob("*.xml")):
        try:
            root = ElementTree.parse(path).getroot()
        except ElementTree.ParseError as error:
            # A report cut off mid-write is what a container killed partway
            # through its run leaves behind, so an unreadable file is a
            # failure rather than a file to pass over.
            problems.append("{} could not be read ({})".format(_relative(path, results_dir), error))
            continue

        if root.tag not in JUNIT_ROOT_TAGS:
            continue

        reports += 1
        for case in root.iter("testcase"):
            cases += 1
            if any(case.find(tag) is not None for tag in FAILURE_TAGS):
                failed.append(_case_name(case, path, results_dir))
            elif case.find(SKIPPED_TAG) is not None:
                skipped += 1

        for suite in root.iter("testsuite"):
            if next(suite.iter("testcase"), None) is None and _declares_a_problem(suite):
                problems.append(
                    "{}: suite '{}' recorded an error without running a test".format(
                        _relative(path, results_dir), suite.get("name", ""),
                    )
                )

    if reports == 0:
        problems.append("no JUnit report was written to {}".format(results_dir))
    elif cases == 0:
        problems.append("the JUnit report holds no test cases -- nothing ran")

    return ServiceTests(
        service=service,
        cases=cases,
        skipped=skipped,
        failed=tuple(failed),
        problems=tuple(problems),
    )


def _declares_a_problem(suite: ElementTree.Element) -> bool:
    for attribute in SUITE_PROBLEM_ATTRIBUTES:
        value = suite.get(attribute, "0")
        if value.strip().isdigit() and int(value) > 0:
            return True
    return False


def _case_name(case: ElementTree.Element, path: Path, results_dir: Path) -> str:
    """How a failed case is named in the summary: the same
    `classname.name` a runner prints, so it can be searched for in the
    report the summary points at.
    """
    name = ".".join(part for part in (case.get("classname"), case.get("name")) if part)
    return "{} ({})".format(name or "unnamed test", _relative(path, results_dir))


def _relative(path: Path, results_dir: Path) -> str:
    """Report paths from the results directory down. The absolute path is
    the same long prefix on every line, and the part that identifies the
    file is what a reader is looking for.
    """
    return str(path.relative_to(results_dir))
