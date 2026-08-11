# Getting a red outcome suite back to green

When an outcome test fails, the job is to make the **application** satisfy it
-- never to make the test agree with the application. This page is the loop
that does that, and what Seal gives you for each step of it.

## The loop

1. Run the **whole** suite from a known baseline, with each failure
   confirmed.
2. Fix the **application** for each confirmed failure.
3. Re-run the whole suite -- not the outcome that was red.
4. Repeat against whatever is still red.

Step 3 is the one that's easy to skip and expensive to skip. A fix scoped to
the one promise you were looking at can break another that nothing re-ran,
and the suite exists precisely to catch that.

## Set up once

```sh
seal up     # long-lived; start it in the background
```

The loop runs against a session that's already up. A fresh cluster per
iteration (`seal ci`) is correct and far too slow to iterate against
-- keep it for the final check.

## One iteration

```sh
seal outcomes run --reset --all --confirm
```

- **`--reset`** puts every service that declared a reset back to its
  baseline, and waits for each. Without it, this run measures the application
  *plus* whatever the last iteration left in it.
- **`--all`** runs every promise the tree holds. Don't narrow it.
- **`--confirm`** re-runs each failure on its own, from a reset, and says
  whether it reproduced.

What the listing tells you:

| | |
| --- | --- |
| `FAIL (confirmed)` | It failed again alone, from a baseline. The application is what to fix. |
| `FAIL (not confirmed)` | It held alone. **Not** an application bug -- see below. |
| `no verdict (confirmed)` | Nothing knows the test ran, twice over. Usually the runner died. |
| `FAIL (quarantined)` | Known and excused; doesn't fail the run. |
| `no test yet` | A promise nothing has been translated from. Not a failure. |

Each failing promise's own log, report and screenshots are in
`tests-results/outcomes/<group>/<epic>/<outcome>/`. Read those rather than
guessing from the verdict.

A round that ends by saying the loop is going in circles, or that it's
reached its backstop, isn't a round to answer with another fix -- that's the
third way out, below.

Before you call an iteration done:

```sh
seal outcomes touched
```

It names every path under `outcomes/` your change reaches, and exits non-zero
if there is one.

## When it isn't the application

An unconfirmed failure held on its own, from a reset. Nothing you change in
the application will settle it. It is one of two things, and the difference
matters:

- **The test doesn't own the data it asserts on.** Outcomes run one at a time
  against the same application, each starting from whatever the one before it
  left. A test that assumes an empty list fails behind one that added to it.
- **The test isn't deterministic.** It races the application -- most often by
  asserting before something has rendered.

Both are the translation's to fix, which means a code owner
([the merge gate](merge-gate.md)). Report which of the two the evidence
points at, and leave it there. While that fix is in flight, the promise can
be [quarantined](outcomes.md#when-a-test-is-the-problem-quarantine) -- also a
code owner's call, and never a step in this loop.

## Where to stop

:::{important} Three ways out, and only three.
:::

**Green.** Every promise holds. Confirm it the way a merge will:

```sh
tilt down
seal ci -- --build_type test
```

That's a fresh cluster, which matters after a session has been reset a dozen
times. Whether green merges is your repository's branch protection and its
code owners -- not something the loop can declare.

**A promise is wrong.** Keeping one outcome test's promise necessarily breaks
another's, or the application is right and the prompt no longer describes it.
Stop, say which promises conflict and why, and leave the prompt to a code
owner. That arbitration is exactly what the gate exists to keep with a human.

**It's going in circles.** Fixing A breaks B and fixing B re-breaks A, or
every round breaks something new. Stop -- an unresolved run can't merge
anyway, because the suite is still red.

```sh
seal outcomes loop
```

A loop is the rounds of the whole suite since the last one in which every
promise held. Nothing starts one and nothing finishes one: it's read off the
record each run appends, so it's the same answer whether a run just asked or
you asked afterwards. What it reports is what each round fixed, what that
cost, what's still red, and whether there's a reason to stop:

- **A cycle** -- a promise fixed and then broken again inside this loop.
  Keeping one promise is breaking another, which no number of further rounds
  settles by itself. Two rounds can establish it.
- **The backstop** your project declares in
  [`seal-test-config.json`](runners.md#loop-where-a-regression-loop-stops),
  in rounds and in minutes. That's what catches the other shape: every round
  breaking something new, repeating nothing and converging on nothing either.

It exits non-zero when there's a reason to stop, so a script can ask without
reading the prose. It's not a verdict on the suite -- that's still `seal
outcomes run`'s -- and a loop with a reason to stop is red already.

Then hand it over rather than concluding yourself. Six rounds in, you have an
account of which promise is at fault, and that account is what needs checking
rather than extending. The conclusion is one of two, and both are somebody
else's: **a translation is stale**, which is rewritten with the motivation
attached and reviewed by a code owner like any other change to the tree, or
**this should be satisfiable and isn't**, which touches nothing and says what
a human has to decide or supply.

## What a coding agent gets

An agent working in a project that has installed Seal's skills
([Coding agents](coding-agents.md)) reads this loop as
`seal-regression-loop`, and can hand one iteration to the
`seal-app-fixer` subagent -- which changes application code only and
never touches `outcomes/`. A loop with a reason to stop goes to
`seal-loop-triager` instead: a separate session, which is what fresh
context over the sequence means in practice.

Seal starts no agent and configures no agent command. What a session
did isn't something a checkout can verify, and Seal claims no
capability it can't verify from one. What it ships is the instructions and
the commands each step needs; every claim about whether the project is green
comes from re-running the suite.
