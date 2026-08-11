# Troubleshooting

The errors you're most likely to hit, and what each one means.

## Getting started

### `not inside a seal project`

`seal` walks up from your current directory looking for one with
**both** a `Tiltfile` and a `services/` subdirectory. Run it from inside
such a directory -- for the bundled example, `examples/angular-django/`.

### `not inside a service directory`

`seal run` only works from inside `services/<name>/`, because that's
how it knows which service's `.env` you mean. From the project root, you
want `seal up` instead.

### `Tiltfile not found` (from `tilt`, not `seal`)

Your project has no root `Tiltfile`. See [Declaring your
services](../guides/project-layout.md#your-root-tiltfile-is-the-service-list).

## Credentials

### A container starts without its credentials

Symptoms: a readiness probe that never passes, or an application error about
a setting it was configured to require. The object the container reads was
deployed empty.

You ran `tilt up` or `tilt ci` directly. Seal fills the objects your
overlay annotates just before Tilt starts, and a bare `tilt` run does not
refuse -- it deploys the annotation without the values, so the failure
surfaces well away from its cause. Run `seal up`/`seal ci`
instead.

The same symptom after editing a `.env`: re-run `seal up` (`Ctrl-C`
the running session first) to refill.

### A key reaches no container

`seal check` names it:

```
overlay '<name>': Deployment '<name>', container '<name>' reads <service>'s
credentials but has no source for '<KEY>'.
```

Either that container's `envFrom` does not list the object claiming the key,
or no object in that overlay claims it. An overlay that splits a service
across several objects has to repoint *every* container that reads it, not
just one.

### `'<cli>' not found on PATH`

Install the CLI your `seal-credentials-config.json` names. The message
carries that provider's own `install_hint`, so it tells you where to get it.

It's only needed if a `.env` you're using actually references that
provider's scheme -- a project whose values are all literals and `k8s://`
markers never reaches for a store at all, and needs no CLI installed.

In CI, this means your `provider_setup` step didn't run or failed.

### A provider can't resolve an item, or isn't logged in (in CI)

Check four things:

1. The run selected the credentials environment you think --
   `--credentials_env`, else `SEAL_CREDENTIALS_ENV`, else the config's
   `default_env`. It is independent of `--k8s_overlay`.
2. `seal-credentials-config.json` maps that provider for that
   environment. `seal check` says so by name if it does not.
3. Your provider's token is set on the **GitHub Environment** this job bound
   to, not as a repository secret, and the caller passes it as the reusable
   workflow's `provider_token`.
4. Your caller workflow names that secret in its own `secrets:` block --
   without the passthrough it silently arrives empty. See
   [the three quirks](../guides/continuous-integration.md#three-github-actions-quirks).

There is deliberately no fallback here: this same `.env` is what production
resolves too.

## Bringing an environment up

### A service you just added doesn't show up in Tilt

Check your root Tiltfile actually `include()`s it. Tilt re-evaluates the
whole Tiltfile from scratch on every run, so there's nothing stale to clear.

### `seal ci` refuses to start, naming Deployments

Every Deployment container needs a `readinessProbe`, or "every resource is
ready" means less than it says. Add one per container -- an HTTP endpoint
where there's a server, a command where there isn't. See
[Readiness](../guides/project-layout.md#readiness-and-what-seal-ci-refuses-to-start-without).

Every offender is reported at once, so you can fix them in one pass.

### `no JUnit report was written to ...`, or `the JUnit report holds no test cases`

From `seal_tests_verdict_<service>`: that service's results came
back, but nothing in them says its tests ran. Seal reads the JUnit
report and nothing else, so this is a failure rather than a pass.

Check, in this order:

1. Your `test_command` actually writes a JUnit report (`pytest
   --junit-xml=...`, karma-junit-reporter, `--reporter junit`).
2. It writes it *inside* the `junit_tests_directory` you declared.
3. The suite collected something. A runner that found no tests writes a
   valid, empty report, and an empty suite is not a green one.

`seal_tests_run_<service>` in the Tilt UI shows what the command
actually did, and `tests-results/<service>/` holds whatever came back.

### `no results came back from the test container`

The syncback found nothing to copy: the container never started, or was
killed before its results were written. Look at that service's own resource
in the Tilt UI first -- this resource is downstream of it.

### `seal ci` fails but `seal up` works

That's the design: `seal up` runs none of the checks, so a
half-finished manifest doesn't stand between you and your cluster. Run
`seal check` to see what `seal ci` would refuse.

## Outcome tests

### An outcome is reported `no verdict`

The test ran, or was meant to, and left nothing to read at
`/outcome-results/<epic>/<outcome>/passed`. **This counts as a failure, not
a gap** -- every way a test silently fails to run looks like an absent file
from here.

Usual causes: the runner exited before reaching that outcome (a container
that exits non-zero takes its resource down with it), or a `custom` runner
isn't writing the verdict file. Under a `tap` group it means no test point
named that outcome -- because the run stopped before reaching it, or because
the point carried a `# SKIP` or `# TODO`, neither of which establishes
anything. Check
`tests-results/outcomes/<group>/<epic>/<outcome>/` and the runner's logs,
and re-read the contract its runner meets --
[a container's](../guides/runners.md#the-contract-a-container-runner-meets),
or [a `tap` group's](../guides/runners.md#what-your-run-has-to-do).

### A `tap` group's `run` won't start

`seal check` refuses a `tap` group with no `run` at its root, and one
whose `run` isn't executable. The second is the one people hit: git records
the executable bit, so a file that is plainly there can still be unable to
start.

```sh
chmod +x outcomes/<group>/run
git update-index --chmod=+x outcomes/<group>/run
```

Nothing could start the group otherwise, and every promise under it would be
reported untested for a reason no listing explains.

### A `tap` runner's points don't match the outcomes it was given

Seal matches each test point's description against the slugs it passed
after `--`, spelled from inside the group (`<epic>/<outcome>`, not
`<group>/<epic>/<outcome>`). A point naming anything else is reported against
the run and files no verdict, and a promise no point named keeps `no verdict`.

Echo the slug you were handed rather than composing one: `ok 1 - $slug`.

### An outcome is reported `no test yet` but there's a test right there

The group's runner can't start what's in the directory. Under `playwright`
that means no file it collects -- `*.spec.ts`, `*.test.ts`, or the `.js`
/`.tsx` spellings -- at any depth under the outcome.

`seal check` refuses exactly this case, because the suite on its own
would report the promise as untested while the test sits in the tree.

### `seal check` refuses something under `helpers/`

A group's `helpers/` holds what its tests share, so nothing walks it for
outcomes and a `playwright` run never looks inside it. Two things filed
there would therefore go unnoticed, and both are refused instead: a
`prompt.md`, which is a promise no run would start (`helpers` is not a name
an epic can have), and a spec file, which is a test nothing collects. Move
the first under an epic of its own; move the second into the outcome it
tests, or rename it for what it is if the tests import it.

A `helpers/` at the *tree's* root is refused for a different reason: a runner
is built from one group's directory, so nothing above it is in the image that
has to import it. Keep one per group, or point a `custom` runner's
`dockerfile_context` at a directory holding both groups. See
[Helpers](../guides/outcomes.md#helpers-what-a-groups-tests-share).

### `seal check` complains about a group or runner

The two ways the tree and `seal-test-config.json` drift apart: a group
directory no runner names, or a runner naming a group that isn't there.
That's the one thing about the tree a walk can't answer, so it's the one
thing that has to be declared -- and therefore the one thing that can go
stale. See
[`seal-test-config.json`](../guides/runners.md#seal-test-configjson).

### `seal check` refuses `waitForTimeout`

A sleep in an outcome test -- or in a helper it imports, where every outcome
importing it inherits the wait -- holds on the machine it was written on and
fails wherever the browser is slower. Wait on the state instead --
`expect(locator).toBeVisible()` or `locator.waitFor()` retries until it
holds, and gives up only when it never does. See [Wait on the
state](../guides/translating-promises.md#wait-on-the-state-never-on-the-clock).

### `seal outcomes run <slug>` says the session isn't up

Naming outcomes runs them against a session `seal up` already has
running. Start one first.

### A test passes alone and fails in the suite

Outcomes run one at a time against the same application, each starting from
whatever the one before it left. A full run resets each service that
declared one *before the run*, not between outcomes -- so write the test to
own the data it asserts on. See
[Deterministic test state](../guides/resetting-state.md).

`seal outcomes run --reset --all --confirm` is what finds this without
guessing: it re-runs each failure on its own, from a reset, and reports
`FAIL (not confirmed)` where the promise then held.

### An outcome's Kubernetes name is too long

A generated name is `seal-outcome-<epic>-<outcome>`, and Kubernetes
allows 63 characters. Seal fails loudly rather than shortening it: two
outcomes silently sharing one Deployment is worse than being told to rename
a directory.

## Getting back to green

### `--reset needs outcomes to run`

`seal outcomes run` with nothing named reads the verdicts a run
already left behind and starts nothing -- that's the form `seal ci`
gates on, and there's nothing there for a reset or a confirmation to come
before. Add `--all` to run every promise now, against a session `seal
up` already has up. The same message appears for `--confirm`.

### `--all runs every promise the tree holds, so there is nothing for a slug to add`

`--all` and naming outcomes are different asks, and there's no reading of the
pair that isn't a guess -- one of the two would report a subset under a flag
that says otherwise. Pick one.

### An outcome is reported `FAIL (not confirmed)`

It failed in the run and then held on its own, from a reset. **Nothing you
change in the application will settle it.** It's one of two things:

- the test doesn't own the data it asserts on -- it passed behind a different
  outcome than it expected;
- the test isn't deterministic -- most often it asserts before something has
  rendered.

Both are the translation's to fix, so both need a code owner. It still fails
the run, and is never reported as a pass: the suite didn't see that promise
kept. See [Getting back to
green](../guides/regression-loop.md#when-it-isnt-the-application).

### `seal check` refuses a quarantine with no reason

A `quarantine.md` says a failure doesn't fail the run. One with nothing
written in it is indistinguishable from a test somebody switched off, and the
code owner approving the diff is who has to tell those apart. Say what is
being fixed and what would let the promise come back to the gate.

### `seal outcomes touched` names paths and exits non-zero

That's it telling you the change reaches the outcome tree, which means it
can't merge unattended any more -- a code owner has to approve every path it
named. That isn't a mistake in itself: a promise has to be able to change,
and a translation has to be written. It *is* a mistake if what you meant to
write was an application fix, in which case the fix isn't there yet.

### `nothing to compare against` from `seal outcomes touched`

It measures a change from where your branch left the repository's default
branch, and it looks for `origin/HEAD`, `origin/main`, `main` and `master`
in that order. A repository with none of those -- a fresh checkout with no
commits, or a differently-named trunk -- needs the ref naming: `seal
outcomes touched --since <ref>`.

## The merge gate

### `seal check` says an outcome isn't covered by CODEOWNERS

Either no rule matches it, or the last one that does names no owner.
Remember that **the last matching rule wins**, not the most specific, and
that **a rule with no owners clears ownership**. A bare `*.py` line anywhere
below your tree's rule silently unlocks every Python test in it.

Cover the directory, not the files: that's what covers files added to it
later.

### `seal check` passes but changes still merge without review

A green `seal check` says the tree is *owned*, not that a merge is
*gated*. `CODEOWNERS` on its own assigns reviewers and lets a pull request
merge unreviewed. Branch protection is the other half, and only a repository
administrator can apply it. See [The half Seal can't
check](../guides/merge-gate.md#the-half-seal-cant-check).
