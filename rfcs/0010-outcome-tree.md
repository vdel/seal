# RFC 0010: The outcome tree

| | |
| --- | --- |
| **Status** | Accepted |
| **Related** | [0002](0002-declaration-by-structure.md), [0009](0009-outcome-tests.md), [0011](0011-outcome-runners.md), [0012](0012-translation-and-review.md) |
| **How-to** | [Outcome tests](../docs/guides/outcomes.md) |

## Context

A project's promises have to live somewhere that survives independently of
any one session -- they are what future sessions translate and re-translate
against, which rules out anything whose home is an issue or a pull-request
description.

And a reviewer looking at a translated test has to be able to reach the
promise it came from. Without that there is nothing to check the test's
intent against, only whether it happens to pass -- and checking intent is the
entire job the review exists to do ([RFC 0009](0009-outcome-tests.md)).

## Decision

**A promise and its translation share a directory**, and the filesystem is
the whole declaration:

```
outcomes/
  seal-test-config.json   # which runner drives each group
  <group>/
    helpers/                    # what this group's tests share
    <epic>/
      <outcome>/
        prompt.md               # the promise
        quarantine.md           # optional: why a failure here doesn't fail a run
        ...                     # the test translated from it
```

- **The prompt is the source of truth.** Its first non-blank line is an H1
  headline, and that headline is the only thing read mechanically.
- **A group holds only epics plus `helpers/`; an epic holds only outcomes.**
  Slugs at all three levels are lowercase letters, digits and single hyphens.
- **The tree sits at the project root**, not under any one service.
- **An outcome with only a prompt is untranslated**, which is a legitimate
  state. **A test with no prompt is refused.**
- A suite reports three states, and only two of them are red: `PASS`/`FAIL`,
  **`no verdict`** for a translated outcome that left nothing to read, and
  **`no test yet`** for a promise nothing has been translated from.

## Rationale

### The prompt is the promise; the test is one reading of it

An outcome prompt is written the way somebody using the application would put
it -- "an item I add is still on the list after a reload". A low-level test is
one agent's translation of that promise against the implementation as it
stands: specific services, specific calls, specific fixtures.

Translating is lossy. The same prompt yields different tests in different
hands, each encoding implementation choices the prompt never specified. So the
prompt is what an epic actually promises, and the test is a reading of it that
a human has to be able to check.

Which is why a prompt is written in the application's own terms and no lower.
An endpoint, a selector, a table or a service name in a prompt is an
implementation choice that belongs in the translation, where it can change
without the promise changing.

And why a prompt promises something about the *application*, to whoever uses
it -- never something about the test harness. "The list starts from the same
three items every run" is not a promise the application makes to anybody; it
is the reset mechanism's own contract
([RFC 0004](0004-deterministic-state.md)), already guaranteed elsewhere.
Restating it as a promise would spend a human's review checking
test-infrastructure behaviour against a promise that was never the
application's to keep.

The headline is what names the outcome wherever it is reported, rather than
the slug -- so a report reads as promises rather than as paths. Everything
below it is prose for whoever translates: context, edge cases worth covering,
and -- just as binding -- what the promise deliberately does *not* claim.

### Traceability is what shapes the layout

An outcome is a directory, so the pairing is the filesystem's own rather than
something a registry has to be kept in agreement with
([RFC 0002](0002-declaration-by-structure.md)). Walking the tree is the whole
discovery mechanism.

**The translation is everything else in the directory**, deliberately
language-agnostic: finding a project's tests should not require knowing
whether they are specs, a Python file or a shell script. Fixtures a single
test needs sit beside it; what several share goes up one level.

**A prompt with no test is allowed; a test with no prompt is not.** The first
is a promise written down before anything compiled it into a test, which is a
state a project legitimately sits in -- and forbidding it would mean a prompt
could only ever land in the same change as its test. The second is a test
whose intent cannot be reviewed, which is the one thing the layout exists to
prevent.

**The tree sits at the project root** because an outcome test drives several
services at once -- that is what makes it an outcome test -- so there is no
one service it belongs to.

**Slugs are held to what three readers agree on.** A slug is a path
component, a test identifier in a report, and a `CODEOWNERS` pattern all at
once. Kubernetes name limits reach it too, since a runner's resources are
named from it.

### The group is what a runner drives

A project's promises are not all of one kind, and neither are the things that
test them. A promise about what somebody sees is only really tested through a
browser; a promise an API-only service makes is tested by talking to the API.
So outcomes are grouped, one group per runner, and the group is the directory
above an epic ([RFC 0011](0011-outcome-runners.md)).

### Helpers: their own directory, at the group's root

Every promise a group makes is tested through the same application, so its
translations repeat themselves: signing in, reaching a page, reading a value
back off it.

**Its own directory rather than an epic**, because epics hold promises and
this holds none. An epic named `helpers` would have every outcome under it
reported as a promise nothing tests, so the name is reserved and a prompt
below it is refused rather than passed over.

**At the group's root and nowhere higher**, because that is the runner's
build context: a group's image is built from that directory, so a helper any
higher is not in the container that has to import it. Two groups with
something genuinely in common share it the way they share anything else -- a
runner whose build context names a directory holding both.

**Nothing is asked of what is in there.** A helper is imported by a test
rather than started by a runner. Two things are refused, both of them a file
reading as something it cannot be: a promise, and a spec file under a runner
that is pointed at one outcome's directory at a time -- it would sit where a
run never looks. A helper that waits on the clock is refused for the same
reason a test that does is, and harder: every outcome importing it inherits
the wait.

**What belongs in a helper is what a promise does not turn on.** A code owner
approves a translation by reading it against its prompt, so the claim the test
makes stays in the test; navigation, setup and reading the page back are what
move.

### Every outcome, every run

A fix scoped to the one test somebody was looking at can break another that
nobody re-ran. So what the suite has to be able to report is "every promise
this project has translated still holds" -- and a listing that leaves an
outcome out is indistinguishable from one where it passed.

That is the claim a merge rests on, which is why the exit code is the suite's
own verdict rather than a summary of one, and why a gate never runs a subset:
a gate on the tests somebody remembered is not a gate.

Naming outcomes on the command line is the other thing entirely -- what
somebody iterating on one translation needs, since paying for the other twenty
on every edit is how a local loop stops being used. It says what it left out,
in as many words, because a summary that didn't would read like a full run.

A slug that names nothing is an error listing the ones that exist, rather than
a run of no outcomes: a typo that quietly selected nothing would report green,
which reads exactly like a run where every promise was kept.

### One at a time

Outcome tests drive the same application, so running them at once would mean
each asserting on a list the others are adding to and deleting from -- and a
promise that holds failing for what another test was doing is the least useful
failure a suite can produce.

One container runs a whole group, so what serialises outcomes is the runner;
groups are serialised in turn by each waiting for the one before it. What that
costs is wall-clock. What would buy it back is isolation per outcome rather
than per run, which is left to the loop that would feel it first
([RFC 0013](0013-regression-loop.md)).

### Three states, and only two of them are red

- **`PASS`/`FAIL`** -- the test ran and said so.
- **`no verdict`** -- a translated outcome that left nothing to read. That is
  a *failure*, not a gap: a test that did not run is exactly what a green
  suite must not be able to claim on a promise's behalf, and every way a test
  silently fails to run looks like an absent file from here.
- **`no test yet`** -- a promise nothing has been translated from. Reported,
  counted, and not a failure: there is nothing for the application to satisfy.

Which promises have no test yet is the question the listing opens with -- it
is what whatever writes the missing translations asks first -- so it is a
column rather than something to infer, and there is a bare-slug form for the
caller that parses it. The rest of the listing stays human-readable: a general
machine-readable form belongs with the first caller that actually parses one.

### Quarantine, and why it lives in the outcome's directory

Sometimes a promise keeps failing for a reason no application fix will settle:
the test does not own the data it asserts on, or it is not deterministic.
Fixing that is its own change, and until it lands the promise should not block
every merge -- but switching the test off is not the answer either, because
then nothing says it is missing.

So a quarantine is a note in the outcome's own directory whose whole content
is the reason. The outcome still runs and is still reported; what changes is
that a failure there does not fail the run.

**It is never reported as a pass.** A green suite has to stay a claim about
promises that were kept, and excusing one from failing the run is not the same
as saying it held.

**It needs a code owner, and no new rule.** Living inside the outcome means
whatever `CODEOWNERS` rule covers the tree covers it
([RFC 0009](0009-outcome-tests.md)). That is the whole reason it lives there.

**A quarantine with no reason is refused.** A test somebody switched off and a
test whose determinism somebody is fixing look identical from the tree, and
the reviewer approving the diff is the person who has to tell them apart.

### Evidence about flakiness, and no threshold

Each run appends what it found, per outcome, and the listing reads back how
often each promise's verdict *changed*. Changes rather than failures: a
promise red every run since somebody broke it is a regression, and the suite
already says so each time. What this finds is the one that has been red and
green in the same window with nothing deciding which.

**It concludes nothing and quarantines nothing.** A rate is evidence; whether
the test is at fault, or the application is genuinely intermittent, or the
environment is, is a judgement. There is deliberately no threshold either: a
number picked before anything had a use for one is guidance dressed as a rule.

### What the layout is worth is what enforces it

The rules above are only worth as much as the check that refuses a tree
breaking them, and `seal ci` runs that check before starting anything.
Two things are deliberately *not* failures: an outcome with a prompt and no
translation, and a project with no outcome tree at all -- which passes
silently, because saying so on every run would train people to read past the
output.

Every offender is reported at once, so a project puts its tree right in one
pass rather than one failed run at a time.

## Consequences

- **The tree is the spec, and it is read by walking.** Adding a promise is
  adding a directory; nothing else has to hear about it.
- **A promise costs a directory and a headline** before anybody writes a test,
  which is what makes writing promises down cheap enough to do first.
- **A run is serial.** Wall-clock is the price of every outcome asserting on
  an application nothing else is touching.
- **Everything in the tree is under review**, including data and notes -- so
  the tree is a place to put things deliberately, not a scratch directory.

## Alternatives considered

**A registry mapping tests to prompts.** It would allow any layout, and it
would be the one file that can disagree with the tree it describes.

**Prompts in issues or pull-request descriptions.** Where promises are usually
written, and they do not survive the session that wrote them, cannot be
diffed, and cannot be owned by a `CODEOWNERS` rule.

**Tests under the service they exercise.** Natural for a unit test, and wrong
for a test whose whole point is that it drives several services at once.

**Retrying a failing outcome until it passes.** The cheapest way to a green
suite, and it papers over exactly the flakiness the environment layer exists
to remove.
