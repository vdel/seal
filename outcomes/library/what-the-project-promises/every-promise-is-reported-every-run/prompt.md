# every promise is reported every run

A run reports on every promise the project has translated, whether it was
kept or not. Nothing is dropped for being uninteresting, and nothing is
dropped for having gone wrong.

A listing that leaves a promise out is indistinguishable from one where it
was kept. That is the whole reason this is a promise rather than a
convenience: a reader cannot tell absence from success, so a suite that
sometimes reports less than everything is a suite whose green means
nothing in particular.

A run that deliberately covers fewer than all of them -- somebody
iterating on one translation -- is a different thing, and says so in as
many words rather than leaving a short green listing to imply otherwise.

## Worth covering

- A promise that failed does not stop the ones after it being reported.
- The count in the summary matches what the tree holds.
- A run narrowed to some promises says what it left out, and does not read
  as the suite's own verdict.

## What this does not claim

Anything about the order promises are reported in, or the format they are
reported in.

That every promise *ran*. A promise nothing has been translated from is
reported as exactly that -- reported, not run, and not a failure.
