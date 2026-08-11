---
name: seal-dev-loop
description: The local loop in a Seal project -- bring the stack up with seal up, edit, put a service's state back with its reset trigger, run one outcome against the running session, and run a single service's own tests or management commands through seal run. Use when asked to start, run, restart or tear down the app, to reproduce something locally, to iterate on a change, or when a session is already up and something needs re-running.
---

# The local loop

## Bring it up

From the project root:

```sh
seal up                            # tilt up, with credentials resolved first
seal up -- --k8s_overlay stag      # arguments after -- go straight to Tilt
```

`seal up` resolves every service's `.env`, fills the Kubernetes
objects the overlay annotates, and then starts Tilt. **Never run `tilt up`
directly**: it does not refuse, it deploys those objects unfilled, so
containers come up without their credentials and the failure surfaces well
away from its cause.

It runs none of the static checks, on purpose: a half-finished manifest
should not stand between somebody and their cluster. `seal check` is
there to be run deliberately.

The session is long-lived and interactive. Start it in the background, or
ask the user to, rather than blocking on it; Tilt keeps rebuilding and
re-deploying as files change, so there is nothing to re-run after an edit
except the tests.

Editing a `.env` is the one exception: **stop the session and re-run
`seal up`**, because those objects are filled before Tilt starts.

## Put the state back

Each service that owns state declares a reset script, which registers a Tilt
resource named `seal_reset_<service_name>` -- the service's name with
hyphens written as underscores:

```sh
tilt trigger seal_reset_example_api
```

Nothing fires it automatically in a `seal up` session: resetting
mid-keystroke is how somebody loses what they were looking at. Under
`seal ci` it runs at startup instead, because a test that starts from
whatever came up varies for reasons unrelated to the change.

## Run one outcome while you work

```sh
seal outcomes                                          # what the project promises
seal outcomes run <group>/<epic>/<outcome>             # just this one, against the running session
seal outcomes run --reset <group>/<epic>/<outcome>     # from a known baseline
seal outcomes run                                      # the whole suite's verdict
seal outcomes run --reset --all                        # the whole suite, run now
seal outcomes run --reset --all --confirm              # ... re-running what failed
```

Naming outcomes is the local loop: same images, same containers, fewer
outcomes started. It says nothing about the outcomes it left out -- the
summary counts what ran and says so.

`--reset` fires every reset the session declares and waits for each before
starting, which is what makes one run comparable to the next. Without it the
run takes the environment as it stands, including whatever the last run left
in it. It is a flag rather than the default because a session somebody is
working in is one whose state they may be looking at.

On the first run after `seal up`, though, it is the difference between
a run and nothing happening at all. Where a project's runner names a reset
among its `resource_deps`, the outcome waits for that reset to have run
once -- and a reset is triggered, not automatic, so in a session that has
only just come up it never has. The outcome then sits in `waiting-for-dep`
indefinitely: no test starts, no verdict is written, and the run reports
nothing to say it is stuck.

The whole suite is what a merge rests on. With nothing named it reads the
verdicts a run already left behind, which is the form `seal ci` gates on;
`--reset --all` goes and runs every promise against the session that is
already up, which is what to re-run after changing the application. Report
one of those two when reporting whether the project is green; never present a
named-subset run as the suite.

Reports land in `tests-results/outcomes/<group>/<epic>/<outcome>/`, beside
each service's own results in `tests-results/<service_name>/`.

## Work on one service outside the cluster

`seal run` injects that service's own `.env` into one command. Run it
from inside `services/<name>/` (or a subdirectory) -- that is how it works
out which service is meant:

```sh
cd services/api
seal run -- uv run python src/manage.py migrate
seal run -- uv run pytest tests/
```

`k8s://`-marked keys are dropped (the manifests supply those), and every
remaining value is resolved: a literal as itself, a `<scheme>://<item>`
reference through whichever provider the project declares for that scheme,
against the store its `environments` map names for this run's credentials
environment. A `.env` that is all literals and `k8s://` markers reaches no
provider at all and needs no CLI installed.

From the project root there is no `.env` to resolve, so `seal run`
refuses: `seal up` is what to reach for there.

## Run what a merge would run

```sh
tilt down                          # free the cluster first
seal ci -- --build_type test
```

`seal ci` is the whole gate in one command: `seal check`, then
credentials, then `tilt ci` (every resource ready, each service's own tests
run inside its running container), then the whole outcome suite, exiting on
its verdict. It exits non-zero on the first thing that fails.

## Tear down

```sh
tilt down
```

## Reporting a run honestly

- A failing outcome names a directory under `tests-results/` -- point at it
  rather than paraphrasing the failure.
- `no verdict` is a **failure**, not a gap: a translated outcome left nothing
  to read, which is what every silent failure-to-run looks like from here.
- `no test yet` is a promise nothing has been translated from. Not a failure,
  and not something to quietly translate mid-task unless that was the ask --
  see `seal-outcome`.
- An outcome that passes alone and fails in the suite is usually a test that
  does not own the data it asserts on. Outcomes run one at a time against the
  same application, each starting from whatever the one before it left.
  `--confirm` is what finds this without guessing: it re-runs every failure on
  its own from a reset, and reports `FAIL (not confirmed)` where the promise
  then held. Never report an unconfirmed failure as a pass -- it isn't one,
  and it isn't the application to fix either.
