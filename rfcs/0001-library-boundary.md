# RFC 0001: The library boundary

| | |
| --- | --- |
| **Status** | Accepted |
| **Related** | [0002](0002-declaration-by-structure.md), [0008](0008-run-axes.md), [0009](0009-outcome-tests.md) |
| **How-to** | [How Seal fits together](../docs/concepts.md) |

## Context

Seal sits between a project's own code and everything that happens to
a build afterwards. Both edges are easy to drift across: a helper that
happens to fit the worked example, a convenience that reaches a cluster, a
command that starts an agent and reports what it did. Each one is small on
its own, and each one moves a fact that belongs to a project into a library
that then has to keep guessing at it.

So the boundary needs stating once, as the standard every other decision
here is held to.

## Decision

**Seal is a library.** `tilt/` and `python/` are the deliverable, plus
the agent-facing half in `.claude/`; `examples/angular-django/` consumes them
and is never where a capability lives.

Three things follow, and they are refusals rather than gaps:

1. **It knows nothing about any application.** No default port, path,
   framework or service name. Where the generic side needs something only a
   project can say, the project says it.
2. **It builds and tests; it never deploys to a named environment.** Nothing
   here knows about a cluster, a registry, an ingress or a domain -- a run
   that publishes pushes to a registry the project named, and Seal
   never learns which one ([RFC 0008](0008-run-axes.md)).
3. **It claims no capability it cannot verify from a checkout.** That rules
   out applying a repository's settings, and it rules out starting an agent.

## Rationale

### The example is a consumer, not a substrate

Code written against `examples/angular-django/` passes every test in this
repository and gives an adopting project nothing. A test over the example's
own files tests the example; it says nothing about the next project. The
example earns its keep by being run end to end in CI, which is a different
job from proving a capability exists.

The test to apply to any change: **a project that doesn't live in this
repository -- would it get this?**

That is also why a product name in the deliverable is a defect rather than a
detail. A store named in `python/` or `tilt/` is a project having to change
Seal to use a store Seal happened not to think of, which is the
same failure in a different costume (see [RFC 0006](0006-credential-resolution.md)).

### Deploying is somebody else's job, and the boundary is load-bearing

Everything a build passes through after this repository's job is done lives
in a separate deployment toolkit, which consumes a project built this way
rather than the other way around.

This is not modesty about scope. An outcome test verifies that the *built*
application behaves correctly, run against a throwaway cluster -- not that a
*deployed* one does. Keeping the two apart is what lets the whole gate run
on a cluster created and discarded per run, where the worst case of a
misbehaving run is a dead Kind cluster.

The same boundary has a security shape. A reusable workflow that accepted a
kubeconfig would accept a credential granting cluster write; its worst case
would stop being a throwaway cluster and start being production. What is
worth sharing between the two sides is the flag vocabulary
([RFC 0008](0008-run-axes.md)), not the credentials.

### A checkout is the unit of verification

Two capabilities are conspicuously absent, for one reason.

**Seal does not apply a repository's settings.** Branch protection is
what makes a `CODEOWNERS` rule blocking rather than advisory, and it lives in
a repository's settings rather than its contents. Reaching it means a token
with admin scope, granted to a tool that cannot then verify from a checkout
whether the settings took. So `seal check` reports that the outcome
tree is *owned*, and whoever administers the repository makes it *gated*
(see [RFC 0009](0009-outcome-tests.md)).

**Seal starts no agent and configures no agent command.** What an agent
session did is not something a checkout can verify. A "run this command each
iteration" seam would have Seal reporting a loop whose steps it cannot
vouch for. Instead it ships the instructions -- the skills and subagents in
`.claude/`, installed into an adopting project -- and makes each step of the
loop one command whose answer comes from re-running the suite
([RFC 0013](0013-regression-loop.md)).

Both are the same rule: a capability Seal cannot verify from a checkout
is one it doesn't claim.

### The agent-facing half ships too

`.claude/` is part of the deliverable rather than this repository's own
configuration. An adopting project installs those skills so that a coding
agent working in *that* repository discovers Seal and uses it
correctly.

Which puts them under the same two rules as the rest: every claim in a skill
has to be something the CLI, the extensions or the checks actually do, and
none of them may name an application's framework, port, path or service. A
skill promising behaviour Seal doesn't have is worse than a missing
skill -- it is a promise made to a reader with no way to check it.

## Consequences

- **A project states more.** The address an outcome test reaches the
  application at, which resources have to be serving first, what putting a
  service's state back involves, which readiness probe is right: all of these
  are the project's, and Seal fails loudly rather than guessing. That is
  more to write once, against never being wrong by default.
- **Some things have no home here at all.** Deploying to a named environment,
  applying branch protection, driving an agent session. Each is a real need,
  and each is met somewhere Seal can be honest about.
- **The example carries weight it cannot be given credit for.** It proves
  the capability end to end; it never *is* the capability.

## Alternatives considered

**A framework you generate a project from.** It would settle every question
this boundary leaves to a project -- and settle it as a default that happens
to fit whichever application the generator was written against. The refusals
above are what a library has instead of defaults.

**Reaching just far enough to be useful** -- applying the branch protection
that makes the gate real, or driving the agent that fixes a red suite. Both
would make a green run mean less, not more: a report about settings that may
not have taken, and a loop whose steps a checkout cannot confirm.
