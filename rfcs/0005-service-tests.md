# RFC 0005: Where a service's own tests run

| | |
| --- | --- |
| **Status** | Accepted |
| **Related** | [0003](0003-readiness.md), [0004](0004-deterministic-state.md), [0008](0008-run-axes.md), [0009](0009-outcome-tests.md) |
| **How-to** | [How a service's tests run](../docs/guides/project-layout.md#how-a-services-tests-run) |

## Context

A project has two kinds of test. Outcome tests drive several services at
once and are what a merge rests on ([RFC 0009](0009-outcome-tests.md)). A
service's own tests are the ordinary kind, and something has to decide where
they run.

The decision is not about convenience. Where a suite runs decides what it
can see, and what it can see decides which tests are allowed to be
*service* tests at all.

## Decision

**A service's tests run inside the container Seal has just deployed.**
The service names the command; Seal runs it with `kubectl exec` once
that service is ready, as a Tilt resource of its own.

The image's `test` stage **carries** the suite -- it installs the test
dependencies and copies the test files in -- and runs nothing.

**The JUnit report the command leaves behind is the whole verdict.**
Seal discards the suite's exit code, and silence counts as failure.

## Rationale

### Why not while the image is built

Running a suite in a `RUN` line is the cheapest thing there is -- no cluster,
and a layer cache that absorbs a rebuild changing nothing. It costs two
things that matter more.

**The suite can only see what the build can see.** A build has no cluster, so
a service's tests cannot reach its own database, its broker, or the
Kubernetes object its `.env` resolved into. Everything that needs one has to
be faked, and the consequence is a boundary in the wrong place: a test that
needs a real database is not a *service* test in that vocabulary, however
small it is, so it has to be written as an outcome test -- gated by
`CODEOWNERS`, run by a container driving the whole application, one of the
handful of promises a merge rests on. Promises are an expensive place to put
"this repository query filters correctly".

**A verdict baked into a layer cannot be re-run.** A failing suite bakes its
report into that layer, and the next build reuses it. The verdict is not
*wrong* -- a cache hit means the same inputs -- but a failure somebody wants
to look at again cannot be re-run without busting the cache, and where the
build cache is shared across CI runs that cache is not one machine's to bust.
"Run it again" is the first thing anybody does with a red suite.

### Why not in the container's entrypoint

Starting the suite from the entrypoint, before the service's own process,
would keep the cluster and need no resource of its own. It is worse three
ways.

A suite that runs before the process starts is a suite inside the readiness
path, so a container with a `livenessProbe` gets restarted partway through a
slow run. It makes readiness mean "and the tests finished", a second meaning
for a signal that already has one ([RFC 0003](0003-readiness.md)). And it
puts the exit-code swallow in a script the project writes, where leaving it
out silently converts a red suite into a service that never comes up.

### The report is the verdict

A service's tests leave their results inside its container, and those results
reach the project by being copied out of it. That decides the shape of the
contract: whatever runs the suite must not stop on a failing one, or it takes
the report of what failed with it.

So nothing upstream of the verdict fails on a red suite, and the JUnit report
in the declared directory is the whole answer. **Seal discards the exit
code itself** rather than asking each project to -- a swallow that lives in
the library is one a service cannot leave out by accident. A service says
what to run, and nothing about what to do when it fails.

**One answer, not two.** A status file written beside the report would be a
second verdict on the same run, free to disagree with the first -- and the
thing a person opens to find out *which* test failed is the report either
way.

What that costs is that a service which never ran its tests leaves a
directory indistinguishable from one whose tests all passed. So silence is
failure: no report, a report holding no test cases, a report that does not
parse, and a suite that recorded an error before running a case are each a
failed service. That is the same rule the outcome suite holds for a promise
-- a test that did not run is exactly what a green gate must not be able to
claim.

**Which file holds the report is not something a project declares.** Runners
disagree -- one `junit.xml` beside a coverage report, one file per browser in
a subdirectory -- so every `.xml` under the results directory is examined and
the ones with a JUnit root element are the report. A coverage report in the
same directory is passed over rather than configured away.

### What the ordering has to say

For a service declaring both a reset and a test command:

```
service ready → reset → this service's tests → reset → the promises
```

**The baseline, twice, from the same script.** Once before the service's own
tests, so they read the state this service owns from a known starting point
like anything else that reads it. Once after, so the outcome suite does too,
whatever those tests did to get their answer.

Neither restore makes the other redundant: dropping the first leaves a
service's tests running against whatever the environment came up with, and
dropping the second makes an outcome's fixture depend on what a unit test
happened to touch -- something Seal cannot know and should not have to.

A Tilt resource can only sit in the graph once, so those are two resources
running one script: one belonging to that service's test pipeline, and
`seal_reset_<service>`, the baseline an outcome reads and the name a
project already puts in its own `resource_deps`
([RFC 0004](0004-deterministic-state.md)).

The syncback **waits for the run** as well. Firing it on the service being up
would copy back whatever the container held before its tests wrote anything,
which reads as a service that never ran them -- and is reported as one.

**Nothing puts a run ahead of the outcome suite unless something says so.**
The trailing reset does it for a service that declares one. A service that
declares no reset has a run concurrent with the suite until the project names
it in `register_outcome_runner()`'s own `resource_deps` -- the same way a
project already names a reset there, and for the same reason: Seal
knows which services declared a test command, not which of them an outcome
would trip over. A browser-driven unit suite running beside a browser driving
the application is two browsers competing for one node, which is a slow
outcome test and then a flaky one.

### One shape, including where it does not pay

A suite with no use for a cluster -- a unit suite talking to nothing -- gains
nothing here and gives up its layer cache. It runs this way anyway.

That is a deliberate trade of a little speed for one thing a project has to
learn instead of two. A second supported shape is not free: it is a choice
every service has to make, a branch in the resource graph, and a second set
of rules about what a test stage may do. What it would buy is a rebuild that
skips a suite nobody changed -- worth measuring before it is worth having.

## Consequences

- **The suite is paid for on every run.** No image layer absorbs a repeat of
  it -- the same property that makes a failure re-runnable.
- **A cluster is needed before a test can fail.** A suite that would have
  failed during a build now fails after an environment has come up.
- **The tests share a cluster with everything else in the run.** They get the
  real database, which is the point, and with it the responsibility to know
  what they touch. The ordering above covers the sequence; what a test writes
  is the project's.
- **A per-service verdict resource** means CI fails pointing at whichever
  service actually broke, rather than at one combined check.

## Alternatives considered

**Tests in the build, as most projects write them.** Faster, cacheable, and
it draws the service/outcome boundary around what a build can reach rather
than around what a test is about. That boundary is the reason not to.

**A status file beside the report.** Simpler to write than parsing JUnit, and
it is a second verdict that can disagree with the report a human reads.

**Letting a service opt out of running in the cluster** when its suite needs
nothing from one. A real saving, and a second shape every project then has to
choose between. Worth revisiting with a measurement behind it.
