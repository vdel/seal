# RFC 0008: What a run selects

| | |
| --- | --- |
| **Status** | Accepted |
| **Related** | [0003](0003-readiness.md), [0005](0005-service-tests.md), [0006](0006-credential-resolution.md), [0009](0009-outcome-tests.md) |
| **How-to** | [Continuous integration](../docs/guides/continuous-integration.md), [Tilt config flags](../docs/reference/tilt-extensions.md#tilt-config-flags) |

## Context

A merge gate is worth what the shape it ran against is worth. A project that
verifies its promises only against the manifests developers work in has a
green gate that says nothing about the shape that ships -- different images,
different manifests, whatever init containers and reverse-proxy arrangement
only that overlay has.

Verifying a second shape means saying: deploy *these* manifests, build
*those* images, publish nothing, and read credentials from the store that is
safe for a throwaway cluster. Those are four independent facts. Derive them
all from one environment name and they cannot be set independently -- and the
combination the gate needs is exactly the one that name cannot express.

## Decision

**A run states four things, on four inputs.**

| Axis | Input | Default |
| --- | --- | --- |
| Which manifest shape to deploy | `--k8s_overlay` | the project's own, named in `select_k8s_overlay()` |
| Which image to build | `--build_type` | `development` |
| Whether images are published | `--publish_images` | off |
| Which credentials resolve | `--credentials_env` | the project's own, named in `default_env` |

A fifth question -- **is this run a gate?** -- is answered by which command
ran, not by any of the four.

Seal names the *kind* of image; a service names the Dockerfile stage
that builds it. Seal learns no overlay name, no registry, and no
environment name.

## Rationale

### One name cannot carry four facts

Each axis answers a different question, and they coincide only for a real
deployment:

- *Which manifest shape is this?* decides what gets deployed, and also what a
  service's own tests see -- the database they connect to, the object their
  `.env` resolved into ([RFC 0005](0005-service-tests.md)).
- *Which image?* decides whether the container carries a test suite at all.
- *Publishing?* decides whether the run reaches a registry. Derived from "not
  the development environment", it turns itself on for exactly the run that
  verifies a production-shaped overlay on a throwaway cluster.
- *Which credentials?* decides which store is read. Derived from the overlay,
  a run verifying the production-shaped overlay would either fail or reach
  production secrets ([RFC 0006](0006-credential-resolution.md)). **The unsafe
  direction must not be the implicit one.**

A single environment name is also read by *projects*, not just by the
library, and each reader takes a different fact off it -- one asking "is this
publishing?", another "which manifest shape is this?". Naming each fact is
what makes each reader correct rather than coincidentally right.

### The build type is Seal's vocabulary; the stage is the service's

`--build_type` has three values -- `development`, `test`, `runtime` -- and is
not a Dockerfile stage name. A service names its own stages, one argument per
build type, so a Dockerfile can spell them however it likes.

Each stage argument defaults to nothing, and each default means something a
project would want:

- **No runtime stage** builds with no target, so Docker builds the last
  stage. Correct for a single-stage service.
- **No development stage** falls back to the runtime one. The claim is that
  this service runs the same image in a session as in a real environment,
  which is true of a worker or a small sidecar. Deliberately *not* an
  independent fallback to "the last stage": in a multi-stage Dockerfile the
  last stage is the runtime one, so an independent default would silently hand
  a working session the production image.
- **No test stage** means this service has no tests of its own. A `test` run
  builds its development image, because the service still has to serve for
  other services' tests and for the outcome suite.

**A stage argument says which image to build, and nothing else.** It does not
say when a suite runs, because no stage does: a test image *carries* the
suite, and Seal runs the command inside the deployed container
afterwards ([RFC 0005](0005-service-tests.md)). That is why the axis holds
up -- a build type picks an image; the resource graph decides what happens to
it.

The declaring function keeps a name that asserts nothing about tests. Test
support is optional by design, and the services with none still want
everything else the call does.

### The outcome suite needs its own signal

Whether the suite runs is its own question, and the build type cannot answer
it. A build type says whether this run also executes a service's own tests;
the suite needs to know whether this run is a **gate**. The two come apart in
the case this design exists for: verifying another shape wants runtime images
*and* the suite, so a gate keyed on the build type would deploy exactly the
right images and never run a test.

The build type is the wrong thing to hang it on for a second reason -- it
already carries more than one meaning: it selects the image, and switches on a
pipeline of resources per tested service. Adding "and decides whether the
promises are read" would be a third.

That third question is larger than the suite's own trigger, because the suite
has a precondition. A service's baseline reset is what a promise about
specific data rests on, so it is due exactly when the promises are read --
whenever the run is a gate, not whenever it builds test images. Keyed on the
build type it would not fire for a runtime-image gate, and the suite would
then wait on a baseline nothing will ever establish: not a red run but one
that never ends ([RFC 0004](0004-deterministic-state.md)).

So the signal is "this run is a gate", which is `seal ci` rather than
`seal up`. `seal ci` exports `SEAL_CI=1` and the suite
auto-runs when it is set, with an explicit override in both directions for
the runs that are exceptions -- a publishing build is not a gate and has
nothing to add to one.

**Nothing beyond the choice of image may be gated on the build type.**

### Stable image tags, for something outside Tilt to reason about

Tilt re-tags whatever it pushes under its own content-digest-derived tag;
even a custom build's own tag argument only controls the local build target,
never what reaches the registry. That is invisible and fine for Tilt's own
deploys, and it means nothing *outside* Tilt -- a release-tracking tool
watching a registry -- can discover or reason about a given build by its
registry tag.

Two environment variables fix that, both set by whatever pipeline actually
publishes: the git SHA being deployed, and a zero-padded, monotonically
increasing build identifier. When the first is set, the already-built image is
re-tagged and pushed a second time as `<build id>-<sha>` -- cheap, since the
image is already in the local daemon, and it happens only when something is
actually publishing.

The build-id prefix exists so that plain lexicographic tag comparison is also
a correct recency comparison. A tool picking the newest image usually sorts by
each image's embedded build timestamp, and a fully cache-hit rebuild
reproduces an earlier build's timestamp exactly; those ties break correctly
only because of the prefix.

A build id derived from a CI run identifier is pinned to the run it was first
assigned to: a re-run pushes the same tag, and the same digest, so it is never
a way to make a new build appear downstream. That needs a genuinely new run.

This is a separate question from `--publish_images`, which decides *whether
and where* images go. The registry itself stays the project's: it is passed
down explicitly to each service, duplicating the root Tiltfile's own value,
because Tilt does not expose that value back to Starlark and a generic build
helper has no business assuming any one project's registry.

### The five things a project does with the axes

| # | What | Overlay | Build type | Publishing | Outcome suite |
| --- | --- | --- | --- | --- | --- |
| 1 | Unit tests | the primary one | `test` | off | — |
| 2 | Outcomes on the primary shape | same | `test` | off | yes |
| 3 | Outcomes on another shape | another | `runtime` | off | yes |
| 4 | Publish, after 1-3 pass | see below | `runtime` | **on** | no |
| 5 | Deploy to a real cluster | another | `runtime` | on | no |

1 and 2 are one run, not two, and not by economy: a service's own tests run
inside the container Seal deployed, so they need a cluster before they
can pass or fail at all -- the same cluster the outcome suite then drives.
There is no arrangement in which they are separate runs.

That gives row 1 a column it would not otherwise have. The overlay is part of
the contract for a service's own tests now, not only for the promises.

Row 3 is the point of the design. It runs no service tests, and cannot: a
runtime image carries the service, not its suite. "Outcomes only" there is a
property of the images, not a policy imposed on top.

Row 5 is out of scope ([RFC 0001](0001-library-boundary.md)).

### The action's shape

The pipeline ships as a composite action rather than a reusable workflow,
because the `seal` CLI it runs lives in this repository. `uses:` on an
action checks out the action's own repository and points
`$GITHUB_ACTION_PATH` into it, so the CLI is there at the same revision as
the YAML running it -- nothing to name, fetch, or keep a second pin in step
with. A reusable workflow ships only its `.yml`, leaving every caller to
vendor the CLI or resolve it by git reference.

It also runs inside the calling job, which is what lets that job bind
`environment:` and pass a per-environment credential by value
([RFC 0006](0006-credential-resolution.md)).

The action takes the primary overlay, an optional list of additional
overlays, and the publishing inputs. The inputs are deliberately not named
after any one project's directory names: the distinction they draw is *which
overlay's run also carries the unit tests* versus *which additional shapes get
their outcomes verified*, which stays true for a project that spells its
overlays some other way.

**The runs are steps in one job.** An action's steps are one job by
construction -- an action cannot define jobs -- and that suits what the runs
need anyway: roughly two hundred lines install the tooling, and each run
wants the cluster, the images and the tooling the ones before it set up.

What that costs is parallelism: the shapes are verified one after another.
What it buys, beyond the setup, is that publishing needs no cross-job plumbing
to wait for them.

**Each run starts from a fresh cluster.** Reusing one leaves the previous
overlay's objects applied, and an object the next overlay does not declare
keeps running -- so a promise can be kept by a container the shape under test
removed. A gate that can report that is worth less than no gate.

**Publishing is a separate job** because Tilt pushes images when it
*deploys*, not when a run finishes successfully. A publishing flag on the test
run would publish before a single test had passed, which is the opposite of
what publishing after a green gate means. It also means a publishing run still
has to name an overlay -- publishing means deploying something and letting
Tilt push what it built.

**The workflow hands results back; it does not report on them.** Two result
sets in one pull request are two different claims -- "the promises hold on the
shape we work in" and "they hold on the shape that ships" -- and whoever
decides whether to merge has to see which one went red. A reporting action
pinned inside would be one every adopting project inherits: the action, the
write scopes it needs on their pull requests, and the kind of runner it
happens to require. None of that is a property of the pipeline; all of it is a
policy about how a project likes to read a run. So the workflow's own jobs ask
a caller for read access and nothing more, and what travels out is the
*reading* of the reports -- computed by the same code that decided each
service's verdict during the run, so the two cannot disagree -- with the
reports themselves in an artifact.

### Local reproducibility is a requirement

Every job in that workflow must be one command a developer or an agent can
run. This is not a convenience: the local loop runs the primary overlay, so if
the merge gate ran only a shape nobody can bring up locally, a red gate would
be unreproducible and an agent could not act on it -- which would undo the
reason the gate exists at all.

So the workflow stays a thin wrapper over the CLI. Nothing in a job may be
something the CLI cannot do.

## Consequences

- **Four flags to state instead of one name.** A run says more, and each
  thing it says is a thing somebody chose.
- **A second shape costs a full run.** Fresh cluster, rebuilt images, the
  whole suite again -- verified serially after the first.
- **A project decides how many shapes are worth verifying.** How much a second
  one adds depends entirely on what that overlay changes: one that adjusts
  replicas and an ingress adds nothing to an outcome suite; one that removes a
  container and rearranges how static files are served adds a great deal.
  Seal makes the axis available and stops there.

## Alternatives considered

**One environment name, with the rest derived.** Fewer inputs, and it cannot
express the combination the gate needs -- while turning publishing on for the
run that most needs it off.

**Keying the outcome suite on the build type.** One fewer signal, and a
runtime-shape gate that either never runs a test or waits forever on a
baseline.

**A kubeconfig input, so the workflow could deploy.** Its worst case today is
a throwaway cluster misbehaving; with that input, its worst case is
production.

## Open questions

- **A service's own tests against a second overlay.** Now that they run
  against whatever database and credentials the deployed overlay gives them, a
  project whose overlays differ there could reasonably want them run against
  both, not only its promises. The workflow shape cannot ask for that:
  additional overlays run at `runtime`, which builds images that carry no
  suite. Letting an additional overlay name its own build type is a real
  extension rather than a detail -- and one worth wanting first.
- **A pull secret in a non-development overlay.** An overlay carrying an
  `imagePullSecrets` entry for a real registry is deploying images Tilt just
  built locally when it runs on a throwaway cluster. Whether that needs the
  secret to exist, or is inert, decides whether such an overlay needs anything
  extra on a CI cluster.
