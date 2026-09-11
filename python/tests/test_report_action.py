"""The contract `actions/report/action.yml` holds, read off the file itself.

`ci` establishes what held and hands it back; this action is how a project
that wants a comment and a summary asks for one (see
/rfcs/0015-reporting-what-a-run-found.md). Two of its properties are
load-bearing and neither has anywhere else to fail.

It must never be something a project gets without asking, because the whole
boundary rests on that -- so what is asserted here is that the scope lives
on the caller's job, and that `ci` still publishes nothing.

And the comment has to be *one* comment, updated. The failure mode is quiet
and cumulative: a marker that stops matching, or a listing that reads one
page of a long pull request's comments, starts adding a report per run
instead of replacing one -- and nothing fails, it just gets worse. So the
script is extracted from the YAML and run against a stub API, which is the
only way to find out whether it actually finds what it wrote last time.
"""

import json
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION = REPO_ROOT / "actions" / "report" / "action.yml"
CI_ACTION = REPO_ROOT / "actions" / "ci" / "action.yml"
CALLER = REPO_ROOT / ".github" / "workflows" / "internal-example.yml"


def _action() -> dict:
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def _steps() -> list[dict]:
    return _action()["runs"]["steps"]


def _comment_step() -> dict:
    return next(step for step in _steps() if "<<'PY'" in str(step.get("run", "")))


def _comment_script() -> str:
    """The Python the comment step runs, lifted out of its heredoc.

    Extracted rather than kept in a file of its own beside the YAML: an
    action's own repository is what `uses:` checks out, so a script in a
    separate file would work -- but the step that runs it would then be a
    path to keep in step with, and what a reader of the action sees would no
    longer be what runs. Lifting it here costs this function and keeps the
    action readable in one pass.
    """
    lines = _comment_step()["run"].splitlines()
    start = next(index for index, line in enumerate(lines) if "<<'PY'" in line) + 1
    end = next(
        index for index, line in enumerate(lines) if line.strip() == "PY" and index > start
    )
    return "\n".join(lines[start:end])


# --- what the action asks of a caller ---------------------------------------


def test_the_results_are_what_it_renders_and_they_are_required():
    """It renders what the gate already said. An action that read the reports
    itself would be a second answer to the question the gate answered, free
    to disagree with it -- which is a comment claiming a promise held where
    the run said it broke."""
    inputs = _action()["inputs"]

    assert inputs["results"]["required"] is True
    assert not any("report" in name and "dir" in name for name in inputs), (
        "no input may point this at a results directory: it renders the reading, "
        "not the reports"
    )


def test_the_comment_and_the_summary_can_each_be_turned_off():
    """Which of them a project wants is the project's. A page nobody asked
    for on every pull request is exactly the inheritance the boundary
    exists to prevent."""
    inputs = _action()["inputs"]

    for name in ("comment", "job_summary"):
        assert inputs[name]["required"] is False
        assert inputs[name]["default"] == "true"


def test_a_boolean_input_is_compared_and_never_read_for_truthiness():
    """Every input an action receives is a string, so `if: inputs.x` is true
    for the literal "false" -- and a step gated that way comments on the
    pull request of a caller that asked for none."""
    for step in _steps():
        condition = str(step.get("if", ""))
        for reference in re.findall(r"inputs\.[A-Za-z_][A-Za-z0-9_]*", condition):
            rest = condition[condition.index(reference) + len(reference):].lstrip()
            assert rest.startswith(("==", "!=")), (
                f"{step.get('name')!r} reads {reference} for truthiness in "
                f"{condition!r}; compare it to a string instead."
            )


def test_the_cli_comes_from_this_actions_own_checkout():
    """The renderer is the `seal` CLI, in this repository. `uses:` checks the
    whole repository out, so it is there at the same revision as this file --
    naming it as an input would reintroduce a credential to fetch it with and
    a revision that can differ from the YAML running it."""
    invocations = [
        step["run"] for step in _steps() if "uvx --from" in str(step.get("run", ""))
    ]

    assert invocations, "the CLI is invoked through uvx"
    for run in invocations:
        assert "${{ github.action_path }}/../../python" in run


def test_the_token_falls_back_to_the_jobs_own():
    """A caller granting `pull-requests: write` already has one. Making it
    required would have every project pass `${{ github.token }}` by hand and
    get an unexplained 403 the one time it forgot."""
    assert _action()["inputs"]["token"]["required"] is False
    assert _comment_step()["env"]["GH_TOKEN"] == "${{ inputs.token || github.token }}"


def test_nothing_reaches_for_a_secret_the_caller_did_not_pass():
    """An action cannot read `secrets`/`vars`, and a reference to either
    resolves to empty at runtime rather than failing."""
    text = ACTION.read_text(encoding="utf-8")

    assert "${{ secrets." not in text
    assert "${{ vars." not in text


def test_the_gate_itself_still_publishes_nothing():
    """The property this action exists in order not to break. A reporting
    step inside `ci` is one every adopting project inherits, along with the
    scope it needs on their pull requests -- so the comment lives here, in a
    job the caller opts into and grants."""
    ci_steps = yaml.safe_load(CI_ACTION.read_text(encoding="utf-8"))["runs"]["steps"]

    for step in ci_steps:
        run = str(step.get("run", ""))
        assert "issues/" not in run and "api.github.com" not in run
        assert "GITHUB_STEP_SUMMARY" not in run, (
            "the gate writes no summary of its own: what it hands back is the "
            "results, and rendering them into somewhere a reader looks is the "
            "project's decision"
        )


def test_the_worked_caller_grants_the_scope_on_the_job_that_needs_it():
    """And on no other. The gate job holds `contents: read`, which is the
    whole point of the comment being somewhere else."""
    jobs = yaml.safe_load(CALLER.read_text(encoding="utf-8"))["jobs"]
    reporting = [
        job
        for job in jobs.values()
        if any(str(step.get("uses", "")).endswith("actions/report") for step in job["steps"])
    ]

    assert reporting, "nothing in the example uses the report action"
    for job in reporting:
        assert job["permissions"]["pull-requests"] == "write"
    assert "pull-requests" not in jobs["tests"]["permissions"]


# --- and whether the comment is actually one comment ------------------------


class _Api:
    """Enough of GitHub's issue-comments API to find out what the script does.

    A stub rather than a mock of the script's own internals: what is under
    test is whether it finds the comment it wrote last time, and that is a
    property of the requests it makes -- how many pages it reads, what it
    matches on, and whether it PATCHes or POSTs.
    """

    def __init__(self, comments: list[dict], status: int = 0, pages: int = 1):
        self.comments = comments
        self.status = status
        self.pages = pages
        self.requests: list[tuple[str, str, dict | None]] = []


@pytest.fixture
def api():
    """A stub API, served for as long as a test needs it."""
    state = _Api(comments=[])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D102 - quiet in the test output
            pass

        def _payload(self):
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or "null") if length else None

        def _respond(self, code, body):
            encoded = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            state.requests.append(("GET", self.path, None))
            # `[?&]`, so `per_page=100` is not read as page 100.
            page = int(re.search(r"[?&]page=(\d+)", self.path).group(1))
            # One comment per page, so a script reading only the first page
            # never reaches the one the marker is on.
            batch = state.comments[page - 1: page] if page <= state.pages else []
            self._respond(200, batch)

        def do_POST(self):
            payload = self._payload()
            state.requests.append(("POST", self.path, payload))
            if state.status:
                return self._respond(state.status, {"message": "no"})
            self._respond(201, {"html_url": "https://example.invalid/new", "id": 99})

        def do_PATCH(self):
            payload = self._payload()
            state.requests.append(("PATCH", self.path, payload))
            if state.status:
                return self._respond(state.status, {"message": "no"})
            self._respond(200, {"html_url": "https://example.invalid/updated", "id": 7})

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.url = "http://127.0.0.1:{}".format(server.server_port)
    yield state
    server.shutdown()


def _run(api, tmp_path: Path, rendering: str = "## it failed\n", **environment):
    """The comment script, run as the action runs it."""
    script = tmp_path / "comment.py"
    script.write_text(_comment_script() + "\n", encoding="utf-8")
    (tmp_path / "seal-report.md").write_text(rendering, encoding="utf-8")
    outputs = tmp_path / "outputs"
    outputs.write_text("", encoding="utf-8")

    environment = {
        "GITHUB_API_URL": api.url,
        "GITHUB_REPOSITORY": "acme/app",
        "GH_TOKEN": "a-token",
        "SEAL_PULL_NUMBER": "42",
        "SEAL_COMMENT_KEY": "default",
        "RUNNER_TEMP": str(tmp_path),
        **environment,
    }
    completed = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )
    return completed


def _output(completed) -> str:
    """What the step wrote to $GITHUB_OUTPUT -- which it prints, so the
    action can redirect it."""
    return completed.stdout.strip()


def test_the_first_run_posts_a_comment(api, tmp_path):
    completed = _run(api, tmp_path)

    assert completed.returncode == 0, completed.stderr
    methods = [method for method, _, _ in api.requests]
    assert "POST" in methods and "PATCH" not in methods
    assert _output(completed) == "url=https://example.invalid/new"


def test_a_later_run_replaces_the_comment_it_wrote_before(api, tmp_path):
    """Twenty pushes should leave one current report, not twenty stale ones
    -- a reader should not have to work out which of them is this run's."""
    api.comments = [{"id": 7, "body": "<!-- seal-report: default -->\n\n## it passed\n"}]

    completed = _run(api, tmp_path)

    assert completed.returncode == 0, completed.stderr
    patches = [(path, payload) for method, path, payload in api.requests if method == "PATCH"]
    assert len(patches) == 1
    path, payload = patches[0]
    assert path.endswith("/comments/7")
    assert "it failed" in payload["body"]
    assert not [method for method, _, _ in api.requests if method == "POST"]


def test_a_comment_under_another_key_is_left_alone(api, tmp_path):
    """A repository gating two projects in one workflow keeps a report for
    each. One overwriting the other is how the second project's results
    silently stop existing."""
    api.comments = [{"id": 7, "body": "<!-- seal-report: other -->\n\n## the other one\n"}]

    completed = _run(api, tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert [method for method, _, _ in api.requests if method == "POST"]


def test_somebody_elses_comment_is_never_replaced(api, tmp_path):
    """The marker is what identifies this action's own comment. Without it,
    the first comment on the pull request would be overwritten by a report
    -- which is somebody's review being deleted."""
    api.comments = [{"id": 7, "body": "This looks good to me, but see the tests."}]

    completed = _run(api, tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert [method for method, _, _ in api.requests if method == "POST"]
    assert not [method for method, _, _ in api.requests if method == "PATCH"]


def test_the_comment_is_found_however_far_down_the_pull_request_it_is(api, tmp_path):
    """It is the *oldest* comment on a long-running pull request, because it
    was written on the first run. A script reading one page of comments
    starts adding a report per run at exactly the point a pull request has
    had enough discussion for it to matter -- and nothing fails."""
    api.comments = [
        {"id": 1, "body": "a review"},
        {"id": 2, "body": "another"},
        {"id": 7, "body": "<!-- seal-report: default -->\n\n## it passed\n"},
    ]
    api.pages = 3

    completed = _run(api, tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert [path for method, path, _ in api.requests if method == "PATCH"][0].endswith(
        "/comments/7"
    )


def test_a_run_with_no_pull_request_comments_nothing_and_says_so(api, tmp_path):
    """A push to a branch, a schedule, a manual run. There is nowhere to
    comment, which is not a failure -- and the output still says so rather
    than being absent for a caller to guess at."""
    completed = _run(api, tmp_path, SEAL_PULL_NUMBER="")

    assert completed.returncode == 0, completed.stderr
    assert api.requests == []
    assert _output(completed) == "url="


def test_a_refused_comment_on_an_ordinary_pull_request_fails_and_names_the_scope(
    api, tmp_path
):
    """The scope is the caller's to grant, and a job that granted none should
    be told which one rather than shown an HTTP status. Failed on rather than
    warned about: a report nobody notices is missing is a report nobody
    reads."""
    api.status = 403

    completed = _run(api, tmp_path)

    assert completed.returncode == 1
    assert "pull-requests: write" in completed.stderr


def test_a_refused_comment_on_a_fork_is_a_warning_and_not_a_failure(api, tmp_path):
    """GitHub gives a workflow triggered by a fork's pull request a read-only
    token however the job declares its permissions. Failing there would fail
    every outside contribution over a comment that was never possible."""
    api.status = 403

    completed = _run(api, tmp_path, SEAL_PULL_FROM_FORK="true")

    assert completed.returncode == 0, completed.stderr
    assert "::warning::" in completed.stderr
    assert _output(completed) == "url="


def test_a_rendering_too_big_to_comment_is_cut_and_says_where_to_read_it(api, tmp_path):
    """GitHub truncates a comment past its limit with nothing to say it did.
    The renderer's own caps keep a normal report far inside it; this is the
    backstop, and what makes it safe is that it points somewhere the whole
    report still exists."""
    completed = _run(api, tmp_path, rendering="x" * 80_000)

    assert completed.returncode == 0, completed.stderr
    [(_, _, payload)] = [
        (method, path, payload)
        for method, path, payload in api.requests
        if method == "POST"
    ]
    assert len(payload["body"]) < 65536
    assert "results artifact" in payload["body"]
