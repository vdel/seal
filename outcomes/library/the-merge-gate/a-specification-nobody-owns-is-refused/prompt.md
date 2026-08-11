# a project whose specification nobody owns is refused

A project whose outcome tree its CODEOWNERS does not cover is refused, and
told which promises are uncovered.

Without this, the gate above is a suggestion. An unowned specification is
one an agent can edit to agree with whatever the application now does, and
a suite that passes because the promises were lowered reads exactly like a
suite that passes because the application works.

The layout being right says nothing about who has to approve a change to
it, so the two are checked separately and this is the half that is easy to
forget: ownership is configuration, not structure, and nothing about a
well-formed tree hints that it is missing.

## Worth covering

- A tree no rule reaches is refused, and the refusal names what is
  uncovered rather than only that something is.
- A tree a rule *partly* reaches is refused for the part it does not: a
  later rule with no owner can uncover what an earlier one covered.
- Everything under an outcome is held to it, not just the test -- a
  promise, a fixture beside it, what a group's tests share.
- A project with no promises at all has nothing to own, and is not refused
  for it.

## What this does not claim

That the named owners are the right people, or that they will review
carefully.

That the repository's branch protection actually enforces the review. That
half of the gate is a repository setting, cannot be read from a checkout,
and is out of scope here -- what is promised is that the tree is covered,
not that the platform is configured.
