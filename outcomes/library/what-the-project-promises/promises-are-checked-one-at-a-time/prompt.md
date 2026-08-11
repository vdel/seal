# promises are checked one at a time against the same application

Promises are checked in turn, never at once, because they drive the same
application.

Two running together means each asserting on state the other is changing.
The result is a promise that would have held reported broken for what
another test was doing -- the least useful failure a suite can produce,
because it is real, reproducible-looking, and about nothing.

The cost is wall-clock, and it is worth paying. A suite that is fast and
occasionally lies about which promise broke is slower than a slow one, once
the time spent chasing the lie is counted.

## Worth covering

- Two promises that would interfere do not run together.
- Each therefore starts from whatever the one before it left -- which is
  what makes owning the data a test asserts on the translation's job.

## What this does not claim

That promises are isolated from each other. They are serialised, not
sandboxed: what one leaves behind is what the next one finds.

Anything about how long a suite takes.
