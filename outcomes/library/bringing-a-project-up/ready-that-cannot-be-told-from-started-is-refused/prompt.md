# a project that cannot tell "ready" from "started" is refused before anything starts

A container with no readiness probe is reported Ready the instant its
process launches, which silently defeats the promise above it. So the run
is refused rather than performed, and every container at fault is named in
one pass.

Refused *before anything starts* is half the promise. A project that
discovers this after a cluster is up and images are built has paid for a
run whose result it then cannot trust; one told at the outset has lost
nothing.

Naming them all at once is the other half. A project putting its manifests
right one failed run at a time is a project whose feedback loop is the
length of a build.

## Worth covering

- Every offending container in one run's output, not the first.
- A shape where the offender is easy to miss: a container a patch
  introduces, or one in an overlay other than the one usually deployed.
- That the refusal comes before the environment is built, not after.

## What this does not claim

That a probe is a *good* probe. A container that declares one Seal
accepts, because what a service needs to be serving is the project's to
know; the promise is that the question was asked and answered.

Anything about containers that legitimately have no probe to declare -- an
init container that runs and exits is not what this is about.
