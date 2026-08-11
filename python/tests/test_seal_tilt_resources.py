"""The Tilt resources seal declares on a project's behalf, and how they're named.

These land in the same flat namespace as a project's own resources, so what
they're called is part of seal's interface rather than an internal detail:
`seal_reset_<service>` is what an end-to-end resource puts in its own
`resource_deps`, and the `seal_` marker is what tells a reader which of
the resources in front of them are theirs.

So what's asserted here is the resource as Tilt itself reports it, read back
from `tilt alpha tiltfile-result` against projects this file writes. Nothing
here depends on the bundled example: a project adopting seal gets what's
checked below, and gets it from the same code.

Needs `tilt` (and the `rsync` its syncback extension verifies on load), and
network on a cold run to fetch the extensions seal loads. Skips without
them rather than failing, the same way the Docker-gated isolation test does.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from seal.outcome_suite import (
    RESET_RESOURCE_PREFIX,
    RUN_PURPOSE,
    SELECTION_FILE,
    SYNCBACK_PURPOSE,
    SYNCBACK_TRIGGER_PURPOSE,
    reset_resources,
    resource_name,
)
from seal.outcomes import HELPERS_DIR_NAME
from seal.runners import CONFIG_FILENAME, CUSTOM, PLAYWRIGHT, RUNNER_FIELD, TAP
from seal.seal import SEAL_CI_ENV_VAR

REPO_ROOT = Path(__file__).resolve().parents[2]
TILT_EXTENSIONS = REPO_ROOT / "tilt"

# Tilt's own wire values, as they appear in tiltfile-result. Asserted as
# numbers because that is what the tool reports; the Starlark side names the
# constants. Tilt folds trigger_mode and auto_init into one value, which is
# why "runs at startup, then only when triggered" has a number of its own.
TRIGGER_MODE_AUTO = 0
TRIGGER_MODE_MANUAL = 2
TRIGGER_MODE_MANUAL_WITH_AUTO_INIT = 1

WITH_RESET = "example-api"
WITHOUT_RESET = "ui"

# Written out rather than derived from WITH_RESET: this string is the
# contract other resources put in their own resource_deps, so a change to
# how it's built should fail here instead of being mirrored into agreement.
# The hyphen in 'example-api' becomes an underscore -- one separator throughout.
RESET_RESOURCE = "seal_reset_example_api"

# What says whether that same service's own tests passed, spelled out for the
# same reason: `seal ci` fails by this resource's name, so it is what a
# project reads in a red run.
VERDICT_RESOURCE = "seal_tests_verdict_example_api"

# What runs that service's own tests inside its running container. Also the
# contract: a project names it to keep something from overlapping with a
# test run, the way it names a reset.
TESTS_RUN_RESOURCE = "seal_tests_run_example_api"

# The same reset script, run before that service's own tests rather than
# after them. Part of the test pipeline rather than the baseline an outcome
# reads, which is what its name says.
TESTS_RESET_RESOURCE = "seal_tests_reset_example_api"

# The group every outcome below sits in, and one outcome in it, spelled the
# way its directories do. A group is what a runner drives, so a slug names
# three of them.
GROUP = "ui"
OUTCOME = f"{GROUP}/todo-list/an-item-survives-a-reload"

# The resources one group's run goes through. Written out rather than built
# from the constants above: these strings are what `seal outcomes run` asks
# Tilt to trigger, so a change to how they're spelled should fail here rather
# than be mirrored into agreement.
RUN_RESOURCE = "seal_outcome_tests_ui"
SYNCBACK_RESOURCE = "seal_outcome_syncback_ui"
SYNCBACK_TRIGGER_RESOURCE = "seal_outcome_syncback_trigger_ui"

# The one resource there is only ever one of per project, whatever it has
# runners: what the whole suite found.
SUITE_RESOURCE = "seal_outcomes"

# Every resource seal declares carries this, and nothing a project would
# plausibly name a resource of its own does.
SEAL_PREFIX = "seal_"

# What every reset resource starts with, whatever service it belongs to.
RESET_PREFIX = "seal_reset_"

pytestmark = pytest.mark.skipif(
    shutil.which("tilt") is None or shutil.which("rsync") is None,
    reason="needs tilt (and the rsync its syncback extension verifies on load)",
)


def _environment(gate: bool) -> dict[str, str]:
    """The environment a Tilt evaluation runs under. `seal ci` puts
    SEAL_CI_ENV_VAR in it to say this run's result is a verdict, so a test
    wanting that answer sets the same thing the CLI would. Explicitly cleared
    otherwise: a session that happens to have been started by `seal ci`
    itself would otherwise leak the signal into every evaluation here."""
    environment = dict(os.environ)
    environment.pop(SEAL_CI_ENV_VAR, None)
    if gate:
        environment[SEAL_CI_ENV_VAR] = "1"
    return environment


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _service(project: Path, name: str, seal_service_args: str = "") -> None:
    _write(
        project / "services" / name / "Tiltfile",
        "load('ext://seal', 'seal_service')\n"
        f"seal_service('{name}', context='.', dockerfile='Dockerfile'{seal_service_args})\n",
    )
    _write(project / "services" / name / "Dockerfile", "FROM alpine\n")


# What each runner is called in these tests. `None` is a promise nothing has
# been translated from yet -- a state a project sits in, not a broken tree.
DEFAULT_RUNNER = PLAYWRIGHT
OWN_RUNNER = CUSTOM

# A group seal starts on the machine rather than in the cluster. This
# file is about what a session declares, and the answer for one of these is
# "nothing" -- which is the assertion, not an omission.
ON_THE_MACHINE = TAP

# What a group's own runner's Dockerfile says, so a test can tell the image
# seal built from the one the project did.
OWN_RUNNER_MARKER = "FROM alpine\n"


def _deployed_service(project: Path, name: str, seal_service_args: str = "") -> None:
    """A service with a Deployment of its own, so it has a Tilt resource
    other resources can actually wait on. `_service()` builds an image and
    stops there, which is enough for anything that only asks what seal
    declared -- not for what waits on what."""
    _service(project, name, seal_service_args)
    manifest = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "labels": {"app": name}},
        "spec": {
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {"containers": [{"name": name, "image": name}]},
            },
        },
    }
    _write(
        project / "services" / name / "Tiltfile",
        (project / "services" / name / "Tiltfile").read_text(encoding="utf-8")
        + f"k8s_yaml(encode_yaml({json.dumps(manifest)}))\n",
    )


def _outcome(
    project: Path, group: str, epic: str, name: str, runner: str | None = DEFAULT_RUNNER
) -> None:
    """One promise in one group of the project's outcome tree, translated for
    the runner named -- or not translated at all, which is a promise with no
    test yet."""
    directory = project / "outcomes" / group / epic / name
    _write(directory / "prompt.md", "# a promise\n")
    if runner == DEFAULT_RUNNER:
        _write(directory / "a-promise.spec.ts", "test('a promise', async () => {});\n")
    elif runner in (OWN_RUNNER, ON_THE_MACHINE):
        # Anything at all is a translation once a group declares a runner of
        # its own: seal has no reading of what that runner starts.
        _write(directory / "check.py", "assert True\n")


# Where the project under test says its application answers. Nothing in these
# tests reaches it -- what's asserted is that it arrives where a runner would
# read it.
BASE_URL = "http://web:8000"


def _declare_runners(project: Path, outcomes: dict[str, str | None] | None) -> None:
    """The config a tree of these outcomes needs: one runner per group they
    name. A group whose outcomes are all untranslated still gets one -- what
    runs a group is a property of the group, not of how far anybody has got
    with writing its tests."""
    if outcomes is None:
        return
    runners: dict[str, str] = {}
    for slug, runner in outcomes.items():
        group = slug.split("/")[0]
        runners[group] = runner or runners.get(group) or DEFAULT_RUNNER
    for group, runner in runners.items():
        if runner == OWN_RUNNER:
            _write(project / "outcomes" / group / "Dockerfile", OWN_RUNNER_MARKER)
        elif runner == ON_THE_MACHINE:
            _write(project / "outcomes" / group / "run", "#!/bin/sh\n")
    _write(
        project / "outcomes" / CONFIG_FILENAME,
        json.dumps(
            {
                RUNNER_FIELD: [
                    {"name": group, "runner_type": runner}
                    for group, runner in runners.items()
                ]
            }
        )
        + "\n",
    )


def _project(
    tmp_path_factory, outcomes: dict[str, str | None] | None = None, **services: str
) -> Path:
    """A project registering seal from this checkout, with one service per
    keyword argument -- the value being whatever else that service passes to
    seal_service(). `outcomes` maps '<epic>/<name>' to the runner that
    translates it (or None for a promise with no test yet); passing the
    argument at all is what makes the project call
    register_outcome_runner()."""
    project = tmp_path_factory.mktemp("project")
    _declare_runners(project, outcomes)
    includes = "".join(f"include('services/{name}/Tiltfile')\n" for name in services)
    runner = (
        f"register_outcome_runner(base_url='{BASE_URL}')\n" if outcomes is not None else ""
    )
    _write(
        project / "Tiltfile",
        # file://, so this exercises tilt/ exactly as it is on disk right now
        # rather than whatever a published revision of it happens to hold.
        f"v1alpha1.extension_repo(name='seal', url='file://{TILT_EXTENSIONS}')\n"
        "v1alpha1.extension(name='seal', repo_name='seal', repo_path='seal')\n"
        "load('ext://seal', 'register_outcome_runner')\n" + includes + runner,
    )
    for name, args in services.items():
        _service(project, name, args)
        if "reset=" in args:
            _write(project / "services" / name / "deploy" / "reset.sh", "#!/bin/sh\necho reset\n")
    for slug, outcome_runner in (outcomes or {}).items():
        _outcome(project, *slug.split("/"), outcome_runner)
    return project


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> Path:
    """One project with a service that declares a reset and one that doesn't.
    `example-api`'s hyphen is deliberate: it's what a real service name
    looks like, and it's the character the resource name normalises."""
    return _project(
        tmp_path_factory,
        **{WITH_RESET: ", reset='deploy/reset.sh'", WITHOUT_RESET: ""},
    )


@pytest.fixture(scope="module")
def manifests(project) -> dict[str, dict]:
    return _evaluate(project)


@pytest.fixture(scope="module")
def every_seal_resource(tmp_path_factory) -> dict[str, dict]:
    """A project with everything seal declares turned on at once -- reset and
    the whole test-result path, which only exists under build_type=test.
    Nothing but seal's own resources are in it, so whatever comes back is
    exactly the set whose names are seal's to answer for."""
    return _evaluate(
        _project(
            tmp_path_factory,
            outcomes={OUTCOME: DEFAULT_RUNNER},
            **{
                WITH_RESET: (
                    ", reset='deploy/reset.sh', test_stage='test'"
                    ", junit_tests_directory='/app/tests-results/'"
                    ", test_command='make unit-tests'"
                ),
            },
        ),
        "--build_type",
        "test",
    )


def _evaluate(
    project: Path, *tiltfile_args: str, gate: bool = False
) -> dict[str, dict]:
    """Evaluate `project`'s Tiltfile with `tiltfile_args` after the `--`.
    `gate=True` runs it under the environment `seal ci` hands Tilt, which is
    how a run says its result is a verdict."""
    result = subprocess.run(
        ["tilt", "alpha", "tiltfile-result", *(["--", *tiltfile_args] if tiltfile_args else [])],
        cwd=project,
        capture_output=True,
        text=True,
        env=_environment(gate),
    )
    if result.returncode != 0:
        pytest.skip(f"tilt could not evaluate the Tiltfile: {result.stderr.strip()[-500:]}")

    return {
        manifest["Name"]: manifest for manifest in json.loads(result.stdout)["Manifests"]
    }


def test_declaring_a_reset_registers_a_resource_named_after_the_service(manifests):
    assert RESET_RESOURCE in manifests


def test_a_service_that_declares_no_reset_registers_nothing(manifests):
    """A service with no state to put back shouldn't acquire a resource that
    does nothing -- and an empty one would still satisfy a resource_deps that
    was expecting a real reset."""
    assert [name for name in manifests if name.startswith(RESET_PREFIX)] == [RESET_RESOURCE]


def test_the_resource_runs_the_declared_script_from_the_service_directory(project, manifests):
    """The path is declared relative to the service's own Tiltfile, and a
    script that runs from anywhere else resolves its own relative paths
    against the wrong place."""
    command = manifests[RESET_RESOURCE]["DeployTarget"]["UpdateCmdSpec"]

    assert command["args"][-1].endswith(
        str(project / "services" / WITH_RESET / "deploy" / "reset.sh")
    )
    assert command["dir"] == str(project / "services" / WITH_RESET)


def test_the_resource_is_triggered_rather_than_run(manifests):
    """Reset throws state away, so nothing should fire it on its own:
    `seal up` would discard whatever a developer was in the middle of
    looking at, and a file edit would do it mid-keystroke."""
    assert manifests[RESET_RESOURCE]["TriggerMode"] == TRIGGER_MODE_MANUAL


def test_the_resource_is_labelled_so_it_groups_in_the_ui(manifests):
    assert "reset" in manifests[RESET_RESOURCE]["Labels"]


def test_a_run_finds_a_reset_by_the_name_the_extension_gives_it(manifests):
    """The half of the contract the Python side holds: `seal outcomes run
    --reset` picks resets out of everything a session declares by prefix, and
    a prefix disagreeing with the extension's spelling would reset nothing at
    all -- silently, since a run with no resets to fire is an ordinary state
    for a project to be in."""
    assert RESET_RESOURCE.startswith(RESET_RESOURCE_PREFIX)
    assert reset_resources(sorted(manifests)) == [RESET_RESOURCE]


def test_a_hyphenated_service_name_is_written_with_underscores(manifests):
    """A resource name reads as one token, so the service name's own
    separator is normalised into the ones around it rather than left to sit
    between them -- `example-api` gives `seal_reset_example_api`, not
    `seal_reset_example-api`."""
    assert "-" not in RESET_RESOURCE
    assert RESET_RESOURCE == RESET_PREFIX + WITH_RESET.replace("-", "_")


def test_every_resource_seal_declares_is_marked_as_seal_s(every_seal_resource):
    """These sit in the same flat namespace as a project's own resources, so
    a reader can only tell which are theirs if seal's all say so. One
    resource missing the marker is one a project can't distinguish from its
    own -- and one it could collide with by naming something reasonably."""
    unmarked = [name for name in every_seal_resource if not name.startswith(SEAL_PREFIX)]

    assert unmarked == []


def test_the_whole_declared_set_is_what_it_should_be(every_seal_resource):
    """Named in full rather than pattern-matched: these strings are what a
    project sees in its Tilt UI and types after `tilt trigger`, so a change
    to any of them should be a decision taken here, not a side effect."""
    assert sorted(every_seal_resource) == [
        "seal_outcome_syncback_trigger_ui",
        "seal_outcome_syncback_ui",
        "seal_outcome_tests_ui",
        "seal_outcomes",
        "seal_reset_example_api",
        "seal_tests_reset_example_api",
        "seal_tests_results_dir",
        "seal_tests_run_example_api",
        "seal_tests_syncback_example_api",
        "seal_tests_syncback_trigger_example_api",
        "seal_tests_verdict_example_api",
    ]


def test_results_are_copied_back_by_number_rather_than_by_name(every_seal_resource):
    """Both halves of the copy, an outcome's results and a service's own.

    A uid inside a container means nothing on the machine the artifacts land
    on, so asking rsync to map one to a name is asking a question with no
    answer -- and the lookup is what makes the copy depend on which base
    image the container happens to be built from."""
    for resource in (
        SYNCBACK_RESOURCE,
        "seal_tests_syncback_example_api",
    ):
        command = " ".join(
            every_seal_resource[resource]["DeployTarget"]["UpdateCmdSpec"]["args"]
        )

        assert "--numeric-ids" in command, resource


def test_a_service_s_verdict_is_read_from_its_own_synced_back_results(every_seal_resource):
    """The other half of the contract python/src/seal/junit.py holds: the
    resource that fails `tilt ci` asks the CLI what that service's report
    says, about the directory that service's own results were copied to.
    Pointed anywhere else it would answer for the wrong service, or for
    nothing at all -- and a directory with no report in it reads as a
    failure, so a mismatch here is red rather than silent."""
    command = " ".join(
        every_seal_resource[VERDICT_RESOURCE]["DeployTarget"]["UpdateCmdSpec"]["args"]
    )

    assert "_tests-verdict" in command
    assert WITH_RESET in command
    assert f"/tests-results/{WITH_RESET}/" in command



@pytest.fixture(scope="module")
def tested_services(tmp_path_factory) -> dict[str, dict]:
    """A test run of a project holding two tested services, one of which
    also declares a reset. Both are deployed, because what is asserted here
    is what waits on what."""
    project = tmp_path_factory.mktemp("tested_services")
    _write(
        project / "Tiltfile",
        f"v1alpha1.extension_repo(name='seal', url='file://{TILT_EXTENSIONS}')\n"
        "v1alpha1.extension(name='seal', repo_name='seal', repo_path='seal')\n"
        f"include('services/{WITH_RESET}/Tiltfile')\n"
        f"include('services/{WITHOUT_RESET}/Tiltfile')\n",
    )
    _deployed_service(
        project,
        WITH_RESET,
        ", reset='deploy/reset.sh', test_stage='test'"
        ", junit_tests_directory='/app/tests-results/'"
        ", test_command='make unit-tests'",
    )
    _write(project / "services" / WITH_RESET / "deploy" / "reset.sh", "#!/bin/sh\necho reset\n")
    _deployed_service(
        project,
        WITHOUT_RESET,
        ", test_stage='test', junit_tests_directory='/app/tests-results/'"
        ", test_command='npm test'",
    )
    return _evaluate(project, "--build_type", "test", gate=True)


def _command(resources: dict[str, dict], name: str) -> str:
    return " ".join(resources[name]["DeployTarget"]["UpdateCmdSpec"]["args"])


def test_a_declared_test_command_runs_inside_the_running_container(tested_services):
    """What a service's tests get by running here rather than in its image's
    build: the container's own environment -- this service's Secret, its
    database, its broker. So the command has to reach the container that
    service actually runs in, named the way the syncback beside it names the
    same pod."""
    command = _command(tested_services, TESTS_RUN_RESOURCE)

    assert "kubectl exec" in command
    assert "deploy/" + WITH_RESET in command
    assert "-c " + WITH_RESET in command
    assert "make unit-tests" in command


def test_a_failing_suite_does_not_fail_the_run_that_performs_it(tested_services):
    """The results are copied out of the container downstream of this, so a
    run that stopped here on a failing suite would take the report of what
    failed with it. The verdict resource is what fails a red run, and it can
    only do that once the report has reached the project.

    Which is why this swallow lives in seal rather than in the command a
    project writes: leaving it out is not a mistake a service should be able
    to make."""
    assert "|| echo" in _command(tested_services, TESTS_RUN_RESOURCE)


def test_the_test_run_waits_for_the_service_it_runs_inside(tested_services):
    """`kubectl exec` against a Deployment that is not up yet reaches
    nothing -- and waiting for ready, rather than merely started, is what
    lets these tests use the dependencies the service itself waited for."""
    other = "seal_tests_run_" + WITHOUT_RESET.replace("-", "_")

    assert tested_services[other]["ResourceDependencies"] == [WITHOUT_RESET]


def test_a_service_with_a_reset_runs_its_tests_from_its_baseline(tested_services):
    """A service's own tests read the state it owns like anything else does,
    so they start from the fixture rather than from whatever the environment
    came up with -- the same reason an outcome test does."""
    assert tested_services[TESTS_RUN_RESOURCE]["ResourceDependencies"] == [
        TESTS_RESET_RESOURCE
    ]
    assert tested_services[TESTS_RESET_RESOURCE]["ResourceDependencies"] == [WITH_RESET]


def test_the_baseline_is_restored_again_after_a_service_s_own_tests(tested_services):
    """Both halves of the sequence: baseline, this service's tests, baseline,
    then the promises. The second restore is what lets an outcome rely on the
    fixture whatever those tests did to get their answer -- without seal
    having to know what they touched."""
    assert tested_services[TESTS_RESET_RESOURCE]["ResourceDependencies"] == [WITH_RESET]
    assert tested_services[TESTS_RUN_RESOURCE]["ResourceDependencies"] == [
        TESTS_RESET_RESOURCE
    ]
    assert tested_services[RESET_RESOURCE]["ResourceDependencies"] == [TESTS_RUN_RESOURCE]


def test_the_results_are_copied_back_only_once_the_tests_have_run(tested_services):
    """A syncback that fired on the service being up would copy back
    whatever the container held before its tests wrote anything -- which
    reads as a service that never ran them."""
    trigger = "seal_tests_syncback_trigger_" + WITH_RESET.replace("-", "_")

    assert TESTS_RUN_RESOURCE in tested_services[trigger]["ResourceDependencies"]


def test_every_tested_service_gets_its_own_run(tested_services):
    """One resource per service rather than one per project: a service's
    tests are its own, and a run that answered for two of them would report
    a failure without saying whose."""
    assert sorted(
        name for name in tested_services if name.startswith("seal_tests_run_")
    ) == [TESTS_RUN_RESOURCE, "seal_tests_run_" + WITHOUT_RESET.replace("-", "_")]


def test_a_test_command_without_a_stage_to_run_it_in_is_refused(tmp_path_factory):
    """The command runs in the deployed container, so the stage holding this
    service's tests has to be the stage that gets built. Left to run, it
    would exec into an image with no tests in it and fail on something that
    reads like the project's own mistake."""
    project = tmp_path_factory.mktemp("no_target")
    _write(
        project / "Tiltfile",
        f"v1alpha1.extension_repo(name='seal', url='file://{TILT_EXTENSIONS}')\n"
        "v1alpha1.extension(name='seal', repo_name='seal', repo_path='seal')\n"
        f"include('services/{WITHOUT_RESET}/Tiltfile')\n",
    )
    _service(project, WITHOUT_RESET, ", test_command='make unit-tests'")

    result = subprocess.run(
        ["tilt", "alpha", "tiltfile-result", "--", "--build_type", "test"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "test_command needs test_stage" in result.stderr


def test_a_tested_service_that_declares_no_reset_still_runs_its_tests(tested_services):
    """A service with no state to put back is not a service with nothing to
    test, and the reset edge above is the only thing the two share."""
    other = WITHOUT_RESET.replace("-", "_")

    assert tested_services["seal_tests_syncback_trigger_" + other][
        "ResourceDependencies"
    ] == ["seal_tests_results_dir", "seal_tests_run_" + other]
    assert "seal_tests_verdict_" + other in tested_services


def test_a_stage_carrying_tests_nothing_runs_is_refused(tmp_path_factory):
    """Building a test stage and never running what is in it produces a
    service that reports no results -- read as a failure, and rightly, but
    with nothing in the message about the declaration that caused it."""
    project = tmp_path_factory.mktemp("no_command")
    _write(
        project / "Tiltfile",
        f"v1alpha1.extension_repo(name='seal', url='file://{TILT_EXTENSIONS}')\n"
        "v1alpha1.extension(name='seal', repo_name='seal', repo_path='seal')\n"
        f"include('services/{WITHOUT_RESET}/Tiltfile')\n",
    )
    _service(
        project,
        WITHOUT_RESET,
        ", test_stage='test', junit_tests_directory='/app/tests-results/'",
    )

    result = subprocess.run(
        ["tilt", "alpha", "tiltfile-result", "--", "--build_type", "test"],
        cwd=project,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "test_command is required" in result.stderr



# --- the outcome suite --------------------------------------------------------


@pytest.fixture(scope="module")
def outcome_suite(tmp_path_factory) -> dict[str, dict]:
    """A project with one translated outcome and one still waiting for a
    test, under a run whose result is a verdict -- which is what makes the
    suite something that happens rather than something to trigger."""
    return _evaluate(
        _project(
            tmp_path_factory,
            outcomes={OUTCOME: DEFAULT_RUNNER, f"{GROUP}/todo-list/deleting-is-permanent": None},
            **{WITHOUT_RESET: ""},
        ),
        gate=True,
    )


def _run_manifest(manifests: dict[str, dict]) -> str:
    return manifests[RUN_RESOURCE]["DeployTarget"]["yaml"]


def test_a_group_is_one_run_however_many_outcomes_it_holds(outcome_suite):
    """One runner per group: the image is built once and the browser
    installed in it once, however many promises the group holds."""
    assert RUN_RESOURCE in outcome_suite
    assert sorted(
        name for name in outcome_suite if name.startswith("seal_outcome")
    ) == [
        SYNCBACK_TRIGGER_RESOURCE,
        SYNCBACK_RESOURCE,
        RUN_RESOURCE,
        SUITE_RESOURCE,
    ]


def test_the_runner_is_told_which_outcomes_to_run(outcome_suite):
    """seal knows which outcomes have been translated and the runner does
    not, so it names them. A runner resolving 'everything in the tree' for
    itself would start promises nobody has written a test for yet and report
    them failed."""
    manifest = _run_manifest(outcome_suite)

    # Named from inside the group: a runner is built from one group and never
    # has to know the others exist.
    assert OUTCOME.split("/", 1)[1] in manifest


def test_a_promise_with_no_test_yet_is_not_one_of_them(outcome_suite):
    """There is nothing to run, and a run told to start it would report a
    promise nobody has translated as a promise that failed."""
    assert "deleting-is-permanent" not in _run_manifest(outcome_suite)


def test_what_a_groups_tests_share_is_not_run_as_an_outcome(tmp_path_factory):
    """`helpers/` holds what a group's tests share and no promises at all, so
    a directory under it is somewhere a helper is kept rather than an outcome
    -- and a run told to start one would report a verdict on something nobody
    promised.

    Under a runner the project brought, where anything at all counts as a
    translation: that is where a nested helper would otherwise read as a test.
    """
    project = _project(
        tmp_path_factory, outcomes={OUTCOME: OWN_RUNNER}, **{WITHOUT_RESET: ""}
    )
    helpers = project / "outcomes" / GROUP / HELPERS_DIR_NAME
    _write(helpers / "todo.py", "LIST = '/todos'\n")
    _write(helpers / "pages" / "todo.py", "PAGE = '/'\n")

    manifest = _run_manifest(_evaluate(project))

    assert OUTCOME.split("/", 1)[1] in manifest
    assert HELPERS_DIR_NAME not in manifest


def test_the_report_is_a_separate_resource_from_the_run(outcome_suite):
    """`tilt ci` stops at the first resource that fails, and "every promise
    still holds" has to be distinguishable from "the one test somebody was
    looking at passed"."""
    assert SUITE_RESOURCE in outcome_suite


def test_the_report_waits_for_the_results_to_arrive(outcome_suite):
    """It reads verdicts, so every verdict has to have arrived first."""
    assert outcome_suite[SUITE_RESOURCE]["ResourceDependencies"] == [SYNCBACK_RESOURCE]


def test_ready_means_the_run_has_finished(outcome_suite):
    """seal writes the probe rather than asking the project for one, which is
    what lets `tilt ci` wait for a run the same way it waits for everything
    else -- and leaves nothing for `seal check`'s readiness rule to catch in a
    manifest seal generated itself.

    The marker rather than a verdict: one container answers for several
    promises, so a run that finished has to be distinguishable from one that
    died after the third of twenty."""
    manifest = _run_manifest(outcome_suite)

    assert "readinessProbe" in manifest
    assert "/outcome-results/done" in manifest


def test_the_suite_runs_seal_outcomes_run(outcome_suite, tmp_path_factory):
    command = outcome_suite[SUITE_RESOURCE]["DeployTarget"]["UpdateCmdSpec"]

    assert command["args"][-1].endswith("outcomes run")


def test_a_project_with_no_outcome_tree_declares_nothing(tmp_path_factory):
    """Outcome tests are something a project adopts, not a precondition for
    calling the function that would wire them in."""
    manifests = _evaluate(_project(tmp_path_factory, outcomes={}, **{WITHOUT_RESET: ""}))

    assert [name for name in manifests if "outcome" in name] == []


def test_a_group_run_on_the_machine_declares_nothing_in_the_session(tmp_path_factory):
    """A 'tap' group is started by `seal outcomes run` as a subprocess,
    not deployed: there is no image to build, no Deployment to wait on and no
    results to copy out of a container. So a session registers nothing for
    it, and what would otherwise be a silent omission is the assertion."""
    manifests = _evaluate(
        _project(
            tmp_path_factory,
            outcomes={"cli/gating/a-promise": ON_THE_MACHINE},
            **{WITHOUT_RESET: ""},
        ),
        "--build_type",
        "test",
    )

    assert [name for name in manifests if "outcome_tests" in name] == []
    assert [name for name in manifests if "outcome_syncback" in name] == []


def test_a_container_group_beside_one_run_on_the_machine_is_untouched(tmp_path_factory):
    """The two kinds coexist in one tree. Whatever seal does about the
    group it cannot deploy, the group it can still gets everything."""
    manifests = _evaluate(
        _project(
            tmp_path_factory,
            outcomes={OUTCOME: DEFAULT_RUNNER, "cli/gating/a-promise": ON_THE_MACHINE},
            **{WITHOUT_RESET: ""},
        ),
        "--build_type",
        "test",
    )

    assert RUN_RESOURCE in manifests
    assert [name for name in manifests if name.endswith("_cli")] == []


# --- what makes the suite run on its own ----------------------------------------


@pytest.fixture(scope="module")
def with_outcomes(tmp_path_factory) -> Path:
    """A project with one translated outcome and nothing else to decide, so
    what the suite does is answered by the run rather than by the project."""
    return _project(
        tmp_path_factory, outcomes={OUTCOME: DEFAULT_RUNNER}, **{WITHOUT_RESET: ""}
    )


def _suite_trigger_modes(manifests: dict[str, dict]) -> list[int]:
    """Both halves of the suite: the group that drives the browser and the
    report that reads what it wrote. A run either performs the whole thing or
    waits to be asked for it -- there is no state where one of them is auto."""
    return [
        manifests[RUN_RESOURCE]["TriggerMode"],
        manifests[SUITE_RESOURCE]["TriggerMode"],
    ]


def test_a_run_whose_result_is_a_verdict_performs_the_suite(with_outcomes):
    """The whole point of the signal: `seal ci` says the run is a gate, and
    the promises are read without anyone asking for them."""
    manifests = _evaluate(with_outcomes, gate=True)

    assert _suite_trigger_modes(manifests) == [TRIGGER_MODE_AUTO, TRIGGER_MODE_AUTO]


def test_a_gate_that_builds_the_images_a_real_environment_runs_still_reads_them(
    with_outcomes,
):
    """The case the build type cannot answer, and the reason the signal
    exists. `--build_type runtime` builds images carrying no test suite --
    which is exactly what a production-shaped overlay deploys -- and the
    promises those images keep are still what the run is gating on."""
    manifests = _evaluate(with_outcomes, "--build_type", "runtime", gate=True)

    assert _suite_trigger_modes(manifests) == [TRIGGER_MODE_AUTO, TRIGGER_MODE_AUTO]


def test_a_gate_that_also_runs_each_service_s_own_tests_reads_them_too(with_outcomes):
    """The other end of the same axis: a build type that turns on each
    service's own test pipeline neither turns the suite on nor off, because
    the run already said."""
    manifests = _evaluate(with_outcomes, "--build_type", "test", gate=True)

    assert _suite_trigger_modes(manifests) == [TRIGGER_MODE_AUTO, TRIGGER_MODE_AUTO]


def test_a_session_somebody_is_about_to_work_in_waits_to_be_asked(with_outcomes):
    """`seal up` starts a session, not a gate, and spending a whole outcome
    suite on every start of one is how a local loop stops being used."""
    manifests = _evaluate(with_outcomes)

    assert _suite_trigger_modes(manifests) == [TRIGGER_MODE_MANUAL, TRIGGER_MODE_MANUAL]


def test_a_run_that_says_it_reads_the_promises_does_so_unasked(with_outcomes):
    """What a build with no CLI in front of it uses -- and what an agent
    reproducing a gate locally reaches for."""
    manifests = _evaluate(with_outcomes, "--run_outcomes", "true")

    assert _suite_trigger_modes(manifests) == [TRIGGER_MODE_AUTO, TRIGGER_MODE_AUTO]


def test_a_run_that_says_it_does_not_overrides_the_gate_it_was_started_as(
    with_outcomes,
):
    """A build whose only job is to publish is started the same way and has
    no promises to read, so saying so has to beat the signal rather than be
    merged with it."""
    manifests = _evaluate(with_outcomes, "--run_outcomes", "false", gate=True)

    assert _suite_trigger_modes(manifests) == [TRIGGER_MODE_MANUAL, TRIGGER_MODE_MANUAL]


def test_a_run_outcomes_value_seal_does_not_know_is_refused(with_outcomes):
    """Naming both is what makes the message actionable, and the flag takes a
    word rather than being bare precisely so a run can say either one."""
    stderr = _evaluation_failure(with_outcomes, "--run_outcomes", "maybe")

    assert "maybe" in stderr
    for known in ("true", "false"):
        assert known in stderr


# --- which runner builds the image a run uses -----------------------------------


def _dockerfile_of(manifests: dict[str, dict], resource: str) -> str:
    """What built the runner's image, as Tilt reports it."""
    (image,) = manifests[resource]["ImageTargets"]
    return image["BuildDetails"]["dockerfileContents"]


def test_a_project_with_only_specs_is_built_by_seal_s_own_runner(outcome_suite):
    """The common case, and the reason the default exists: a project writes
    spec files, and seal supplies the browser, the framework pinned to it,
    and the reporting every outcome would otherwise repeat."""
    dockerfile = _dockerfile_of(outcome_suite, RUN_RESOURCE)

    assert "@playwright/test@" in dockerfile
    assert "npx playwright test" in dockerfile


def test_the_playwright_runner_does_what_every_runner_has_to(outcome_suite):
    """Write the verdict where the suite reads it, and stay up so it can be
    copied out. A runner that exits takes its own results with it."""
    dockerfile = _dockerfile_of(outcome_suite, RUN_RESOURCE)

    assert "/outcome-results/" in dockerfile
    assert "passed" in dockerfile
    assert "sleep infinity" in dockerfile


def test_the_playwright_runner_starts_through_an_entrypoint(outcome_suite):
    """Kubernetes `args` replace an image's CMD rather than adding to it, so
    the arguments a run is told to cover only reach a runner that declares an
    ENTRYPOINT. Its exec form is a JSON array, and an unescaped quote inside
    one ends the string and has Docker read the rest as something else --
    which nothing makes visible until the build fails, a whole CI cycle
    away."""
    (entrypoint,) = [
        line for line in _dockerfile_of(outcome_suite, RUN_RESOURCE).splitlines()
        if line.startswith("ENTRYPOINT ")
    ]

    assert json.loads(entrypoint[len("ENTRYPOINT "):]) == ["/outcome/run.sh"]


def test_the_playwright_runner_pins_its_browser_to_its_framework(outcome_suite):
    """A browser and the framework driving it have to be the same release, or
    it refuses to launch -- which would read as a promise failing. One
    version spells both: the framework is pinned exactly, and the browser is
    whatever *that* install brings, never a separately-versioned base image
    that could drift from it."""
    dockerfile = _dockerfile_of(outcome_suite, RUN_RESOURCE)
    (pinned,) = re.findall(r"@playwright/test@(\S+)", dockerfile)

    assert re.fullmatch(r"\d+\.\d+\.\d+", pinned), f"not an exact version: {pinned}"
    assert "--save-exact" in dockerfile
    assert "npx playwright install --with-deps chromium" in dockerfile


def test_the_playwright_runner_carries_only_the_browser_it_launches(outcome_suite):
    """Its config launches Chromium and nothing else. Firefox and WebKit
    would be freight -- paid for on the daemon that builds the image, the
    registry it is pushed to, and the node that pulls it."""
    dockerfile = _dockerfile_of(outcome_suite, RUN_RESOURCE)

    assert "chromium" in dockerfile
    assert "firefox" not in dockerfile
    assert "webkit" not in dockerfile


def test_a_group_that_brings_a_runner_is_built_by_it(tmp_path_factory):
    """What keeps the tree language-agnostic rather than merely broad: a
    group whose outcomes are not browser-shaped says how they run, and seal
    builds that."""
    manifests = _evaluate(
        _project(tmp_path_factory, outcomes={OUTCOME: OWN_RUNNER}, **{WITHOUT_RESET: ""}),
        "--build_type",
        "test",
    )

    assert _dockerfile_of(manifests, RUN_RESOURCE) == OWN_RUNNER_MARKER


def test_every_runner_is_told_where_the_application_answers(outcome_suite):
    """seal knows nothing about an app's own service names or ports, so the
    project says it once and every runner gets it -- a test that had to
    hardcode an address would be one more thing to keep in agreement."""
    manifest = _run_manifest(outcome_suite)

    assert "SEAL_BASE_URL" in manifest
    assert BASE_URL in manifest


# --- what an outcome test starts from -----------------------------------------


def _reset_project(tmp_path_factory) -> Path:
    """A project whose one service declares a reset, and whose promises are
    read against it."""
    return _project(
        tmp_path_factory,
        outcomes={OUTCOME: DEFAULT_RUNNER},
        **{WITH_RESET: ", reset='deploy/reset.sh'"},
    )


@pytest.fixture(scope="module")
def sequenced(tmp_path_factory) -> dict[str, dict]:
    """A gate run of a project whose service declares a reset, with its
    outcome told to wait for that reset -- the way
    /rfcs/0004-deterministic-state.md says an end-to-end resource names one.

    A gate, because the baseline is due exactly when the promises are read
    against it, and the promises are read when a run's result is a verdict."""
    project = tmp_path_factory.mktemp("sequenced")
    _write(
        project / "Tiltfile",
        f"v1alpha1.extension_repo(name='seal', url='file://{TILT_EXTENSIONS}')\n"
        "v1alpha1.extension(name='seal', repo_name='seal', repo_path='seal')\n"
        "load('ext://seal', 'register_outcome_runner', 'reset_resource_name')\n"
        f"include('services/{WITH_RESET}/Tiltfile')\n"
        f"register_outcome_runner(base_url='{BASE_URL}', resource_deps=[reset_resource_name('{WITH_RESET}')])\n",
    )
    _deployed_service(project, WITH_RESET, ", reset='deploy/reset.sh'")
    _write(project / "services" / WITH_RESET / "deploy" / "reset.sh", "#!/bin/sh\necho reset\n")
    _declare_runners(project, {OUTCOME: DEFAULT_RUNNER})
    _outcome(project, *OUTCOME.split("/"))
    return _evaluate(project, "--build_type", "test", gate=True)


def test_a_test_run_puts_a_service_back_to_its_baseline_before_it_starts(sequenced):
    """A test that starts from whatever the environment came up with fails
    for reasons that have nothing to do with the change under test. There is
    nothing to preserve in a test run -- unlike `seal up`, where the state a
    developer left is the whole point of not resetting."""
    assert sequenced[RESET_RESOURCE]["TriggerMode"] == TRIGGER_MODE_MANUAL_WITH_AUTO_INIT


def test_a_gate_that_builds_runtime_images_still_establishes_the_baseline(
    tmp_path_factory,
):
    """The case a second overlay is verified under. Those images carry no
    test suite, so nothing about them says `test` -- but the promises are
    still read, and they are read against the baseline. A reset that waited
    for test images would leave the suite waiting on a baseline nothing was
    ever going to establish, which is not a red run but a run that never
    ends."""
    manifests = _evaluate(
        _reset_project(tmp_path_factory), "--build_type", "runtime", gate=True
    )

    assert manifests[RESET_RESOURCE]["TriggerMode"] == TRIGGER_MODE_MANUAL_WITH_AUTO_INIT


def test_a_session_somebody_works_in_leaves_the_baseline_alone(tmp_path_factory):
    """`seal up` would throw away the state they left. The way back to the
    baseline is a trigger they ask for."""
    manifests = _evaluate(_reset_project(tmp_path_factory), "--build_type", "runtime")

    assert manifests[RESET_RESOURCE]["TriggerMode"] == TRIGGER_MODE_MANUAL


def test_a_reset_waits_for_the_service_whose_state_it_puts_back(sequenced):
    """The script acts on the service through the cluster, and `kubectl exec`
    against a Deployment that isn't up yet reaches nothing."""
    assert sequenced[RESET_RESOURCE]["ResourceDependencies"] == [WITH_RESET]


def test_an_outcome_waits_for_what_the_project_told_it_to(sequenced):
    """seal knows which services declared a reset, not which ones an outcome
    reads -- and a dependency nobody asked for is a slower run at best and a
    cycle at worst. So the project names them."""
    assert sequenced[RUN_RESOURCE]["ResourceDependencies"] == [RESET_RESOURCE]


def test_outcomes_run_one_at_a_time(outcome_suite):
    """They drive the same application, so running them at once means each
    asserting on a list the others are adding to and deleting from -- and a
    promise that holds would fail for what another test was doing.

    One container runs every outcome, so what serialises them is the runner's
    own configuration rather than the order Tilt starts resources in."""
    dockerfile = _dockerfile_of(outcome_suite, RUN_RESOURCE)

    assert "workers: 1" in dockerfile


def test_naming_outcomes_narrows_a_run(tmp_path_factory):
    """What `seal outcomes run <slug>...` writes, and what makes a subset
    cheap: the same runner, told to start fewer of them."""
    second = f"{GROUP}/todo-list/deleting-is-permanent"
    project = _project(
        tmp_path_factory,
        outcomes={OUTCOME: DEFAULT_RUNNER, second: DEFAULT_RUNNER},
        **{WITHOUT_RESET: ""},
    )
    _write(project / SELECTION_FILE, f"{second}\n")
    manifest = _run_manifest(_evaluate(project))

    assert second.split("/", 1)[1] in manifest
    assert OUTCOME.split("/", 1)[1] not in manifest


def test_naming_nothing_runs_every_translated_outcome(tmp_path_factory):
    """An empty selection is the whole tree, which is what `seal ci` runs --
    a merge gate over the tests somebody remembered is not a gate."""
    second = f"{GROUP}/todo-list/deleting-is-permanent"
    project = _project(
        tmp_path_factory,
        outcomes={OUTCOME: DEFAULT_RUNNER, second: DEFAULT_RUNNER},
        **{WITHOUT_RESET: ""},
    )
    _write(project / SELECTION_FILE, "")
    manifest = _run_manifest(_evaluate(project))

    assert OUTCOME.split("/", 1)[1] in manifest
    assert second.split("/", 1)[1] in manifest


def test_a_selection_naming_nothing_that_exists_does_not_stop_the_session(tmp_path_factory):
    """`seal outcomes run` refuses an unknown slug before writing the file,
    so what reaches the Tiltfile is already checked -- and a stale file left
    by an older tree should not stop a session loading."""
    project = _project(
        tmp_path_factory, outcomes={OUTCOME: DEFAULT_RUNNER}, **{WITHOUT_RESET: ""}
    )
    _write(project / SELECTION_FILE, f"{GROUP}/todo-list/nothing-by-that-name\n")
    manifests = _evaluate(project, "--build_type", "test")

    assert [name for name in manifests if "outcome" in name] == []


def test_the_cli_names_the_same_resources_the_extension_declares(outcome_suite):
    """`seal outcomes run <slug>` triggers these by name, and nothing checks
    a name before triggering it -- Tilt is content to be asked about a
    resource that does not exist. A name that drifted from the extension's
    would run nothing, wait for nothing, and leave the last run's verdicts to
    be read as this one's, which is why both halves are pinned here rather
    than each against itself."""
    for purpose, resource in (
        (RUN_PURPOSE, RUN_RESOURCE),
        (SYNCBACK_TRIGGER_PURPOSE, SYNCBACK_TRIGGER_RESOURCE),
        (SYNCBACK_PURPOSE, SYNCBACK_RESOURCE),
    ):
        assert resource_name(purpose, GROUP) == resource
        assert resource in outcome_suite


# --- more than one group ------------------------------------------------------

# A second group, run by a runner the project brings -- an API-only service's
# promises, which have no page to open.
OTHER_GROUP = "api"
OTHER_OUTCOME = f"{OTHER_GROUP}/billing/an-invoice-is-issued-once"
OTHER_RUN_RESOURCE = "seal_outcome_tests_api"


@pytest.fixture(scope="module")
def two_groups(tmp_path_factory) -> dict[str, dict]:
    """A project whose promises are not all of one kind: browser-shaped ones
    under seal's own runner, and API-shaped ones under the project's. Under a
    run whose result is a verdict, which is when the order they run in is
    seal's to decide."""
    return _evaluate(
        _project(
            tmp_path_factory,
            outcomes={OUTCOME: DEFAULT_RUNNER, OTHER_OUTCOME: OWN_RUNNER},
            **{WITHOUT_RESET: ""},
        ),
        gate=True,
    )


def test_each_group_gets_the_runner_declared_for_it(two_groups):
    """The whole point of grouping: what an API-only service promises is not
    tested by the thing that tests what somebody sees."""
    assert "@playwright/test@" in _dockerfile_of(two_groups, RUN_RESOURCE)
    assert _dockerfile_of(two_groups, OTHER_RUN_RESOURCE) == OWN_RUNNER_MARKER


def test_a_group_is_told_only_its_own_outcomes(two_groups):
    """A runner is built from one group and reports into <epic>/<outcome>,
    so a slug from another group would name a directory it does not have."""
    assert "billing" not in _run_manifest(two_groups)
    assert "todo-list" not in two_groups[OTHER_RUN_RESOURCE]["DeployTarget"]["yaml"]


def test_a_runners_own_arguments_come_before_the_outcomes_it_runs(tmp_path_factory):
    """The one thing about a runner seal has no way to know, and the reason
    the argument list has a separator in it: a runner that takes no arguments
    still reads its outcomes from one fixed place."""
    project = _project(
        tmp_path_factory, outcomes={OUTCOME: DEFAULT_RUNNER}, **{WITHOUT_RESET: ""}
    )
    _write(
        project / "outcomes" / CONFIG_FILENAME,
        json.dumps(
            {
                RUNNER_FIELD: [
                    {
                        "name": GROUP,
                        "runner_type": PLAYWRIGHT,
                        "runner_args": ["--timeout=60000"],
                    }
                ]
            }
        )
        + "\n",
    )
    manifest = _run_manifest(_evaluate(project))
    arguments = yaml.safe_load(manifest)["spec"]["template"]["spec"]["containers"][0]["args"]

    assert arguments == ["--timeout=60000", "--", OUTCOME.split("/", 1)[1]]


def test_groups_run_one_after_another(two_groups):
    """Two groups at once is the same interference two outcomes at once would
    be: each asserting on state the other is changing, and a promise that
    holds failing for what another test was doing.

    Groups are ordered by name, so 'api' runs first and 'ui' waits for it.
    Tilt reports a resource with no dependencies as None rather than an empty
    list, which is what the first of them looks like."""
    assert two_groups[OTHER_RUN_RESOURCE]["ResourceDependencies"] in (None, [])
    assert two_groups[RUN_RESOURCE]["ResourceDependencies"] == [OTHER_RUN_RESOURCE]


def test_the_report_waits_for_every_group_s_results(two_groups):
    """"Every promise still holds" is a claim about all of them, so no
    group's verdicts can still be in flight when it is read."""
    assert sorted(two_groups[SUITE_RESOURCE]["ResourceDependencies"]) == [
        "seal_outcome_syncback_api",
        "seal_outcome_syncback_ui",
    ]


# --- The build kind ---------------------------------------------------------
#
# `--build_type` is an enum seal owns (see /rfcs/0008-run-axes.md). These
# exercise the flag itself: which values it takes, what it resolves to when
# nothing says, and that its predecessor is refused rather than ignored.
#
# The stage a service builds is observable only once its image attaches to a
# workload, so this fixture -- unlike the rest of this file's, which assert on
# local_resources -- gives the service a Deployment to attach to.


def _built_target(project: Path, *tiltfile_args: str) -> str | None:
    """The Dockerfile stage `docker_build()` was asked for, as Tilt recorded
    it. Empty means a build with no target at all, which Docker resolves to
    the Dockerfile's last stage."""
    result = subprocess.run(
        ["tilt", "alpha", "tiltfile-result", *(["--", *tiltfile_args] if tiltfile_args else [])],
        cwd=project,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"tilt could not evaluate the Tiltfile: {result.stderr.strip()[-500:]}")

    targets = [
        (image["BuildDetails"] or {}).get("target")
        for manifest in json.loads(result.stdout)["Manifests"]
        for image in (manifest.get("ImageTargets") or [])
    ]
    assert len(targets) == 1, f"expected one built image, got {len(targets)}"
    return targets[0]


def _deployed_project(
    tmp_path_factory, seal_service_args: str = "", root_extra: str = "",
) -> Path:
    """One service with a Deployment to attach its image to. `root_extra` is
    written into the root Tiltfile before the service is included, which is
    where a project's own `default_registry()` call has to go -- Tilt only
    rewrites image refs built after it."""
    project = tmp_path_factory.mktemp("build_type")
    _write(
        project / "Tiltfile",
        f"v1alpha1.extension_repo(name='seal', url='file://{TILT_EXTENSIONS}')\n"
        "v1alpha1.extension(name='seal', repo_name='seal', repo_path='seal')\n"
        + root_extra
        + f"include('services/{WITHOUT_RESET}/Tiltfile')\n"
        "k8s_yaml('workload.yaml')\n",
    )
    _service(project, WITHOUT_RESET, seal_service_args)
    _write(
        project / "workload.yaml",
        "apiVersion: apps/v1\n"
        "kind: Deployment\n"
        f"metadata:\n  name: {WITHOUT_RESET}\n"
        "spec:\n"
        f"  selector:\n    matchLabels:\n      app: {WITHOUT_RESET}\n"
        "  template:\n"
        f"    metadata:\n      labels:\n        app: {WITHOUT_RESET}\n"
        "    spec:\n"
        "      containers:\n"
        f"      - name: {WITHOUT_RESET}\n        image: {WITHOUT_RESET}\n"
        "        readinessProbe:\n          httpGet:\n            path: /\n            port: 80\n",
    )
    return project


# What a service's own Dockerfile calls each of its stages. Deliberately not
# the build type's own spelling: seal names a kind of image, the service
# names what to build for it, and a test that used one word for both could
# not tell the two apart.
DEVELOPMENT_STAGE = "while-you-work"
RUNTIME_STAGE = "for-real"
TEST_STAGE = "carries-the-suite"

ALL_STAGES = (
    f", development_stage='{DEVELOPMENT_STAGE}'"
    f", runtime_stage='{RUNTIME_STAGE}'"
    f", test_stage='{TEST_STAGE}'"
    ", test_command='make unit-tests'"
    ", junit_tests_directory='/app/tests-results/'"
)


@pytest.fixture(scope="module")
def deployed_project(tmp_path_factory) -> Path:
    return _deployed_project(tmp_path_factory, ALL_STAGES)


@pytest.mark.parametrize(
    "build_type,stage",
    [
        ("development", DEVELOPMENT_STAGE),
        ("runtime", RUNTIME_STAGE),
        ("test", TEST_STAGE),
    ],
)
def test_the_build_type_picks_the_stage_the_service_named(
    deployed_project, build_type, stage,
):
    """seal owns the kind, the service owns the name. Nothing here requires a
    project to spell its stages the way seal spells its build types."""
    assert _built_target(deployed_project, "--build_type", build_type) == stage


def test_no_build_type_given_is_a_development_build(deployed_project):
    """A run that says nothing is a working session, which is the only kind
    of run somebody starts without stating what it is for."""
    assert _built_target(deployed_project) == DEVELOPMENT_STAGE


def test_the_overlay_does_not_decide_the_build_type(deployed_project):
    """A build kind is not something a manifest shape gets to imply. An
    overlay that resolved its own would make a run against a
    production-shaped one silently build production images -- and, where the
    run publishes, push them."""
    assert (
        _built_target(deployed_project, "--k8s_overlay", "stag") == DEVELOPMENT_STAGE
    )


def test_a_service_with_no_stages_builds_the_whole_dockerfile(tmp_path_factory):
    """One stage, no names: the service says nothing and the build gets no
    target, which is Docker's own way of saying "all of it"."""
    project = _deployed_project(tmp_path_factory)

    assert not _built_target(project, "--build_type", "runtime")


def test_a_service_with_no_development_stage_runs_its_runtime_one(tmp_path_factory):
    """A worker or a small sidecar runs the same image in a session as in a
    real environment. Deliberately not an independent fallback to the
    Dockerfile's last stage: in a multi-stage Dockerfile that *is* the
    runtime stage, so a session would silently get the production image."""
    project = _deployed_project(tmp_path_factory, f", runtime_stage='{RUNTIME_STAGE}'")

    assert _built_target(project, "--build_type", "development") == RUNTIME_STAGE


def test_a_service_with_no_tests_of_its_own_builds_what_a_session_would(
    tmp_path_factory,
):
    """It still has to serve -- for the outcome suite, and for whatever other
    services test against it -- so a test run cannot simply leave it out."""
    project = _deployed_project(
        tmp_path_factory,
        f", development_stage='{DEVELOPMENT_STAGE}', runtime_stage='{RUNTIME_STAGE}'",
    )

    assert _built_target(project, "--build_type", "test") == DEVELOPMENT_STAGE


def test_a_service_with_no_tests_registers_no_test_pipeline(tmp_path_factory):
    """Naming no test stage is how a service says it has no tests of its own,
    so nothing should be waiting on a run that will never report."""
    project = _deployed_project(
        tmp_path_factory, f", development_stage='{DEVELOPMENT_STAGE}'",
    )

    result = subprocess.run(
        ["tilt", "alpha", "tiltfile-result", "--", "--build_type", "test"],
        cwd=project,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-500:]
    names = [m["Name"] for m in json.loads(result.stdout)["Manifests"]]

    service = WITHOUT_RESET.replace("-", "_")
    assert [
        name
        for name in names
        if name.startswith("seal_tests_") and name.endswith(service)
    ] == []


def _evaluation_failure(project: Path, *tiltfile_args: str, gate: bool = False) -> str:
    result = subprocess.run(
        ["tilt", "alpha", "tiltfile-result", "--", *tiltfile_args],
        cwd=project,
        capture_output=True,
        text=True,
        env=_environment(gate),
    )
    assert result.returncode != 0, "expected the Tiltfile to be refused"
    return result.stderr


def test_a_build_type_seal_does_not_know_is_refused(deployed_project):
    """Naming the three is what makes the message actionable -- a rejection
    that only says the value is wrong leaves a reader guessing."""
    stderr = _evaluation_failure(deployed_project, "--build_type", "staging")

    assert "staging" in stderr
    for known in ("development", "test", "runtime"):
        assert known in stderr


def test_the_flag_this_one_replaces_is_refused_by_name(deployed_project):
    """Silently ignoring it would leave a run building something other than
    what it was told to, which is worse than refusing to start."""
    stderr = _evaluation_failure(deployed_project, "--docker_target", "test")

    assert "--build_type" in stderr


def test_a_stage_named_the_way_it_used_to_be_is_refused(tmp_path_factory):
    """A service naming its test stage through anything but `test_stage`
    leaves seal with no stage to build and a command to run in it, which is
    the one thing the trio's own rejection already covers -- so the message
    a project gets points at the argument it should be writing."""
    project = _deployed_project(
        tmp_path_factory,
        ", test_target='test', test_command='make unit-tests'"
        ", junit_tests_directory='/app/tests-results/'",
    )

    stderr = _evaluation_failure(project, "--build_type", "test")

    assert "test_stage" in stderr


# --- Publishing ------------------------------------------------------------
#
# Whether a run pushes what it builds to a real registry is its own input.
# Which registry is the project's to name, through Tilt's own
# default_registry(), so what these assert on is Tilt's record of that call
# having happened -- not a name seal would have had to learn.

REGISTRY = "ghcr.io/an-org"

PUBLISHING_ROOT = (
    "load('ext://seal', 'publish_images')\n"
    "if publish_images:\n"
    f"    default_registry('{REGISTRY}')\n"
)


@pytest.fixture(scope="module")
def publishing_project(tmp_path_factory) -> Path:
    return _deployed_project(tmp_path_factory, root_extra=PUBLISHING_ROOT)


def _default_registry(project: Path, *tiltfile_args: str):
    result = subprocess.run(
        ["tilt", "alpha", "tiltfile-result", *(["--", *tiltfile_args] if tiltfile_args else [])],
        cwd=project,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"tilt could not evaluate the Tiltfile: {result.stderr.strip()[-500:]}")
    return json.loads(result.stdout).get("DefaultRegistry")


@pytest.mark.parametrize("args", [(), ("--publish_images=false",)])
def test_a_run_does_not_publish_unless_it_says_so(publishing_project, args):
    """Off is the answer that costs nothing to be wrong about. A run that
    published by default would push whatever a throwaway cluster happened to
    build, and the push is the half that cannot be taken back."""
    assert _default_registry(publishing_project, *args) is None


@pytest.mark.parametrize("args", [("--publish_images",), ("--publish_images=true",)])
def test_a_run_that_asks_to_publish_gets_the_projects_registry(
    publishing_project, args,
):
    """Bare and explicit both mean the same thing, so a project can write
    whichever reads better in its own pipeline."""
    assert _default_registry(publishing_project, *args) == {"host": REGISTRY}


def test_naming_an_overlay_does_not_start_publishing(publishing_project):
    """The two are independent, and this is the direction that matters: a run
    against a production-shaped overlay wants that shape on a throwaway
    cluster without pushing what it built to a registry anyone else reads."""
    assert _default_registry(publishing_project, "--k8s_overlay", "stag") is None


# --- Which overlay a run deploys -------------------------------------------
#
# These are the only tests here that build a kustomization, which Tilt does by
# shelling out to `kubectl kustomize` -- hence a guard the rest of the file
# doesn't need.
#
# The overlays are directories the project made and named, so seal knows none
# of their names -- what a bare run means is what that project's own
# select_k8s_overlay() call says. These use overlay names seal could not have
# guessed, so a test passing because a name happened to match seal's idea of
# a default is not possible.

needs_kustomize = pytest.mark.skipif(
    shutil.which("kubectl") is None,
    reason="needs kubectl, which Tilt's kustomize() shells out to",
)

WORKING_OVERLAY = "as-we-work"
SHIPPING_OVERLAY = "as-it-ships"


def _overlay_project(tmp_path_factory, default_overlay: str = WORKING_OVERLAY) -> Path:
    """A project with two overlays, each holding one workload, and a root
    Tiltfile that selects between them the way a project's does."""
    project = tmp_path_factory.mktemp("overlays")
    _write(
        project / "Tiltfile",
        f"v1alpha1.extension_repo(name='seal', url='file://{TILT_EXTENSIONS}')\n"
        "v1alpha1.extension(name='seal', repo_name='seal', repo_path='seal')\n"
        "load('ext://seal', 'select_k8s_overlay')\n"
        f"select_k8s_overlay(k8s_dir='k8s', default_overlay='{default_overlay}')\n",
    )
    for overlay in (WORKING_OVERLAY, SHIPPING_OVERLAY):
        _write(
            project / "k8s" / overlay / "kustomization.yaml",
            "apiVersion: kustomize.config.k8s.io/v1beta1\n"
            "kind: Kustomization\n"
            "resources:\n- workload.yaml\n",
        )
        _write(
            project / "k8s" / overlay / "workload.yaml",
            "apiVersion: apps/v1\n"
            "kind: Deployment\n"
            f"metadata:\n  name: {overlay}\n"
            "spec:\n"
            f"  selector:\n    matchLabels:\n      app: {overlay}\n"
            "  template:\n"
            f"    metadata:\n      labels:\n        app: {overlay}\n"
            "    spec:\n"
            f"      containers:\n      - name: c\n        image: nginx\n",
        )
    return project


def _deployed_workloads(project: Path, *tiltfile_args: str) -> list[str]:
    result = subprocess.run(
        ["tilt", "alpha", "tiltfile-result", *(["--", *tiltfile_args] if tiltfile_args else [])],
        cwd=project,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"tilt could not evaluate the Tiltfile: {result.stderr.strip()[-500:]}")
    return sorted(m["Name"] for m in json.loads(result.stdout)["Manifests"])


@needs_kustomize
def test_a_run_deploys_the_overlay_it_names(tmp_path_factory):
    assert _deployed_workloads(
        _overlay_project(tmp_path_factory), "--k8s_overlay", SHIPPING_OVERLAY,
    ) == [SHIPPING_OVERLAY]


@needs_kustomize
def test_a_run_that_names_none_deploys_the_projects_own_default(tmp_path_factory):
    assert _deployed_workloads(_overlay_project(tmp_path_factory)) == [WORKING_OVERLAY]


@needs_kustomize
def test_the_default_is_the_projects_rather_than_one_seal_picked(tmp_path_factory):
    """The same project, told a different default, deploys that one. seal
    knows no overlay names: they are directories a project made, and which of
    them a bare run means is the project's to say."""
    project = _overlay_project(tmp_path_factory, default_overlay=SHIPPING_OVERLAY)

    assert _deployed_workloads(project) == [SHIPPING_OVERLAY]


@needs_kustomize
def test_an_overlay_that_is_not_there_is_refused_by_name(tmp_path_factory):
    """Left alone this reaches kustomize as a path that does not resolve, and
    what comes back is an error about a directory rather than about the flag
    somebody typed."""
    stderr = _evaluation_failure(
        _overlay_project(tmp_path_factory), "--k8s_overlay", "as-it-shps",
    )

    assert "as-it-shps" in stderr


@needs_kustomize
def test_the_refusal_lists_the_overlays_that_do_exist(tmp_path_factory):
    """Knowing the name is wrong is half an answer; the other half is what
    could have been written instead, which seal can see and the reader
    cannot."""
    stderr = _evaluation_failure(
        _overlay_project(tmp_path_factory), "--k8s_overlay", "as-it-shps",
    )

    assert WORKING_OVERLAY in stderr
    assert SHIPPING_OVERLAY in stderr


@needs_kustomize
def test_a_project_with_no_overlays_at_all_is_told_so(tmp_path_factory):
    """Listing what is available says nothing useful when there is nothing,
    and a bare "available: " reads as a bug in the message rather than an
    answer about the project."""
    project = tmp_path_factory.mktemp("no_overlays")
    _write(
        project / "Tiltfile",
        f"v1alpha1.extension_repo(name='seal', url='file://{TILT_EXTENSIONS}')\n"
        "v1alpha1.extension(name='seal', repo_name='seal', repo_path='seal')\n"
        "load('ext://seal', 'select_k8s_overlay')\n"
        "select_k8s_overlay(k8s_dir='k8s', default_overlay='dev')\n",
    )

    stderr = _evaluation_failure(project)

    assert "no overlays at all" in stderr
