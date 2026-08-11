# a promise that has been changing its mind is named

A promise whose verdict has been changing across recent runs is named.

A test that fails one run in four looks perfectly ordinary in any single
one of them. Nobody notices it from a run; they notice it from a mood --
that the suite has been annoying lately -- which is not something anybody
can act on.

Changes of verdict rather than failures. A promise red every run since
somebody broke it is a regression, and the suite already says so each
time. What this finds is the one that has been red and green in the same
window with nothing deciding which.

## Worth covering

- A promise that has flipped repeatedly is named; a steadily red one is
  not, because it is a different thing.
- The evidence is what is reported -- how often, over how many runs.

## What this does not claim

**It concludes nothing.** Whether the test is at fault, the application is
genuinely intermittent, or the environment is, is a judgement -- and the
change it leads to goes through review like any other. A rate is evidence.

There is no threshold. A number chosen before anything had measured one
would be guidance dressed as a rule.
