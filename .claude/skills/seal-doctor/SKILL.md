---
name: seal-doctor
description: Diagnose a failure in a Seal project from its error message -- not inside a seal project, a container that starts without its credentials, a value naming a scheme no provider declares, seal ci refusing to start over readinessProbe, an outcome reported no verdict or no test yet, a rejected waitForTimeout, a group or runner seal check complains about, a name too long for Kubernetes, or a test that passes alone and fails in the suite. Use whenever a seal, tilt or outcome-suite command fails and the cause is not immediately obvious.
---

# Diagnosing a Seal failure

Read the message first: Seal fails loudly and names the offender, and
`seal check` reports every offender at once rather than one failed run
at a time.

## Getting started

**`not inside a seal project`** -- `seal up`, `ci` and `run`
walk up looking for a directory with **both** a `Tiltfile` and a `services/`
subdirectory. The outcome commands and `seal check` also accept a
directory holding the outcome tree, so a project that states promises and
brings nothing up is one of those and not the others. Run it from inside a
directory that is what the command needs.

**`not inside a service directory`** -- `seal run` works only from inside
`services/<name>/`, because that is how it knows which `.env` is meant. From
the project root, `seal up` is the command.

**`Tiltfile not found`** (from `tilt`, not `seal`) -- the project has
no root Tiltfile. See `seal-add-service`.

## Credentials

**A container starts, then fails on a missing setting** (or its readiness
probe never passes) -- the object it reads was deployed unfilled. Seal
fills the objects an overlay annotates just before Tilt starts, so `tilt up`
or `tilt ci` run *directly* deploys the stub with no `data` in it. Run
`seal up`/`seal ci` instead. The same symptom after editing a
`.env` means the session needs stopping and `seal up` re-running.

**A key reaches no container** -- `seal check` names it:
`Deployment '<name>', container '<name>' reads <service>'s credentials but
has no source for '<KEY>'`. Either the container's `envFrom` does not list
the object claiming that key, or no object in that overlay claims it. An
overlay that splits a service across objects has to repoint *every*
container reading it, not just one.

**`<KEY> names '<scheme>', which no provider declares`** -- the `.env`
references a store the project has not declared. Add it to
`seal-credentials-config.json`, or fix the scheme.

**`<KEY> names '<value>', which contains '${'`** -- rejected on purpose. A
reference names an item; which store holds it is the declaration's
`environments` map, not text interpolated into the value.

**`<provider> declares no store for '<env>'`** -- the run selected a
credentials environment the declaration does not map. The message lists the
ones it does declare. Its sibling, **`<provider> reads a different store per
environment, and ...`**, means no environment was selected at all: pass
`--credentials_env`, set `SEAL_CREDENTIALS_ENV`, or give the config a
`default_env`.

**`'<cli>' not found on PATH`** -- install the CLI the declaration names; the
message carries its `install_hint`. It is needed only if a `.env` in use
actually references that provider's scheme. In CI, the `provider_setup` step
did not run or failed.

**A provider cannot resolve an item, or is not logged in, in CI** -- check
four things, in this order: the run selected the environment you think
(`--credentials_env`, else `SEAL_CREDENTIALS_ENV`, else `default_env`
-- and it is independent of `--k8s_overlay`); the declaration maps that
provider for that environment; the token is set on the **GitHub Environment**
rather than as a repository secret; and the job running the action binds that
`environment:` -- `provider_token` is read in the caller's own job, so
without the binding it resolves at repository scope and silently arrives
empty. There is deliberately no fallback -- this same `.env` is what
production resolves.

## Bringing an environment up

**A service just added does not show up in Tilt** -- the root Tiltfile does
not `include()` it. Tilt re-evaluates the whole Tiltfile from scratch every
run, so there is nothing stale to clear.

**`seal ci` refuses to start, naming an overlay's Deployments** -- every
Deployment container needs a `readinessProbe`, or "every resource is ready"
means less than it says. An HTTP endpoint where there is a server, a command
where there is not. The overlay is named because a container can be fine in
one shape and missing a probe in another; all offenders are listed, so fix
them in one pass.

**`seal check` says an overlay will not build** -- kustomize refused
it, and the error it gave follows. A shape that cannot be built is a shape
nothing can deploy, so this fails the check rather than being skipped past.

**`seal_tests_verdict_<service>` says no JUnit report, or no test cases**
-- that service's results came back with nothing in them saying its tests
ran, which Seal reads as a failure rather than a pass. Its `test_command`
has to leave a JUnit report inside the `junit_tests_directory` declared for
it. A runner that collected nothing writes a valid, empty report; an empty
suite is not a green one. `seal_tests_run_<service>`'s own output says
what the command did, and `tests-results/<service>/` holds whatever came
back.

**`no results came back from the test container`** -- the syncback found
nothing to copy, so the container never started or was killed before writing
anything. That service's own resource is upstream of this one; look there
first.

**`seal ci` fails where `seal up` worked** -- that is the
design. `seal up` runs none of the checks, so a half-finished manifest
does not stand between somebody and their cluster. `seal check` shows
what `seal ci` would refuse.

## Outcome tests

**An outcome is reported `no verdict`** -- the test ran, or was meant to, and
left nothing at `/outcome-results/<epic>/<outcome>/passed`. **This is a
failure, not a gap.** Usual causes: the runner exited before reaching that
outcome (a container that exits non-zero takes its resource down with it), or
a `custom` runner is not writing the verdict file. Under a `tap` group it
means no test point named that outcome -- the run stopped before reaching it,
or the point carried a `# SKIP` or `# TODO`, neither of which establishes
anything. Look in `tests-results/outcomes/<group>/<epic>/<outcome>/` and at
the runner's logs, then re-read the runner contract in `seal-outcome`.

**An outcome is reported `no test yet` but the test is right there** -- the
group's runner cannot start what is in the directory. Under `playwright`
that means no file it collects (`*.spec.ts`, `*.test.ts`, or the
`.js`/`.tsx` spellings) at any depth under the outcome. `seal check`
refuses exactly this, because the suite alone would report the promise as
untested while the test sits in the tree.

**A `tap` group's `run` will not start** -- `seal check` refuses a
`tap` group with no `run` at its root, and one whose `run` is not
executable. The second is the one people hit, since git records the bit:
`chmod +x outcomes/<group>/run` and
`git update-index --chmod=+x` it. Nothing could start the group otherwise,
and every promise under it reads as untested.

**A `tap` runner's points name outcomes the run did not ask about** --
Seal matches each point's description against the slugs it passed
after `--`, spelled from inside the group (`<epic>/<outcome>`, not
`<group>/<epic>/<outcome>`). Echo the slug handed to the runner rather than
composing one.

**`seal check` refuses something under `helpers/`** -- a group's
`helpers/` holds what its tests share, so nothing walks it for outcomes and
a `playwright` run never looks inside it. A `prompt.md` there is a promise
no run would start (`helpers` is not a name an epic can have); a spec file
there is a test nothing collects. Move the first under an epic of its own,
the second into the outcome it tests.

**`seal check` complains about a group or runner** -- the two ways the
tree and `seal-test-config.json` drift apart: a group directory no
runner names, or a runner naming a group that is not there.

**`seal check` refuses `waitForTimeout`** -- a sleep, in a test or in a
helper it imports, holds on the machine it was written on and fails wherever
the browser is slower. Wait on the
state instead: `expect(locator).toBeVisible()` or `locator.waitFor()`.

**`seal outcomes run <slug>` says the session is not up** -- naming
outcomes runs them against a session `seal up` already has running.
Start one first.

**A test passes alone and fails in the suite** -- outcomes run one at a time
against the same application, each starting from whatever the one before it
left. A full run resets each service that declared one *before* the run, not
between outcomes. Write the test to own the data it asserts on, or trigger
the reset yourself.

**An outcome's Kubernetes name is too long** -- a generated name is
`seal-outcome-<epic>-<outcome>` and Kubernetes allows 63 characters.
Seal fails rather than shortening it: two outcomes silently sharing
one Deployment is worse than being told to rename a directory.

## The merge gate

**`seal check` says an outcome is not covered by CODEOWNERS** --
either no rule matches it, or the last one that does names no owner. The
last matching rule wins, not the most specific, and a rule with no owners
clears ownership. Cover the directory, not the files.

**`seal check` passes but changes still merge without review** -- a green
check says the tree is *owned*, not that a merge is *gated*. Branch
protection is the other half, and only a repository administrator can apply
it. See `seal-merge-gate`.

## When none of these fit

The RFCs at <https://github.com/vdel/seal/tree/main/rfcs> cover the
reasoning behind each rule, which is often what is actually being
asked when a rule seems surprising. Report what failed, what was run, and
which directory under `tests-results/` holds the evidence -- rather than
working around the rule.
