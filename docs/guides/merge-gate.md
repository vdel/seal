# The merge gate

Why a change to an outcome test has to be approved by a human, what Seal
enforces about that, and the half that lives in your repository's settings
instead.

## What the gate is for

The point of outcome tests is that a pull request can merge on its own
say-so for changes those tests cover -- not because its author is trusted,
but because they cannot merge without satisfying tests they cannot quietly
rewrite.

That distinction is the whole thing, and nothing about a green run shows it.
A suite passes identically whether the author fixed the application or
edited the test that failed. Left to the author, the difference is a
judgement call -- "is this a regression, or has the spec changed?" -- made
by the party with an interest in the answer, at the moment it's most
inconvenient to answer honestly.

So the gate doesn't ask. It makes the two cases structurally different:

- **Fix the application → merge unattended.** Every currently-committed
  outcome test still passes, and nobody has to look at the diff.
- **Change what a test asserts → get a human.** The diff touches a path
  under `CODEOWNERS`, so the platform blocks the merge until a code owner
  approves it.

An author who can't find an application fix has exactly one move left, and
it's the one that ends with a person reading the change.

That person is reading a diff which, for a change that only adds or rewrites
a translation, doesn't contain the promise -- the prompt didn't change. What
they need in front of them is both, which is what
[`seal outcomes review`](translating-promises.md#reviewing-a-translation)
renders.

One consequence is deliberate: an application fix that satisfies every
outcome test merges unattended even when it's a substantial rewrite. The
outcome tests are the spec being enforced, not a stand-in for "small diff".

## CODEOWNERS over the outcome tree

The whole tree is owned, prompt and translation alike:

```
/outcomes/ @your-team
```

The prompt is covered for the same reason as the test. It's what the project
promises; an author free to rewrite the promise never has to touch a test to
change what the project claims. And an outcome's fixtures sit inside its
directory, so a rule over the tree covers a test's seed data as surely as
its assertions -- which matters, because a test can be defanged from either
end.

A group's `helpers/` is inside the tree for exactly that reason. What
several translations share is as likely to be the assertion as the
navigation, so a helper anybody could edit unreviewed defangs every test
importing it without touching a test at all. `seal check` holds it to the
same rule the outcomes are held to.

A quarantine note is covered too, for the same reason turned round. A
`quarantine.md` in an outcome's directory says a failure there doesn't fail a
run (see [Outcome prompts and their tests](outcomes.md)), so a promise can be
excused from the gate without its test changing at all. It lives inside the
outcome for exactly that reason: whatever rule covers the tree covers it,
with nothing to remember to add.

Two properties of `CODEOWNERS` decide whether a rule actually holds, and
both are easy to get wrong by hand:

:::{warning}
**The last matching rule wins**, not the most specific. A broad `/outcomes/
@your-team` is overridden for anything a later rule matches.

**A rule with no owners clears ownership.** `*.py` on a line of its own,
anywhere below the tree's rule, silently unlocks every Python test in it.
:::

## What `seal check` refuses

`seal check` reads your repository's `CODEOWNERS` and refuses a tree the
gate doesn't cover -- and `seal ci` runs the same check before starting
Tilt:

```sh
seal check
```

- **An outcome directory the gate doesn't reach** -- no rule matches it, or
  the last one that does names no owner. Reported at the *directory*,
  because covering a directory is what covers the files added to it later; a
  rule written per-file is one somebody has to remember to extend.
- **A file inside an owned outcome that a later rule unowns.** The directory
  being covered isn't enough on its own.
- **An outcome tree with no `CODEOWNERS` anywhere the platform reads one.** A
  project that has written its promises down and left them ungated is the
  state this check exists to surface, not one that hasn't opted in yet.

Every offender is reported at once, each naming why it's unowned.

A project that declares no outcomes passes silently: there's no gate to ask
for over nothing.

`CODEOWNERS` is read from the three locations GitHub itself reads --
`CODEOWNERS`, `.github/CODEOWNERS`, `docs/CODEOWNERS` -- in the **enclosing
git repository**, which is not necessarily your project root. A project that
sits inside a larger repository is governed by that repository's file, at
patterns carrying the project's own directory prefix.

There's no environment variable to point this somewhere else, unlike
`SEAL_K8S_DIR` and `SEAL_OUTCOMES_DIR`: a file the platform
never reads owns nothing, so an escape hatch here would only let a project
pass a check while having no gate.

## The half Seal can't check

**`CODEOWNERS` on its own blocks nothing.** Without branch protection it
assigns reviewers to a pull request and lets it merge unreviewed. Three
settings on the branch those outcome tests gate are what turn it into a
gate, and a repository administrator has to apply them:

1. **Require a pull request before merging** -- otherwise a push to the
   branch bypasses every rule below.
2. **Require review from Code Owners** -- this is the one that makes a
   `CODEOWNERS` entry blocking rather than advisory.
3. **Require status checks to pass** -- the check that runs `seal ci` among
   them, since that's what runs the outcome suite. Without it, "every
   outcome test passes" is a claim nothing verifies before a merge.

Seal deliberately doesn't apply these. They live in a repository's
settings rather than its contents, so reaching them means a token with admin
scope, granted to a tool that cannot verify from a checkout whether the
settings took. That's the same boundary Seal draws around clusters,
registries and domains.

:::{important}
A green `seal check` says the tree is **owned**, not that a merge is
**gated**. The second needs the three settings above, and confirming them is
a job for whoever administers the repository.
:::

## What the gate doesn't claim

It makes an outcome test un-editable without review. It says nothing about
whether the tests it protects *ran* -- a gate over tests nobody executed is
a gate over nothing.

Unattended merge needs both halves: every outcome test run in one pass, and
every one of them un-editable without a human. This page is the second;
[`seal outcomes run`](outcomes.md#running-the-suite) is the first, and
`seal ci` is what puts it in front of a merge.

Running them is still not the same as covering them. A suite reports every
promise a project has *translated*, and a promise nobody has written a test
from yet is reported as exactly that rather than counted as kept -- so a
green suite is a claim about the promises in the tree, and what belongs in
the tree stays a human's judgement.
