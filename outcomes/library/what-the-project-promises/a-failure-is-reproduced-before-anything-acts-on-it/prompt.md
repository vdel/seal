# a failure is reproduced on its own, from a baseline, before anything acts on it

A promise that failed can be run again -- on its own, from a baseline --
and the result of that second run is attached to the failure.

Both halves of "again" carry weight. From a baseline, because a failure
retried in place is retried against the state that may have caused it,
which is how a shared-state bug gets papered over instead of found. On its
own, because promises run against the same application in turn: one that
fails in the suite and holds by itself is a test that does not own the
data it asserts on, which is a third thing again -- neither a regression
nor chance.

Multi-service end-to-end tests are the most flake-prone class of test a
project runs, and a failure chased on one observation is time spent on
noise, or worse, a fix for a bug that was never there.

## Worth covering

- A failure that fails again is marked as having reproduced; one that
  holds is marked as not having.
- The second run is from a baseline and covers that promise alone.
- What the first run left is kept beside what the second found, so the
  interesting case -- the one that did not reproduce -- has something to
  compare.

## What this does not claim

**It changes no verdict.** A promise this run did not see kept is one it
did not see kept, and an unreproduced failure still fails the run. What a
second run buys is a reason attached to the failure, not a way out of it.
A translation that read this as "a flaky failure is excused" would encode
the opposite of the promise.

That a failure is retried until it passes. Once, and only what was red --
re-running a red test until it goes green is exactly the retry this whole
layer refuses.
