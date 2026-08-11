# a test I don't trust yet can be set aside with a stated reason, and is never reported as kept

A translation that is not trustworthy -- one that does not own the data it
asserts on, or is not deterministic -- can be set aside with a written
reason, so its failure does not block every merge while somebody fixes it.

The reason is the whole mechanism. A test somebody switched off and a test
whose determinism somebody is fixing look identical from the tree, and the
person approving the change is the only one who can tell them apart. Set
aside with a stated reason, that judgement is available; set aside
silently, it is gone.

And it is never reported as kept. A green suite has to stay a claim about
promises that held, and excusing one from failing the run is not the same
as saying it held.

## Worth covering

- A set-aside promise that fails does not fail the run.
- It is still run, still reported, and reported as having failed.
- Setting one aside without a reason is refused.

## What this does not claim

That setting a test aside is free. It needs the same approval as any other
change to what the project promises -- one an agent could do for itself
would be a route to a green suite that never went near the application.

That a set-aside test is fixed, or will be.
