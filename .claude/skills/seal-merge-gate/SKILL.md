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

Seal ships the build-and-test pipeline as a reusable workflow, so the
project's own CI file is boilerplate pointing at it:

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
      python_dir: seal/python      # where Seal's own python/ is checked out
    secrets:
      PROTON_PASS_PERSONAL_ACCESS_TOKEN: ${{ secrets.PROTON_PASS_PERSONAL_ACCESS_TOKEN }}
```

Note what is absent: the application's own variable and secret names.
`seal ci` resolves each service's `.env` directly, so this file never
enumerates them and never goes stale against them.

| Input | Meaning |
| --- | --- |
| `project_dir` | Path from the repository root to the project's root Tiltfile and services. Required. |
| `k8s_overlay` | Which overlay the gate deploys. Its run also executes each service's own tests, so it should be the shape the local loop brings up. Required. |
| `additional_k8s_overlays` | Further overlays to verify the promises against, as a JSON list -- `'["prod-like"]'`. Each runs the outcome suite alone, against runtime images. Empty by default. |
| `publish_images` | Whether to push the images built, once every gate has passed. Required. |
| `publish_k8s_overlay` | Which overlay the publishing run deploys. Required whenever `publish_images` is true; the run fails saying so rather than guessing. |
| `gh_environment` | The GitHub Environment the job binds to -- protection rules and secret scoping. Not `credentials_env` below, which picks which store the project's `.env` references resolve against. Required. |
| `ref` | Branch or SHA to check out. Defaults to the triggering ref. |
| `runs_on` | Runner label; defaults to `ubuntu-latest`. Everything beyond a Linux machine with a reachable Docker daemon, the job installs itself. |
| `provider_setup` | Shell run before `seal ci`, putting every CLI the project's `seal-credentials-config.json` names on `PATH` and authenticating it. The `provider_token` secret reaches it as `$SEAL_PROVIDER_TOKEN`. Empty by default, and correct empty: a project whose `.env` files hold only literals and `k8s://` markers reaches no provider. |
| `credentials_env` | Which of the project's credentials environments the run reads -- which store each `.env` reference resolves against. Reaches `seal ci` as `SEAL_CREDENTIALS_ENV`. Left empty, the project's own `default_env` applies. Independent of `k8s_overlay` by design. |
| `python_dir` | Path from `project_dir` to Seal's checked-out `python/`. The `../../python` default resolves only for a project living inside a checkout of Seal itself. |
| `results_artifact` | Name of the artifact the run uploads its results to; defaults to `tests-results`. A name has to be unique within a workflow run, so a repository calling this workflow more than once names each call. |
| `results_retention_days` | How long that artifact is kept; defaults to 7. It exists for the caller's own reporting job to read in the same run. |

### What comes back

The workflow does not publish a report. How a project's results are presented
is that project's own policy -- along with whichever action implements it and
the write scopes that action needs on their pull requests -- so the workflow
hands back three outputs and stops:

| Output | What it carries |
| --- | --- |
| `overlays` | The overlays this run verified, as a JSON list. Empty when the run died before it could say which shapes it was going to run, and `fromJSON('')` fails the job reading it -- so a caller guards on that. |
| `results` | What every run found, as one line of JSON keyed by overlay: `passed`, `cases`, `skipped`, `failed`, `problems`, and one `sources` entry per directory the results came back in (each service under its own name, the outcome suite under `outcomes`). Read by the same `junit.py` the gate's own verdict comes from, so it cannot disagree with the run. Failed test names are capped per source, with `failed_omitted` saying how many were left out; the failed count never is. |
| `results_artifact` | Name of the artifact holding the reports themselves, as `<overlay>/<service>/junit.xml` -- what to download to feed an action that wants XML, or the coverage `results` does not carry. Nothing is uploaded when a run produced no results, so a download step guards against a missing artifact. |

A summary job reading `results` needs no permissions at all. A job publishing
a check or a pull-request comment downloads the artifact and gets
`checks: write` / `pull-requests: write` of its own -- never by widening what
the caller grants the reusable workflow.

### Three GitHub Actions quirks

Each one fails quietly, and none is obvious from GitHub's documentation:

- **A job that calls a reusable workflow cannot also set `environment:` on
  itself** -- GitHub rejects the whole file. Hence `gh_environment` as a
  plain input. The consequence: every `vars.X` in the caller resolves at
  repository or organisation scope.
- **`secrets.X` does not follow that rule.** An environment-scoped secret
  reaches a reusable-workflow job only if the caller also names it in its own
  `secrets:` block -- even though the value the caller passes is empty. Drop
  the passthrough and it silently arrives empty.
- **A reusable-workflow job only gets the `permissions:` its caller
  declares.** Where the default `GITHUB_TOKEN` is read-only, the block must
  cover whatever the callee requests or the run fails at startup with zero
  jobs scheduled. `seal-ci.yml` requests `contents: read` and nothing else.

A provider's credential goes on the GitHub Environment (Settings →
Environments → `<name>` → Secrets), not as a repository secret -- one per
environment, each scoped to only what that environment should read. The
caller passes it as the reusable workflow's `provider_token` secret, and it
reaches `provider_setup` as `$SEAL_PROVIDER_TOKEN`; the workflow never
names the store, so what that token opens is the project's business. It is
optional: only a `.env` that actually references a provider needs one.

The passthrough matters as much as the value. A reusable-workflow job
resolves an Environment-scoped secret only if the caller names it in its own
`secrets:` block -- omit it and the value silently arrives empty even with
the secret correctly set.

## What the gate does not claim

It makes an outcome test un-editable without review. It says nothing about
whether those tests *ran* -- a gate over tests nobody executed is a gate over
nothing. Unattended merge needs both halves: every outcome test run in one
pass (`seal ci`), and every one of them un-editable without a human (this
page).

And running is not the same as covering. A suite reports every promise the
project has *translated*; a promise nobody has written a test from yet is
reported as exactly that rather than counted as kept.
