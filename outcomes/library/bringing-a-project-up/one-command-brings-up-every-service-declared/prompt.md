# one command brings up every service the project declares

From a checkout, one command brings up the whole application: every
service the project declares, built and deployed, with no per-service step
to remember and no list to keep in agreement with the services that exist.

What the project declares is its own structure -- the services it has are
the services that come up. A project cannot end up with a service that
exists but is never started, because there is no second place where the
list could have gone stale.

## Worth covering

- Every declared service is running afterwards, not most of them.
- A service added to the project comes up on the next run without anything
  else being told about it.
- A service removed stops coming up, for the same reason.

## What this does not claim

Anything about how long it takes, or in what order services start.

That the command is all a machine needs. A container runtime has to be
there; what is promised is that nothing *else* is a step somebody has to
know about.
