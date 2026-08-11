# Deterministic test state

A test that starts from "whatever the last run left behind" fails for
reasons that have nothing to do with the change under test. This page is the
convention that removes that class of flake, so an outcome test can name a
row and mean it.

## One script per service

A service declares the way back to its baseline in its own Tiltfile:

```python
seal_service(
    'example-api',
    ...,
    reset='deploy/reset.sh',   # relative to this service's Tiltfile
)
```

That registers a Tilt resource named **`seal_reset_example_api`** -- the
service's name with hyphens written as underscores, so the whole thing reads
as one token -- which runs the script from the service's own directory, once
that service is up. (The script acts on the service through the cluster, so
a `kubectl exec` against a Deployment that isn't up yet reaches nothing.)

A service that owns no state declares no `reset` and gets no resource. An
empty one would still satisfy a `resource_deps` expecting a real reset,
which is worse than being absent.

### One script, not a clean step and a seed step

What a test needs is the service's state at a known *useful* baseline, and
an empty database is only half of that. Emptying the stores and loading the
fixture data are one job, in one place, where their order isn't something a
caller can get wrong.

### It's addressed to a service, never a datastore

`postgres` and `valkey` aren't services in this model -- no Tiltfile, no
`.env`, no image of their own, just manifests in your overlay. The unit of
reset is the service whose code puts data there. Flushing a broker belongs
in the reset of the service that uses it as one, not in Seal, which
deliberately knows nothing about datastores.

## Triggering it

**No file edit ever fires a reset.** Nothing about editing a file says this
service's data should go back to its baseline, and firing one mid-keystroke
is how somebody loses what they were looking at. Ask for it:

```sh
tilt trigger seal_reset_example_api
```

...or the button in the Tilt UI.

Whether it *also* runs once at startup is one question: does this run read
your promises at the end of it?

| Run | Runs at startup? | Why |
| --- | --- | --- |
| `seal up` | No | You're about to work in it; throwing away the state you left is not what starting a session means. |
| `seal ci` | Yes | The suite is about to read the promises, and one that starts from whatever came up varies for reasons unrelated to the change. A throwaway cluster has nothing to preserve. |
| either, with `--run_outcomes false` | No | A run whose only job is to build and publish reads no promises, so there's no baseline for anything to start from. |

Deliberately not what the run *builds*. A gate against a production-shaped
overlay builds runtime images, reads the same promises, and resets first
exactly as one that built test images does -- a reset waiting on a `test`
build would leave that suite waiting forever on a baseline nothing was going
to establish.

A reset script acts on the running cluster through `kubectl`, where each pod
already holds the credentials `seal up` generated from its `.env` --
so it needs no password-manager round trip, which keeps it cheap enough to
trigger in a tight loop.

Which cluster it can touch is Tilt's own question: the script runs wherever
the session is pointed, and that session is already bounded by
`allow_k8s_contexts`, so a reset inherits the guard the rest of the project
runs under rather than carrying a second one.

## The resource name is the contract

Anything that needs a service reset before it runs names
`seal_reset_<service_name>` in its own `resource_deps` -- an outcome
test, most obviously. There's no registry of hooks to consult and no path to
guess. `reset_resource_name()` is exported from `ext://seal` so you
can build that name without hardcoding the spelling:

```python
load('ext://seal', 'register_outcome_runner', 'reset_resource_name')

register_outcome_runner(
    base_url='http://web:8000',
    resource_deps=[reset_resource_name('example-api')],
)
```

Seal deliberately doesn't infer that edge. It knows which services
declared a reset; it doesn't know which of them any one outcome actually
reads, and a dependency nobody asked for is a slower run at best and a cycle
at worst.

## What makes seed data deterministic

The mechanism is Seal's; the *content* of a reset script -- which tables,
which fixture, which broker to flush -- is your service's. Five rules make
the difference between data that's merely present and data a test can assert
on:

**Check the data in; don't write a script that creates rows.** A fixture
diffs as data, and reviewing "this row changed" is a different job from
reviewing "this loop changed".

**Pin every primary key.** A test that says "todo 3" has to keep meaning the
same row across runs, which auto-assigned ids don't guarantee.

**Pin anything time-derived.** A `created_at` that defaults to "now" makes
the seeded list's *order* depend on when the fixture loaded -- exactly the
kind of thing that fails one run in twenty. Where your loader saves raw
values (Django's `loaddata` does), the fixture's own timestamps win, which
is what you want.

**Seed something interesting.** A list where every item is already done
can't distinguish a working "remaining" count from a broken one.

**Assume the tables were just emptied.** The fixture loads at the end of the
same script that emptied them. Loading it over existing rows overwrites by
primary key rather than producing the baseline.

The worked example is the todo list in `examples/angular-django`:
`services/api/src/core/fixtures/baseline.json`, loaded by
`services/api/deploy/reset.sh` via `manage.py loaddata baseline`.

## What this buys an outcome test

A full outcome run puts every service that declared a reset back to its
baseline before it starts anything. That is what lets an outcome test assert
on a specific row rather than on whatever happens to be there.

Two things it deliberately doesn't cover:

- **`seal outcomes run <slug>` doesn't reset unless you ask.** Naming
  outcomes runs them against the environment as it stands, because what
  you're iterating on is usually the test rather than the state underneath
  it. `seal outcomes run --reset <slug>` puts every service that declared one
  back first and waits for each; without it, trigger the reset yourself, or
  write the test to own the data it asserts on.
- **Outcomes within a run don't reset between each other.** They run one at
  a time against the same application, each starting from whatever the one
  before it left -- so a test should own the data it asserts on. See
  [Outcome-test runners](runners.md).
