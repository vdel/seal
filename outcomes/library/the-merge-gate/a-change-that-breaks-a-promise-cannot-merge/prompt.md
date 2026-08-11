# a change that breaks a promise cannot merge

A pull request that stops a promise being kept fails the gate, and the
gate blocks the merge. The suite's exit status is its verdict rather than a
summary of one, and every promise is checked -- not the ones somebody
remembered.

This is what the whole library is for. Everything else it does -- the
reproducible environment, the readiness rule, the credential path, the
runners -- exists so that this claim can be made honestly.

The verdict has to rest on the whole suite. A gate on a subset is a gate on
whichever tests somebody thought to run, which is the judgement the gate
exists to replace.

## Worth covering

- A promise that stops being kept turns the run red and the run red blocks
  the merge -- both halves, since a red run nothing gates on is a report.
- The whole suite ran, not a subset: a project cannot go green by narrowing
  what was checked.
- A quarantined promise is the one documented exception, and it is never
  reported as kept even when it does not fail the run.

## What this does not claim

That an agent's change is *good*. The gate is structural: it establishes
that every currently-committed promise still holds, and says nothing about
whether the change is elegant, small, or well-judged. A substantial rewrite
that satisfies every promise merges, and that is the intended outcome
rather than a loophole.

That the application is correct beyond what it promises. What is not
promised is not checked.
