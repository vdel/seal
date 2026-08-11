# a session that reports itself ready is one I can test against

A run succeeds only once every resource is actually serving -- not once
every process has started.

This is the promise that makes a gate worth having. A suite that starts
against a half-built environment reports promises broken for something the
application never did, and a red run nobody can reproduce is one nobody
acts on. Every other promise about a running environment is downstream of
this one being true.

What "serving" means is the project's to say, per container, and Seal
takes it at its word. What Seal guarantees is that it waits for the
answer rather than assuming one.

## Worth covering

- A service that takes a while to become useful after its process starts --
  a database accepting connections, a migration running, a cache warming.
  The gap between "started" and "serving" is where this promise lives, so a
  translation with no gap in it proves nothing.
- The run's own exit: it does not report success while something is still
  coming up.

## What this does not claim

Anything about how long a session takes to come up. A slow environment
keeps this promise as fully as a fast one.

That a serving resource is a *correct* one. Readiness is a claim about
whether a test can drive the thing, not about whether it behaves.
