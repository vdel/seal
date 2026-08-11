# whatever shape my password manager's CLI takes, I declare it rather than wait for support

A project says how its password manager's CLI is invoked, and that is the
whole of what adopting it takes. A CLI that wraps a command, one that
resolves a file of references, one that dumps a scope, and one that
answers a single lookup at a time are all declarable -- including a script
somebody wrote here.

The alternative is a library that knows a list of products, where adopting
the one you use means waiting for somebody to add it. That makes the
library's own release cycle a dependency of a project's choice of vault,
which is a strange thing to make anybody accept.

The lowest common denominator matters most: one lookup, one value. A
provider that can do only that is still declarable, because that is what
makes "bring your own" true rather than aspirational.

## Worth covering

- A provider is declared and its values reach the services that named
  them.
- A CLI of each shape works, including the one-lookup-at-a-time kind.
- Something homegrown -- a script with no product behind it at all -- is
  as declarable as anything else.

## What this does not claim

That any particular product is supported, or named anywhere. Nothing in
the library knows a vendor; a project that needs one describes it.

That a declaration is checked against the real CLI's behaviour. What is
promised is that the shape can be stated, not that a mis-stated one is
caught before it runs.
