# every promise is checked on every pull request, against an environment built for that run

Every pull request has every promise checked against an environment built
for it, not one left over from a previous run.

Built for that run is the load-bearing half. An environment reused between
runs carries whatever the last one left: objects a shape no longer
declares, rows a test wrote, a container still running that this change
removed. A promise can then be kept by something the change under test
took away, and a gate that can report that is worth less than no gate.

Every pull request, because a gate that runs sometimes is a gate whose
green means "this was checked, or it wasn't".

## Worth covering

- A run starts from a fresh environment rather than one already there.
- Every promise is covered, not a selection.
- The verdict is what decides whether the change can merge.

## What this does not claim

Anything about how long that takes, or what it costs.

That the environment resembles a production one. It is built from what the
project declares, and which shape that is is a separate decision.
