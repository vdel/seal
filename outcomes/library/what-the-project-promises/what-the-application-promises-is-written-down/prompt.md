# what the application promises is written down in the repository, in the words somebody using it would use

A project's promises live in the repository, stated the way somebody using
the application would state them -- not as test names, not as tickets, not
as an agent's summary of a conversation.

Two things follow from where they live. They survive any one session, any
one person, and any one agent, which is what lets them be the thing future
work is checked against. And they can be read by somebody who does not
know the codebase, which is what makes a translation reviewable: a
reviewer with only a test in front of them can check whether it passes,
never whether it means anything.

In the users' own words matters as much. A promise stated in terms of an
endpoint or a table is an implementation choice wearing a promise's
clothes, and when the implementation changes the promise looks broken
while nothing anybody cared about has changed.

## Worth covering

- The promises are answerable from the repository alone, by somebody who
  arrived just now.
- Each is stated in terms of the application rather than its internals.

## What this does not claim

That the promises are the *right* ones, or complete. What a project
promises is the project's to decide.

Anything about how they are worded beyond being the application's own
terms.
