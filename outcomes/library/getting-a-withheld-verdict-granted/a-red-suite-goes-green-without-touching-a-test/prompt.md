# a red suite can be driven back to green without anybody touching a test

There is a way to work a red suite back to green that changes the
application only: run everything from a known baseline, confirm each
failure, fix the application, run everything again, repeat.

Every promise, every round. A fix scoped to the one test somebody was
looking at can break another nobody re-ran, and a listing that leaves that
one out is indistinguishable from one where it held. So the loop's unit is
the whole suite, not the failure that started it.

This is the loop the gate assumes exists. Without it, the gate's answer to
a red run is "get a human", and a gate that always ends there is a gate
nobody can merge through.

## Worth covering

- The loop's unit is every promise, from a baseline, each round.
- A failure is confirmed before it is acted on.
- What changes is the application. Nothing about the loop requires a test
  to be edited to reach green.

## What this does not claim

That every red suite *can* be driven green. Sometimes two promises are
genuinely incompatible, and then at least one has to change -- which is a
person's decision, and routes through review by construction.

That the loop is unattended, or that it always terminates on its own.
