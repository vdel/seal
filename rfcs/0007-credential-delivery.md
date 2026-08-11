# RFC 0007: Credentials: the overlay owns the objects

| | |
| --- | --- |
| **Status** | Accepted |
| **Related** | [0006](0006-credential-resolution.md), [0003](0003-readiness.md), [0008](0008-run-axes.md) |
| **How-to** | [The objects a service's values land in](../docs/guides/credentials.md#the-objects-a-services-values-land-in) |

## Context

[RFC 0006](0006-credential-resolution.md) settles where a service's values
come from. This is the same question at the other end: a `.env` says which
item a service needs, and something has to say **which Kubernetes object
carries it into the pod**.

A library can answer that itself -- render one `Secret` per service, name it
after the service, and have the Deployment consume it. It is the obvious
shape, and it is a Kubernetes name chosen inside a library rather than by the
project whose manifests it lands in.

## Decision

**Each overlay declares the objects, and Seal fills the ones the
overlay marks.** An object carries an annotation naming the service whose
`.env` fills it; Seal supplies its `data` and nothing else.

- A marked object with **no key list claims every key** of that service's
  `.env` that no other object claims. Splitting is opt-in, and only a split
  object names its keys.
- Both `Secret` and `ConfigMap` work. Which an object is decides RBAC and
  what `kubectl describe` prints, which is why the project picks it.
- Values arrive as a **strategic-merge patch**, not a second copy of the
  object.
- **A project that marks nothing gets nothing filled**, and everything else
  still works.
- `seal check` accounts for a pod's environment in **every** overlay: a
  key no overlay consumes, and a container whose sources supply nothing for a
  key its service declares, are each reported by name before anything
  deploys.

## Rationale

### What a single library-named object costs

A real environment does not assemble a pod's environment from one object. It
uses several, split by who owns them and how each is filled: a ConfigMap of
non-secret settings, a Secret per credential group, populated by an operator,
a CSI driver or a sealed secret. Four things then differ between what a
session runs and what ships:

- **Names and grouping.** A session has one object per service; a real
  environment has several. The two pods assemble their environment from
  differently shaped sets of objects, and only one of the two shapes is ever
  exercised.
- **Precedence.** With several `envFrom` sources the later one wins, and an
  explicit `env:` beats all of them. A key shadowed in a real environment
  cannot be shadowed in a session that has one source.
- **ConfigMap versus Secret.** Everything goes into a Secret, since there is
  no schema file to classify keys by. That is the right call for a single
  object and the wrong one for a real environment, where the split decides
  RBAC and what `kubectl describe` shows.
- **Files.** A TLS certificate, a service-account JSON, anything a CSI driver
  mounts. A `.env` has no expression for a credential that arrives as a file,
  and one object consumed by convention cannot mount part of itself and inject
  the rest.

The first of those ships a broken environment silently. The last is a thing
that design cannot say at all.

### The manifests already state the contract

A Deployment says exactly what fills its environment, in the same language in
every environment -- an `envFrom` list, or a volume. That list *is* the
provisioning contract, and it is already per overlay.

So the divergences above collapse into one file per overlay whose whole job
is to say who fills what: a session's overlay carries objects Seal
fills, a real environment's overlay carries whatever populates them there.
The consuming Deployment is then identical in both, belongs in the base, and
never needs patching -- because the only thing that differs between
environments is which manifest fills the object it already names.

Files stop being a gap with no new mechanism: an object a Deployment mounts
as a volume is filled exactly like one it reads through `envFrom`. Seal
resolves values; the manifest decides how each one reaches the process.

### The default has to stay one object with no key list

An object that listed its keys would mean adding a secret in two places. That
trade is not worth making: `.env` being the only schema is the property
[RFC 0006](0006-credential-resolution.md) exists to protect.

So a marked object with no key list claims every key of that service's `.env`
that no other object claims. A project wanting one object writes four lines
once and never touches them again -- what a library-named object would have
given it, with the name owned by the project. Only a split object names keys,
and the one naming none takes the rest.

### A patch, not a copy

The object already arrives from the overlay, and kustomize refuses a
duplicate id outright. A strategic-merge patch also means one object reaches
the cluster with the project's own name, labels and annotations intact and
only `data` supplied, so nothing depends on which of two copies is applied
last.

Each overlay's patches are written beside a generated kustomization naming
the real overlay as its single resource, and that is what a session deploys
-- so the overlay a project wrote stays exactly as written.

**Every overlay is filled, not the one this run deploys.** Which overlay Tilt
selects is computed in Starlark from a flag and a default the project's own
Tiltfile passes -- an argument the Python process never sees. Reproducing
that selection would mean a second implementation of it, in another language,
against an input it does not have. So each overlay's objects are filled
beside it and the Tiltfile reads the one it picked. It is cheap: only an
overlay carrying annotations has anything filled, and each service resolves
once however many overlays name it.

### Accounting for a pod's environment

Independent of the objects, and cheaper: the check already walks every
overlay, so for each container it can compute which environment variable
names that overlay's sources supply and compare that against the `.env` key
list.

Two findings come out: a key declared in a `.env` that no overlay consumes,
and a container in a real environment's overlay whose sources account for no
value for a key that service needs. The second is the failure that ships a
broken environment, caught at merge time, against the shape that actually
ships.

Its limit is worth stating: with an operator or a CSI driver an object's
*content* is neither in the repository nor known at deploy time. Seal
can check names and key sets, never that a store holds a value.

### A run that never had its credentials fails away from the cause

Running Tilt directly, without the resolution step, does not fail outright.
It deploys the annotated objects with no `data` in them, so containers start
without their credentials and the failure surfaces as a readiness timeout or
an application error. That is a real cost of filling objects the overlay
already declares, and it is why the wrapper exists and why the failure is
documented where somebody hits it.

### A real environment is on the other side of the boundary

`seal up`/`ci` produce plaintext values and hand them to Tilt to apply
live -- fine for a throwaway cluster. A real staging or production deploy
never goes through that, and never has a plaintext `Secret` applied to it
from outside the cluster ([RFC 0001](0001-library-boundary.md)).

What this design needs from a real environment is only that the *resolution*
is the same, so a service's credentials there are whatever its own `.env`
says they are, read from that environment's own store. How the object gets
filled -- a sealed secret committed like any other manifest, an operator, a
CSI driver -- is that environment's business, and it simply doesn't annotate
those objects.

That is the point of the overlay owning the objects rather than Seal:
what differs between a session and a real environment collapses into which
manifest fills a name both already use.

## Consequences

- **A project writes one small manifest per overlay it wants filled.** Four
  lines for the simple case, and something to think about for the case where
  a real environment splits its objects.
- **Splitting repoints every container that reads the service.** Where
  several Deployments run the same image against the same settings, that is
  several `envFrom` lists to update -- and the accounting names each container
  left behind rather than letting it start short of a key.
- **Seal never chooses a Kubernetes name.** Which also means it cannot
  fix a name mismatch for you; the check reports it instead.
- **An operator-only project is a supported shape**, not a workaround: mark
  nothing, and a session matches a real environment exactly.

## Alternatives considered

**One `Secret` per service, named by the library.** Fewer files, and every
cost in "What a single library-named object costs" above.

**Seal applying its own copy of the object beside the overlay's.**
Whichever is applied last wins, which is not a thing to leave to apply
ordering.

**Filling a real environment's objects.** Operators that sync a CRD into a
real `Secret` from inside the cluster already do this, generalised across
every provider surveyed. They sit on the same side of the same boundary: a
real environment never has a plaintext `Secret` pushed into it from outside,
and Seal is not what deploys there.

**A schema file classifying keys as secret or not.** It would let one object
be split automatically, and it would be the second schema this design exists
to avoid.
