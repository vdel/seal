---
name: seal-regression-loop
description: Drive a Seal project's outcome suite back to green without touching a test -- run the whole suite from a known baseline, confirm each failure before acting on it, fix the application, re-run everything, repeat. Use when outcome tests are failing and the job is to make them pass, when asked to iterate until the suite is green, to fix a regression an outcome test caught, or to work through a red seal ci that is red because a promise is not being kept.
---

# Getting back to green

The loop, in one line: **run the whole suite, confirm what failed, fix the
application, run the whole suite again.** Repeat until nothing is red.

Every claim about whether the project is green comes from re-running the
suite. Not from what an iteration reports about itself, and not from the one
test you were looking at.

## Set up once

```sh
seal up                     # long-lived; start it in the background
```

The loop runs against a session that is already up, and puts the services
back to a known baseline between runs. A fresh cluster per iteration
(`seal ci`) is correct too, and far too slow to iterate against --
keep it for the final check.

## One iteration

```sh
seal outcomes run --reset --all --confirm
```

- `--reset` fires every `seal_reset_<service>` the session declares and
  waits for each, so this run measures the application rather than the
  application plus what the last iteration left in it.
- `--all` runs every promise the tree holds. **Never narrow this.** A fix
  scoped to the test that was red is exactly how another promise gets broken
  with nobody looking.
- `--confirm` re-runs each failure on its own, from a reset, and says whether
  it reproduced.

Read the result:

| Line | What it means | What to do |
| --- | --- | --- |
| `FAIL (confirmed)` | It failed again alone, from a baseline. | Fix the application. |
| `FAIL (not confirmed)` | It held alone. | **Not** an application bug. See below. |
| `no verdict (confirmed)` | Nothing knows the test ran, twice. | Usually the runner died -- `seal-ci-doctor`. |
| `FAIL (quarantined)` | Already known; doesn't fail the run. | Leave it. |
| `no test yet` | A promise nothing has been translated from. | Not a failure. `seal-outcome`. |

A round that ends with `seal outcomes run:` saying the loop is going in
circles, or that it has reached the backstop, is not a round to answer with
another fix. That is exit 3 below, and it arrives in the round it happened
rather than waiting for somebody to think of asking.

Then fix **the application**, one confirmed failure at a time, and go round
again. `tests-results/outcomes/<group>/<epic>/<outcome>/` holds that
promise's own log, report and screenshots -- read it rather than guessing
from the verdict.

Before calling an iteration done:

```sh
seal outcomes touched     # exits non-zero if this change reached outcomes/
```

## The rules

These are the ones that look locally reasonable and are globally wrong.

- **Never edit a test, a prompt, or a fixture to get green.** The suite
  passes identically whether the application was fixed or the test was
  rewritten, and that difference is the entire gate. `seal outcomes touched`
  is how you check you didn't; `CODEOWNERS` is what stops it merging if you
  did.
- **Never quarantine your way out.** A `quarantine.md` excuses a promise from
  failing the run. It is a code owner's call, for a test whose determinism
  somebody is fixing -- never a step in this loop. Propose one, with the
  reason, and let a human decide.
- **Never act on an unconfirmed failure.** It held on its own from a reset,
  so nothing you change in the application will settle it: the test either
  doesn't own the data it asserts on (outcomes run one at a time against the
  same application, each starting from what the one before it left) or it
  isn't deterministic. Report it, say which of the two the evidence points
  at, and leave the test to a code owner.
- **Never re-run a failure hoping for green.** `--confirm` runs it once more,
  for the evidence. A third run is retry-until-green, which is the thing the
  runners already refuse to do.
- **Never report a subset as the suite.** `seal outcomes run` with slugs
  named says nothing about the promises it left out, and says so.
- **Never declare the change mergeable.** Green is a fact about the suite.
  Whether that merges is the repository's branch protection and its code
  owners, not this loop's to say.

## Where it stops

Three ways out, and only three:

1. **Green.** Every promise holds. Confirm it the way a merge would --
   `tilt down && seal ci -- --build_type test` -- because that is a fresh
   cluster, and a loop's session has been reset a dozen times.
2. **The promise is wrong.** Satisfying one outcome test necessarily breaks
   another, or the application is right and the promise no longer describes
   it. Stop. Say which promises conflict and why, and leave the prompt to a
   code owner -- that arbitration is the one thing the gate exists to keep
   with a human.
3. **You are going round in circles.** Fixing A breaks B and fixing B
   re-breaks A, or every round breaks something new. Stop, and hand it to
   `seal-loop-triager` -- a session that has not been in this loop. Do not
   keep going: an unresolved run cannot merge anyway, because the suite is
   still red.

```sh
seal outcomes loop     # the rounds so far, and whether there is a reason to stop
```

It reads the record every run of the whole suite appends: what each round
fixed, what that cost, what is still red, and either that a promise has been
fixed and broken again in this loop or that it has reached the backstop the
project declares in `seal-test-config.json`. A failing round says the
same thing in passing, so you find out in the round it happened. The exit
code is whether there is a reason to stop -- not a verdict on the suite,
which is still `seal outcomes run`'s.

Hand over rather than concluding yourself. Six rounds in, you have an account
of which promise is at fault, and that account is what needs checking rather
than extending -- which is the whole reason the triage agent is a separate
session. It reaches one of two conclusions: a translation is stale, which it
rewrites with the motivation attached for a code owner to approve, or this
should be satisfiable and isn't, which it leaves alone and puts to a human.

Nothing here is enforcement. `seal check`, the outcome suite and
`CODEOWNERS` are the only things that enforce; this is how to work inside
them.
