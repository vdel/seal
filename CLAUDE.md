# CLAUDE.md

Guidance for AI agents (and anyone else) contributing to this repo.

## What this repo is

A library. `tilt/` and `python/` are the deliverable;
`examples/angular-django/` consumes them and is never where a capability
lives. Before adding behaviour or a rule, read the root `README.md`'s
"Seal is a library" section -- it is the standard a change here is
held to, and code written against the example passes every test while giving
an adopting project nothing.

## The agent skills

`.claude/` is part of the deliverable, not this repo's own configuration:
the skills and subagents there are what an adopting project installs (with
`bin/install-seal-skills`) so a coding agent working in *that* repository
discovers Seal and uses it correctly. They're live here too, so a session
working on Seal or on the worked example reads the same instructions.

Read `.claude/README.md` before changing them. Two rules matter most: every
claim in a skill has to be something the CLI, the extensions or the checks
actually do, and none of them may name an application's framework, port,
path or service. A skill promising behaviour Seal doesn't have is
worse than a missing skill.

## Comment style

Comments and docs describe the *current* design and its rationale —
never the journey that got here. Concretely:

- **No issue/PR references** (`#NN`, `owner/repo#NN`, `PR#NN`, issue/PR
  URLs). This repo may be forked, republished, or renumbered elsewhere; a
  citation to "this repo's own issue #59" is meaningless — or actively
  wrong — once that's no longer true, and it's dead weight even when it
  is: the reasoning belongs in the comment itself, not behind a link a
  reader has to go fetch.
- **Don't narrate history.** Avoid "X used to work this way", "no longer
  does Y", "replaces the old Z", "originally", "previously", "confirmed
  the hard way" — these describe a migration a reader of the current code
  never needs to reconstruct. State what the code does now and why, as if
  it had always been this way. If a past failure mode is still a live
  risk worth warning about (e.g. "a stale name mismatch here silently
  breaks anything that matches by name"), describe the mechanism and the
  risk directly — don't frame it as an anecdote about when it happened.
- **Present-tense comparisons between two things that both exist today**
  (e.g. "unlike ubuntu-latest", "unlike Postgres") are fine — that's not
  history, it's describing the current codebase's own structure.
- **Skip hedges about failure modes the current design already
  prevents.** If a comment exists only to reassure a reader that
  something *won't* go wrong, cut it, or replace it with the actual
  constraint that prevents it — don't narrate the near-miss.
- Functional values (a real `repoURL`, an image ref, a registry path, a
  `CODEOWNERS` entry) are not comments — this guidance doesn't ask you to
  genericize them, only to keep the prose around them focused on what's
  true now.

When editing a comment for another reason, fix nearby violations of this
in the same file rather than leaving them for later.
