# Continuous integration

Seal ships the build-and-test pipeline as a composite GitHub Action, so a
project's own CI file is boilerplate that uses it.

## What a green run means

The action runs `seal ci`, and `seal ci` exits zero only when
**both** of these hold:

1. **The environment came up.** Every resource Tilt manages reported ready
   -- which means something, because `seal check` refused to start at all
   until every Deployment container declared a `readinessProbe`. Without
   that, Kubernetes reports a container Ready the instant its process
   starts.
2. **Every promise the project has translated still holds.** The whole
   outcome suite ran in one pass, and the exit code is its verdict.

Each service's own tests run inside its running container along the way,
once that service is ready, and fail pointing at that service.

One promise can be exempt from that second claim, and only by saying so in
the repository. An outcome carrying a
[`quarantine.md`](outcomes.md#when-a-test-is-the-problem-quarantine) doesn't
fail the run while somebody fixes its test's determinism -- it is still run,
still reported, and never counted as passed, so the report says which
promises were held to the gate and which weren't. Because that file lives in
the outcome's own directory, adding one needs a code owner exactly as
editing the test would.

Both claims are the default, and either can be switched off for a run --
see [`run_service_tests` and `run_outcomes`](#inputs) below. A run with one
of them off is a faster check to have *beside* the gate rather than the gate
itself; with both off it gates on readiness alone.

It never touches a real cluster: the job creates a throwaway Kind cluster
and discards it.

## Your project's CI file

The only project-specific piece. Copy it and point `project_dir` at your
project:

```yaml
name: My project

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  tests:
    runs-on: ubuntu-latest
    # Your job binds the Environment, so the secret below resolves against
    # it and the action receives the value. See "Why an action" below.
    environment: dev
    permissions:
      contents: read
    # Read by the reporting job below. An action's outputs belong to the
    # step that ran it; a job's belong to whatever `needs:` it.
    outputs:
      results: ${{ steps.seal.outputs.results }}
      recordings: ${{ steps.seal.outputs.recordings }}
      results_artifact_url: ${{ steps.seal.outputs.results_artifact_url }}
    steps:
      - uses: actions/checkout@v6

      - id: seal
        uses: vdel/seal/actions/ci@<ref>
        with:
          project_dir: my-project
          k8s_overlay: dev            # the shape the gate deploys
          publish_images: false
          # Only if your services' `.env` files reference a store. Put the
          # CLI your seal-credentials-config.json names on PATH, and log it
          # in -- `provider_token` reaches this shell as
          # $SEAL_PROVIDER_TOKEN.
          provider_setup: |
            curl -fsSL https://example.invalid/install.sh | bash
            echo "$SEAL_PROVIDER_TOKEN" | its-cli login
          provider_token: ${{ secrets.WHATEVER_YOUR_STORE_CALLS_ITS_TOKEN }}

  # Optional, and a job of its own because the comment needs a write scope
  # the gate has no business holding. Drop it and you still get the results,
  # the reports and the rendered page in the artifact.
  report:
    needs: tests
    if: (!cancelled()) && needs.tests.outputs.results != ''
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v6
      - uses: vdel/seal/actions/report@<ref>
        with:
          results: ${{ needs.tests.outputs.results }}
          # So a broken promise's line links straight to a video of it.
          recordings: ${{ needs.tests.outputs.recordings }}
          artifact_url: ${{ needs.tests.outputs.results_artifact_url }}
```

Note what isn't there: **your application's variable and secret names**, and
**which password manager you use**. `seal ci` resolves each service's
own `.env` through the providers your project declares, the same way
`seal up` does locally, so this file never enumerates them and never
goes stale against them. A project whose `.env` files hold only literals and
`k8s://` markers drops both `provider_setup` and `provider_token` entirely.

Nor is there a pin for the `seal` CLI. `uses:` checks out this action's own
repository, so the CLI is already beside it, at the revision `<ref>` names.

## Inputs

| Input | Required | Meaning |
| --- | --- | --- |
| `project_dir` | yes | Path, relative to the repository root, to the project's root Tiltfile and services. |
| `k8s_overlay` | yes | Which of your Kubernetes overlays the gate deploys. The run against this one also executes each service's own tests, so name the shape you bring up locally -- a gate on a shape nobody can reproduce is one nobody can act on. |
| `additional_k8s_overlays` | no | Further overlays to verify your promises against, as a JSON list -- `'["prod-like"]'`. Each runs the outcome suite alone, against the images a real environment runs. Empty by default. |
| `run_service_tests` | no | Whether the run on `k8s_overlay` executes each service's own tests -- `true` or `false`, `true` by default. It is the only run that can: a suite runs inside the service's container, so it lives only in images built at `--build_type test`, and this input is what decides which kind that run builds. Off, it builds what a real environment runs and reads your promises against that. |
| `run_outcomes` | no | Whether these runs read your promises -- `true` or `false`, `true` by default. Turned off, what is left is each service's own tests and the readiness gate: a faster check to have *beside* the gate, never one to have instead of it. It also leaves `additional_k8s_overlays` nothing to verify, so naming both is refused. Off alongside `run_service_tests` it leaves a run that reads nothing and gates on readiness alone -- allowed deliberately, for the emergency where that is the question. |
| `publish_images` | yes | Whether to push the images built, once every gate above has passed. |
| `publish_k8s_overlay` | when publishing | Which overlay the publishing run deploys. Publishing means deploying and letting Tilt push what it built, so it still names a shape -- the one the deployment will use. |
| `ref` | no | Branch or SHA to check out. Defaults to the triggering ref. |
| `provider_setup` | no | Shell run before `seal ci`, putting every CLI your `seal-credentials-config.json` names on `PATH` and authenticating it. `provider_token` reaches it as `$SEAL_PROVIDER_TOKEN`. Empty by default, and correct empty: a project whose `.env` files hold only literals and `k8s://` markers reaches no provider and needs no CLI. |
| `credentials_env` | no | Which of your credentials environments this run reads -- which store each `.env` reference resolves against, per your own `seal-credentials-config.json`. Reaches `seal ci` as `SEAL_CREDENTIALS_ENV`. Left empty, your `default_env` applies. Deliberately independent of `k8s_overlay`: deriving one from the other would make a production-shaped overlay on a throwaway cluster reach real secrets. |
| `results_artifact` | no | Name of the artifact the run uploads its results to. Defaults to `tests-results`. An artifact name has to be unique within a workflow run, so give each use its own name if you use this action more than once. |
| `publish_recordings` | no | Whether each broken promise's recording also gets an artifact of its own, so a report can link straight to it -- `true` or `false`, `true` by default. Costs one upload per broken promise and sends the recording's bytes twice, since it stays in the results artifact where the page that plays it lives. |
| `results_retention_days` | no | How long that artifact is kept. Defaults to 7: it exists for your own reporting job to read in the same run. |
| `provider_token` | no | One credential for `provider_setup` to authenticate with, reaching it as `$SEAL_PROVIDER_TOKEN`. What it opens, and which store, is your project's business. Passed by value: read it from `secrets` in your own job, which is what binds the Environment it resolves against. |
| `submodules_token` | no | Read access to whatever the checkout needs beyond your own repository -- a private git submodule your project vendors. `GITHUB_TOKEN` is scoped to the repository whose workflow is running and can read no other, so without this such a submodule fails to clone with a bare "Repository not found" before any later step runs. Nothing about Seal itself needs it: the CLI is this action's own repository, checked out beside it. |

## Outputs

The action doesn't publish anything. It reads what its runs left behind and
hands that back, so **which check, comment or dashboard your results become
is your project's decision** rather than one you inherit -- along with
whichever third-party action implements it, the write scopes that action
needs on your pull requests, and the kind of runner it happens to require.

What it does do is render: the artifact it uploads carries a readable page
of the same results, and [`actions/report`](#one-comment-updated-in-place)
is a separate, opt-in action that puts that rendering on the pull request.
`/rfcs/0015-reporting-what-a-run-found.md` is where that line is drawn, and
why.

| Output | What it carries |
| --- | --- |
| `overlays` | The overlays this run verified, as a JSON list. What to matrix a per-shape report over. Empty if the run died before it could say which shapes it was going to run -- guard on that, because `fromJSON('')` fails the job reading it. |
| `results` | What every run found, as one line of JSON keyed by overlay. `{}` when no run was asked to read anything (both switches off) -- an absence of reports by design, not a run that lost them, so the job's own status is the whole of what such a run says. |
| `results_artifact` | Name of the artifact holding the reports themselves, the reading, and the rendered page. Nothing is uploaded when a run failed before producing any results, so guard your download step. |
| `results_artifact_url` | Where that artifact can be downloaded. Empty when nothing was uploaded. |
| `recordings` | Where each broken promise's recording was published, as JSON keyed by `<overlay>/<slug>`. What a report links to say "watch this failure". `{}` on a green run, or where `publish_recordings` is off. |

`results` is shaped like this:

```json
{
  "dev": {
    "passed": false,
    "cases": 208,
    "skipped": 4,
    "failed": 0,
    "problems": [],
    "sources": [
      {"name": "api", "passed": true, "cases": 208, "skipped": 4,
       "failed": [], "failed_omitted": 0, "problems": []}
    ],
    "outcomes": {
      "read": true,
      "passed": false,
      "counts": {"PASS": 11, "FAIL": 1},
      "quarantined": 0,
      "problems": [],
      "promises": [
        {"slug": "ui/todo-list/an-added-item-shows-up",
         "headline": "an added item shows up", "state": "PASS",
         "quarantined": false, "failed": []},
        {"slug": "ui/todo-list/a-deleted-item-stays-deleted",
         "headline": "a deleted item stays deleted", "state": "FAIL",
         "quarantined": false,
         "failed": ["deleted.stays deleted (junit.xml)"],
         "evidence": [
           {"kind": "video",
            "path": "outcomes/ui/todo-list/a-deleted-item-stays-deleted/artifacts/…/video.webm"},
           {"kind": "log",
            "path": "outcomes/ui/todo-list/a-deleted-item-stays-deleted/log.txt"}
         ],
         "evidence_omitted": 0}
      ]
    }
  }
}
```

Two halves, read by two different things -- the same two the run's own
verdicts came from, so neither can disagree with what the gate concluded.

**`sources`** is one entry per service whose own tests came back, under its
own name. A `problem` is a reason the results can't be believed rather than a
test that failed -- no report written, a report that didn't parse, a run that
produced nothing at all -- because a shape whose run died looks exactly like
one whose tests all passed, and that is the claim a gate must never let a
report make. The failed *names* are capped per source (a job output is a
string with a size limit) and `failed_omitted` says how many were left out;
the failed *count* is never capped.

**`outcomes`** is every promise your tree declares, in one of four `state`s:

| `state` | Means |
| --- | --- |
| `PASS` | The promise held. |
| `FAIL` | It didn't. |
| `no verdict` | It has a test, and nothing here knows whether it ran -- which is a failure, not an absence. |
| `no test yet` | Nothing has been translated from it. An ordinary state to sit in, and not a reason the run is red. |

A promise is named by its prompt's headline as well as by its slug, because
the headline is what your project actually promises. `quarantined` marks one
the suite has been told not to gate on: it is still reported, and still not
reported as passed. `failed` carries which case gave way, where that
promise's runner also wrote a JUnit report -- detail beside the verdict, not
the verdict itself, which is the file the runner wrote.

`evidence` is what a promise that did **not** hold left behind to look at,
each `path` relative to that run's own results and so a path inside the
artifact once the run's name is prefixed. `kind` is `video`, `image`,
`trace`, `page` or `log`, classified by what opening the file does -- a
runner writes whatever it writes, so this is not a list of names any runner
was told to produce. The key is absent where a promise recorded nothing, and
never present for one that passed.

`read` is `false` when the run was not asked to read the promises at all
(`run_outcomes: false`). `promises` is then empty and `passed` is `true` --
because nothing here is a claim about them. That distinction matters: a run
that never looked and a run whose every test failed to write a verdict leave
exactly the same absence behind, and only the workflow knows which it was, so
it says rather than letting the second one read as the first.

`passed` at the top is both halves together: every service's own tests, and
every promise the suite read.

### What's in the artifact

| Path | What it is |
| --- | --- |
| `<overlay>/<service>/junit.xml` | Each service's own report, as its test stage wrote it. `coverage.xml` and anything else it produced sits beside it, untouched. |
| `<overlay>/outcomes/<group>/<epic>/<outcome>/` | One directory per promise: the `passed` verdict its container wrote, and whatever else its runner left there -- for a promise that failed under the `playwright` runner, that includes a video of the browser and a screenshot of the moment it gave way. |
| `results.json` | The `results` output above, as a file -- for whoever opens the artifact rather than the workflow run. |
| `index.html` | A self-contained page: every promise and its state, every service, every failure -- and it **plays the recording** of each failed promise, since the video sits beside it in the same archive. Open it from the extracted artifact; it fetches nothing of its own. |
| `report.md` | The same thing as Markdown, which is what `actions/report` posts. |

### Watching a failure

A promise that failed under the `playwright` runner seal supplies leaves a
video of the browser and a screenshot of the moment it gave way, recorded
`retain-on-failure` -- so a suite that kept every promise records nothing it
keeps. They land in that promise's own results directory, which is what puts
them in the artifact.

`index.html` is where they are worth opening: download the artifact, extract
it, open the page, and each failed promise has its recording embedded under
it. Nothing is fetched from the network, and nothing is preloaded until you
press play.

A `trace` is deliberately not recorded. It is the better debugging tool and
it is megabytes per test, viewable only by loading it into Playwright's own
viewer -- so it is left to a project that wants it:

```json
{"runner": [{"name": "ui", "runner_type": "playwright",
             "runner_args": ["--trace", "retain-on-failure"]}]}
```

Traces land beside the videos and are reported the same way.

### Watching one from GitHub, without a download

A file inside a CI artifact has no address of its own: an artifact is one
archive, fetched whole, so a link to a video *inside* one is a download to go
looking through.

So each broken promise's recording is **also** published as an artifact of
its own, unarchived — which `actions/upload-artifact` allows for a single
file, and which makes the artifact's name the file's name. Each one is named
after the promise it belongs to, so the run's artifact list reads as a list
of what broke:

```
dev--ui--todo-list--a-deleted-item-stays-deleted.webm
```

`actions/ci` hands back where each went in its `recordings` output, and
`actions/report` puts that in the comment as a link per failure:

> - `ui/todo-list/a-deleted-item-stays-deleted` — FAIL: a deleted item stays deleted
>   - ▶ watch this failure &nbsp;*(a link to the recording itself)*

**The link reaches the recording rather than an archive containing it.**
Whether your browser plays it there or saves it is the browser's call on the
content type — either way there is no archive to open and nothing to go
looking through.

| | |
| --- | --- |
| How many | Five per run, at most. A composite action can't loop an upload step and a run doesn't know how many promises broke until it has finished, so the number of addresses is fixed. Past that, the recordings are still in the results artifact. |
| Which files | The videos, one per broken promise. Screenshots, logs and traces stay with the results, where the page shows them together. |
| What it costs | One upload per broken promise, and the recording's bytes travelling twice — it stays in the results artifact too, since that is where the page that plays it lives. `publish_recordings: false` keeps the page and skips the uploads. |
| On a green run | Nothing. There is no recording to publish, so no upload happens and the comment has no link to make. |

### One comment, updated in place

`actions/report` renders the reading into the job's summary and keeps a
single comment on the pull request current -- replaced on every run rather
than added to, so twenty pushes leave one report instead of twenty stale
ones.

It is a separate action, used from a job of your own, because the comment
needs `pull-requests: write` and the gate has no business holding it:

```yaml
  report:
    needs: tests
    if: (!cancelled()) && needs.tests.outputs.results != ''
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
    - uses: actions/checkout@v6
    - uses: vdel/seal/actions/report@<ref>
      with:
        results: ${{ needs.tests.outputs.results }}
```

| Input | Required | Meaning |
| --- | --- | --- |
| `results` | yes | The `results` output of `actions/ci`, passed through verbatim. An empty string is reported as a run that produced nothing -- which is what it was. |
| `title` | no | The heading both renderings carry. Defaults to `Seal test results`. |
| `comment` | no | Whether to post and update the pull-request comment. `'true'` by default; compared as a string, so anything else turns it off. |
| `comment_key` | no | Which comment a run replaces. Defaults to `default`. Give each use its own if you gate two projects in one workflow, or each will overwrite the other's report. |
| `job_summary` | no | Whether to write the rendering to this job's summary page. `'true'` by default, and needs no permissions. |
| `recordings` | no | The `recordings` output of `actions/ci`, so each failure's line links straight to its own recording. |
| `artifact_url` | no | The `results_artifact_url` output of `actions/ci`, so the comment can link the archive holding everything else. |
| `source` | no | What names the run -- a commit, a branch, a URL. Rendered verbatim on the page. |
| `token` | no | What the comment authenticates as. Defaults to the job's own `GITHUB_TOKEN`. |

It outputs `comment_url`, empty where it commented nothing.

The comment ends with the commit it is about:

> Results for commit [1a2b3c4](https://github.com/you/your-project/commit/1a2b3c4).

It is replaced in place on every run, so that line is the only thing dating
it -- and it names the pull request's **head** commit, not the merge commit
`github.sha` carries on a `pull_request` event, which appears nowhere in your
branch.

Two more behaviours worth knowing:

- **A pull request from a fork gets no comment.** GitHub gives such a run a
  read-only token whatever your job's `permissions` say, so the action warns
  and carries on rather than failing an outside contribution over a comment
  that was never possible. The summary and the artifact still have the
  report. Anywhere else, a refused comment fails the job and names the scope
  you're missing.
- **A run with no pull request comments nothing.** A push to a branch, a
  schedule, a manual run: there is nowhere to comment, which isn't a
  failure.

### Doing something else with them

A summary of your own needs no permissions at all:

```yaml
  summary:
    needs: tests
    if: (!cancelled()) && needs.tests.outputs.results != ''
    runs-on: ubuntu-latest
    steps:
    - env:
        SEAL_RESULTS: ${{ needs.tests.outputs.results }}
      run: |
        python3 - <<'PY' >> "$GITHUB_STEP_SUMMARY"
        import json, os
        for overlay, run in json.loads(os.environ["SEAL_RESULTS"]).items():
            print("## {}: {}".format(overlay, "passed" if run["passed"] else "FAILED"))
        PY
```

A check run per shape wants the XML rather than the reading of it -- download
the artifact and point whichever action you like at it, granting *that* job
the `checks: write` it needs:

```yaml
    # in a job matrixing over fromJSON(needs.tests.outputs.overlays), so each
    # shape gets a check of its own
    - id: download
      continue-on-error: true            # a failed run may have uploaded nothing
      uses: actions/download-artifact@v8
      with:
        name: ${{ needs.tests.outputs.results_artifact }}
        path: results
    - if: steps.download.outcome == 'success'
      uses: EnricoMi/publish-unit-test-result-action@v2
      with:
        files: results/${{ matrix.overlay }}/**/junit.xml
        check_name: "Test Results (${{ matrix.overlay }})"
```

Reading and reports are worth having together. A check carries the per-case
detail, and `results` carries what no report can, because a shape whose run
died before writing one has nothing to publish a check from: `problems` names
it, and the check would simply not appear.

`.github/workflows/internal-example.yml` in this repository is a worked
caller doing both.

## Secrets

One, and it's infrastructure-level rather than application config:

**`provider_token`** -- one credential for your `provider_setup` script to
authenticate with, reaching it as `$SEAL_PROVIDER_TOKEN`. What it
opens, and which store, is your project's business: the action never names
one. Scope it to only what this environment should read. Optional: only
needed if a service's `.env` actually references a provider. See
[Credentials](credentials.md#ci-staging-and-production).

Set it under **Settings → Environments → `<name>` → Secrets**, not as a
repository secret. Per-environment scoping is what makes a `dev` token
unable to read a `prod` store.

## Why an action, and what follows from it

The pipeline is a composite action rather than a reusable workflow, and two
things follow that shape your own CI file.

**The `seal` CLI travels with the action.** `uses:` on an action checks out
its whole repository and points `$GITHUB_ACTION_PATH` into it, so `python/`
is right there -- at the revision the action was used at. Nothing names it,
nothing fetches it, and it cannot be a different version from the YAML
running it. A reusable workflow ships only its `.yml`, which is why one
would leave you to vendor the CLI as a submodule or pin it by git reference
and keep that pin in step by hand.

**Your job binds the environment, and passes values.** An action runs inside
the calling job, so that job sets `environment:` on itself and every
`secrets.X`/`vars.X` it reads resolves against that Environment. What the
action receives is the value:

```yaml
jobs:
  tests:
    runs-on: ubuntu-latest
    environment: dev
    permissions:
      contents: read
    outputs:
      overlays: ${{ steps.seal.outputs.overlays }}
      results: ${{ steps.seal.outputs.results }}
      results_artifact: ${{ steps.seal.outputs.results_artifact }}
    steps:
      - uses: actions/checkout@v6
      - id: seal
        uses: vdel/seal/actions/ci@<ref>
        with:
          project_dir: .
          k8s_overlay: dev
          publish_images: false
          provider_token: ${{ secrets.WHATEVER_YOUR_STORE_CALLS_IT }}
```

Two details in that shape are easy to miss:

- **Re-expose the outputs.** An action's outputs belong to the step; a
  job's belong to whatever `needs:` it. If a later job fans out over
  `overlays` or reports from `results`, the job running the action has to
  declare them as its own.
- **`permissions:` is yours to set.** An action runs under whatever the
  calling job has. This one reads your repository and reports nothing back
  to it, so `contents: read` is enough -- the write scopes belong on your
  own reporting job, if you write one.

**One pin is left.** Your root Tiltfile registers the Starlark half with
`v1alpha1.extension_repo(ref=...)`. The Starlark and the Python are one
library, so that ref and the ref you use this action at have to name the
same revision.

## What the job actually does

1. Checks out the repository.
2. Installs uv, Tilt, ctlptl, kubectl, kind and rsync.
3. Writes the script each run below starts with -- `ctlptl delete cluster
   kind` then `ctlptl create cluster kind --registry=ctlptl-registry`. The
   registry is a container of its own and outlives the cluster, so what an
   earlier run pushed is still there to pull.
4. Sets up Docker Buildx with the GitHub Actions cache exporter, and sets
   `SEAL_BUILDX_CACHE=1` so `seal_service()` builds through
   `cached_docker_build()`.
5. Runs your `provider_setup` script, with `provider_token` in its
   environment as `$SEAL_PROVIDER_TOKEN` -- but only if you passed
   one, which a project whose `.env` files reference no provider does not
   need to.
6. Runs the gate on `k8s_overlay`: `uvx --from <the action's own python/> seal ci --
   --k8s_overlay <k8s_overlay> --build_type test`. This is the run that also
   executes each service's own tests, because `test` is the build kind whose
   images carry them. Both halves of what it verifies are yours to switch
   off: `run_service_tests: false` builds `--build_type runtime` instead,
   leaving the promises and the readiness gate, and `run_outcomes: false`
   appends `--run_outcomes false`, leaving the service tests and the
   readiness gate. Off together they leave the readiness gate alone -- the
   images build, the manifests apply, every resource comes up -- which the
   run says in a warning, since no results come back to say it for them.
   Every one of the four is one `seal ci` you can type.
7. Runs the gate again on each of `additional_k8s_overlays`, at
   `--build_type runtime` -- the images a real environment runs, which carry
   no test suite, so these runs verify the promises alone.
8. If `publish_images`, deploys `publish_k8s_overlay` at `--build_type
   runtime --publish_images --run_outcomes false` and lets Tilt push what it
   built. Not a gate: the promises were read by the runs above, and reading
   them again would say the same thing more slowly.
9. Reads what the runs left behind into the `results` output -- each
   service's own reports through `seal _tests-results`' `junit.py`, the same
   module that decided that service's verdict during the run, and the
   promises through the `outcome_suite.py` their verdicts came from. A run
   asked not to read the promises says so here, rather than reporting a tree
   that left no verdict.
10. Renders that reading into `index.html` and `report.md` (`seal _report`),
   and uploads `tests-results/` as an artifact -- filed under the overlay
   that produced it, so one run's results never overwrite another's, with
   the reading and the page beside them at the root. All of it happens
   whatever the gates said: a failed run's results are the ones somebody
   needs.

Steps 6 to 8 are steps of one job rather than jobs of their own: each needs
the cluster, the images and the tooling the ones before it set up, and a
separate job would rebuild all of that to run one `seal ci`.

Each of them does start from a cluster with nothing on it, though, which is
what step 3's script is for. Reusing one leaves the previous overlay's
objects applied, and an object the next overlay doesn't declare keeps
running -- so a promise can be kept by a container the shape under test
*removed*. That is a false green, and a gate that can produce one is worth
less than no gate at all.

Reporting per overlay is what makes the gate readable, and why the results
are keyed by one. Two result sets in one pull request are two different
claims -- "the promises hold on the shape we work in" and "they hold on the
shape that ships" -- and somebody deciding whether to merge has to see which
one went red. Both a service's own test stage and the outcome runners write
JUnit XML into `tests-results/`, so the primary overlay's results cover unit
tests and promises together; an additional overlay's covers its promises
alone, since the images it runs carry no suite.

## Making it a merge gate

Green CI is only half of a gate. The other half is that an outcome test
can't be edited without a human -- which needs `CODEOWNERS` over the outcome
tree *and* branch protection requiring code-owner review and this check
passing. See [The merge gate](merge-gate.md).

## Deployment is out of scope

Publishing an image to a real registry, applying an overlay that names a
real environment, and sealing credentials for one are deliberately not here.
This workflow builds and tests what's in the repository; what happens to a
build afterwards belongs to whoever deploys it.

The one place Seal's own code meets that concern is
[`SEAL_IMAGE_TAG`/`SEAL_BUILD_ID`](project-layout.md#stable-image-tags-for-a-publishing-pipeline),
which a publishing pipeline sets to get a stable, externally-discoverable
registry tag.
