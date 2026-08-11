"""What an overlay says seal should fill, read off the overlay itself.

A `.env` names what a service needs. Which Kubernetes object carries each of
those values into a pod is a different fact, and one that differs per
environment: a session has one object per service, a real environment has a
ConfigMap of settings beside a Secret per credential group, each populated
by whatever populates it there. That list is already stated, per overlay, in
the `envFrom` of the Deployment that consumes it -- so it is the overlay's
to state, not a name a library picks.

A **stub** is an object in an overlay annotated `seal-test.dev/fill-from:
<service>`: it says "seal fills this one, from that service's `.env`".
A session's overlay carries stubs; a real environment's overlay carries an
ExternalSecret or a SealedSecret or whatever else populates the same name
there, and the consuming Deployment is identical in both. See
/rfcs/0007-credential-delivery.md.

**A stub naming no keys claims the rest.** A key list on every stub would
mean adding a secret in two places, and `.env` being the only schema is the
property the whole design protects. So a project wanting one object writes
one four-line stub and never touches it again; splitting is opt-in, and only
a split stub names `seal-test.dev/keys`.

This module only reads. Filling is seal.py's, and deciding that an
unclaimed key is a problem is `seal check`'s -- that answer depends on
which overlay is being asked about, which a caller knows and this does not.
"""

from dataclasses import dataclass

# Under seal's own domain, so a project's objects can carry these
# beside whatever annotations its own tooling already puts there without
# either having to know about the other.
FILL_FROM_ANNOTATION = "seal-test.dev/fill-from"
KEYS_ANNOTATION = "seal-test.dev/keys"

# What a stub can be. Both carry a flat string map a container reads through
# `envFrom`, which is the whole requirement; the difference is RBAC and
# whether `kubectl describe` prints the values, which is the project's call
# to make and the reason it picks rather than seal.
FILLABLE_KINDS = ("Secret", "ConfigMap")

# How a split stub separates the keys it names. Commas rather than a YAML
# list because an annotation value is a string either way, and a string a
# reader can take in at a glance beats one they have to parse.
KEYS_SEPARATOR = ","


@dataclass(frozen=True)
class Stub:
    """One object an overlay asks seal to fill.

    `keys` is None where the stub names none -- which is what makes it that
    service's catch-all rather than a stub claiming nothing. An empty claim
    and an unstated one are different things, and a project only ever writes
    the second by accident.
    """

    kind: str
    name: str
    service: str
    keys: tuple[str, ...] | None

    def describe(self) -> str:
        return f"{self.kind} '{self.name}'"


def stubs_in(documents: list[dict]) -> list[Stub]:
    """Every stub among a built overlay's documents, in the order the
    overlay produced them.

    Read off already-parsed documents rather than files: what an overlay
    deploys is what `kustomize build` renders, and an annotation a patch
    adds is as real as one written in a base. Documents that are not
    fillable, or carry no `fill-from`, are simply not stubs -- most of an
    overlay is neither.
    """
    found: list[Stub] = []
    for document in documents:
        if document.get("kind") not in FILLABLE_KINDS:
            continue
        metadata = document.get("metadata") or {}
        annotations = metadata.get("annotations") or {}
        service = annotations.get(FILL_FROM_ANNOTATION)
        if not service:
            continue
        listed = annotations.get(KEYS_ANNOTATION)
        keys: tuple[str, ...] | None = None
        if listed is not None:
            keys = tuple(
                part.strip() for part in listed.split(KEYS_SEPARATOR) if part.strip()
            )
        found.append(
            Stub(
                kind=document["kind"],
                name=metadata.get("name", "<unnamed>"),
                service=service,
                keys=keys,
            )
        )
    return found


def claims(
    stubs: list[Stub], claimable: dict[str, list[str]]
) -> tuple[dict[Stub, tuple[str, ...]], list[str]]:
    """Which keys each stub actually claims, and everything wrong with how
    they were declared.

    `claimable` maps a service name to the keys of its `.env` that are
    seal's to fill -- literals and references, never `k8s://` markers,
    which the manifests supply and no stub is entitled to.

    Problems are returned rather than raised, the way read_config() and
    declaration_problems() report theirs: a project should be able to put
    its overlay right in one pass rather than one run per mistake.
    """
    problems: list[str] = []
    claimed: dict[Stub, tuple[str, ...]] = {}

    by_service: dict[str, list[Stub]] = {}
    for stub in stubs:
        by_service.setdefault(stub.service, []).append(stub)

    for service, service_stubs in by_service.items():
        if service not in claimable:
            named = ", ".join(sorted(stub.describe() for stub in service_stubs))
            problems.append(
                f"{named} names service '{service}' in "
                f"'{FILL_FROM_ANNOTATION}', which has no .env for seal to "
                "fill it from."
            )
            for stub in service_stubs:
                claimed[stub] = ()
            continue

        available = claimable[service]
        # Which stub claims a key, so a second claim on it can name the first.
        claimant: dict[str, Stub] = {}
        for stub in service_stubs:
            if stub.keys is None:
                continue
            taken: list[str] = []
            for key in stub.keys:
                if key not in available:
                    problems.append(
                        f"{stub.describe()} names '{key}' in "
                        f"'{KEYS_ANNOTATION}', which {service}'s .env does not "
                        "declare."
                    )
                    continue
                if key in claimant:
                    problems.append(
                        f"{stub.describe()} and {claimant[key].describe()} both "
                        f"claim '{key}'. A key reaches a pod from one object, so "
                        "which one has to be something the overlay says."
                    )
                    continue
                claimant[key] = stub
                taken.append(key)
            claimed[stub] = tuple(taken)

        catch_alls = [stub for stub in service_stubs if stub.keys is None]
        if len(catch_alls) > 1:
            named = ", ".join(sorted(stub.describe() for stub in catch_alls))
            problems.append(
                f"{named} each name no '{KEYS_ANNOTATION}', so each claims "
                f"whatever else {service}'s .env declares. Give all but one of "
                "them a key list."
            )
        for stub in catch_alls:
            # Every catch-all gets the same remainder: reporting the ambiguity
            # above and then silently picking a winner here would make the
            # problem look like a preference.
            claimed[stub] = tuple(key for key in available if key not in claimant)

    return claimed, problems
