"""Whether every key a service declares actually reaches the process.

A `.env` says what a service needs; an overlay says which objects carry each
value into the pod. Those two statements can disagree, and nothing catches
it: a Deployment whose `envFrom` names an object that supplies nothing for
`DATABASE_URL` starts a container that has never heard of it, and finds out
at whatever depth the application first reads it.

So, over every overlay a run could deploy -- not the one it selected --
two rules:

- **A key nothing consumes.** A `.env` key that no container in any overlay
  ends up with a source for is dead weight at best, and at worst a value a
  project believes is reaching a process that never sees it.
- **A container with no source for a key its service declares.** The one
  that ships broken. Checked per overlay, because the same container can be
  correctly provisioned in the shape someone works in and missing a value in
  the shape that deploys.

Which container belongs to which service is not guessed from a name: a
container is a service's when one of its `envFrom` sources is an object
annotated `seal-test.dev/fill-from: <service>` (see stubs.py). That
annotation is already how an overlay says who fills what, so it answers this
too, and a project whose objects are named nothing like its services is
checked exactly as well as one whose names line up.

**What this cannot check.** With an operator or a CSI driver an object's
*content* is neither in the repository nor known at deploy time. This reads
names and key sets, never that a store holds a value -- the same boundary
the `.env`-and-declaration rules stop at.
"""

from dataclasses import dataclass
from pathlib import Path

from seal.checks import containers_in, overlays_in, render
from seal.stubs import claims, stubs_in

# Where an object states the keys it holds. `data` and `stringData` both
# reach a container the same way; a Secret written either way is one a
# container reads through `envFrom` identically.
_KEY_FIELDS = ("data", "stringData")

# What an `envFrom` entry can name, and the kind each names.
_ENV_FROM_SOURCES = {"configMapRef": "ConfigMap", "secretRef": "Secret"}


@dataclass(frozen=True)
class UnconsumedKey:
    """One `.env` key no overlay gives any container a source for."""

    service: str
    key: str

    def describe(self) -> str:
        return (
            f"{self.service}'s .env declares '{self.key}', which no container in "
            "any overlay has a source for."
        )


@dataclass(frozen=True)
class UnsourcedKey:
    """One container that would start without a value its service needs."""

    overlay: str
    deployment: str
    container: str
    service: str
    key: str

    def describe(self) -> str:
        return (
            f"overlay '{self.overlay}': Deployment '{self.deployment}', container "
            f"'{self.container}' reads {self.service}'s credentials but has no "
            f"source for '{self.key}'."
        )


def _supplies(documents: list[dict], claimed_by_stub: dict) -> dict[tuple[str, str], set[str]]:
    """Which keys each object in this overlay supplies, by (kind, name).

    A stub supplies what it claims (seal has not filled it yet at
    check time, so its own `data` is empty and says nothing). Any other
    object supplies the keys it actually carries.
    """
    supplies: dict[tuple[str, str], set[str]] = {}
    stub_identities = {
        (stub.kind, stub.name): set(keys) for stub, keys in claimed_by_stub.items()
    }
    for document in documents:
        kind = document.get("kind")
        if kind not in ("ConfigMap", "Secret"):
            continue
        name = (document.get("metadata") or {}).get("name", "<unnamed>")
        identity = (kind, name)
        if identity in stub_identities:
            supplies[identity] = stub_identities[identity]
            continue
        keys: set[str] = set()
        for field in _KEY_FIELDS:
            values = document.get(field) or {}
            if isinstance(values, dict):
                keys.update(values)
        supplies[identity] = keys
    return supplies


def _referenced(container: dict) -> list[tuple[str, str]]:
    """The (kind, name) of every object this container reads through
    `envFrom`, in the order it reads them."""
    found: list[tuple[str, str]] = []
    for entry in container.get("envFrom") or []:
        if not isinstance(entry, dict):
            continue
        for field, kind in _ENV_FROM_SOURCES.items():
            source = entry.get(field)
            if isinstance(source, dict) and source.get("name"):
                found.append((kind, source["name"]))
    return found


def _named_directly(container: dict) -> set[str]:
    """Names this container's own `env:` supplies, however each is filled.

    A literal `value` and a `valueFrom` pointing at a key of some object are
    both a source for that name -- what this checks is that the name is
    accounted for, not where the value comes from.
    """
    return {
        entry["name"]
        for entry in container.get("env") or []
        if isinstance(entry, dict) and entry.get("name")
    }


def _service_of(
    referenced: list[tuple[str, str]], service_by_object: dict[tuple[str, str], str]
) -> str | None:
    """Which service's credentials this container reads, if any.

    The `fill-from` annotation on an object it reads, rather than a guess
    from its own name: an overlay already states who fills what, and a
    project whose object names look nothing like its service names is not a
    project this should check any less well.
    """
    for identity in referenced:
        service = service_by_object.get(identity)
        if service is not None:
            return service
    return None


def accounted_in(
    overlay_name: str, documents: list[dict], claimable: dict[str, list[str]]
) -> tuple[list[UnsourcedKey], dict[str, set[str]]]:
    """One overlay's own answer: which containers are short a key, and which
    keys this overlay supplies to somebody.

    `consumed` holds an entry only for a service this overlay actually
    places -- one some object here says seal fills. A service no
    overlay places is one seal was never asked to put anywhere, and
    the walk below says nothing about it at all: the same silence the
    outcome checks keep for a project with no outcome tree.

    Separate from the walk below so the whole judgement is exercisable
    against documents a test writes, rather than only against something
    kustomize had to build first.
    """
    claimed_by_stub, _ = claims(stubs_in(documents), claimable)
    supplies = _supplies(documents, claimed_by_stub)
    service_by_object = {(stub.kind, stub.name): stub.service for stub in claimed_by_stub}

    unsourced: list[UnsourcedKey] = []
    consumed: dict[str, set[str]] = {
        stub.service: set() for stub in claimed_by_stub if stub.service in claimable
    }

    for document in documents:
        if document.get("kind") != "Deployment":
            continue
        deployment = (document.get("metadata") or {}).get("name", "<unnamed>")
        for container in containers_in(document):
            referenced = _referenced(container)
            service = _service_of(referenced, service_by_object)
            if service is None:
                continue  # not a container any service's credentials reach

            supplied = set(_named_directly(container))
            for identity in referenced:
                supplied.update(supplies.get(identity, set()))

            consumed[service].update(supplied & set(claimable[service]))
            for key in claimable[service]:
                if key not in supplied:
                    unsourced.append(
                        UnsourcedKey(
                            overlay=overlay_name,
                            deployment=deployment,
                            container=container.get("name", "<unnamed>"),
                            service=service,
                            key=key,
                        )
                    )
    return unsourced, consumed


def unaccounted_keys(
    k8s_dir: Path, claimable: dict[str, list[str]]
) -> tuple[list[UnconsumedKey], list[UnsourcedKey]]:
    """Both rules, over every overlay under `k8s_dir`.

    `claimable` maps a service to the keys of its `.env` that something has
    to supply -- literals and references, never `k8s://` markers, which the
    manifests declare individually and this never expects an object to hold.

    A key nothing anywhere consumes is reported once, as dead, rather than
    again per overlay as unsourced: those are one mistake, and naming it
    once per overlay would bury it.
    """
    if not claimable or not k8s_dir.is_dir():
        return [], []

    unsourced: list[UnsourcedKey] = []
    consumed: dict[str, set[str]] = {}
    for overlay in overlays_in(k8s_dir):
        found, supplied = accounted_in(overlay.name, render(overlay), claimable)
        unsourced.extend(found)
        for service, keys in supplied.items():
            consumed.setdefault(service, set()).update(keys)

    return _split(unsourced, consumed, claimable)


def _split(
    unsourced: list[UnsourcedKey],
    consumed: dict[str, set[str]],
    claimable: dict[str, list[str]],
) -> tuple[list[UnconsumedKey], list[UnsourcedKey]]:
    """A key nothing consumes is one mistake, so it is reported once as dead
    rather than again in every overlay that also lacks it.

    Only for a service some overlay places: `consumed` holds an entry for
    exactly those (see accounted_in()), so a project whose overlays name no
    object of seal's has nothing said about it rather than every key
    it declares called dead.
    """
    unconsumed = [
        UnconsumedKey(service=service, key=key)
        for service, supplied in sorted(consumed.items())
        for key in claimable[service]
        if key not in supplied
    ]
    dead = {(problem.service, problem.key) for problem in unconsumed}
    return unconsumed, [
        problem for problem in unsourced if (problem.service, problem.key) not in dead
    ]
