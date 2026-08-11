# RFC 0003: Readiness, and what a green run claims

| | |
| --- | --- |
| **Status** | Accepted |
| **Related** | [0002](0002-declaration-by-structure.md), [0009](0009-outcome-tests.md) |
| **How-to** | [Readiness, and what `seal ci` refuses to start without](../docs/guides/project-layout.md#readiness-and-what-seal-ci-refuses-to-start-without) |

## Context

`seal ci` exits successfully only once Tilt reports every resource
ready. That is the whole of what makes it usable as a gate: green means the
environment finished coming up, not that it started to.

The guarantee is only as good as Kubernetes' idea of "ready". A container
with no `readinessProbe` is marked Ready the instant its process starts --
before it can serve a request, run a task or answer anything. One such
Deployment turns the run's claim into a weaker one, without ever failing.

That failure is invisible in exactly the situation the gate exists for: the
suite runs against something that isn't serving yet, a promise goes red for
reasons the change never caused, and the cost lands on whoever has to work
out why.

## Decision

**`seal ci` refuses to start until every Deployment a run can deploy
declares a `readinessProbe` on every container.** `seal check` runs the
same rule on its own.

Each overlay is **built**, and what comes out is what is checked. A finding
names the overlay it came from.

`seal up` runs no such check.

## Rationale

### A precondition, not a lint

The rule is not a style preference about manifests. It is the condition
under which "every resource ready" means anything at all, so it runs before
anything is deployed rather than as advice afterwards. A run that cannot
report readiness honestly produces a result nobody should act on, and
finding that out costs a directory walk.

### Built, not read as written

A manifest file is not what reaches the cluster. A kustomize patch is a
Deployment document too, and an entry in its `containers` may be introducing
a container, amending one a base declares, or deleting it -- three things a
reader of the file alone cannot tell apart.

Requiring a probe in each of them would mean copying a base's probe into
every patch that touches a container, and a copied probe is one that goes
stale. Rendering the overlay settles it: what the check sees is what
Kubernetes would get, and a patch adding a volume mount needn't restate a
probe that lives in the base.

Findings are per overlay because the same container can be fine in the shape
developers work in and missing a probe in the shape that ships. Which is
also why the check walks every overlay rather than the one a run selected
([RFC 0008](0008-run-axes.md)).

### What is deliberately not checked

**Which resource waits on which** (Tilt's `resource_deps`). Declaring those
edges reduces crash-loop churn while an environment comes up and is worth
doing, but `tilt ci` waits for every resource whatever order they started
in -- so ordering isn't what makes the signal trustworthy. Inferring the
right edges would mean guessing at dependencies the manifests only imply
([RFC 0002](0002-declaration-by-structure.md)).

**Which probe is right.** An HTTP endpoint where there is a server, a
command where there isn't. That is the service's business; Seal has no
reading of what "serving" means for somebody else's process.

### `seal up` is not a gate

A half-finished manifest should not stand between a developer and their
cluster. The check exists to protect a claim a merge rests on, and a local
session makes no such claim.

### Why the manifest directory is an environment variable

A project that keeps its manifests somewhere other than `k8s/` names that
directory in `SEAL_K8S_DIR`. It is an environment variable rather than
a flag because `seal ci` hands every argument it is given straight to
`tilt ci`, leaving it none of its own to spend. The same directory is what
the project passes to `select_k8s_overlay(k8s_dir=...)`, which Starlark
never hands back to the CLI.

## Consequences

- **Adding a Deployment means writing a probe.** For a worker with no port
  to poll that is a command rather than an HTTP get, which is more thought
  than a default would have asked for and the reason a default would have
  been wrong.
- **The check needs kustomize.** Building an overlay is what makes the rule
  correct, and it is one more tool a run depends on -- the same one Tilt's
  own `kustomize()` shells out to, so it is already there.
- **A green `seal ci` is a claim about the environment, not about the
  application.** What the application promises is the outcome suite's claim
  ([RFC 0009](0009-outcome-tests.md)); this is the condition that lets the
  suite be believed.

## Alternatives considered

**Warning instead of refusing.** A warning on a run that then goes green is
read past. The failure this prevents is silent by construction, so the
response has to be one that stops the run.

**Checking readiness at the end of a run instead** -- asking the cluster
which containers actually had probes. It would be accurate and far too late:
the suite has already run against whatever was up.

**Inferring a probe.** Seal could synthesise a TCP check against a
declared port. It would be right often enough to be trusted and wrong
exactly where a process listens before it can serve, which is the case the
rule exists for.
