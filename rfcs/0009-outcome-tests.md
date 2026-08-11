# RFC 0009: Outcome tests and unattended merge

| | |
| --- | --- |
| **Status** | Accepted. The half that lives in a repository's settings is a project's to apply, by design |
| **Related** | [0001](0001-library-boundary.md), [0010](0010-outcome-tree.md), [0012](0012-translation-and-review.md), [0013](0013-regression-loop.md) |
| **How-to** | [The merge gate](../docs/guides/merge-gate.md), [Outcome tests](../docs/guides/outcomes.md) |

## Context

The goal is a pull request that can merge on its own say-so for changes
covered by outcome tests -- a person's or a coding agent's -- **not because
anybody trusts the author**, but because the author cannot merge without
satisfying tests they cannot quietly rewrite.

Nothing about a green suite shows the difference that matters. A suite passes
identically whether the application was fixed or the failing test was edited.
Left to the author, telling those apart is a judgment call -- "is this a
regression, or has the spec changed?" -- made by the party with an interest
in the answer, at the moment it is least convenient to answer honestly.

This is the design the rest of the outcome series serves. It only works for
changes an epic's outcome tests actually cover; it is not a replacement for
human review generally, but a way to make specific, well-specified functional
promises self-enforcing.

## Decision

**Make the two cases structurally different rather than asking which one this
is.**

- **Fix the application, merge unattended.** Every currently-committed outcome
  test still passes, and nobody has to look at the diff.
- **Change what a test asserts, get a human.** The diff touches a path under
  `CODEOWNERS`, so the platform blocks the merge until a code owner approves.

The whole outcome tree is owned -- prompts, translations, shared helpers,
fixtures and quarantine notes alike. `seal check` refuses a tree the
gate does not cover, and `seal ci` runs that check before it starts.

The half that turns `CODEOWNERS` into a block -- branch protection -- is a
repository setting, and Seal deliberately does not apply it.

## Rationale

### Why the gate is structural rather than a classification

An author who cannot find an application fix has exactly one move left, and
it is the one that ends with a person reading the change. That is the
mechanism: not a rule about what an agent should do, but a fact about what it
*can* do without review.

It also converts the "regression or spec change?" question from an opinion
into an experiment. Whether the application *can* be patched to satisfy every
outcome test at once settles it: if it can, it was a regression; if keeping
one promise necessarily breaks another, that is a real conflict between what
the project claims, at least one promise has to change, and that routes
through a human by construction ([RFC 0013](0013-regression-loop.md)).

One consequence is deliberate: **an application fix that satisfies every
outcome test merges unattended even when it is a substantial rewrite.** The
outcome tests are the spec being enforced, not a proxy for "small diff".

### Why this lives in Seal rather than a separate tool

An outcome test drives several services together -- that is what makes it an
outcome test -- so it needs a reproducible multi-service environment to run
against. The outcome-test layer is downstream of the
environment-reproducibility layer by necessity, not by convenience: you
cannot write the high-level test without the low-level substrate existing
first.

Both halves of that substrate come *before* the loop that has to survive
them: an environment reproducible enough to judge against
([RFC 0003](0003-readiness.md), [RFC 0004](0004-deterministic-state.md)), and
a tree locked in by review so a failing test cannot be edited away.

The scope boundary applies here too: an outcome test verifies that the
*built* application behaves correctly, run against a throwaway cluster -- not
that a *deployed* one does ([RFC 0001](0001-library-boundary.md)). Nothing in
this design may end up assuming an outcome test needs a named environment or
a real registry.

### Why the prompt is owned as well as the test

A promise and its translation are separate artifacts
([RFC 0010](0010-outcome-tree.md)), and both are covered by the same rule.
The prompt is what an epic promises; an author free to rewrite the promise
never has to touch a test to change what the project claims.

The same reasoning reaches three more things inside the tree:

- **Fixtures**, which sit inside an outcome's own directory. A test can be
  defanged from either end -- change what it asserts, or change the data it
  asserts against.
- **A group's shared helpers.** What several translations share is as likely
  to be the assertion as the navigation, so a helper reachable without review
  defangs every test importing it without touching a test at all.
- **A quarantine note**, which says a failure in this outcome does not fail a
  run. It lives inside the outcome's directory for exactly this reason:
  whatever rule covers the tree covers it, with nothing to remember to add. A
  quarantine an agent could add for itself would be a way to a green suite
  that never went near the application.

### Two properties of CODEOWNERS decide whether a rule holds

Both are easy to get wrong by hand, and both fail silently:

- **The last matching rule wins**, not the most specific. A broad rule over
  the tree is overridden for anything a later rule matches.
- **A rule with no owners clears ownership.** A pattern on a line of its own,
  anywhere below the tree's rule, unlocks everything it matches.

So the check does not merely look for a rule mentioning the tree. It reads
the file the way the platform does and reports: an outcome directory no rule
reaches or whose last matching rule names no owner; a file inside an owned
outcome that a later rule unowns; and an outcome tree with no `CODEOWNERS`
anywhere the platform reads one.

Findings are reported at the **directory**, because covering a directory is
what covers the files added to it later; a rule written per file is one
somebody has to remember to extend. Every offender is reported at once, so a
project puts its file right in one pass.

The file is read from the enclosing **git repository**, not the project root
-- a project inside a larger repository is governed by that repository's
file, at patterns carrying the project's own directory prefix. There is
deliberately no environment variable to point this elsewhere, unlike the
manifest and outcome directories: a file the platform never reads owns
nothing, so an escape hatch here would only let a project pass a check while
having no gate.

A project that declares no outcomes passes silently. Outcome tests are
something a project adopts, and there is no gate to ask for over nothing.

### The half Seal cannot check

`CODEOWNERS` on its own blocks nothing. Without branch protection it assigns
reviewers and lets a pull request merge unreviewed. Three settings turn it
into a gate: require a pull request before merging, require review from code
owners, and require the status check that runs the suite.

Seal does not apply them ([RFC 0001](0001-library-boundary.md)). They
live in a repository's settings rather than its contents, so reaching them
means an admin-scoped token granted to a tool that then cannot verify from a
checkout whether the settings took.

Which means a green check says the tree is **owned**, not that a merge is
**gated**. Saying so plainly is the honest version; claiming the second would
be a promise nobody could check.

### What the gate does not claim

It makes an outcome test un-editable without review. It says nothing about
whether the tests it protects ran -- a gate over tests nobody executed is a
gate over nothing. Unattended merge needs both halves: every outcome test run
in one pass ([RFC 0010](0010-outcome-tree.md)), and every one of them
un-editable without a human.

Running them is still not the same as covering them. A suite reports every
promise a project has *translated*, and a promise nobody has written a test
from yet is reported as exactly that rather than counted as kept. A green
suite is a claim about the promises in the tree; what belongs in the tree
stays a human's judgement.

### Flakiness is handled at the environment layer

Multi-service end-to-end tests are the most flake-prone class of test there
is, and every false failure costs real time -- or worse, produces a spurious
fix. The policy is to handle it where the cause is, rather than by asking
authors to write more defensive tests:

- **Reproduce before triage.** A single failure does not enter the regression
  loop; it is re-run on its own from a baseline first
  ([RFC 0013](0013-regression-loop.md)).
- **Fix causes, not symptoms.** Startup races, shared state between runs,
  wall-clock and random-id dependence: these belong to the environment's
  isolation story, which is already Seal's job.
- **Track what changes its mind.** A test that fails one run in four looks
  ordinary in any single one of them, so the evidence is accumulated across
  runs and reported. It concludes nothing.
- **Quarantine is the declared exception**, and a code owner's call like any
  other change under the tree.
- **Constrain how a test waits**, which is the one mechanical rule a check
  can hold ([RFC 0012](0012-translation-and-review.md)).

Mocking externalities is deliberately unsettled: a convention written before a
service that really calls out exists would have no user. The epic that
introduces one also has to settle where an *inspectable* double plugs in --
keeping a call off the network is only half of it, since a test usually has to
observe the call it stubbed.

## Consequences

- **A red suite has exactly two exits**, and one of them costs a human's
  attention. That is the design working, not friction to be smoothed.
- **Review is concentrated in one place.** The translation is the only thing
  on the everything-is-green path that needs a person, which is what makes the
  review worth doing properly ([RFC 0012](0012-translation-and-review.md)).
- **A project can adopt half of this and get half the value**, visibly: the
  check says the tree is owned, and the settings that make ownership blocking
  are somebody's job to apply.
- **Substantial rewrites merge unattended** when every promise still holds.

## Alternatives considered

**Asking the agent to classify the failure** -- "is this a regression or a
spec change?" -- and reviewing only the spec changes. It puts the judgment
with the party that benefits from one answer, at the worst possible moment.

**Reviewing every diff.** The status quo everywhere, and the thing this design
exists to make unnecessary for well-specified promises.

**Seal applying branch protection itself.** It would close the gap in
one command, and it would need admin scope and could not verify the result.

## Open questions

- **How a run decides which outcome tests are in scope for a given change.**
  The suite runs all of them, every time. The layout gives a scoped answer
  somewhere to come from -- an epic is a directory -- but which of the two a
  merge should rest on is undecided.
- **How a promise gets retired or superseded** as a project evolves, beyond
  "editing one is a diff under the tree like any other" -- whether an epic's
  prompts are archived rather than deleted, for history.
