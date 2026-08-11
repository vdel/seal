# RFC 0013: The regression loop

| | |
| --- | --- |
| **Status** | Accepted |
| **Related** | [0009](0009-outcome-tests.md), [0004](0004-deterministic-state.md), [0010](0010-outcome-tree.md), [0012](0012-translation-and-review.md) |
| **How-to** | [Getting a red outcome suite back to green](../docs/guides/regression-loop.md) |

## Context

The gate says a change merges unattended only if every committed outcome test
passes ([RFC 0009](0009-outcome-tests.md)). What happens between a red suite
and that state is a loop somebody -- usually an agent session -- runs, and it
has three ways to go wrong:

- it chases a failure that was noise, and spends real time or produces a fix
  for a bug that was never there;
- it fixes the promise that was red and breaks one nothing re-ran;
- it never terminates, because fixing A breaks B and fixing B re-breaks A.

## Decision

**The loop is empirical, and Seal's half of it is that each step is one
command whose answer is checkable from a checkout.**

1. Run the **whole** suite from a known baseline, and confirm each failure
   before acting on it.
2. Fix the **application** -- never the test -- for each confirmed failure.
3. Re-run the whole suite.
4. Repeat against whatever is still red.

- **The agent is fully external.** Seal starts none and configures no
  agent command; it ships the instructions.
- **Iterations run against a live session**, with every declared reset fired
  between runs, rather than a fresh cluster each time.
- **A failure is confirmed by re-running it on its own, from a reset**, once
  -- never until it passes.
- **The boundary is reported here and enforced at the merge.**
- **A loop is derived** from the record every run of the suite already
  appends, never declared by the session running it.
- **Triage belongs to a session that was not in the loop.**

## Rationale

### Empirical, not a classification

Whether a failure was "a regression" or "the spec changed" is settled by
whether the application *can* be patched to satisfy every outcome test at
once, not by anybody declaring an opinion about it. If it can, it was a
regression. If it provably cannot -- keeping one promise necessarily breaks
another -- that is a real conflict between what the project claims, at least
one prompt has to change, and that routes through a human by construction.

That is why step 3 re-runs everything. A fix scoped to one promise that
nothing re-verified against the rest is how another gets broken with nobody
looking.

### The agent is external, and every claim comes from re-running the suite

What an agent session did is not something a checkout can verify, and
Seal claims no capability it cannot verify from one
([RFC 0001](0001-library-boundary.md)). A "run this command each iteration"
seam would have Seal reporting a loop whose steps it cannot vouch for.

So the loop lives where the agent already is -- shipped as skills and a
subagent installed into an adopting project -- and Seal's half is making
each step one command: the whole suite from a baseline with failures
confirmed, one promise while working on it, whether this iteration stayed
inside the application, what has been changing its mind, whether the loop is
going anywhere, and the final check as a merge would run it.

**Every claim about whether the project is green comes from re-running the
suite. Never from what an iteration reports about itself.**

### Live session, reset between iterations

A run that starts from whatever the previous fix left behind is measuring
both. Firing every declared reset before each run
([RFC 0004](0004-deterministic-state.md)) is what makes one iteration the same
experiment as the last.

A fresh cluster per run stays the gate, and stays what a merge rests on. It is
simply not what a tight loop should pay for every iteration -- a full cluster
spin-up per attempt is the cost that makes a loop not worth running. So the
two coexist: reset to iterate, a fresh cluster to conclude.

### Nothing enters the loop unconfirmed

Multi-service end-to-end tests are the most flake-prone class of test a
project runs, so each failure is run **again, on its own, from a reset**. Both
halves carry weight:

- **Retried in place**, a failure is retried against the state that may have
  caused it, which papers a shared-state bug over rather than finding it.
- **Run alongside the others**, it is run against what they are doing to the
  same application -- and a promise that fails in the suite and holds by
  itself is a test that does not own the data it asserts on, which is a third
  thing again and not a matter of chance.

**Confirmed** means the application is what to fix. **Not confirmed** means
nothing in the application will settle it: either the test does not own its
data or it is not deterministic, and both are the translation's to fix, which
is a code owner's call ([RFC 0012](0012-translation-and-review.md)).

**It changes no verdict.** A promise this run did not see kept is one it did
not see kept, so an unconfirmed failure still fails the run and is never
reported as a pass. What a second run buys is a reason attached to the
failure, not a way out of it -- and it happens **once**, never until the test
goes green, which is exactly the retry the runners already refuse to do
([RFC 0011](0011-outcome-runners.md)).

### The boundary, twice over

The rule the whole design turns on is that a fix goes in the application and
never in the test. It is held in two places, and they are not alternatives.

**`CODEOWNERS` enforces it, at the merge.** That is the real gate, and it does
not depend on anything the loop does.

**A command reports it, now.** It names every path under the outcome tree a
change reaches and exits non-zero where there is one. Enforcement arriving at
the merge is many iterations after the line was crossed; a session that spent
four rounds converging on a change that cannot merge unattended has spent four
rounds. This is the part of the boundary a checkout can answer for itself -- a
diff against a directory, with nothing inferred about what a session did or
intended.

**It reports rather than refusing**, deliberately. Changing a promise is a
legitimate thing to do; what it costs is a human's approval. A second
mechanism that could refuse what `CODEOWNERS` allows, or allow what it
refuses, would make a green run mean less rather than more.

### Where a loop stops

Three ways, and only three:

1. **Green.** Every promise holds, confirmed the way a merge would confirm it
   -- a fresh cluster, since a loop's session has been reset a dozen times.
   Whether that green merges is the repository's branch protection and its
   code owners, never the loop's to declare.
2. **A promise is wrong.** Keeping one outcome test's promise necessarily
   breaks another's, or the application is right and the prompt no longer
   describes it. The loop stops and says which promises conflict; changing a
   prompt is a code owner's call, and that arbitration is exactly what the
   gate exists to keep with a human.
3. **It is going in circles.**

### A loop is derived, not declared

A loop is the rounds of the whole suite since the last one in which every
promise held. Nothing starts one and nothing finishes one: each run already
appends what it found, and a loop is a reading of that record.

The alternative -- an id a session carries, or a "loop start" it is asked to
run -- makes the bookkeeping depend on the session that is thrashing. That is
the same session this design gives no say in triage, for the same reason, so
letting it delimit the evidence would give it the say back through the side
door.

Two things are consequently not rounds. A run naming outcomes says nothing
about the promises it left out, so read as a round it would report every one
of them as fixed. And a quarantined promise is not red here, because the run
itself did not fail on it: counted otherwise, a code owner's deliberate
decision would hold a project in a loop no application fix could ever end.

### A cycle, and a backstop

**A cycle is a promise fixed and then broken again inside one loop.** Two
rounds establish it, so it is a signal on its own rather than a threshold --
and it is bounded by the loop, since a promise re-broken either side of a
green run belongs to two different ones and any long enough record would look
like a cycle otherwise.

**A backstop catches the other shape**: the chain where every round breaks
something never seen before -- no repeat, and no convergence either. It is
declared beside the runners, as a limit in rounds and a limit in minutes, and
held to the same standard as the rest of that file.

A project that declares nothing gets Seal's own numbers, and they are
backstops rather than measurements. Nothing has measured a loop, and a number
picked before anything has is guidance dressed as a rule -- so they sit past
any loop that is converging by a margin wide enough that a project which has
never thought about them is not fighting them. A project that has measured its
own replaces them in one place, which is the point of their being declared at
all.

The minutes counted are the loop's own: its first round to its last, not the
time since it started. A loop nobody has run since yesterday has not been
looping since yesterday.

### Triage has fresh context by construction

Six rounds of fixing A and breaking B is six rounds of building an account of
which promise is at fault, and **that account is what needs checking rather
than extending**. So the conclusion belongs to a session that was not in the
loop, shipped as instructions like the loop itself, and it reaches one of two:

- **A translation is stale.** Its prompt still describes what the project
  promises and the test has stopped being a faithful reading of it. Rewriting
  it is an ordinary change under the outcome tree and rides the same
  `CODEOWNERS` gate as any other, so no separate mechanism is needed. What the
  motivation buys is the reviewer's time: "yes, this test was out of date" is a
  minute, and reconstructing a six-round loop is not.
- **This should be satisfiable and isn't.** Nothing is touched. What a human
  has to decide or supply is said plainly, and the run simply stays red.

The two are the same gate and very different reviews, which is why the
motivation stays attached to whichever one it reached. **A prompt is never the
triage session's to rewrite**: deciding that what a project promises has
changed is exactly the arbitration the gate exists to keep with a human.

Nothing here enforces anything. An unresolved run cannot merge anyway -- the
suite is still red, and "every outcome test green" is already the merge's
precondition. What all of it buys is that the state gets surfaced with a
reason attached instead of being retried forever, which is a quality of the
report and not of the gate.

## Consequences

- **An iteration costs the whole suite.** That is what makes each one
  comparable to the last, and what stops a scoped fix breaking something
  quietly.
- **A confirmation costs an extra run per failure.** Once, and only for what
  was red -- a promise that held has nothing to reproduce.
- **The loop's record is a project artifact.** It is what a cycle, a backstop
  and the changing-its-mind report are all read from.
- **A stuck loop ends with a human, with a reason attached** rather than with
  a silent retry.

## Alternatives considered

**A namespace per iteration.** Cheaper than a cluster and stronger than a
logical reset, and it cuts across every path that currently assumes one
namespace. Machinery to add when something has measured the reset as
insufficient, not before.

**A fresh cluster per iteration.** What the gate does, and the cost that makes
a loop not worth running.

**Refusing a change that touches the outcome tree.** It would make the
boundary local rather than at the merge, and it would refuse something
legitimate -- and any disagreement with `CODEOWNERS` makes a green run mean
less.

**Letting the looping session declare its own loop, or triage it.** Both give
the account that needs checking authority over the evidence.
