# a test is always reachable from the promise it was translated from

Anyone looking at a test can reach the promise it came from, and anyone
looking at a promise can reach whatever has been translated from it.

This is what a review of a translation rests on. Translating is lossy: the
same promise yields different tests in different hands, each encoding
choices the promise never made. A reviewer's job is to check that the test
means what the promise says -- and with only the test in front of them,
the most they can check is whether it passes, which is the one thing that
needed no reviewer.

The reverse is what it rules out: a test with no promise behind it. That
is a test whose intent cannot be reviewed, only its result, and a suite of
those is a suite nobody can argue with.

## Worth covering

- From any test, the promise it was translated from is reachable without a
  lookup somewhere else.
- A test with no promise behind it is refused rather than accepted
  quietly.
- A promise with nothing translated from it yet is fine -- the missing
  direction is the one that matters.

## What this does not claim

That the test is a *good* translation of the promise. Reachability is what
makes that judgeable; making the judgement is a person's.
