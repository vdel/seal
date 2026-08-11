# a service can put its own state back to a known baseline, on demand

A service that owns state can declare how to put it back, and that reset
can be asked for -- and waited for -- rather than hoped for.

A test that starts from whatever the last run left fails for reasons that
have nothing to do with the change under test. This is what lets a test
name a row and mean it, which is the difference between a suite that
reports on the application and one that reports on the order its tests
happened to run in.

Waiting matters as much as asking. A test racing a reset that is still
emptying a store reports a promise broken for something the application
never did.

## Worth covering

- A service that declares a reset gets one that can be triggered.
- A run that asks for a baseline gets one before anything starts, and does
  not start until it is finished.
- A service that declares no reset is not made to, and nothing breaks
  because it did not.

## What this does not claim

**What any baseline holds.** Which tables, which fixture, which broker to
flush belongs to whichever project owns that service. What is promised is
that the mechanism is declarable and waitable, not that the data behind it
is any good -- that is the project's own business, and Seal has no
view on it.

That state is reset automatically. A session somebody is working in is not
thrown away because they re-ran a test; asking is part of the promise.
