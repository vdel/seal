---
name: seal-merge-gate
description: Make a Seal project's merge gate real -- CODEOWNERS over the outcome tree, the branch protection settings that make it blocking, and the reusable GitHub Actions workflow that runs seal ci on every pull request. Use when asked whether a change can merge unattended, when seal check reports an outcome CODEOWNERS does not cover, when setting up or fixing CI for a Seal project, or when a test is being edited to make a run green.
---

# The merge gate

## What the gate is for

A pull request should be able to merge on its own say-so for changes the
outcome tests cover -- not because its author is trusted, but because they
cannot merge without satisfying tests they cannot quietly rewrite.

Nothing about a green run shows that distinction. A suite passes identically
whether the author fixed the application or edited the test that failed. So
the gate does not ask; it makes the two cases structurally different:

- **Fix the application → merge unattended.** Every committed outcome test
  still passes, and nobody has to read the diff.
- **Change what a test asserts → get a human.** The diff touches a path under
  `CODEOWNERS`, and the platform blocks the merge until a code owner approves.

An author who cannot find an application fix has exactly one move left, and
it ends with a person reading the change. **That is the move to take
openly:** say the promise looks wrong, change `prompt.md` and the test
together, and let a code owner decide. Quietly weakening a test to get green
is the one thing this whole mechanism exists to prevent.

One consequence is deliberate: an application fix that satisfies every
outcome test merges unattended even when it is a substantial rewrite. The
outcome tests are the spec being enforced, not a stand-in for "small diff".

## CODEOWNERS over the outcome tree

```
/outcomes/ @your-team
```

The whole tree, prompt and translation alike. The prompt is covered for the
same reason as the test: an author free to rewrite the promise never has to
touch a test to change what the project claims. Fixtures sit inside an
outcome's directory, and a group's `helpers/` inside the tree, so a rule over
the tree covers a test's seed data and what several tests share as surely as
its assertions -- a test can be defanged from either end, or from a helper it
imports.

Two properties decide whether a rule holds, and both are easy to get wrong:

- **The last matching rule wins**, not the most specific. A broad
  `/outcomes/ @your-team` is overridden by anything a later rule matches.
- **A rule with no owners clears ownership.** A bare `*.py` line anywhere
  below the tree's rule silently unlocks every Python test in it.

`seal check` reads the file from the three locations the platform itself
reads -- `CODEOWNERS`, `.github/CODEOWNERS`, `docs/CODEOWNERS` -- in the
**enclosing git repository**, which is not necessarily the project root. A
project inside a larger repository is governed by that repository's file, at
patterns carrying the project's own directory prefix. There is deliberately
no environment variable pointing this elsewhere: a file the platform never
reads owns nothing.

It refuses an outcome directory the gate does not reach, a file inside an
owned outcome that a later rule unowns, and an outcome tree with no
`CODEOWNERS` anywhere. Cover the *directory*, not the files -- that is what
covers files added to it later.

## The half Seal cannot check

**`CODEOWNERS` on its own blocks nothing.** Without branch protection it
assigns reviewers and lets a pull request merge unreviewed. Three settings on
the protected branch turn it into a gate, and only a repository administrator
can apply them:

1. **Require a pull request before merging** -- otherwise a push bypasses
   every rule below.
2. **Require review from Code Owners** -- this is what makes a `CODEOWNERS`
   entry blocking rather than advisory.
3. **Require status checks to pass**, the check that runs `seal ci` among
   them -- without it, "every outcome test passes" is a claim nothing
   verifies before a merge.

Seal does not apply these: they live in a repository's settings rather
than its contents, and reaching them means a token with admin scope granted
to a tool that cannot verify from a checkout whether the settings took.
Report them to whoever administers the repository instead of trying.

A green `seal check` says the tree is **owned**, not that a merge is
**gated**. Never report the second on the strength of the first.

## CI

Seal ships the build-and-test pipeline as a composite action, so the
project's own CI file is boilerplate using it:

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
    # Bound by the calling job, which is what an action makes possible: the
    # secret below resolves against this Environment and reaches the action
    # as a value.
    environment: dev
    permissions:
      contents: read
    # An action's outputs belong to the step that ran it, so a job that
    # later jobs read through `needs.tests.outputs.*` re-exposes them.
    outputs:
      overlays: ${{ steps.seal.outputs.overlays }}
      results: ${{ steps.seal.outputs.results }}
      results_artifact: ${{ steps.seal.outputs.results_artifact }}
    steps:
      - uses: actions/checkout@v6

      - id: seal
        uses: vdel/seal/actions/ci@v0.3
        with:
          project_dir: my-project
          k8s_overlay: dev            # the shape the gate deploys
          publish_images: false
          # Only for a project whose `.env` files reach a password manager;
          # omit both for one holding literals and `k8s://` markers.
          provider_setup: |
            curl -fsSL https://example.invalid/install.sh | bash
            echo "$SEAL_PROVIDER_TOKEN" | its-cli login
          provider_token: ${{ secrets.PROTON_PASS_PERSONAL_ACCESS_TOKEN }}
```

The `seal` CLI needs no pin of its own: an action is checked out with its
own repository, so the CLI runs at whatever revision the `@ref` above names.
That leaves one ref to keep in step -- the root Tiltfile's
`v1alpha1.extension_repo(ref=...)`, which registers the same library's
Starlark half and has to name the same revision.

Note what is absent: the application's own variable and secret names.
`seal ci` resolves each service's `.env` directly, so this file never
enumerates them and never goes stale against them.

| Input | Meaning |
| --- | --- |
| `project_dir` | Path from the repository root to the project's root Tiltfile and services. Required. |
| `k8s_overlay` | Which overlay the gate deploys. Its run also executes each service's own tests, so it should be the shape the local loop brings up. Required. |
| `additional_k8s_overlays` | Further overlays to verify the promises against, as a JSON list -- `'["prod-like"]'`. Each runs the outcome suite alone, against runtime images. Empty by default. |
| `run_service_tests` | Whether the run on `k8s_overlay` executes each service's own tests -- `true` or `false`, `true` by default. Only that run can: a suite runs inside the service's container, so it exists only in images built at `--build_type test`, which this input decides. Off, that run builds what a real environment runs and reads the promises against it. |
| `run_outcomes` | Whether these runs read the promises -- `true` or `false`, `true` by default. Off, the run is each service's own tests and the readiness gate and nothing more, which is a check to have beside the merge gate rather than as it. It leaves `additional_k8s_overlays` nothing to verify, so naming both is refused. Off alongside `run_service_tests` the run reads nothing and gates on readiness alone, which is allowed for the emergency where that is the question. |
| `publish_images` | Whether to push the images built, once every gate has passed. Required. |
| `publish_k8s_overlay` | Which overlay the publishing run deploys. Required whenever `publish_images` is true; the run fails saying so rather than guessing. |
| `ref` | Branch or SHA to check out. Defaults to the triggering ref. |
| `provider_setup` | Shell run before `seal ci`, putting every CLI the project's `seal-credentials-config.json` names on `PATH` and authenticating it. `provider_token` reaches it as `$SEAL_PROVIDER_TOKEN`. Empty by default, and correct empty: a project whose `.env` files hold only literals and `k8s://` markers reaches no provider. |
| `provider_token` | The one credential `provider_setup` authenticates with. Passed by value, resolved against the Environment the calling job binds. Empty by default. |
| `submodules_token` | Read access for a private git submodule the checkout needs. `GITHUB_TOKEN` is scoped to the calling repository alone, so without it such a submodule fails to clone. Nothing about Seal needs it. |
| `credentials_env` | Which of the project's credentials environments the run reads -- which store each `.env` reference resolves against. Reaches `seal ci` as `SEAL_CREDENTIALS_ENV`. Left empty, the project's own `default_env` applies. Independent of `k8s_overlay` by design. |
| `results_artifact` | Name of the artifact the run uploads its results to; defaults to `tests-results`. A name has to be unique within a workflow run, so a repository using this action more than once names each use. |
| `results_artifact_url` | Where that artifact can be downloaded -- what a comment links so somebody can reach a recording. Empty when nothing was uploaded. |
| `results_retention_days` | How long that artifact is kept; defaults to 7. It exists for the caller's own reporting job to read in the same run. |

### What comes back

The action publishes nothing -- no check, no comment, no status, not even a
job summary. Which of those a project's results become is that project's own
policy, along with whichever action implements it and the write scopes that
action needs on their pull requests. So it hands back three outputs and
stops:

| Output | What it carries |
| --- | --- |
| `overlays` | The overlays this run verified, as a JSON list. Empty when the run died before it could say which shapes it was going to run, and `fromJSON('')` fails the job reading it -- so a caller guards on that. |
| `results` | What every run found, as one line of JSON keyed by overlay: `passed`, `cases`, `skipped`, `failed`, `problems`, one `sources` entry per service whose own tests came back, and an `outcomes` block holding every promise the tree declares. Read by the same two modules the gate's own verdicts came from, so it cannot disagree with the run. Failed test names are capped per source, with `failed_omitted` saying how many were left out; the failed count never is, and no promise is ever left out. |
| `results_artifact` | Name of the artifact holding the reports themselves, the reading as `results.json`, and a self-contained `index.html` page of both. Each service's own report is at `<overlay>/<service>/junit.xml` and each promise's directory at `<overlay>/outcomes/<group>/<epic>/<outcome>/`. Nothing is uploaded when a run produced no results, so a download step guards against a missing artifact. |

Each promise in `outcomes.promises` carries its `slug`, its prompt's
`headline`, whether it is `quarantined`, and one of four states: `PASS`,
`FAIL`, `no verdict` (it has a test and nothing knows whether it ran -- a
failure), or `no test yet` (nothing translated from it -- not a failure).
`outcomes.counts` counts them by state.

A promise that did **not** hold also carries `evidence`: what it left behind
to look at, each `path` relative to that run's results and so a path inside
the artifact. `kind` is `video`, `image`, `trace`, `page` or `log`. The
`playwright` runner records a video and a screenshot on failure, so a red
promise has one and a green one has nothing to show. The rendered
`index.html` plays them where they sit; a comment names the path and links
the archive, because a file inside a CI artifact has no address of its own.

`outcomes.read` is `false` where the run was asked not to read them
(`run_outcomes: false`): `promises` is empty and nothing in the results is a
claim about them. A run that never looked and a run whose every test failed
to write a verdict leave the same absence behind, so which it was is stated
rather than inferred.

A summary job reading `results` needs no permissions at all. For a comment
on the pull request, use Seal's own `report` action from a job of its own:

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
      - uses: vdel/seal/actions/report@v0.3
        with:
          results: ${{ needs.tests.outputs.results }}
          # Which comment a run replaces, so two projects gated in one
          # workflow keep a report each. Defaults to `default`.
          comment_key: my-project
```

It writes the rendering to that job's summary and keeps one comment on the
pull request current, replaced on every run -- ending with the head commit
it is about, since replacing it in place leaves nothing else to date it by.
Both can be turned off
(`comment`, `job_summary` -- compared as the strings `'true'`/anything
else). A pull request from a fork gets a read-only token whatever the job
declares, so there the action warns instead of failing.

A job publishing a check run instead downloads the artifact and gets
`checks: write` of its own -- never by widening what the job running the
gate grants.

### What an action changes about the caller

- **The calling job binds `environment:` itself**, and every `secrets.X` /
  `vars.X` it reads resolves against that Environment. The action receives
  values, never the name of a secret to look up.
- **Re-expose the outputs.** An action's outputs belong to the step that ran
  it; a job's belong to whatever `needs:` it. A later job fanning out over
  `overlays` or reporting from `results` needs the running job to declare
  them as its own.
- **`permissions:` is the calling job's.** An action runs under whatever
  that job has. The gate reads the repository and publishes nothing, so
  `contents: read` is enough for it; the reporting job above declares the
  `pull-requests: write` its comment needs, and nothing else does.
- **The CLI travels with the action**, at the revision it was used at. The
  one pin left is the project's root Tiltfile registering the Starlark half
  with `v1alpha1.extension_repo(ref=...)` -- the two halves are one library,
  so that ref and the action's have to name the same revision.

A provider's credential goes on the GitHub Environment (Settings →
Environments → `<name>` → Secrets), not as a repository secret -- one per
environment, each scoped to only what that environment should read. The
job reads it -- bound to that Environment -- and passes it as the action's
`provider_token` input, where it reaches `provider_setup` as
`$SEAL_PROVIDER_TOKEN`. The action never names the store, so what that token
opens is the project's business. It is optional: only a `.env` that actually
references a provider needs one.

## What the gate does not claim

It makes an outcome test un-editable without review. It says nothing about
whether those tests *ran* -- a gate over tests nobody executed is a gate over
nothing. Unattended merge needs both halves: every outcome test run in one
pass (`seal ci`), and every one of them un-editable without a human (this
page).

And running is not the same as covering. A suite reports every promise the
project has *translated*; a promise nobody has written a test from yet is
reported as exactly that rather than counted as kept.
