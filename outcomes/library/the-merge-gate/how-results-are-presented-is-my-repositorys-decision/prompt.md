# how a run's results are presented is my repository's decision

A run hands back what it found. Which check it becomes, which comment,
which dashboard, is the project's.

Adopting a gate should not mean adopting somebody else's reporting. When
the library presents results itself, an adopting repository inherits the
tools it chose, the permissions those tools need, and the platform
they assume -- three things it never asked for, to get one thing it did.

Handing the results back keeps the boundary where it belongs: the library
establishes what held, and the repository decides who hears about it and
how.

## Worth covering

- A run's findings are available to the caller in a form it can act on.
- Nothing is published on the project's behalf that it did not ask for.
- A project that wants a particular presentation can build it from what it
  was handed.

## What this does not claim

That a project gets a presentation for free. It gets the findings; making
them into a report is the project's, and that is the trade.

Anything about which reporting tools exist or are any good.
