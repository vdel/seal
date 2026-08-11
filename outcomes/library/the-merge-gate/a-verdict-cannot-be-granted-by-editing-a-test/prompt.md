# a withheld verdict cannot be granted by editing a test

Every path under the specification needs a code owner's approval -- the
promise and the test translated from it alike. So an agent that cannot find
an application fix has exactly one move left, and it ends with a person
reading the change.

Nothing about a green run shows which happened. A suite passes identically
whether the application was fixed or the failing test was rewritten to
agree with it, and left to the party with an interest in the answer, that
difference is a judgement made at the moment it is least convenient to make
honestly. The gate does not ask. It makes the two cases structurally
different.

The prompt is covered for the same reason as the test: an agent free to
rewrite what the project claims never has to touch a test to change what a
green run means.

## Worth covering

- A change touching a translation requires review; one touching only the
  application does not.
- A change touching a *prompt* requires it too.
- What a group's tests share is covered as surely as a test is -- an
  assertion moves into shared code as readily as anything else, and one a
  change could reach without review would defang every test importing it.

## What this does not claim

That a code owner will notice a bad edit. This is a promise about who has
to look, not about what they conclude.

That a test can never change. Translations are rewritten as
implementations change; the promise is that a person approves it when they
are.
