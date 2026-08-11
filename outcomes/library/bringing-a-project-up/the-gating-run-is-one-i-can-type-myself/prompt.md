# the run that gates my merge is one I can type on my own machine

Every step of the gate is something the command line can do. There is no
part of it that exists only inside CI.

A withheld verdict nobody can reproduce is one nobody can act on. It ends
in guesses pushed to see what CI says, which is the slowest possible
debugging loop and the one that burns the most trust. Worse, it makes the
gate unusable by an agent: a run whose failure cannot be reproduced
locally cannot be worked.

This is what makes the gate a tool rather than a gatekeeper.

## Worth covering

- What CI runs is a command, and the same command run by hand does the
  same thing.
- No step of the gate is a bespoke sequence living in a workflow file.

## What this does not claim

That the machine needs nothing installed. A container runtime and a
cluster have to be available; what is promised is that no *step* is
unavailable.

That a local run is as fast as CI, or vice versa.
