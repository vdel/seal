# a promise whose test did not run is never reported as kept

A translated promise that left no verdict behind is reported as a failure,
not as a gap and never as a pass.

Every way a test silently fails to run looks the same from outside: an
image that never started, a container killed before it wrote anything, a
runner that died on the third of twenty, a report nobody produced. None of
them is evidence the promise held, and a suite that treated an absent
answer as a good one would let a project go green by breaking its own
tests.

This is the failure mode the merge gate is most exposed to, because it is
the one that looks like nothing happening.

## Worth covering

- A translated promise with no verdict file at all.
- A verdict that is there but unreadable -- a truncated write is the same
  thing as no write from here.
- A run that stopped partway: the promises it never reached are reported as
  untested rather than as failures it invented, and neither is a pass.

## What this does not claim

That the suite can say *why* a test did not run. It reports what it can
establish, which is that nothing vouched for this promise.

Anything about a promise nothing has been translated from. That is a
different state, reported differently, and not a failure -- writing a
promise down before a test exists is ordinary.
