# a service's own tests run against the database and credentials it was deployed with

A service's own test suite runs inside the container that was deployed --
against its real database, its real credentials, the real objects its
environment was assembled from.

Not against a mock of them, and not during the image build, where neither
exists. A suite that passes against substitutes has established that the
substitutes agree with each other.

This is what makes a service's own tests worth anything to the gate: they
are exercising the same wiring the application will use, put there by the
same path.

## Worth covering

- The suite reaches the service's database and gets the deployed one.
- It reads a credential and gets the value that was provisioned, not a
  placeholder.
- It runs after the service is serving, rather than during its build.

## What this does not claim

Anything about what a service's tests assert, how many there are, or what
framework runs them. That is the service's own business.

That a service must have tests. One that declares none is not made to, and
still serves for everything else.
