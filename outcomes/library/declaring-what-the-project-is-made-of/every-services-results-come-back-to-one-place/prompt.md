# every service's results come back to one place, and a service whose suite failed is reported as that service

What a run found comes back together -- every service's results in one
place -- and a service whose own tests failed is reported by name rather
than as part of an aggregate.

Both halves are about somebody reading a red run. Results scattered across
containers are results somebody has to go and collect, and a run that
reports only that *something* failed is one where finding out what costs
more than fixing it.

Naming the service is what makes the report a starting point rather than a
prompt to start looking.

## Worth covering

- Results from more than one service arrive together after a run.
- A service whose suite failed is identified as that service.
- A service whose suite passed is reported too -- silence and success are
  different things.

## What this does not claim

Anything about the format of a service's own test output, or which
framework produced it.

Anything about how the results are presented afterwards. Where they land
is promised; what a project does with them is the project's.
