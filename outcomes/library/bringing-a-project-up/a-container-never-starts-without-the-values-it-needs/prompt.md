# a container never starts without the values it was declared to need

Before anything is deployed, every key a service declares is accounted
for: a key no object supplies it, and an object supplying a key nothing
declares, are each named.

A container that starts without a setting it needs fails somewhere else --
in a readiness probe that never passes, in a request that returns a
confusing error, in a log nobody is watching. The cost of finding it there
is a whole run and a diagnosis; the cost of finding it here is a message.

Accounted for *in every shape the project deploys*, not just the one it
usually runs. A key supplied in one and missing from another is a
difference that only shows up when somebody deploys the other.

## Worth covering

- A key a service declares that nothing supplies is named before anything
  deploys.
- A key supplied to a container that never asked for it is named too --
  the reverse mistake, and the one that quietly grows.
- A shape other than the usual one is checked as thoroughly.

## What this does not claim

That the *value* is right. Seal establishes that something supplies
the key, not that what it supplies works.

That a project must supply everything from one place. Splitting values
across several objects is ordinary, and the accounting is over all of
them.
