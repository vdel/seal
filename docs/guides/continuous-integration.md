# Continuous integration

Seal ships the build-and-test pipeline as a reusable GitHub Actions
workflow, so a project's own CI file is boilerplate that points at it.

## What a green run means

The workflow runs `seal ci`, and `seal ci` exits zero only when
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
    uses: ./.github/workflows/seal-ci.yml
    permissions:
      contents: read
    with:
      project_dir: my-project
      gh_environment: dev
      k8s_overlay: dev            # the shape the gate deploys
      publish_images: false
      # Only if your services' `.env` files reference a store. Put the CLI
      # your seal-credentials-config.json names on PATH, and log it in --
      # `secrets.provider_token` reaches this shell as $SEAL_PROVIDER_TOKEN.
      provider_setup: |
        curl -fsSL https://example.invalid/install.sh | bash
        echo "$SEAL_PROVIDER_TOKEN" | its-cli login
    secrets:
      provider_token: ${{ secrets.WHATEVER_YOUR_STORE_CALLS_ITS_TOKEN }}
```

Note what isn't there: **your application's variable and secret names**, and
**which password manager you use**. `seal ci` resolves each service's
own `.env` through the providers your project declares, the same way
`seal up` does locally, so this file never enumerates them and never
goes stale against them. A project whose `.env` files hold only literals and
`k8s://` markers drops both the `provider_setup` and the `secrets:` block
entirely.

## Inputs

| Input | Required | Meaning |
| --- | --- | --- |
| `project_dir` | yes | Path, relative to the repository root, to the project's root Tiltfile and services. |
| `k8s_overlay` | yes | Which of your Kubernetes overlays the gate deploys. The run against this one also executes each service's own tests, so name the shape you bring up locally -- a gate on a shape nobody can reproduce is one nobody can act on. |
| `additional_k8s_overlays` | no | Further overlays to verify your promises against, as a JSON list -- `'["prod-like"]'`. Each runs the outcome suite alone, against the images a real environment runs. Empty by default. |
| `publish_images` | yes | Whether to push the images built, once every gate above has passed. |
| `publish_k8s_overlay` | when publishing | Which overlay the publishing run deploys. Publishing means deploying and letting Tilt push what it built, so it still names a shape -- the one the deployment will use. |
| `gh_environment` | yes | The GitHub Environment this job binds to -- protection rules, and scoping for what the workflow reads from `vars`/`secrets` itself. Not `credentials_env` below, which picks which store your `.env` references resolve against. |
| `ref` | no | Branch or SHA to check out. Defaults to the triggering ref. |
| `runs_on` | no | Runner label. Defaults to `ubuntu-latest`. Everything beyond a Linux machine with a reachable Docker daemon -- uv, Tilt, ctlptl, kubectl, kind, rsync -- the job installs itself, so a self-hosted label works too. |
| `provider_setup` | no | Shell run before `seal ci`, putting every CLI your `seal-credentials-config.json` names on `PATH` and authenticating it. `provider_token` reaches it as `$SEAL_PROVIDER_TOKEN`. Empty by default, and correct empty: a project whose `.env` files hold only literals and `k8s://` markers reaches no provider and needs no CLI. |
| `credentials_env` | no | Which of your credentials environments this run reads -- which store each `.env` reference resolves against, per your own `seal-credentials-config.json`. Reaches `seal ci` as `SEAL_CREDENTIALS_ENV`. Left empty, your `default_env` applies. Deliberately independent of `k8s_overlay`: deriving one from the other would make a production-shaped overlay on a throwaway cluster reach real secrets. |
| `python_dir` | no | Path, relative to `project_dir`, to Seal's own checked-out `python/` package. Defaults to `../../python`. |
| `results_artifact` | no | Name of the artifact the run uploads its results to. Defaults to `tests-results`. An artifact name has to be unique within a workflow run, so give each call its own name if you call this workflow more than once. |
| `results_retention_days` | no | How long that artifact is kept. Defaults to 7: it exists for your own reporting job to read in the same run. |

### Secrets

| Secret | Required | Meaning |
| --- | --- | --- |
| `provider_token` | no | One credential for `provider_setup` to authenticate with, reaching it as `$SEAL_PROVIDER_TOKEN`. What it opens, and which store, is your project's business. |
| `source_repo_token` | no | Read access to whatever the checkout needs beyond your own repository — in practice a private git submodule vendoring Seal. Falls back to `GITHUB_TOKEN`. |

### About `python_dir`

A reusable-workflow call checks out only the *caller's* repository. The
`../../python` default therefore resolves only when your project lives
inside a checkout of Seal itself, two directories deep -- which is
true of the bundled example and not of your project.

A project in its own repository that vendors Seal as a git submodule
overrides it to point at the submodule's own `python/`:

```yaml
with:
  project_dir: my-project
  python_dir: seal/python     # submodule checked out at my-project/seal
```

If that submodule is **private**, pass a token that can read it as the
`source_repo_token` secret. `GITHUB_TOKEN` is scoped to the repository whose
workflow is running and can read no other, so the submodule's clone
otherwise fails with a bare "Repository not found" before any step of the
job runs — and nothing later recovers, since both the Tilt extensions and
the CLI resolve out of that checkout.

```yaml
secrets:
  source_repo_token: ${{ secrets.A_TOKEN_THAT_CAN_READ_IT }}
```

## Outputs

The workflow doesn't publish a report. It reads the JUnit reports its runs
left behind and hands them back, so **how your results are presented is your
project's decision** rather than one you inherit -- along with whichever
third-party action implements it, the write scopes that action needs on your
pull requests, and the kind of runner it happens to require.

| Output | What it carries |
| --- | --- |
| `overlays` | The overlays this run verified, as a JSON list. What to matrix a per-shape report over. Empty if the run died before it could say which shapes it was going to run -- guard on that, because `fromJSON('')` fails the job reading it. |
| `results` | What every run found, as one line of JSON keyed by overlay. |
| `results_artifact` | Name of the artifact holding the reports themselves, laid out as `<overlay>/<service>/junit.xml`. Nothing is uploaded when a run failed before producing any results, so guard your download step. |

`results` is shaped like this:

```json
{
  "dev": {
    "passed": false,
    "cases": 312,
    "skipped": 4,
    "failed": 1,
    "problems": [],
    "sources": [
      {"name": "api", "passed": true, "cases": 208, "skipped": 4,
       "failed": [], "failed_omitted": 0, "problems": []},
      {"name": "outcomes", "passed": false, "cases": 12, "skipped": 0,
       "failed": ["a-deleted-item-stays-deleted (todo-list/a-deleted-item-stays-deleted/junit.xml)"],
       "failed_omitted": 0, "problems": []}
    ]
  }
}
```

One `source` per directory a run's results came back in: each service under
its own name, the outcome suite under `outcomes`. A `problem` is a reason
the results can't be believed rather than a test that failed -- no report
written, a report that didn't parse, a run that produced nothing at all --
because a shape whose run died looks exactly like one whose tests all
passed, and that is the claim a gate must never let a report make.

It's read by the same `junit.py` the gate's own per-service verdict comes
from, so it can't say a test passed where the run said it failed. The failed
*names* are capped per source (a job output is a string with a size limit)
and `failed_omitted` says how many were left out; the failed *count* is never
capped.

### Doing something with them

A summary needs no permissions at all:

```yaml
  report:
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

A check per shape, or a comment on the pull request, wants the XML rather
than the reading of it -- download the artifact and point whichever action
you like at it, granting *that* job the `checks: write` /
`pull-requests: write` it needs:

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

The artifact is also where coverage lives: `results` covers JUnit reports,
and a service's `coverage.xml` sits beside its `junit.xml` untouched.

The two are worth having together. A check carries the detail -- which test
failed, and what it said -- and `results` carries what no report can, because
a shape whose run died before writing one has nothing to publish a check
from: `problems` names it, and the check would simply not appear.

`.github/workflows/internal-example.yml` in this repository is a worked
caller doing both.

## Secrets

One, and it's infrastructure-level rather than application config:

**`provider_token`** -- one credential for your `provider_setup` script to
authenticate with, reaching it as `$SEAL_PROVIDER_TOKEN`. What it
opens, and which store, is your project's business: the workflow never names
one. Scope it to only what this environment should read. Optional: only
needed if a service's `.env` actually references a provider. See
[Credentials](credentials.md#ci-staging-and-production).

Set it under **Settings → Environments → `<name>` → Secrets**, not as a
repository secret. Per-environment scoping is what makes a `dev` token
unable to read a `prod` store.

## Three GitHub Actions quirks

None is obvious from GitHub's own documentation, and each one fails quietly:

**A job that calls a reusable workflow can't also set `environment:` on
itself.** GitHub rejects the whole file. That's why `gh_environment` is
threaded through as a plain input -- the reusable workflow's own job binds
to it directly. The consequence: every `vars.X` expression in *your* caller
resolves at repository/organisation scope, not the environment's.

**`secrets.X` doesn't follow that same rule.** GitHub resolves an
environment-scoped secret for a reusable-workflow job only if that secret
was *also* named in the caller's own `secrets:` block -- even though the
value the caller passes is empty (the caller job isn't bound to any
environment). Drop the passthrough and the value silently arrives empty,
even with the secret correctly set on the environment.

**A reusable-workflow job only gets the `permissions:` its caller
declares.** Where a repository's default `GITHUB_TOKEN` permissions are
read-only, the `permissions:` block above must cover whatever the callee's
jobs request, or the run fails at startup with zero jobs scheduled. This one
requests `contents: read` and nothing else -- it reads your repository and
reports nothing back to it. The write scopes belong on your own reporting
job, if you write one.

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
6. Runs the gate on `k8s_overlay`: `uvx --from <python_dir> seal ci --
   --k8s_overlay <k8s_overlay> --build_type test`. This is the run that also
   executes each service's own tests, because `test` is the build kind whose
   images carry them.
7. Runs the gate again on each of `additional_k8s_overlays`, at
   `--build_type runtime` -- the images a real environment runs, which carry
   no test suite, so these runs verify the promises alone.
8. If `publish_images`, deploys `publish_k8s_overlay` at `--build_type
   runtime --publish_images --run_outcomes false` and lets Tilt push what it
   built. Not a gate: the promises were read by the runs above, and reading
   them again would say the same thing more slowly.
9. Reads every JUnit report the runs left behind (`seal _tests-results`,
   the same `junit.py` that decided each service's verdict during the run)
   into the `results` output, and uploads `tests-results/` as an artifact --
   filed under the overlay that produced it, so one run's results never
   overwrite another's. Both happen whatever the gates said: a failed run's
   results are the ones somebody needs.

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
