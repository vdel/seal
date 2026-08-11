# RFC 0011: Outcome runners

| | |
| --- | --- |
| **Status** | Accepted |
| **Related** | [0010](0010-outcome-tree.md), [0009](0009-outcome-tests.md), [0008](0008-run-axes.md) |
| **How-to** | [Outcome-test runners](../docs/guides/runners.md) |

## Context

Being able to *find* a test is not being able to *run* one, and a suite that
cannot run a test reports the promise as untested -- which reads exactly like
a promise nobody has got to yet ([RFC 0010](0010-outcome-tree.md)).

A project's promises are not all of one kind. Some are only really tested
through a browser; some are tested by talking to an API, or driving a worker,
or running a command-line tool. So something has to say what starts each of
them, without Seal deciding that every promise is browser-shaped.

## Decision

**A runner is an image built from the outcome tree, run as a container
against the environment, and told which outcomes to run.**

- **One runner per group**, declared in `seal-test-config.json`.
  Seal supplies a Playwright runner; a project brings a `Dockerfile` for
  anything else.
- The container is started with its own arguments, then `--`, then one outcome
  per argument, **named from inside the group**.
- Every runner meets the same five-part contract: run what it was told, write
  each verdict to a known path, leave everything else worth keeping beside it,
  say when the whole run finished, and stay up afterwards.
- **Failing by exiting is the one thing a runner must not do.**
- Seal passes in one address and nothing else.

## Rationale

### A container, not a script on somebody's machine

An outcome test drives several services at once, so it has to reach them.
From inside the cluster it reaches each one by name, the same way the services
reach each other. The alternative is a port-forward, which exists only while a
session is up and is a different thing to arrange in CI, locally, and inside a
regression loop.

### One runner per group, not one per outcome

A run is one container per group either way, and it is told which outcomes to
run -- so the image is built once and the browser installed in it once,
however many promises the group holds. That is what makes running a single
outcome while you work on it cheap enough to actually do.

Groups run one after another, for the same reason outcomes inside one do: they
drive the same application, so two at once means each asserting on state the
other is changing.

### Seal names the outcomes; a runner never resolves them

Seal knows which outcomes have been translated and a runner does not. A
runner that resolved "everything in the group" for itself would start promises
nobody has written a test for yet and report them failed.

Outcomes are named from inside the group, because a runner is built from one
group and never has to know the others exist; the group is added back when the
results come home. The `--` separator is there so a runner that takes no
arguments still reads its outcomes from one fixed place, and one that does
never has to tell a flag from a slug.

Because those arguments reach the image's entrypoint, a project's own runner
has to declare one: container args replace an image's default command rather
than adding to it, so a runner whose work lives in that command would be
started without it.

### The contract, and why each part of it exists

**A verdict file per outcome**, whose absence or malformed content is a
*failure* rather than a pass -- the same rule the suite holds everywhere: a
test that did not run is exactly what a green gate must not be able to claim
on a promise's behalf ([RFC 0009](0009-outcome-tests.md)).

**Everything else beside it.** Logs, reports, screenshots. The whole results
directory comes back to the project laid out by group, epic and outcome, which
is where a failing promise's report points somebody.

**A file saying the run finished.** One container answers for several
promises, so "the run finished" has to be distinguishable from "it died after
the third of twenty", and no count of verdicts can tell you which. It is also
what Seal's readiness probe watches, so the run is waited for the way
everything else is ([RFC 0003](0003-readiness.md)).

**Stay up afterwards.** The results are copied out of the *running*
container, so one that exits takes them with it -- and the Deployment behind
it would then start the run over.

**Never fail by exiting.** A container that exits non-zero takes its own
resource down with it and stops the run before the outcomes behind it have
said anything -- which is the suite reporting one test instead of every
promise, the exact failure the whole suite exists to prevent. Catch each
failure, write the verdict, carry on.

### One address in, and nothing else

A runner gets the address the application answers at, as the project declared
it, and the environment its pod carries. Seal knows nothing about an
app's own service names or ports, so this is the one address a runner should
need; hardcoding another is one more thing to keep in agreement with the
manifests.

Nothing else is injected -- **an outcome test drives the application from
outside, the way a person does**, so it should not need the application's own
credentials.

### What the Playwright runner pins, and what it refuses

One version pins both the framework and the browser, because the two cannot be
allowed to drift: a browser a framework does not recognise refuses to launch,
which reads as a promise failing. The browser comes from that same install
rather than from a separately-versioned base image, so there is nothing to
keep in agreement.

**Only one browser is installed**, which is all the generated config launches.
An all-browser image carries the others as freight, paid for three times -- the
daemon that builds the image, the registry it is pushed to, and the node that
pulls it -- which on a CI runner already holding a cluster is the difference
between a run and a runner that dies partway through one.

The generated config sets a single worker, which is what keeps two outcomes off
the application at once, and writes a JUnit report per outcome so outcome
results land in the same CI report as each service's own. Each outcome's
directory is run on its own, so that outcome's report and verdict land in its
own directory -- and so one red promise does not take the rest of the run with
it.

What it deliberately does not do: **retry a failing test**, run more than one
browser, or shard. A retry would paper over exactly the flakiness the
environment layer is supposed to remove; the rest is a decision that wants a
project's evidence behind it.

### Bringing your own, and what Seal then stops claiming

A custom runner is a `Dockerfile` the project brings, built from the group's
own directory so every outcome in it is available along with anything kept
beside the `Dockerfile` for the runner's own use. That is what keeps the tree
language-agnostic rather than merely broad: an API-only service, a worker or a
command-line tool says how it runs, in whatever it runs in.

Files at a group's level are that runner's build context; directories are
epics. A `Dockerfile` *inside* an outcome is an ordinary file belonging to the
translation beside it -- a test that builds an image of its own is doing
something ordinary, and what starts a run is the one path the config names
rather than whichever one a walk reaches first.

Two checks stop applying to such a group, deliberately. Whether a translation
is something the runner can start, and whether it waits on the clock, are both
questions Seal answers by reading what its own runner collects. It has
no reading of what somebody else's runner starts -- that is the whole point of
bringing one -- so it takes the project at its word rather than shipping a
lint for every language a `Dockerfile` might run.

### What the config can drift from, and what it can't

Which outcomes exist stays the tree's own business. What the config adds is
the one thing a walk cannot answer, which makes it the one place the tree and
a declaration can drift apart -- so the check refuses a group no runner names
and a runner naming a directory that isn't there, along with an unknown runner
type, a build path reaching outside the tree, and two runners naming one
group.

A group nothing claims has every promise under it reported untested, which
reads exactly like a promise nobody has got to yet. A build path reaching
outside the tree produces an image whose contents depend on where it was
built.

## Consequences

- **A project can test anything it can containerise**, and Seal learns
  nothing about it.
- **A custom runner carries the contract itself**, including the two things
  that are easy to get wrong: never exiting on failure, and staying up.
- **Serial by construction.** One container per group, one outcome at a time,
  one group after another.
- **Each outcome starts from whatever the one before it left**, so a test has
  to own the data it asserts on ([RFC 0012](0012-translation-and-review.md)).

## Alternatives considered

**Running outcome tests from the host with a port-forward.** No image to
build, and a different arrangement locally, in CI, and inside a loop -- plus a
tunnel that exists only while a session does.

**One runner per outcome.** Perfect isolation, and an image build and browser
install per promise.

**Letting a runner discover its own outcomes.** One fewer argument, and it
would start promises with no test and report them failed.

**Retries in the runner.** The cheapest green suite there is, and it hides the
evidence the environment layer needs to fix the cause.
