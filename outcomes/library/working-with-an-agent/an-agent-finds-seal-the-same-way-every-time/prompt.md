# an agent working in my repository finds Seal the same way every time

An agent that lands in a project using Seal finds the same
instructions there: which command replaces which, what a promise and its
translation are, what never to edit, and what an error means.

Without this, every session rediscovers the project from scratch, and
rediscovery is where the expensive mistakes live -- the tilt command run
directly instead of the wrapper, the failing test edited instead of the
application, the promise rewritten to agree with what the code now does.
Each is a reasonable thing to do if you do not know better, and each is
exactly what the gate exists to prevent.

Installed into the project rather than remembered per session, because a
session's memory is not something the next one has.

## Worth covering

- A project that has adopted Seal carries those instructions.
- They are the same in any project that adopted it, rather than something
  each one wrote.
- They say what the tools actually do.

## What this does not claim

That an agent will follow them. These are instructions, not enforcement --
what enforces is the check, the suite, and who has to approve a change to
the specification.

That they cover everything an agent needs to know about a project. They
cover Seal; the project is the project's to explain.
