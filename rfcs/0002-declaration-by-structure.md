# RFC 0002: Declaration by structure

| | |
| --- | --- |
| **Status** | Accepted |
| **Related** | [0001](0001-library-boundary.md), [0004](0004-deterministic-state.md), [0010](0010-outcome-tree.md), [0011](0011-outcome-runners.md) |
| **How-to** | [Declaring your services](../docs/guides/project-layout.md), [How Seal fits together](../docs/concepts.md) |

## Context

A multi-service tool has to know several things about a project: which
services exist and where their files are, which credentials each one needs,
which promises the project makes. The obvious way to learn them is a config
file listing all of it.

Every such file is a second source of truth. It can disagree with the tree
it describes, and nothing about adding a directory keeps it in agreement --
so the failure mode is a service, a key or a promise that exists and is
invisible, or one that is declared and absent.

## Decision

**What a project already has is the declaration.** Seal keeps no
registry that has to be kept in agreement with the tree:

| The question | Answered by |
| --- | --- |
| Which services exist | whatever the root `Tiltfile` `include()`s |
| Where a service's files are | wherever that service's own `Tiltfile` is |
| Which credentials a service needs | the key names in its own `.env` |
| Which promises a project makes | the directories under `outcomes/` |
| What has to run before what | a Tilt resource named in `resource_deps` |

Two declarations exist, both narrow, both for the one question a walk cannot
answer: `outcomes/seal-test-config.json` says which runner drives each
group of promises ([RFC 0011](0011-outcome-runners.md)), and
`seal-credentials-config.json` says where a project's stores are
([RFC 0006](0006-credential-resolution.md)).

## Rationale

### A walk covers what is added later; a list covers what somebody remembered

An outcome added to the tree is covered by having been added. A service
`include()`d is deployed by having been `include()`d. A key added to a `.env`
is claimed by the object that already claims that service's keys, with
nothing else to touch.

The alternative is the same work plus a second step, where forgetting the
second step is silent. A promise nobody registered is reported as no promise
at all; a manifest nobody listed is a Deployment nothing checks. Both read
exactly like the state where the work was never done.

### The mechanics that make it possible

Two properties, neither obvious, and both load-bearing.

**Tilt resolves a relative path against whichever Tiltfile's top-level code
is currently executing** -- not the file where the calling function is
*defined*. A plain function call doesn't change that; only `include()` and
`load()` do. So a helper several calls deep can read a bare relative path and
correctly reach *that service's own* file -- `seal_service()`'s `reset`
script, for one. This is what lets a service's own directory be the only
thing that knows where it is. It is not stated in Tilt's own documentation
and was confirmed empirically, which is why it is written down here.

**The same information reaches Python by asking Tilt.** `seal
up`/`seal ci` need each service's name and directory before Tilt
starts. They get it from `tilt alpha tiltfile-result` against the project's
root Tiltfile: a full evaluation -- the same `include()`s and
`seal_service()` calls a real run would make -- with no live cluster,
printed as JSON. Every image build appears as one `ImageTargets[]` entry
whose selector is the service's name and whose build context is its
directory.

That is why the project's root Tiltfile has to be a real, checked-in file
rather than something Seal synthesises: it is the input to the
discovery pass, and a project reads it to know what it deploys.

Discovery runs with `IS_BUILD_OR_TEST=1` set, so a project's own Tiltfile can
branch on it to skip whatever a discovery pass has no cluster for. The whole
point of that pass is that it runs first.

### A resource name is a contract, not a lookup

Anything that has to happen before something else names the Tilt resource it
waits for: `seal_reset_<service>` before an outcome test reads a
baseline, `seal_tests_run_<service>` before a suite that would compete
with it. There is no registry of hooks to consult and no path to guess.

The names are exported as functions -- `reset_resource_name()`,
`tests_run_resource_name()` -- so a project builds one without hardcoding the
spelling. A stale name that no longer matches anything is how a dependency
silently stops holding, and a function is what removes the chance to
misspell it.

**Seal declares no edge it would have to infer.** It knows which
services declared a reset; it does not know which of them any one outcome
actually reads. A dependency nobody asked for is a slower run at best and a
cycle at worst, so the project names the edges it needs.

### Where a project root is, and why the rule is what it is

`seal run`/`up`/`ci` walk up from the current directory for one with
both its own `Tiltfile` and a `services/` subdirectory. A service's own
directory has a `Tiltfile` too, but never its own nested `services/`, so the
search is unambiguous without a marker file to keep anywhere.

### The two exceptions, and why they are exceptions

Nothing about a directory of promises says what image starts them, and
nothing about a `.env` reference says which vault holds the item. Both facts
are real, and neither is in the tree -- so both are declared.

Being declared is exactly what makes them the two places the tree and a
declaration can drift apart, and both are checked for it: `seal check`
refuses a group no runner names and a runner naming no group, and a `.env`
naming a scheme no provider declares.

A second config-file format would be a second thing every adopting project
has to learn, which is why both are JSON, both named `<subject>-config.json`,
and both sit where the thing they describe already lives.

## Consequences

- **A project's own files carry more meaning.** The root Tiltfile is not
  boilerplate: it is the service list, and its order matters.
- **Nothing can be listed without existing.** There is no way to declare a
  service that isn't there, because declaring one means `include()`ing a real
  file.
- **What a walk cannot see, Seal cannot know.** Which promises exist is
  the tree's business; which of them a change should satisfy is not something
  the layout answers ([RFC 0009](0009-outcome-tests.md)).

## Alternatives considered

**An `seal.json` mapping names to paths.** It would make discovery a
file read rather than a Tiltfile evaluation, and it would make every added
service a two-step job whose second step fails silently. The evaluation costs
one process and needs no cluster.

**Inferring dependency edges from the manifests.** A Deployment that mounts a
Secret or names a Service implies an ordering, and Seal could declare
it. It would be guessing at dependencies the manifests only imply, and a
wrong guess is a cycle in somebody else's project.
