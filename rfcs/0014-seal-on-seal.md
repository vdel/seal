# RFC 0014: Seal homologates itself

| | |
| --- | --- |
| **Status** | Accepted, partly implemented |
| **Related** | [0001](0001-library-boundary.md), [0009](0009-outcome-tests.md), [0010](0010-outcome-tree.md), [0011](0011-outcome-runners.md) |

The promise set below is what Seal already does. The specification
that states it, and the runner that starts it, are not built.

## Context

Seal holds a project to a standard: say what you promise, in the words
somebody using it would use, and let a run establish whether what was built
still says the same thing ([RFC 0009](0009-outcome-tests.md)). It does not
meet that standard itself.

What it has instead is a large unit suite, which asserts against fixtures it
builds for the occasion. That is the right shape for the rules
([RFC 0001](0001-library-boundary.md): generic code is tested generically),
and it establishes nothing about the guarantees. `seal ci` exiting
non-zero on a broken promise, a credential reaching a pod, a session that
reports itself ready being one a test can drive -- each is asserted somewhere
as a property of a function, and none is established end to end against a
project.

Two things are missing, and only one of them is a test.

**The promises are nowhere written down.** They are distributed across
fourteen RFCs as rationale, across `/docs/` as instructions, and across the
unit suite as assertions. Nothing states them as promises, so nothing can be
checked against them -- and a promise set assembled later, from whatever
turned out to be testable, would describe the tests rather than the library.

**Nothing can run them.** Both existing runners are containers inside the
environment under test ([RFC 0011](0011-outcome-runners.md)). Seal's
promises are about the layer beneath that environment -- bringing one up,
refusing to start, resolving a `.env` before any pod exists -- and no
container in a session can answer whether `seal up` brings that session
up.

## Decision

**Seal states its own promises as a specification, and homologates
itself against the worked example.** The promise set is below; the tree that
holds it lives at this repository's root, like any project's.

**A third runner type, `tap`, runs a group on the machine and reports on a
stream.** It exists for promises about the layer beneath a session, and it
amends [RFC 0011](0011-outcome-runners.md) in three places:

- **Invoked once per group**, not once per outcome. The runner is told the
  same arguments a container runner is -- its own, then `--`, then one slug
  per argument.
- **It reports [TAP](https://testanything.org/) on stdout.** One test point
  per outcome, described by the slug as the runner spells it. Seal
  reads the stream and writes the verdicts, so what a run costs stops being
  tied to how many promises it covers.
- **It runs as a subprocess of `seal outcomes run`**, not as a pod.

The five-part container contract is untouched: `playwright` and `custom`
still write their own verdict files, still stay up, still must not exit on
failure. A `tap` runner writes nothing and may exit however it likes -- the
stream is the whole of what it says.

## The promises

Seven epics. Each is stated as its headline, followed by what it carries and
what it deliberately does not claim.

The application here is the `seal` CLI and the Tilt extensions beside
it; its users are a project that has adopted Seal and the people and
agents working in that project. That fixes the vocabulary: `seal up`,
`services/<name>/.env`, the specification and CODEOWNERS over it are the
application's own surface and a promise may name them. A module, a Tilt
resource Seal declares for itself, or the shape of a generated
Dockerfile may not -- those are translation's business, and they change
without any promise changing.

### Bringing a project up

- **one command brings up every service the project declares.** From a
  checkout, with no per-service steps to remember and no list to keep in
  agreement with the services that exist.
- **a session that reports itself ready is one I can test against.** A run
  succeeds only once every resource is serving -- not once every process has
  started. This is what makes a gate worth having: a suite that starts
  against a half-built environment reports promises broken for something the
  application never did.
- **a project that cannot tell "ready" from "started" is refused before
  anything starts**, naming every container at fault in one pass.
- **a container never starts without the values it was declared to need.** A
  key no overlay consumes, and a container whose sources supply nothing for a
  key its service declares, are each reported by name before anything
  deploys.
- **the run that gates my merge is one I can type on my own machine.** A
  withheld verdict nobody can reproduce locally is one an agent cannot act
  on, which would undo the reason the gate exists.
- **which shape I deploy, which images I build, whether images are published
  and which credentials resolve are four separate decisions.**

### Declaring what the project is made of

- **adding a service to the project is declaring it, and nothing else.** The
  root Tiltfile is the list; there is no second registry, and no place a new
  service can be half-added.
- **a service can put its own state back to a known baseline, on demand.**
  What that baseline holds is the service's own business; that it can be
  restored, and that a run can wait for it, is Seal's.
- **a service's own tests run against the database and credentials it was
  deployed with.** Not against a mock of them, and not in the image build,
  where neither exists.
- **every service's results come back to one place, and a service whose suite
  failed is reported as that service.**

### Credentials

- **a credential is written down once, in the service that needs it.** The
  `.env`'s key names are the schema; there is no second list of them
  anywhere.
- **a secret reaches the running container without being committed.**
- **my manifests name the objects that carry a service's values.** Seal
  fills what an overlay marks and supplies nothing the overlay did not ask
  for, so a session and a real environment assemble a pod's environment the
  same way.
- **whatever shape my password manager's CLI takes, I declare it rather than
  wait for support.** A CLI that wraps a command, resolves a file of
  references, dumps a scope, or answers one lookup at a time -- a script
  somebody wrote here included -- is a declaration, not a change to
  Seal.
- **which store a run reads from is one thing I select**, and the same `.env`
  serves every environment.
- **CI never has to learn my application's variable names.**
- **a project that keeps no secret in a store needs no password manager to
  run.**

### What the project promises

- **what the application promises is written down in the repository, in the
  words somebody using it would use.**
- **a test is always reachable from the promise it was translated from.**
- **every promise is reported every run.** A listing that leaves one out is
  indistinguishable from one where it was kept, and a run reporting a subset
  says so in as many words.
- **a promise whose test did not run is never reported as kept.**
- **a promise nothing has been written from yet is reported, and does not
  withhold the verdict.**
- **promises are checked one at a time against the same application.**
- **I can check one promise while I work on it, against the session already
  up.**
- **a failure is reproduced on its own, from a baseline, before anything acts
  on it.** It changes no verdict: what a second run buys is a reason attached
  to the failure, not a way out of it.
- **a test I don't trust yet can be set aside with a stated reason, and is
  never reported as kept.**
- **a promise that isn't browser-shaped is checked by whatever does check
  it.**

### The merge gate

- **a change that breaks a promise cannot merge.**
- **a withheld verdict cannot be granted by editing a test.** Every path
  under the specification needs a code owner's approval, prompt and
  translation alike, so an agent that cannot find an application fix has one
  move left and it ends with a person reading the change.
- **a project whose specification nobody owns is refused.**
- **every promise is checked on every pull request, against an environment
  built for that run.**
- **the same promises can be checked against the shape that actually ships.**
- **how a run's results are presented is my repository's decision.** A run
  hands back what it found; which check it becomes is the project's, and
  adopting Seal does not inherit somebody else's reporting or the
  permissions it needs.

### Getting a withheld verdict granted

- **a red suite can be driven back to green without anybody touching a
  test.**
- **an iteration says whether it stayed inside the application.** Whether a
  round reached for the specification is a fact somebody can check, not
  something an agent reports about itself.
- **a loop that isn't getting anywhere stops, and says why.**
- **a promise that has been changing its mind is named.** Evidence, not a
  conclusion.

### Working with an agent

- **an agent working in my repository finds Seal the same way every
  time.**
- **I'm told when what's installed here has fallen behind.**

## Rationale

### Why the promises come before the runner

A promise set chosen around what happens to be cheap to run is a description
of the tests. The order matters more here than in an adopting project,
because the thing being promised is the machinery doing the checking: every
shortcut is available, and each one looks reasonable at the moment it is
taken.

So the set above was written from what the library does, not from what a
container could reach -- and the runner below exists because the set demanded
something neither existing runner could give, rather than the set being
trimmed to what they could.

### Why a container cannot hold these

An outcome test drives an application from outside, the way a person does,
and from inside the cluster it reaches each service by name
([RFC 0011](0011-outcome-runners.md)). That is right for a promise about an
application. Seal's promises are one layer down: they are about a
machine with a container runtime, a checkout and a CLI, and about what
happens when that CLI is asked to bring a cluster up or refuses to.

Running `seal ci` from a pod inside the cluster `seal ci` created
is the shape that argument ends in. The layer under test is the one the
runner would have to be standing on.

### Why TAP, and why once per group

A verdict file per outcome ties the number of processes to the number of
promises: one invocation, one verdict. That is affordable for a container
that runs twenty specs, and not for a group whose outcomes each bring a
cluster up.

A stream breaks that tie. The runner is invoked once, does whatever it does,
and says `ok 3 - bringing-up/refuses-without-a-probe` when it gets there.
Seal reads test points as they arrive and writes the verdicts, so a
group can amortise an expensive setup across every promise that needs it --
and the same contract reads identically for a subprocess and for a container,
which is what keeps this from being a second reporting convention to
maintain.

TAP rather than a format invented here: it is a line-oriented text protocol
older than any of the frameworks that emit it, every language has a producer,
and the useful subset is a plan line and one `ok`/`not ok` per point. The
alternative, an exit code per outcome, is more agnostic still and cannot
describe more than one result per process, which is the tie this is here to
break.

**A `# SKIP` or `# TODO` directive is not a pass.** It is a test point that
did not establish anything, which is the same state as a missing one: a
promise the run cannot claim was kept ([RFC 0009](0009-outcome-tests.md)).
Seal reports it as no verdict rather than reading a directive as
success.

### The example is the project, and the library is the subject

Seal's promises are homologated against `examples/angular-django/`,
because a promise about a project needs a project. What the tests assert on
is Seal's own behaviour -- what a command does when pointed at that
checkout -- never the example's todo list, which is the example's promise to
its own users and already has its own specification.

That distinction is [RFC 0001](0001-library-boundary.md)'s, applied to this
suite: a test that would pass because of how the example is laid out is
testing the example. Where a promise turns on a project shape the example
does not have, the translation builds the project it needs, the same way the
unit suite already does.

## Consequences

**A `tap` group depends on what is installed on the machine.** That is the
dependence the container model exists to remove, reintroduced deliberately
and bounded: `tap` is for promises *about* that layer. A promise about an
application's behaviour still belongs in the cluster, where every runner sees
the same environment.

**A project whose groups are all `tap` needs no Tiltfile and no cluster to
run its suite.** Which is what lets this repository hold a specification
without pretending to be a multi-service application, and what keeps the
self-homologating run from recursing: `seal outcomes run --all` at the
root starts no cluster, and the tests inside it invoke `seal ci` on the
example.

It also means `find_seal_root()` has to stop requiring a `Tiltfile`
beside a `services/` directory for the outcome commands. A project that
states promises and no services is now a project.

**The unit suite loses what the specification establishes better.** A unit
test whose whole value was simulating an end-to-end run is a duplicate once
that run happens for real, and it goes. What stays is everything covering a
shape a run cannot reach cheaply -- every offender reported at once, a patch
that deletes a container, a misspelled config field -- which is most of it.
Removing a guard because something else *looks* like it covers the same
ground is how coverage disappears quietly, so each removal names the outcome
that replaced it.

**This suite is slower than any other gate in the repository.** Several
promises need a cluster each. That cost is the reason the promise set is
tiered rather than flat, and the reason the run is its own workflow rather
than something every pull request pays for.

## Alternatives considered

**A `custom` runner with a Dockerfile.** Already supported, and it fails on
the one thing that matters: it is a container in the cluster under test.
Docker-in-docker inside a Kind node would technically run, and it would make
every promise about bringing an environment up a promise about nesting one.

**Exit code per outcome, one process each.** The most technology-agnostic
contract available -- every language can exit non-zero -- and the reason it
lost is above: one process per promise, with no way to amortise a cluster
across a group.

**A framework Seal supplies, as it supplies Playwright.** A `pytest`
runner would give the best assertions and fixtures of any option here, and
would make Python the language a project writes its non-browser promises in.
That is a technology choice the library has no business making for a project
whose services are in Go.

**Leaving Seal's promises to the unit suite.** It is where they are
now, and it is why they are invisible: an assertion about a function is not a
promise anybody can read, and a reader has no way to ask what this library
guarantees. The suite also cannot fail for the reason that matters -- a
guarantee that stopped holding for a project while every function still
behaved as written.

## Open questions

- **Which promises earn a cluster.** The set is tiered by what the library is
  worth nothing without, not by what a run costs, and the two do not agree:
  the load-bearing tier includes both the cheapest promises and the most
  expensive. Where the first pass draws its line is a budget decision, and
  the tiers exist so it can be drawn with the cost visible.
- **Whether `tap` groups and container groups belong in one tree.** They do
  by construction -- a group is a runner, and the tree holds groups -- but
  nothing has yet had both, and a project's specification reading as two
  suites in one directory is a cost that would show up in use before it
  shows up here.
- **What a `tap` runner is told about where the application answers.**
  `SEAL_BASE_URL` is an address inside a cluster, and a subprocess on
  the machine has no cluster to reach until it has brought one up itself.
  A group that never needs the variable should probably not be made to
  declare one.
