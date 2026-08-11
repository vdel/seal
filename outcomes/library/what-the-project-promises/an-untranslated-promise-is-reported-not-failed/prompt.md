# a promise nothing has been written from yet is reported, and does not withhold the verdict

A promise with no test yet is listed, counted, and does not fail the run.

It is an ordinary state. A project writes down what it promises before it
works out how to check each one, and a library that refused that would
force every promise to arrive in the same change as its test -- which in
practice means promises get written only when somebody is ready to test
them, and the specification quietly becomes a list of what was convenient.

Reported rather than passed over, though. A promise nobody has got to yet
and a promise nobody has thought about look identical from outside unless
the listing says which.

## Worth covering

- An untranslated promise appears in the listing, marked as having no test
  yet.
- It does not fail the run.
- It is distinguishable from a promise whose test ran and said nothing,
  which is a failure.

## What this does not claim

That leaving a promise untranslated is fine indefinitely. The listing
makes it visible; what to do about it is the project's.

That an untranslated promise is checked in any way.
