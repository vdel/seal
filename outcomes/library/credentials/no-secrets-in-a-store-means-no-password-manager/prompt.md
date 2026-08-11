# a project that keeps no secret in a store needs no password manager to run

A project whose values are all literals, or all supplied by its manifests,
reaches for no password manager -- and does not have to declare that it
uses none.

Not having a thing should not cost a declaration saying so. A library that
required one would be making every project pay for a feature it does not
use, and the cost lands on exactly the projects least able to absorb it:
the small one, the example, the fresh checkout somebody is trying out.

It also keeps the failure honest. A project that never names a store and
cannot resolve one has a real problem; one that never names a store and is
asked for one has been given a chore.

## Worth covering

- A project with no store reference runs without one installed, logged in,
  or declared.
- A project that does reference one still resolves it.

## What this does not claim

That a project can mix the two badly and be told. This is about the case
where there is nothing to resolve.
