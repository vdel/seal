"""The contract `actions/ci/action.yml` holds, read off the file itself.

Two of its properties are load-bearing and neither has anywhere else to fail.

A flag the workflow passes has to be one the Tilt extension defines: rename
one on the Starlark side and CI keeps passing the old spelling, which Tilt
rejects at parse time -- in a pipeline, on somebody else's pull request,
with nothing in this repository having noticed.

And every run has to be one `seal ci` a person can type. That is what makes a
red gate reproducible, which is the whole reason a second overlay is an
additional gate rather than a replacement for the one the local loop runs
(see /rfcs/0008-run-axes.md). It stops being true the moment a step reaches
for something the CLI cannot do, and nothing but a test says so.
"""

import re
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml

from seal.seal import MAX_PUBLISHED_RECORDINGS

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION = REPO_ROOT / "actions" / "ci" / "action.yml"
CALLER = REPO_ROOT / ".github" / "workflows" / "internal-example.yml"
CONFIG_TILTFILE = REPO_ROOT / "tilt" / "seal" / "config.Tiltfile"

# What `seal ci` is invoked as, wherever it appears. Split on the `--` Tilt
# uses to separate its own arguments from a Tiltfile's config flags.
SEAL_CI = "seal ci --"

# The step that runs the shape a merge rests on, named so the tests below
# reach it by something stabler than a prefix of its prose.
PRIMARY_RUN = "Verify the promises, and each service's own tests"


def _caller_with() -> dict:
    """What the worked caller passes the action -- on the step that uses it,
    not on the job."""
    steps = yaml.safe_load(CALLER.read_text(encoding="utf-8"))["jobs"]["tests"]["steps"]
    step = next(s for s in steps if str(s.get("uses", "")).endswith("actions/ci"))
    return step.get("with", {})


def _workflow() -> dict:
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def _action_inputs() -> dict:
    # `on` is read back as the boolean True: YAML 1.1 spells `true` several
    # ways and this is one of them, which every GitHub workflow trips over.
    workflow = _workflow()
    return _workflow()["inputs"]


def _steps() -> list[dict]:
    return _workflow()["runs"]["steps"]


def _run_scripts() -> list[str]:
    return [step["run"] for step in _steps() if "run" in step]


def _invocations_in(script: str) -> list[list[str]]:
    """Every `seal ci` one script runs, as the config flags it passes.

    Line continuations are folded first: an invocation is written across
    several lines to stay readable, and the flags on the later ones are as
    much part of it as the ones on the first. Matched through the `uvx` that
    runs it, so a line merely naming the command -- a log group's label, a
    comment quoting what is about to run -- is not read as one."""
    invocations = []
    for line in script.replace("\\\n", " ").splitlines():
        if not re.search(r"\buvx\b.*" + re.escape(SEAL_CI), line):
            continue
        invocations.append(shlex.split(line.split(SEAL_CI, 1)[1]))
    return invocations


def _seal_ci_invocations() -> list[list[str]]:
    return [i for script in _run_scripts() for i in _invocations_in(script)]


def _results_upload() -> dict:
    """The step that uploads the results artifact -- reached by its id, since
    the recording uploads below are the same action."""
    return next(step for step in _steps() if step.get("id") == "upload")


def _recording_uploads() -> list[dict]:
    """Every step that publishes one recording on its own."""
    return [
        step
        for step in _steps()
        if str(step.get("id", "")).startswith("recording")
        and step.get("uses", "").startswith("actions/upload-artifact")
    ]


def _gate_step() -> dict:
    """The run on `k8s_overlay` -- the one a project's own local loop
    reproduces, and the only one that can execute a service's own tests."""
    return next(step for step in _steps() if step["name"] == PRIMARY_RUN)


def _defined_flags() -> set[str]:
    """The Tiltfile config flags the extension declares, read from the
    Starlark rather than restated here -- a list written out in this file
    would agree with itself while disagreeing with Tilt."""
    return set(
        re.findall(
            r"config\.define_(?:string|bool|string_list)\('([^']+)'\)",
            CONFIG_TILTFILE.read_text(encoding="utf-8"),
        )
    )


def _flags_passed(invocation: list[str]) -> set[str]:
    return {
        token.split("=", 1)[0].removeprefix("--")
        for token in invocation
        if token.startswith("--")
    }


# --- the inputs a project fills in -----------------------------------------


@pytest.fixture(scope="module")
def inputs() -> dict:
    return _action_inputs()


def test_a_project_says_which_overlay_the_gate_deploys(inputs):
    """Required, and with no default: an overlay is a directory a project
    named, so there is no value this file could supply. A gate that picked
    one would be picking which shape a merge rests on."""
    assert inputs["k8s_overlay"]["required"] is True
    assert "default" not in inputs["k8s_overlay"]


def test_further_shapes_are_optional_and_a_project_has_none_by_default(inputs):
    """How much a second shape adds depends entirely on what that overlay
    changes, so whether to have one is the project's call and not this
    file's."""
    assert inputs["additional_k8s_overlays"]["required"] is False
    assert yaml.safe_load(inputs["additional_k8s_overlays"]["default"]) == []


def test_a_project_chooses_whether_the_service_tests_run(inputs):
    """Running them is the default, and the run on `k8s_overlay` is the only
    one that can: a suite runs inside the service's container, so it is there
    only in images built at --build_type test."""
    assert inputs["run_service_tests"]["required"] is False
    assert inputs["run_service_tests"]["default"] == "true"
    # No `type:`: an action's inputs are strings, and this one is compared
    # against the two words it takes rather than read for truthiness.
    assert "type" not in inputs["run_service_tests"]


def test_a_project_chooses_whether_the_promises_are_read(inputs):
    """Reading them is the default, because that is what makes a run the
    merge gate. A project turning them off gets each service's own tests and
    the readiness gate -- a faster check to have beside the gate, never one
    to have instead of it."""
    assert inputs["run_outcomes"]["required"] is False
    assert inputs["run_outcomes"]["default"] == "true"
    # No `type:`: an action's inputs are strings, and this one is compared
    # against the two words it takes rather than read for truthiness.
    assert "type" not in inputs["run_outcomes"]


@pytest.mark.parametrize("switch", ["run_service_tests", "run_outcomes"])
def test_a_value_the_action_does_not_know_is_refused(switch):
    """Checked against both words rather than against "true" alone. Anything
    a run does not recognise would otherwise read as "not true" and switch
    that half off -- and the direction that verifies less must never be the
    one a typo takes."""
    plan = next(step for step in _steps() if step.get("id") == "plan")

    # The membership check itself, not the message it prints: an allow-list
    # of the two words is the property, and a message can be reworded.
    assert 'value not in ("true", "false")' in plan["run"]
    assert 'switch("{}")'.format(switch) in plan["run"]


def test_a_run_can_read_neither_half_and_gate_on_readiness_alone():
    """Both halves off is allowed on purpose -- the emergency where the
    question is only whether the thing comes up. The run is not refused, it
    says out loud what it is, and the results a caller is handed do not claim
    it produced nothing: an absence of reports by design is not the same
    thing as a run that lost them, and only this file knows which it is."""
    plan = next(step for step in _steps() if step.get("id") == "plan")
    assert "both false" not in plan["run"]

    gate = _gate_step()
    assert "::warning::" in gate["run"]
    assert "gates on readiness alone" in gate["run"]

    collect = next(step for step in _steps() if step.get("id") == "collect")
    # Named to `seal _tests-results` only when something was asked of it: a
    # results directory that is not there is rendered as a failure, which is
    # the right reading for a run that died and the wrong one for this.
    assert '[ "$RUN_SERVICE_TESTS" = "true" ] || [ "$RUN_OUTCOMES" = "true" ]' in collect["run"]
    assert "results={}" in collect["run"]


def test_further_shapes_with_the_promises_off_is_refused():
    """An additional shape is verified at --build_type runtime, whose images
    carry no test suite -- so the promises are the only thing such a run
    reads, and with them off it would spend a whole cluster asserting
    nothing. Refused rather than quietly dropped: which of the two inputs the
    caller meant is not this file's to guess."""
    plan = next(step for step in _steps() if step.get("id") == "plan")

    assert "additional_k8s_overlays names" in plan["run"]
    assert "run_outcomes is false" in plan["run"]


def test_publishing_is_asked_for_rather_than_inferred(inputs):
    """A boolean of its own, and required: inferring it from an overlay name
    is what makes deploying a production-shaped overlay on a throwaway
    cluster start pushing images."""
    assert inputs["publish_images"]["required"] is True
    # No `type:`: an action's inputs are strings, so the flag is required
    # rather than defaulted -- there is no false to fall back to that a
    # reader could mistake for "off".
    assert "type" not in inputs["publish_images"]


def test_a_publishing_run_still_names_a_shape(inputs):
    """Publishing means deploying something and letting Tilt push what it
    built, so it names an overlay like every other run. Optional in the
    schema because a project that never publishes has nothing to say here;
    the run itself refuses to guess."""
    assert "publish_k8s_overlay" in inputs

    publish_step = next(
        step for step in _steps() if step["name"] == "Publish the images"
    )

    assert "publish_k8s_overlay names no overlay" in publish_step["run"]


# --- what the runs actually do ---------------------------------------------


def test_every_run_is_one_command_somebody_can_type():
    """The local-reproducibility requirement. A step reaching for `tilt`
    directly, or for a flag `seal ci` does not forward, would give this
    pipeline a capability the local loop does not have -- and a red gate
    nobody can reproduce is one nobody can act on."""
    assert _seal_ci_invocations(), "no seal ci invocation found at all"

    # Comments stripped first: they are where the file explains what `seal
    # ci` does with `tilt ci`, and prose about a command is not a call to it.
    commands = "\n".join(
        line
        for script in _run_scripts()
        for line in script.splitlines()
        if not line.lstrip().startswith("#")
    )

    # `tilt` only ever through the CLI: the bare binary would be a run this
    # file knows how to do and a developer does not.
    assert not re.search(r"(?<![-\w/])tilt ", commands)


def test_every_flag_the_workflow_passes_is_one_the_extension_defines():
    """The agreement that has nowhere else to fail. Tilt rejects an
    unrecognised config flag at parse time, so a rename on the Starlark side
    turns every project's pipeline red at once, without a single test in this
    repository going red first."""
    defined = _defined_flags()

    for invocation in _seal_ci_invocations():
        assert _flags_passed(invocation) <= defined, (
            "seal ci -- {} passes a flag config.Tiltfile does not define".format(
                " ".join(invocation)
            )
        )


def test_the_gate_runs_a_shape_and_says_which():
    """Every run names its overlay. Left unsaid it would deploy whichever one
    the project's own select_k8s_overlay() defaults to, which makes the shape
    a merge rests on a property of the project's Tiltfile rather than of the
    pipeline that gated it."""
    for invocation in _seal_ci_invocations():
        assert "k8s_overlay" in _flags_passed(invocation)


def test_only_the_primary_run_can_build_test_images():
    """The run on `k8s_overlay` is the only one that executes a service's own
    tests, because it is the only one that can build images carrying a suite.
    Every other run verifies what a real environment runs -- a property of
    those images, not a policy -- so `runtime` is written into them, while
    the primary one picks from `run_service_tests`."""
    gate = _gate_step()
    assert len(_invocations_in(gate["run"])) == 1

    # Chosen in the shell rather than written into the command: which kind of
    # image this run builds *is* the whole of whether a service's tests run,
    # so a literal here would be the choice made in the wrong place.
    assert '--build_type "$build_type"' in gate["run"]
    assert "build_type=test" in gate["run"]
    assert "build_type=runtime" in gate["run"]

    others = [
        invocation
        for step in _steps()
        if step["name"] != PRIMARY_RUN
        for invocation in _invocations_in(step.get("run", ""))
    ]
    assert others, "the primary run is the only one there is"
    for invocation in others:
        assert invocation[invocation.index("--build_type") + 1] == "runtime"


def test_only_the_publishing_run_publishes_and_it_reads_no_promises():
    """`--publish_images` on a gate run would push before a single promise
    had been read, because Tilt pushes when it deploys rather than when a run
    succeeds. And the publishing run is not a gate: the promises were read
    against these same images by the runs it waited for."""
    invocations = _seal_ci_invocations()
    publishing = [i for i in invocations if "publish_images" in _flags_passed(i)]
    gates = [i for i in invocations if "publish_images" not in _flags_passed(i)]

    assert len(publishing) == 1
    assert "--run_outcomes" in publishing[0]
    assert publishing[0][publishing[0].index("--run_outcomes") + 1] == "false"

    assert gates, "every run publishes, so none of them is a gate"
    for gate in gates:
        # Never a literal value on a gate: reading the promises is what being
        # a gate means, so the only thing a gate has to say about them is
        # that this run does not read them -- and that comes from the
        # `run_outcomes` input, through the shell below, rather than from a
        # word written into the command.
        assert "run_outcomes" not in _flags_passed(gate)


def test_the_gate_says_run_outcomes_only_to_turn_them_off():
    """The run on `k8s_overlay` is the one a project can ask to skip the
    promises, and it asks through the input rather than through a second
    invocation somebody could get out of step with this one."""
    gate = _gate_step()

    assert gate["env"]["RUN_SERVICE_TESTS"] == "${{ inputs.run_service_tests }}"
    assert gate["env"]["RUN_OUTCOMES"] == "${{ inputs.run_outcomes }}"
    assert "--run_outcomes false" in gate["run"]
    # Compared against the word, not read for truthiness -- and against the
    # one that turns them off, so the value the plan step let through decides
    # this rather than the shell's idea of false.
    assert '"$RUN_OUTCOMES" = "false"' in gate["run"]


def test_publishing_waits_for_every_gate_to_have_passed():
    """`success()` rather than the input alone. A step that only checked
    whether publishing was asked for would publish alongside a red gate,
    which is the ordering this whole arrangement exists to get right."""
    publish_step = next(
        step for step in _steps() if step["name"] == "Publish the images"
    )

    assert "success()" in publish_step["if"]
    assert "inputs.publish_images" in publish_step["if"]


def test_a_boolean_input_is_compared_and_never_read_for_truthiness():
    """Every input an action receives is a string, so `if: inputs.x` is true
    for the literal "false". A step gated that way runs for a caller that
    asked for the opposite -- here, publishing runs for a caller that wanted
    none, and then fails on its own missing-overlay guard, which reads as the
    gate being broken rather than as the condition being wrong.

    Held on the condition's shape rather than on one step: the trap is the
    same for any input a future step gates on."""
    for step in _steps():
        condition = str(step.get("if", ""))
        for reference in re.findall(r"inputs\.[A-Za-z_][A-Za-z0-9_]*", condition):
            rest = condition[condition.index(reference) + len(reference):].lstrip()
            assert rest.startswith(("==", "!=")), (
                f"{step.get('name')!r} reads {reference} for truthiness in "
                f"{condition!r}; compare it to a string instead -- \"false\" is "
                f"truthy."
            )


def test_each_run_starts_from_a_cluster_with_nothing_on_it():
    """An object the next overlay does not declare keeps running otherwise,
    so a promise can be kept by a container the shape under test removed.
    That failure is silent and green, which is worse than no second shape at
    all."""
    seal_ci_steps = [
        step for step in _steps() if "run" in step and SEAL_CI in step["run"]
    ]

    assert seal_ci_steps
    for step in seal_ci_steps:
        assert "fresh-cluster.sh" in step["run"], step["name"]


# --- what a reader gets back -----------------------------------------------


def test_every_shape_the_run_verified_is_in_what_the_caller_gets_back():
    """Two result sets in one pull request are two different claims, and
    somebody deciding whether to merge has to see which of them went red. So
    the results are keyed by overlay -- the primary one and every additional
    one -- rather than added up into a single verdict the caller cannot take
    apart."""
    collect = next(
        step for step in _steps() if step.get("id") == "collect"
    )

    # One --run per shape: the primary one by name, the additional ones read
    # from the file the plan step wrote.
    assert '--run "$PRIMARY_K8S_OVERLAY=' in collect["run"]
    assert '--run "$overlay=' in collect["run"]
    assert "additional-overlays" in collect["run"]

    # And it happens whatever the gates said. A failed run's results are the
    # ones somebody needs.
    assert "!cancelled()" in collect["if"]


def test_the_caller_is_handed_the_results_rather_than_a_report_of_them():
    """How a project's results are presented is the project's own policy. A
    reporting action pinned in here is one every adopting project inherits --
    along with the write scopes it needs on their pull requests and the kind
    of runner it happens to require -- so this file hands back what the runs
    found and stops there."""
    outputs = _workflow()["outputs"]
    assert {"overlays", "results", "results_artifact"} <= set(outputs)

    # An action declares no `permissions:` -- it runs under whatever the
    # calling job has, so a scope cannot be asserted here. What can is that
    # nothing reports: no step posts a check, a comment or a status.
    for step in _steps():
        run = str(step.get("run", ""))
        uses = str(step.get("uses", ""))
        assert not run.lstrip().startswith("gh "), "no step reports through gh"
        assert " gh api" not in run and "\ngh " not in run
        assert "github-script" not in uses, "no step reports through github-script"


def test_the_results_are_read_by_the_cli_that_decided_the_run_s_own_verdict():
    """A rendering that parsed the reports here would be a second answer to
    the question `seal ci` already answered, free to disagree with it -- and
    the disagreement would surface as a green gate whose results say a test
    failed, or the reverse."""
    collect = next(step for step in _steps() if step.get("id") == "collect")

    assert "seal _tests-results" in collect["run"]


def test_the_artifact_carries_a_report_a_person_can_read():
    """A download of raw XML answers "did it pass?" only to whoever will
    parse it. The page renders what the reading already says, so the results
    a project is handed are readable as well as parseable -- and it publishes
    nothing and needs no scope, which is what keeps it on this side of the
    boundary while a check or a comment stays the project's decision.

    Rendered by the CLI, for the same reason the reading is: a page that
    parsed the reports itself could say a promise held where the gate said it
    broke.
    """
    render = next(
        step for step in _steps() if step["name"] == "Render what each run found"
    )

    assert "seal _report" in render["run"]
    assert "uvx --from" in render["run"]
    # Into the directory the artifact is uploaded from, so it travels with
    # the reports it describes rather than as a second thing to find.
    assert "$RUNNER_TEMP/seal-results/index.html" in render["run"]
    # And whatever the gates said: a failed run's report is the one somebody
    # needs to read.
    assert "!cancelled()" in render["if"]

    upload = next(
        step for step in _steps() if step.get("uses", "").startswith("actions/upload-artifact")
    )
    assert _steps().index(render) < _steps().index(upload), (
        "a page rendered after the upload is a page nobody receives"
    )


def test_a_run_that_did_not_read_the_promises_says_so_rather_than_reporting_none_kept():
    """With `run_outcomes` off, every promise has no verdict -- which from the
    results alone is exactly what a suite whose tests all failed to write one
    looks like, and that is a failure. Only this file knows which of the two
    it is, so it tells the reading."""
    collect = next(step for step in _steps() if step.get("id") == "collect")

    assert "--no-outcomes" in collect["run"]
    assert 'if [ "$RUN_OUTCOMES" != "true" ]; then' in collect["run"]
    # And not into the array the emptiness check counts: a switch is not a
    # run, and one counted as such sends a command naming no results
    # directory at all.
    switch = collect["run"].index("--no-outcomes")
    assert collect["run"].index("${#runs[@]} -eq 0") < switch


def test_the_reading_travels_with_the_reports_as_well_as_out_as_an_output():
    """An output is readable by this workflow run alone. Somebody opening a
    failed run's artifact weeks later gets the reports; without the reading
    beside them, the one thing it says that no report can -- that a shape's
    run produced nothing at all -- is the thing they cannot get."""
    collect = next(step for step in _steps() if step.get("id") == "collect")

    assert "$GITHUB_OUTPUT" in collect["run"]
    assert "$RUNNER_TEMP/seal-results/results.json" in collect["run"]


def test_a_recording_is_published_under_an_address_of_its_own():
    """The point of the whole arrangement: a file inside an artifact has no
    address, so a link to one is a download to go looking through. Uploaded
    unarchived, a recording gets a URL that reaches the recording."""
    uploads = _recording_uploads()

    assert uploads, "nothing publishes a recording on its own"
    for step in uploads:
        assert step["with"]["archive"] is False, (
            "zipped, the URL reaches an archive rather than the video in it"
        )
        # A re-run publishes the same names again, and an artifact name has
        # to be unique within a run.
        assert step["with"]["overwrite"] is True


def test_as_many_addresses_as_the_cli_says_it_will_name():
    """A composite action cannot loop a `uses:` step, and how many promises
    broke is not known until the run has finished -- so the uploads are
    unrolled and their number is fixed. Fixed in two files, which is exactly
    the kind of agreement that goes quietly wrong: one more upload step than
    the CLI names is a step that never runs, and one fewer is a recording
    published nowhere with nothing saying so."""
    assert len(_recording_uploads()) == MAX_PUBLISHED_RECORDINGS


def test_every_published_recording_is_reachable_from_the_promise_that_broke():
    """The uploads each know their own URL and nothing else. Something has to
    turn them into one thing a report can look a promise up in -- keyed by
    run and slug, since two shapes can break the same promise."""
    collect = next(step for step in _steps() if step.get("id") == "recordings")

    for index in range(1, MAX_PUBLISHED_RECORDINGS + 1):
        assert "steps.stage.outputs.key{}".format(index) in collect["env"]["SEAL_RECORDINGS"]
        assert (
            "steps.recording{}.outputs.artifact-url".format(index)
            in collect["env"]["SEAL_RECORDINGS"]
        )

    outputs = _workflow()["outputs"]
    assert outputs["recordings"]["value"] == "${{ steps.recordings.outputs.published }}"


def test_publishing_recordings_can_be_turned_off():
    """It costs an upload per broken promise and sends the recording's bytes
    twice, since it stays in the results artifact where the page that plays
    it lives. A project that would rather not pay that keeps the page."""
    inputs = _action_inputs()

    assert inputs["publish_recordings"]["required"] is False
    assert inputs["publish_recordings"]["default"] == "true"
    stage = next(step for step in _steps() if step.get("id") == "stage")
    assert "inputs.publish_recordings == 'true'" in stage["if"]


def test_which_files_are_recordings_is_the_clis_to_say():
    """A `find` by extension in the workflow would be a second answer to a
    classification that lives beside the verdict it belongs to. The staging
    step copies what the CLI listed, and nothing else."""
    stage = next(step for step in _steps() if step.get("id") == "stage")
    render = next(step for step in _steps() if step["name"] == "Render what each run found")

    assert "--recordings-list" in render["run"]
    assert "seal-recordings.json" in stage["run"]
    assert ".webm" not in stage["run"] and "find " not in stage["run"]


def test_where_the_recordings_can_be_fetched_is_handed_back_too():
    """A file inside a CI artifact has no address of its own -- the artifact
    is one archive, fetched whole -- so this is as close as a report
    published outside the run can get to the recording of a failure. Read off
    the upload step rather than built from a run id, because only the upload
    knows which artifact it created."""
    outputs = _workflow()["outputs"]
    upload = _results_upload()

    assert upload["uses"].startswith("actions/upload-artifact")
    assert outputs["results_artifact_url"]["value"] == "${{ steps.upload.outputs.artifact-url }}"


def test_the_reports_themselves_survive_the_run_that_produced_them():
    """The `results` output carries what the reports say, not the reports:
    it is a string with a size limit, and the coverage sitting beside them
    isn't JUnit at all. A caller wanting either downloads the artifact, so
    the workflow has to name it back."""
    upload = _results_upload()
    inputs = _action_inputs()

    assert upload["with"]["name"] == "${{ inputs.results_artifact }}"
    assert "results_artifact" in inputs
    # Kept only long enough for the caller's own reporting to read it, in the
    # same run. What somebody comes back to later is what that reporting
    # published.
    assert upload["with"]["retention-days"] == "${{ inputs.results_retention_days }}"
    assert inputs["results_retention_days"]["default"] > 0


def test_the_worked_example_does_something_with_everything_it_is_handed():
    """The one assertion above that says the outputs are usable rather than
    merely declared. Without a caller reading them, `results` is a string
    nothing has ever parsed -- and the failure that would find out is an
    adopting project's, on their pull request.

    All three, because they answer different questions: which shapes ran,
    what each of their runs found, and where the reports themselves are. A
    caller reaching for one of them proves nothing about the other two.
    """
    jobs = yaml.safe_load(CALLER.read_text(encoding="utf-8"))["jobs"]
    consumers = {name: job for name, job in jobs.items() if job.get("needs") == "tests"}
    body = str(consumers)

    assert consumers, "nothing in the example reads what the workflow hands back"
    for output in ("overlays", "results", "results_artifact", "results_artifact_url"):
        assert "needs.tests.outputs.{}".format(output) in body, output

    # And each of them reports on a run that went red, which is the run whose
    # results somebody actually needs.
    for name, job in consumers.items():
        assert "!cancelled()" in job["if"], name


def test_the_worked_example_publishes_from_the_reports_and_not_from_the_reading():
    """`results` says what the reports say; it is not the reports. An action
    publishing a check wants the XML, so the example downloads the artifact
    for it -- and takes the `checks: write` that needs on its own job, which
    is the whole point of the action not asking a caller for it."""
    report = yaml.safe_load(CALLER.read_text(encoding="utf-8"))["jobs"]["report"]
    download = next(
        step for step in report["steps"]
        if step.get("uses", "").startswith("actions/download-artifact")
    )

    assert report["permissions"]["checks"] == "write"
    assert download["with"]["name"] == "${{ needs.tests.outputs.results_artifact }}"
    # A run that produced no results uploaded no artifact, which is not a
    # reason to fail this job on top of the one that already failed.
    assert download["continue-on-error"] is True

    # One check per shape, named for it.
    assert "needs.tests.outputs.overlays" in report["strategy"]["matrix"]["overlay"]
    publish = next(step for step in report["steps"] if step["name"] == "Publish Test Results")
    assert "${{ matrix.overlay }}" in publish["with"]["check_name"]
    assert "${{ matrix.overlay }}" in publish["with"]["files"]


def test_this_repo_s_own_caller_fills_in_what_the_workflow_now_requires():
    """The worked example is the only caller here, so it is where a required
    input nobody passes shows up -- as a workflow that fails to start, with
    zero jobs scheduled and no test having run."""
    passed = _caller_with()
    required = {
        name
        for name, spec in _action_inputs().items()
        if spec.get("required")
    }

    assert required <= set(passed)


# --- and that this repository actually exercises it -------------------------


def test_the_worked_example_verifies_more_than_one_shape():
    """Every assertion above is about what the workflow *can* do. This is the
    one that says it is being done: the example grows a second overlay and the
    caller names it, so `additional_k8s_overlays` is covered by a run rather
    than by its own default.

    Without this, deleting the overlay or dropping the input would return the
    repository to proving nothing about a capability it ships, with every
    other test still green."""
    example = REPO_ROOT / "examples" / "angular-django"
    overlays = {
        path.name
        for path in (example / "k8s").iterdir()
        if path.is_dir() and (path / "kustomization.yaml").is_file()
    }
    passed = _caller_with()
    additional = yaml.safe_load(passed.get("additional_k8s_overlays") or "[]")

    assert len(overlays) > 1, "the example deploys one shape, so it proves nothing"
    assert additional, "the example has a second shape and the gate never runs it"
    assert set(additional) <= overlays - {passed["k8s_overlay"]}


def test_no_stale_spelling_of_a_service_s_test_target_survives():
    """A rename across a repository fails by missing one quotation of it, and
    what is left behind is a document telling a reader to run a target that
    no longer exists. Every tracked file is read, not a chosen set of
    suffixes: the last one missed here was a Dockerfile comment, which a
    filter written from the obvious file types would have skipped."""
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")

    # Assembled rather than written out, so this file is not itself a hit --
    # which lets the search cover every tracked file with no exemption for
    # the one doing the searching. Spelling it whole here would make the
    # guard fail on itself, and the obvious fix for that (skipping this
    # file) is a hole.
    retired = "test-" + "ci"

    stale = []
    for name in filter(None, tracked):
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # not text, so not somewhere a command is written down
        if retired in body:
            stale.append(name)

    assert stale == [], "these still name a target that does not exist: {}".format(stale)


# Blocks GitHub Actions rejects when they are present but hold nothing.
# Commenting out the last entry of one leaves the key behind with an empty
# mapping under it, which is what makes this worth a test rather than care.
CONFIGURATION_BLOCKS = (
    "env",
    "with",
    "secrets",
    "permissions",
    "outputs",
    "inputs",
    "defaults",
)


def _empty_blocks(node, where: str) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in CONFIGURATION_BLOCKS and (value is None or value == {}):
                found.append(f"{where}.{key}")
            found.extend(_empty_blocks(value, f"{where}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_empty_blocks(value, f"{where}[{index}]"))
    return found


@pytest.mark.parametrize(
    "path",
    sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")),
    ids=lambda p: p.name,
)
def test_no_workflow_leaves_a_configuration_block_empty(path):
    """An `env:` holding only comments is valid YAML and an invalid workflow.

    GitHub rejects the file before scheduling anything, so the run fails
    with no jobs and therefore no check runs -- and a pull request whose
    other workflows passed looks green while its whole test suite never
    ran. That is the one failure shape nothing else here would catch.
    """
    empty = _empty_blocks(yaml.safe_load(path.read_text(encoding="utf-8")), path.name)

    assert not empty, (
        f"{path.name} has nothing under {', '.join(empty)}. Delete the key: "
        "GitHub rejects the workflow before scheduling a job, and a run that "
        "schedules nothing reports no failing check."
    )


def test_installing_a_provider_is_the_callers_business():
    """The workflow ships to projects keeping their secrets anywhere. What
    puts a CLI on PATH and logs it in is the one thing only the caller
    knows, so it is passed in rather than built in."""
    inputs = _action_inputs()

    assert "provider_setup" in inputs
    assert not inputs["provider_setup"].get("required", False)
    # Correct empty: a project whose `.env` files hold only literals and
    # `k8s://` markers reaches no provider and should not have to say so.
    assert inputs["provider_setup"].get("default", "") == ""

    assert "provider_token" in inputs
    assert not inputs["provider_token"].get("required", False)


def test_a_private_vendored_checkout_can_authenticate():
    """A project vendoring something of its own as a private submodule needs
    a token: GITHUB_TOKEN can read only the repository whose workflow is
    running, so that clone fails before any later step runs.

    Nothing about Seal needs it -- the CLI is this action's own repository --
    which is why it is optional and falls back to GITHUB_TOKEN."""
    inputs = _action_inputs()
    assert "submodules_token" in inputs
    assert not inputs["submodules_token"].get("required", False)

    checkout = [step for step in _steps() if step.get("uses", "").startswith("actions/checkout@")]
    assert len(checkout) == 1, "one checkout, so there is one place a token has to reach"
    with_ = checkout[0]["with"]
    # Without this the token would authenticate the caller's own clone and
    # leave the submodule -- the only thing that actually needs it -- to
    # fail exactly as before.
    assert with_["submodules"] is True
    assert with_["token"] == "${{ inputs.submodules_token || github.token }}"


def test_the_setup_step_runs_what_the_caller_passed_before_seal_ci():
    """No caller in this repository passes `provider_setup`, and none
    honestly can: the worked example keeps literals precisely so its CI
    does not depend on a store being reachable. So the step's behaviour is
    guaranteed structurally rather than by having been run -- which is worth
    saying plainly, because "it has never executed" is the thing a green
    pipeline would otherwise imply the opposite of.

    What is checked is the whole of the contract the input promises: the
    shell is what runs, the token reaches it, it is skipped when nothing was
    passed, and it happens before anything resolves a credential.
    """
    steps = _steps()
    setup = [step for step in steps if "provider_setup" in str(step.get("run", ""))]

    assert len(setup) == 1, "exactly one step runs the caller's setup"
    step = setup[0]

    # The shell the caller passed is the whole of what runs -- not wrapped,
    # not appended to, so what a project debugs locally is what ran here.
    assert step["run"].strip() == "${{ inputs.provider_setup }}"

    # Skipped when nothing was passed. Without this a project reaching no
    # provider runs an empty shell step, which is noise at best and a
    # failing step on some runners.
    assert "inputs.provider_setup" in step.get("if", "")

    # The token reaches it under seal's own name, so the caller's secret can
    # be called whatever that store calls it. The calling job binds the
    # Environment and reads it there, so the value that arrives is already
    # the right environment's.
    assert step["env"]["SEAL_PROVIDER_TOKEN"] == "${{ inputs.provider_token }}"

    # Before every `seal ci`: a CLI installed after the first resolution is
    # a CLI installed too late.
    first_seal_ci = next(
        index
        for index, other in enumerate(steps)
        if SEAL_CI in str(other.get("run", ""))
    )
    assert steps.index(step) < first_seal_ci

def test_the_cli_comes_from_this_actions_own_checkout():
    """`uses:` on an action checks its whole repository out, so `python/` is
    there at the same revision as this file. Naming it as an input instead
    would reintroduce two things at once: a credential to fetch it with, and
    a revision that can differ from the YAML running it -- and the Starlark
    half and the Python half are one library, so running two revisions is
    running two libraries."""
    assert not any("python" in name for name in _action_inputs()), (
        "no input may say where the CLI comes from"
    )
    invocations = [
        step["run"] for step in _steps()
        if "uvx --from" in str(step.get("run", ""))
    ]
    assert invocations, "the CLI is invoked through uvx"
    for run in invocations:
        assert "${{ github.action_path }}/../../python" in run


def test_nothing_reaches_for_a_secret_the_caller_did_not_pass():
    """An action cannot read `secrets`/`vars`, and a reference to either
    resolves to empty at runtime rather than failing. Every credential is an
    input, so the calling job -- which binds the Environment -- is what
    decides which environment's values arrive."""
    text = ACTION.read_text(encoding="utf-8")
    assert "${{ secrets." not in text
    assert "${{ vars." not in text
    setup = [step for step in _steps() if "provider_setup" in str(step.get("run", ""))]
    assert setup[0]["env"]["SEAL_PROVIDER_TOKEN"] == "${{ inputs.provider_token }}"
