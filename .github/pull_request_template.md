<!-- Thanks for contributing to Seal.

This is an early-stage project: the layout and the public surface still
move, so a PR that turns out to need a different shape is a normal outcome,
not a wasted one. Small PRs get read fastest, and drafts are welcome --
open one early if you'd rather agree on an approach before writing it all.

Every section below is short on purpose. Delete any that don't apply. -->

## What this changes, and why

<!-- The problem, and how this PR addresses it. If there's no issue to
link, describe the problem here: what's broken or missing, and what "fixed"
looks like. -->

**Related issue:** <!-- e.g. Fixes #12 -- or leave blank, an issue isn't required -->

## Where the change lives

<!-- Seal is a library: `tilt/` and `python/` are the deliverable, and
`examples/angular-django/` only consumes them. The README's "Seal is a
library" section is the standard a change here is held to -- the test it
applies is a project that doesn't live in this repo. Tick what applies. -->

- [ ] **Library** (`tilt/`, `python/`, `bin/`) — an adopting project gets
      this by upgrading Seal, not by copying anything out of
      `examples/`, and nothing added names an application's framework, port,
      path or service.
- [ ] **Worked example** (`examples/angular-django/`) — that project's own
      services, manifests or outcomes, not a capability other projects need.
- [ ] **Agent skills** (`.claude/`) — every claim added is something the CLI,
      the extensions or the checks actually do.
- [ ] **Docs** (`README.md`, `docs/`, `rfcs/`).

## How this was tested

<!-- What you ran, plus any new or updated tests. For the library that's
usually `cd python && uv sync --group dev && make test`; for the example,
`make up` and the outcome suite. Anything needing a cluster is fine to leave
to CI -- say what you couldn't run locally rather than guessing at it. -->

-

## Open questions

<!-- Optional. Anything you're unsure about, or want a maintainer's read on
before this is finished. -->
