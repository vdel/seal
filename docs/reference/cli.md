# CLI reference

One command is installed: `seal`. See
[Installation](../installation.md#installing-the-seal-cli).

```
Usage: seal run -- <cmd> [args...]  |  seal up [tilt-up args...]  |
       seal ci [tilt-ci args...]  |
       seal check [--credentials_env ENV] [--k8s-dir DIR] [--outcomes-dir DIR]  |
       seal outcomes [--outcomes-dir DIR] [--untranslated]  |
       seal outcomes run [--outcomes-dir DIR] [--results-dir DIR] [--reset] [--all]
                         [--confirm] [slug...]  |
       seal outcomes translate [--outcomes-dir DIR] [--rewrite] <slug>  |
       seal outcomes review [--outcomes-dir DIR] <slug>  |
       seal outcomes touched [--outcomes-dir DIR] [--since REF]  |
       seal outcomes loop [--outcomes-dir DIR]
```

Every subcommand finds the **project root** by walking up from the current
directory looking for one with both its own `Tiltfile` and a `services/`
subdirectory.

---

## `seal run`

```sh
seal run -- <cmd> [args...]
```

Runs an arbitrary command with the current service's `.env` resolved into
its environment. Run it from inside `services/<name>/`, or a subdirectory of
one -- that's how it works out which service you mean.

```sh
cd services/api
seal run -- uv run python src/manage.py migrate
seal run -- uv run pytest tests/
```

`k8s://`-marked keys are dropped (the manifests supply those), and every
remaining value is resolved: a literal as itself, a `<scheme>://<item>`
reference through whichever provider the project declares for that scheme,
against the store its `environments` map names for this run's credentials
environment. A `.env` of literals and `k8s://` markers reaches no provider
and needs no CLI installed.

See [Credentials](../guides/credentials.md#seal-run----cmd).

---

## `seal up`

```sh
seal up [tilt-up args...]
```

From the project root. Resolves every service's `.env` and fills the
Kubernetes objects the overlay annotates, then execs `tilt up`, forwarding
every argument exactly as passed.

Use this instead of `tilt up`. A bare `tilt up` does not refuse -- it
deploys those objects unfilled, so containers start without their
credentials.

`seal up` runs **no** checks: a half-finished manifest should not stand
between you and your cluster.

Common Tilt flags to pass through:

```sh
seal up -- --k8s_overlay stag        # deploy k8s/stag/ instead of the project's default
```

---

## `seal ci`

```sh
seal ci [tilt-ci args...]
```

CI's equivalent of `seal up`, and the whole gate in one command:

1. Runs `seal check` -- all five rules. Refuses to start if any fails.
2. Resolves every service's credentials and fills the objects the overlay
   annotates, exactly as `seal up` does.
3. Sets [`SEAL_CI`](environment-variables.md#seal_ci), which is how it says
   that this run's result is a verdict.
4. Execs `tilt ci`, forwarding every argument.

The suite is not a fifth step here: step 4 replaces this process, so what
runs it is the Tilt session, whose outcome resource reads that signal and
starts on its own. Which is why `seal up` gets no suite and a plain `tilt
ci`, started without the CLI, gets none either.

```sh
seal ci -- --build_type test
seal ci -- --k8s_overlay prod-like --build_type runtime
seal ci -- --publish_images --run_outcomes false   # build and push, no verdict
```

`--run_outcomes true`/`false` overrides the signal either way, for a run that
knows better than the command that started it.

It exits successfully only once Tilt reports **every** resource ready --
the outcome suite among them, wherever this run reads the promises. That is
what makes it usable as a merge gate.

Because every argument is handed straight to `tilt ci`, `seal ci` has
no flags of its own -- which is why `SEAL_K8S_DIR` and
`SEAL_OUTCOMES_DIR` are environment variables.

---

## `seal check`

```sh
seal check [--credentials_env ENV] [--k8s-dir DIR] [--outcomes-dir DIR]
```

From the project root. Statically checks five things a `seal ci` run's
claims rest on. Every offender is reported at once, so you put things right
in one pass.

**Readiness.** Every Deployment your overlays deploy declares a
`readinessProbe` on every container -- or "everything is ready" means less
than it says. Each overlay under `./k8s` (or `$SEAL_K8S_DIR`, or
`--k8s-dir`) is built with kustomize and what comes out is what's checked,
so a finding names the overlay rather than a file. See [Declaring your
services](../guides/project-layout.md#readiness-and-what-seal-ci-refuses-to-start-without).

**Declared credentials.** Every service's `.env` matches what the project
declared in `seal-credentials-config.json`, without resolving anything: no
value names a scheme nothing declares, no declared provider that some
`.env` reaches is left with no mapping for the selected environment, and no
value carries a `${` a project meant to expand. The environment is selected
the same way `seal run`/`up`/`ci` select one -- `--credentials_env`, then
`SEAL_CREDENTIALS_ENV`, then the project's own `default_env`. See
[Credentials](../guides/credentials.md).

**A pod's environment.** Every key a service's `.env` declares has a source
in every overlay: an object a container reads through `envFrom` that supplies
it, or an explicit `env:` entry naming it. A container whose sources account
for nothing for a key its service needs starts without it and finds out
wherever the application first reads it. Which container belongs to which
service comes from the `seal-test.dev/fill-from` annotation on an object it
reads, not from a name. Like the readiness check, this walks every overlay --
the same container can be correctly provisioned in the shape you work in and
short a value in the shape that ships. It reads names and key sets, never
that a store holds a value.

**The outcome tree.** Every test sits beside the prompt it was translated
from, every group is behind a runner that can start it, and no translation
waits on the clock -- or "every outcome test passes" is a claim about tests
nobody can review the intent of, that nothing ever ran, or that a slow
browser can turn red. Read from `./outcomes`, or `$SEAL_OUTCOMES_DIR`, or
`--outcomes-dir`. See
[Outcome tests](../guides/outcomes.md#what-seal-check-refuses).

**CODEOWNERS.** The repository's `CODEOWNERS` covers that tree -- or a green
suite is a gate anything can walk through by editing the test that failed.
Read from wherever the platform itself would read it, in the enclosing
repository. See [The merge gate](../guides/merge-gate.md).

`seal ci` runs all five itself before starting Tilt, so a project gets
them without opting in. A project with no `seal-credentials-config.json`,
or whose `.env` files reference no provider, passes the credentials check
silently; one with no outcome tree passes the outcome-tree and CODEOWNERS
checks silently.

---

## `seal outcomes`

```sh
seal outcomes [--outcomes-dir DIR] [--untranslated]
```

Lists every outcome the project declares -- its slug, whether a test has
been translated from its prompt yet, and the prompt's own headline.

```
ui/todo-list/an-item-survives-a-reload  translated   an item I add is still on the list after a reload
ui/todo-list/deleting-is-permanent      no test yet  deleting an item takes it off the list for good

2 outcome(s), 1 translated.
```

`--untranslated` narrows that to the promises nothing has been written from,
as bare slugs, one per line:

```
ui/todo-list/deleting-is-permanent
```

That's the machine-readable form, and its caller is `seal outcomes
translate`, a promise at a time.

---

## `seal outcomes run`

```sh
seal outcomes run [--outcomes-dir DIR] [--results-dir DIR] [--reset] [--all] [--confirm]
                  [slug...]
```

**With no slugs**: the whole suite's verdict, read from what every outcome's
test container left behind. Every outcome at once, deliberately -- a fix
scoped to one test can break another nobody re-ran. This is what `seal
ci` gates on, and the exit code is the suite's verdict.

**With slugs**: runs those outcomes now, against a session already up, and
reports only them. The local loop somebody iterating on one translation
wants, and never what a merge rests on. An outcome is named
`<group>/<epic>/<outcome>`.

**With `--all`**: runs every promise the tree holds now, against that same
session, and reports all of them. It leaves nothing out, so it carries no
caveat -- the suite's own claim, about a run this command performed rather
than one it found, which the summary says. This is what a regression loop
re-runs each iteration, without paying for a fresh cluster every time.
`--all` and naming slugs are different asks and cannot be combined.

**With `--confirm`**: every promise that failed is run again, on its own,
from a reset, and the listing says whether that reproduced -- `FAIL
(confirmed)` or `FAIL (not confirmed)`. It changes no verdict: an unconfirmed
failure still fails the run and is never reported as a pass. The failing
run's results are kept beside the confirmation's, under the outcome's own
directory name with `.first-run` appended. See [Confirming a failure before
anything acts on
it](../guides/outcomes.md#confirming-a-failure-before-anything-acts-on-it).

```sh
seal outcomes run                                          # the whole suite's verdict, read
seal outcomes run --reset --all                            # the whole suite, run now
seal outcomes run --reset --all --confirm                  # ... and re-run what failed
seal outcomes run ui/todo-list/a-deleted-item-stays-deleted
seal outcomes run --reset ui/todo-list/a-deleted-item-stays-deleted
```

A slug that names nothing is an error listing the ones that exist, rather
than a run of no outcomes.

`--results-dir` overrides where results are read from; it defaults to
`tests-results`.

`--reset` puts every service that declared a reset back to its baseline
before the run, waiting for each -- what makes one run comparable to the
next. Without it the run takes the environment as it stands, including
whatever the run before it left in it; it is asked for rather than assumed
because a session somebody is working in is one whose state they may be
looking at. It needs outcomes to run: with no slugs this reads verdicts a
run already left behind and starts nothing, so there is nothing for a reset
to come before -- pass `--all` to run them. See [Running one outcome while
you work](../guides/outcomes.md#running-one-outcome-while-you-work).

### Verdicts

| | |
| --- | --- |
| `PASS` / `FAIL` | The test ran and said so. |
| `no verdict` | A translated outcome left nothing to read. A **failure**. |
| `no test yet` | A promise nothing has been translated from. Not a failure. |
| `(confirmed)` | Under `--confirm`: it failed again on its own, from a reset. |
| `(not confirmed)` | Under `--confirm`: it held on its own. Still a failure. |
| `(quarantined)` | The outcome declares a `quarantine.md`. Reported, never counted as passed, and does not fail the run. |

---

## `seal outcomes translate`

```sh
seal outcomes translate [--outcomes-dir DIR] [--rewrite] <slug>
```

Everything needed to compile one promise into a low-level test: the prompt
in full, the directory the translation goes in, whichever runner its group
declares, and what the result has to satisfy. Prose on stdout.

Seal poses the task and checks the answer. It writes nothing and
starts no agent.

An outcome that already has a translation needs `--rewrite`: a replacement
and a first authorship are both reviewed by a human, but they are different
things to review.

See [Translating a promise](../guides/translating-promises.md).

---

## `seal outcomes review`

```sh
seal outcomes review [--outcomes-dir DIR] <slug>
```

One translation and the promise it claims to encode, side by side, plus what
has already been settled mechanically -- so the review is spent on intent.

A promise with no translation yet is refused rather than reviewed.

---

## `seal outcomes touched`

```sh
seal outcomes touched [--outcomes-dir DIR] [--since REF]
```

Every path under the outcome tree this change reaches -- staged, unstaged
and untracked alike -- and a non-zero exit where there is one.

`--since` defaults to where this branch left the repository's default
branch, so what it answers is "has this *change* touched a promise?" rather
than "is there anything uncommitted". Name a ref to measure from somewhere
else.

It **reports**; `CODEOWNERS` is what enforces. Touching the tree is an
ordinary thing to do -- a translation has to be written, a promise has to be
able to change -- and what it costs is a code owner's approval, which is to
say that the change can no longer merge unattended. That is worth knowing in
the round it happened rather than in a review nobody was expecting, which is
the whole of why this exists. See [Getting a red outcome suite back to
green](../guides/regression-loop.md).

---

## `seal outcomes loop`

```sh
seal outcomes loop [--outcomes-dir DIR]
```

The regression loop this project is in: the rounds of the whole suite since
the last one in which every promise held, what each one fixed and what that
cost, what's still red, and whether there's a reason to stop.

A loop is *derived*, not declared -- it's read off the record each run of the
suite appends under `.workspace/seal/`. Nothing starts one and nothing
finishes one. A run naming outcomes isn't a round of it (it says nothing
about the promises it left out), and a quarantined promise isn't red in it
(the run itself didn't fail on one).

Two reasons to stop:

- **A cycle**: a promise fixed and then broken again inside this loop.
- **The backstop**: the rounds or minutes declared in
  [`seal-test-config.json`](../guides/runners.md#loop-where-a-regression-loop-stops),
  or Seal's defaults.

Exits `1` where there is one and `0` otherwise, including for a loop that's
getting somewhere and for no loop at all. That's not a verdict on the suite
-- `seal outcomes run` is -- and it changes nothing about one: a
reason to stop is a reason attached to a report, never a gate. A failing
round of the whole suite says the same thing in passing, so a loop finds out
in the round it happened.

See [Getting a red outcome suite back to
green](../guides/regression-loop.md#where-to-stop).

---

## Exit codes

`0` on success; `1` on any failure, with the reason on stderr. `seal
outcomes run`'s exit code is the suite's own verdict, which is what lets CI
gate on it.
