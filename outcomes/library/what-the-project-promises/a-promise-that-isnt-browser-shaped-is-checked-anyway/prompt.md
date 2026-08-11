# a promise that isn't browser-shaped is checked by whatever does check it

A project's promises are not all of one kind, and neither are the things
that check them. A promise about what somebody sees is tested through a
browser; one an API-only service makes is tested by talking to the API; one
about a worker, a scheduled job or a command-line tool is tested by
whatever tests those.

So a project brings its own way of checking, in whatever it runs in, and
is taken at its word about what that starts. Seal has no reading of
somebody else's runner, which is the whole point of being able to declare
one.

Without this, a project's specification is limited to the promises that
happen to be browser-shaped -- and the promises it could not express would
simply go unwritten, which reads exactly like a project that promises
less.

## Worth covering

- A group whose promises are checked by something the project brought runs
  and reports like any other.
- What it is written in is not constrained.
- Its results are read the same way, so everything downstream -- the
  report, setting a test aside, driving a red suite back to green -- works
  on it unchanged.

## What this does not claim

That Seal validates what a project's own runner does. It is taken at
its word, deliberately: a library with a reading of what your test starts
is a library with an opinion about how you test.

That every kind of promise is equally cheap to check. Some need more
around them than others; what is promised is that none is shut out.
