# Outcome tests

Where a project keeps the promises its application makes, the tests
translated from them, and how the whole suite is run and reported. This is
the layer a merge gate rests on.

## The prompt is the source of truth

An outcome prompt is a promise, written the way somebody *using* the
application would put it:

> an item I add is still on the list after a reload

A low-level test is one reading of that promise against the implementation
as it stands -- specific services, specific calls, specific fixtures.
Translating is lossy: the same prompt yields different tests in different
hands, each encoding implementation choices the prompt never specified.

So the prompt is what the project actually promises, and the test is a
reading of it that a human has to be able to check. Which means a reviewer
looking at a test must be able to reach the prompt it came from -- otherwise
there's nothing to check its intent against, only whether it happens to
pass.

## The layout

That traceability is what shapes the tree: **a prompt and its translation
share a directory.**

```
outcomes/
  seal-test-config.json  # what runs each group
  <group>/
    helpers/             # what this group's tests share
    <epic>/
      <outcome>/
        prompt.md        # the promise
        ...              # the test translated from it
```

An outcome is a directory, so the pairing is the filesystem's own rather
than something a registry has to be kept in agreement with. Walking the tree
is the whole discovery mechanism.

The rules:

- **A group holds only epic directories, plus `helpers/`; an epic holds only
  outcome directories.** A prompt or test filed at any other depth has no
  outcome directory to be paired inside. (A group run by a `custom` runner
  keeps files at its own level too: they are that runner's build context.)
- **Slugs are lowercase letters, digits and single hyphens** at all three
  levels. A slug is a path component, a test identifier in a report and a
  `CODEOWNERS` pattern all at once, so it's held to what all three read the
  same way.
- **The tree sits at the project root**, not under `services/<name>/`. An
  outcome test drives several services at once -- that's what makes it an
  outcome test rather than a unit test -- so there's no one service it
  belongs to.
- Keeping the tree somewhere else? Name that directory in
  **`SEAL_OUTCOMES_DIR`**.

The group above an epic is what a runner drives -- see
[Outcome-test runners](runners.md).

## The prompt file

`prompt.md`, whose first non-blank line is an ATX H1:

```markdown
# an item I add is still on the list after a reload

Adding an item is the one thing this list is for, and a list that forgets
it on the next page load is broken however good the rest of it looks.
Reload means a fresh page load against the same running environment, not a
re-seeded one.
```

The headline is the single thing read mechanically -- it's what names the
outcome in a report, rather than the slug. Everything below it is prose for
whoever translates the prompt: context, edge cases worth covering, and what
the promise deliberately does *not* claim.

**Write the promise in the application's own terms and no lower.** An
endpoint, a selector, a table or a service name in a prompt is an
implementation choice that belongs in the translation, where it can change
without the promise changing.

**A prompt promises something about the application, to whoever uses it** --
never something about the test harness that exercises it. "The list starts
from the same three items every run" isn't a promise the application makes
to anybody; it's the [reset mechanism's](resetting-state.md) own contract,
already guaranteed elsewhere. Restating it as a prompt would spend a human
review checking test infrastructure against a promise that was never the
application's to keep.

## The translation

Everything in the outcome's directory besides `prompt.md`. That's
deliberately language-agnostic: finding a project's tests shouldn't require
knowing whether they're Playwright specs, pytest or a shell script. A test
that needs fixtures of its own keeps them beside itself; what several tests
share goes one level up, in [the group's
`helpers/`](#helpers-what-a-groups-tests-share).

An outcome directory holding only its prompt is **untranslated** -- a
promise written down before anything compiled it into a test. That's a state
a project legitimately sits in, and it's reported rather than failed. See
[Translating a promise](translating-promises.md) for what gets it out of
that state.

The reverse is what the layout rules out: a test with no prompt to trace it
back to.

## Helpers: what a group's tests share

Every promise a group makes is tested through the same application, so the
translations repeat themselves: signing in, reaching a page, reading a value
back off it. `helpers/` at the group's root is where that goes.

```
outcomes/
  ui/
    helpers/
      todo-page.ts       # imported by the specs below
    todo-list/
      an-item-survives-a-reload/
        prompt.md
        an-item-survives-a-reload.spec.ts
```

Import it the way any other file is imported. Nothing has to put it in the
image: a runner is built from the group's own directory, so a spec reaches
it as an ordinary relative path -- `../../helpers/todo-page` from an
outcome.

- **At the group's root, and nowhere higher.** That directory is the build
  context, so a helper above it isn't in the container that has to import
  it. Two groups that genuinely share something share it the way they share
  anything else: a `custom` runner whose `dockerfile_context` names a
  directory holding both (see [Runners](runners.md)).
- **It holds no promises.** `helpers` is not a name an epic can have -- a
  `prompt.md` below it is refused rather than passed over, because nothing
  walks that directory for outcomes and the promise would run nowhere.
- **Under the `playwright` runner, no spec files either.** A run is pointed
  at one outcome's directory at a time, so a spec here is collected by
  nothing and its failures are seen by nobody.
- **Keep the assertion in the test.** A code owner approves a translation by
  reading it against its prompt, so what the promise turns on belongs where
  they'll read it. Navigation, setup and reading the page back are what move.
- **Helpers are owned like everything else in the tree.** The same
  `CODEOWNERS` rule covers them, and for a sharper reason than tidiness: an
  assertion moves into a helper as readily as anything else, so a helper
  anybody could edit unreviewed defangs every test importing it (see
  [The merge gate](merge-gate.md)).

Otherwise nothing is asked of what's in there. A helper is imported by a
test rather than started by a runner, so what it's called and what it holds
are yours.

## Listing what a project promises

```sh
seal outcomes                          # over ./outcomes
seal outcomes --outcomes-dir promises  # look somewhere else, just this once
```

```
ui/todo-list/an-item-survives-a-reload  translated   an item I add is still on the list after a reload
ui/todo-list/deleting-is-permanent      no test yet  deleting an item takes it off the list for good

2 outcome(s), 1 translated.
```

`translated` means there's a test the run can actually start -- one the
group's runner collects -- not merely that the directory holds something
besides the prompt.

Which promises have no test yet is the question this opens with, so it's a
column rather than something to infer. And because that question has a
caller that parses the answer, it has a form for one:

```sh
seal outcomes --untranslated
```

```
ui/todo-list/deleting-is-permanent
```

Bare slugs, one per line, in the tree's own order -- nothing to strip, and
nothing at all where every promise has a test.

## Wiring the tree into your project

One call from your root Tiltfile, after every service is `include()`d:

```python
load('ext://seal', 'register_outcome_runner', 'reset_resource_name')

register_outcome_runner(
    base_url='http://web:8000',
    resource_deps=[reset_resource_name('example-api')],
)
```

**`base_url`** is where the application answers, as an outcome test reaches
it *from inside the cluster*. Your project says it because only your project
can -- Seal knows nothing about your service names or ports. Every runner
gets it as `SEAL_BASE_URL`, and the `playwright` runner makes it
Playwright's `baseURL`, so a spec navigates with `page.goto('/')` rather
than an address it would have to keep in agreement with the manifests.

**`resource_deps`** is what every outcome test waits for, and it's yours to
name for the same reason: only you know which resources have to be serving
before a test means anything, and which services have to be at a known
baseline first. Naming a service's reset here is what makes "the list starts
from these three items" something a test can rely on.

That one call builds each group's runner image, runs every translated
outcome against the environment Tilt has just brought up -- a group at a
time -- and brings the verdicts back.

Under `seal ci` the suite runs as part of the same pass, so a green CI
run means every promise still holds. Under `seal up` it's registered
and waits to be asked: spending a whole outcome suite on every start of a
session you're about to work in is how a local loop stops being used.

## Running the suite

From the project root:

```sh
seal outcomes run
```

```
ui/todo-list/a-deleted-item-stays-deleted     FAIL         deleting an item takes it off the list for good
ui/todo-list/an-added-item-survives-a-reload  PASS         an item I add is still on the list after a reload
ui/todo-list/ticking-an-item-off-the-count    no test yet  ticking an item off updates how many are left

3 outcome(s): 1 passed, 1 failed, 1 with no test yet.
```

The exit code is the suite's verdict, not a summary of one -- which is what
lets `seal ci` gate on it.

**Reading a run, and asking for one.** With nothing named, this reads the
verdicts a run already left behind -- which is the form `seal ci`
gates on, after Tilt has driven the suite in the same pass. `--all` runs
every promise the tree holds here and now, against a session that is already
up:

```sh
seal outcomes run --reset --all
```

```
ui/todo-list/a-deleted-item-stays-deleted     PASS         deleting an item takes it off the list for good
ui/todo-list/an-added-item-survives-a-reload  PASS         an item I add is still on the list after a reload
ui/todo-list/ticking-an-item-off-the-count    no test yet  ticking an item off updates how many are left

3 outcome(s), run just now against the session already up: 2 passed, 1 with
no test yet.
```

Both cover every promise, so neither disclaims anything -- and the summary
says which one it is, because a verdict read from a run somebody else
performed and a verdict this command went and got are worth telling apart.
`--all` is what a loop iterating towards green re-runs each time round: the
whole suite, without paying for a fresh cluster on every iteration. Naming
slugs remains the other thing entirely, and still says what it left out.


**Every outcome, every run.** A fix scoped to the one test somebody was
looking at can break another nobody re-ran, so what the suite has to be able
to report is "every promise this project has translated still holds". A
listing that leaves an outcome out is indistinguishable from one where it
passed.

**One at a time.** Outcome tests drive the same application, so running them
at once would mean each asserting on a list the others are adding to and
deleting from -- and a promise that holds failing because of what another
test was doing is the least useful failure a suite can produce. One
container runs a whole group, so serialising within a group is the runner's
job; groups are serialised in turn by each waiting for the one before it.

### The three states

| State | Meaning |
| --- | --- |
| **`PASS`** / **`FAIL`** | The test ran and said so. |
| **`no verdict`** | A translated outcome left nothing to read. **This is a failure, not a gap**: a test that didn't run is exactly what a green suite must not be able to claim on a promise's behalf, and every way one silently fails to run looks like an absent file from here. |
| **`no test yet`** | A promise nothing has been translated from. Reported, counted, and not a failure -- there's nothing for the application to satisfy. |

Each runner writes a verdict per outcome, and they reach your project as
`tests-results/outcomes/<group>/<epic>/<outcome>/` -- beside where each
service's own test results land. `seal outcomes run` reads all of them at
once.

## Confirming a failure before anything acts on it

Multi-service end-to-end tests are the most flake-prone class of test a
project runs, and a failure chased on one observation is agent time spent on
noise -- or worse, a "fix" for a bug that was never there. `--confirm` puts a
second run behind every failure first:

```sh
seal outcomes run --reset --all --confirm
```

```
ui/todo-list/a-deleted-item-stays-deleted     FAIL (confirmed)      deleting an item takes it off the list for good
ui/todo-list/an-added-item-survives-a-reload  FAIL (not confirmed)  an item I add is still on the list after a reload
```

Each promise that failed is run **again, on its own, from a reset**. Both
halves carry weight. Retried in place, a failure is retried against the state
that may have caused it, which is how a shared-state bug gets papered over
rather than found. Run alongside the others, it is run against what they are
doing to the same application -- and a promise that fails in the suite and
holds by itself is a test that doesn't own the data it asserts on, which is a
third thing again.

- **Confirmed** -- it failed again. This is the application to fix.
- **Not confirmed** -- it held. Not something an application fix will settle:
  the test either doesn't own its data or isn't deterministic. The failing
  run is kept beside the one that held, so the two can be compared.

**It changes no verdict.** A promise this run did not see kept is one it did
not see kept, so an unconfirmed failure still fails the run and is never
reported as a pass. What a second run buys is a reason attached to the
failure, not a way out of it -- and a red test re-run until it goes green is
exactly the retry the runners already refuse to do.

**Once, not until it passes**, and only what was red: a confirmation costs a
whole run each, and a promise that held has nothing to reproduce.

## When a test is the problem: quarantine

Sometimes a promise keeps failing for a reason no application fix will
settle: the test doesn't own the data it asserts on, or it isn't
deterministic. Fixing that is its own change. Until it lands, the promise
shouldn't block every merge -- and switching the test off isn't the answer
either, because then nothing says it is missing.

A **quarantine** is a `quarantine.md` in the outcome's own directory, whose
whole content is the reason:

```
outcomes/ui/todo-list/a-deleted-item-stays-deleted/
  prompt.md
  a-deleted-item-stays-deleted.spec.ts
  quarantine.md
```

```markdown
The delete button races the list re-render, so this fails on a loaded runner
about one run in five. Being rewritten to wait on the row disappearing.
```

A quarantined outcome still runs and is still reported. What changes is that
a failure there doesn't fail the run:

```
ui/todo-list/a-deleted-item-stays-deleted  FAIL (quarantined)  deleting an item takes it off the list for good

1 outcome(s): 1 failed -- 1 of them quarantined, so a failure there did not
fail this run.
```

**It is never reported as a pass.** A green suite has to stay a claim about
promises that were kept, and excusing one from failing the run is not the
same as saying it held.

**It needs a code owner, and no new rule.** The note lives in the outcome's
directory, so whatever CODEOWNERS rule already covers the tree covers this
(see [the merge gate](merge-gate.md)). That is the whole reason it lives
there: a quarantine an agent could add for itself would be a way to a green
suite that never went near the application.

**A quarantine with no reason is refused** by `seal check`. A test
somebody switched off and a test whose determinism somebody is fixing look
identical from the tree, and the reviewer approving the diff is the person
who has to tell them apart. Say what is being fixed, and what would let it
come back.

## What has been changing its mind

A test that fails one run in four looks perfectly ordinary in any single one
of them. So each run appends what it found, per outcome, under
`.workspace/seal/`, and `seal outcomes` reads back how often
each promise's verdict *changed*:

```
Changing their mind, over the last 10 runs recorded here:
  ui/todo-list/a-deleted-item-stays-deleted: 3 change(s) of verdict in 8 run(s)
```

Changes rather than failures: a promise that has been red every run since
somebody broke it is a regression, and the suite already says so each time.
What this finds is the one that has been red and green in the same window
with nothing deciding which.

**It concludes nothing, and quarantines nothing.** A rate is evidence.
Whether the test is at fault, or the application is genuinely intermittent,
or the environment is, is a judgement -- and the change it leads to goes
through a code owner like any other. There is no threshold either: a number
picked before anything had a use for one is guidance dressed as a rule.

## Running one outcome while you work

The whole suite is what a merge rests on. One outcome is what somebody
iterating on a translation needs, and paying for the other twenty on every
edit is how a local loop stops being used:

```sh
seal outcomes run ui/todo-list/a-deleted-item-stays-deleted
```

```
ui/todo-list/a-deleted-item-stays-deleted  PASS  deleting an item takes it off the list for good

1 of 3 outcome(s), named on the command line: 1 passed. The other 2 did not
run, so nothing here says whether they still hold -- only the whole suite
does that.
```

An outcome is named by the three directories that spell it,
`<group>/<epic>/<outcome>`, against a session `seal up` already has
running. A slug that names nothing is an error listing the ones that exist,
rather than a run of no outcomes -- a typo that quietly selected nothing
would report green.

This runs through the same Tilt resources a full run uses: the same images
and the same containers, told to start fewer outcomes. What it can't report
is anything about the outcomes it left out, which is why the summary counts
what ran and says so in as many words.

**It runs against the environment as it stands, unless you ask otherwise.**
A full run resets first; naming outcomes doesn't, because what you're
iterating on is usually the test rather than the state underneath it. Ask for
one with `--reset`:

```sh
seal outcomes run --reset ui/todo-list/a-deleted-item-stays-deleted
```

Every service that declared a reset goes back to its baseline, and the run
waits for each before starting. Otherwise, trigger the reset yourself, or
write the test to own its data.

**CI never does this.** `seal ci` runs `seal outcomes run` with
nothing named. A merge gate that ran a subset would be a gate on the tests
somebody remembered.

## What `seal check` refuses

The layout is only worth as much as what enforces it. `seal check`
reads the tree and refuses one that breaks it -- and `seal ci` runs
the same check before starting Tilt:

```sh
seal check                          # over ./outcomes
seal check --outcomes-dir promises  # look somewhere else, just this once
```

- **An outcome directory with no `prompt.md`.** This is the one the merge
  gate rests on: a translation nobody can reach the promise for is a test
  whose intent can't be reviewed, only whether it passes.
- **A `prompt.md` with no H1 headline.** Nothing can name the outcome
  wherever it's reported.
- **A file where the layout has only directories** -- in an epic, or at a
  `playwright` group's own level. Nothing would discover it.
- **A promise or a test filed under a group's `helpers/`.** Nothing walks
  that directory for outcomes and a run never looks in it, so both fail
  silently: the prompt is a promise nothing starts, the spec a test nothing
  collects.
- **A group no runner names, or a runner naming no group.** The two ways the
  tree and `seal-test-config.json` drift apart. A group nothing claims has
  every promise under it reported untested, which reads exactly like a
  promise nobody has got to yet.
- **A translation the group's runner can't run** -- files that are plainly a
  test, with no spec file among them, in a `playwright` group. The suite
  would report the promise as untested while the test sits right there.
- **A translation or a helper that waits on the clock** -- `waitForTimeout`
  in a `playwright` group. It passes on the machine it was written on and fails
  wherever the browser is slower, and a promise reported broken because
  something was slow is worse than a promise with no test at all.
- **A name that isn't a slug**, at any of the three levels.
- **An outcome the repository's `CODEOWNERS` doesn't cover** -- see
  [The merge gate](merge-gate.md).

Every offender is reported at once, so you put the tree right in one pass
rather than one failed run at a time.

Two things are deliberately **not** failures: an outcome with a prompt and
no translation yet (otherwise a prompt could only ever land in the same
change as its test), and a project with no outcome tree at all, which passes
silently.

Dot-entries above an outcome are tooling's, not the project's -- a
`.gitkeep` or an editor's leavings are neither a promise nor a test. Inside
an outcome no such filter applies: everything there is part of the
translation.
