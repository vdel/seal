# RFC 0004: Deterministic state

| | |
| --- | --- |
| **Status** | Accepted |
| **Related** | [0002](0002-declaration-by-structure.md), [0005](0005-service-tests.md), [0010](0010-outcome-tree.md), [0013](0013-regression-loop.md) |
| **How-to** | [Deterministic test state](../docs/guides/resetting-state.md) |

## Context

A test that starts from "whatever the last run left behind" fails for
reasons that have nothing to do with the change under test. That is the
flake class an outcome suite cannot afford: a promise reported broken
because of what a previous iteration wrote is a promise somebody spends real
time on for nothing.

`seal ci` starts from a clean slate by construction -- a throwaway
cluster per run -- but a local session runs against a long-lived one whose
volumes outlive every iteration, and the regression loop deliberately
iterates against that session rather than paying for a cluster per attempt
([RFC 0013](0013-regression-loop.md)). Something has to put a service's state
back.

## Decision

**A service declares one script that puts the state it owns back to a known
baseline**, through `seal_service(reset=...)`, and Seal registers
it as a Tilt resource named `seal_reset_<service>`.

- One script, doing both halves: empty the stores *and* load the fixture
  data.
- Addressed to a service, never to a datastore.
- Never fired by a file edit. A gate fires it before reading the promises; a
  working session does not.
- The resource name is the contract anything waiting on a baseline names in
  its own `resource_deps`.

What the script does is the project's. What makes its data trustworthy is a
convention, not a mechanism.

## Rationale

### One script, not a clean step and a seed step

What a test needs is the service's state at a known *useful* baseline, and
an empty database is only half of that. Emptying the stores and loading the
fixture are one job, in one place, where their order isn't something a
caller can get wrong.

Two separate hooks would let a caller run the wrong one, run them out of
order, or run only one -- three ways to a baseline that looks established
and isn't.

### Addressed to a service, never to a datastore

`postgres` and `valkey` are not services in this model: no Tiltfile, no
`.env`, no image of their own, just manifests in an overlay. The unit of
reset is the service whose code puts data there, because that is the thing
that knows which rows matter and which broker holds its queue. Flushing a
broker belongs in the reset of the service that uses it as one, not in
Seal, which deliberately knows nothing about datastores
([RFC 0001](0001-library-boundary.md)).

A service that owns no state declares no `reset` and gets no resource. An
empty one would still satisfy a `resource_deps` expecting a real reset, which
is worse than being absent -- it is a dependency that reports success while
guaranteeing nothing.

### When it fires, and the question that decides it

The question is not what the run *builds*; it is whether the run **reads the
promises at the end of it**.

- In a session somebody is about to work in, it doesn't fire. Starting a
  session should not throw away the state they left, and the way back is a
  trigger they ask for.
- In a run that is a gate, it does. A suite that starts from whatever the
  environment came up with varies for reasons unrelated to the change, and a
  throwaway cluster has nothing to preserve.

Conditioning it on the build kind instead would be wrong in a way that does
not fail loudly: a gate against a production-shaped overlay builds runtime
images and reads the same promises, so a reset keyed on a `test` build leaves
that suite waiting forever on a baseline nothing was going to establish --
not a red run, but one that never ends ([RFC 0008](0008-run-axes.md)).

**No file edit ever fires it.** Nothing about editing a file says this
service's data should go back to its baseline, and firing a reset
mid-keystroke is how somebody loses what they were looking at.

### Where the guard around it comes from

A reset script acts on the running cluster through `kubectl`, and it runs
wherever the Tilt session is pointed -- a session already bounded by
`allow_k8s_contexts`. So a reset inherits the guard the rest of the project
runs under rather than carrying a second one of its own, which would be a
second thing to keep in agreement.

Acting through the cluster also means each pod already holds the credentials
the session generated from its `.env`, so a reset needs no store round trip.
That is what keeps it cheap enough to trigger in a tight loop.

### What makes seed data deterministic

The mechanism is Seal's; the *content* of any one script -- which
tables, which fixture, which broker -- belongs to whichever project owns that
service. Five properties are what separate data a test can assert on from
data that merely exists:

- **Checked-in data, not a script that creates rows.** A fixture diffs as
  data, and reviewing "this row changed" is a different job from reviewing
  "this loop changed".
- **Pin every primary key.** A test that says "todo 3" has to keep meaning
  the same row across runs, which auto-assigned ids don't guarantee.
- **Pin anything time-derived.** A `created_at` defaulting to "now" makes the
  seeded list's *order* depend on when the fixture loaded -- exactly the kind
  of thing that fails one run in twenty.
- **Seed something interesting.** A list where every item is already done
  can't distinguish a working "remaining" count from a broken one.
- **Assume the tables were just emptied.** The fixture loads at the end of
  the same script that emptied them; loading it over existing rows overwrites
  by primary key rather than producing the baseline.

These are conventions rather than checks, deliberately. A rule that could
verify them would have to know what a project's data means.

### What is tested here, and what isn't

The reset *mechanism* is Seal's and is covered by tests that assert
against what Tilt reports for a project the test writes itself: that
`seal_service(reset=...)` registers `seal_reset_<service>`,
running the declared script from the service's own directory, triggered
rather than run, and that a service declaring no reset gets no resource.
Nothing it checks depends on the bundled example.

The example's own script is a worked reference, not something Seal
tests on a project's behalf.

## Consequences

- **A reset costs a run.** It is paid for on every gate, and on every
  iteration of a loop that asks for it. That is the price of one iteration
  being the same experiment as the last.
- **Outcomes within a run still don't reset between each other.** They run
  one at a time against the same application, each starting from whatever the
  one before it left, so a test has to own the data it asserts on
  ([RFC 0011](0011-outcome-runners.md)). Isolation per outcome would cost a
  reset per promise; the design buys back the part that matters by re-running
  a *failure* on its own from a reset ([RFC 0013](0013-regression-loop.md)).
- **A service that declares no reset gives an outcome nothing to wait on.**
  Which is honest, and visible: the project either names another edge or
  writes tests that own their data.

## Alternatives considered

**Deleting the volume.** Reset at the storage level rather than the logical
one. It is cruder than it looks -- it takes the schema with it, which means a
migration on every iteration -- and it says nothing about seed data, which is
the half that makes a baseline *useful*.

**Seal knowing about datastores.** A built-in "truncate every table in
this Postgres" would remove one script per service, and would put a library
that deliberately knows nothing about an application in charge of deciding
what its data means.

**Resetting on file change.** Free from the developer's point of view, and it
discards whatever they were looking at at the least convenient moment.
