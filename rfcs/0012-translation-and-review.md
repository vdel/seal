# RFC 0012: Translation and review

| | |
| --- | --- |
| **Status** | Accepted |
| **Related** | [0009](0009-outcome-tests.md), [0010](0010-outcome-tree.md), [0011](0011-outcome-runners.md) |
| **How-to** | [Translating a promise](../docs/guides/translating-promises.md) |

## Context

A prompt is what the application promises. A test is one reading of that
promise against the implementation as it stands, and the reading is lossy: the
same prompt yields different tests in different hands, each pinning
implementation choices the prompt never made.

So a translation needs a person to approve it -- not because whoever wrote it
isn't trusted, but because **which reading this is** is not something the test
can attest to about itself.

This is deliberately the *only* place review happens on the everything-is-green
path ([RFC 0009](0009-outcome-tests.md)), which is what makes it worth doing
properly.

## Decision

**Seal does not write the test.** It does the three things around it:

- **Poses the task.** A brief gathers what one translation needs -- the
  promise in full, the one directory it can go in, whichever runner its group
  declares, how the test reaches the application, and what the result has to
  satisfy -- read off the project it is invoked in.
- **Checks the answer**, for the one constraint that is mechanical rather than
  a judgement: a translation waits on state, never on the clock.
- **Puts it in front of the reviewer**, rendering the promise beside the
  translation, since a change that only adds a test does not carry the prompt
  in its diff.

Asking for a translation where one already exists is refused unless a flag
says a rewrite is intended. Reviewing a promise with no translation is refused
rather than answered.

**Nothing here starts an agent, and nothing here reaches the platform.**

## Rationale

### One brief, one promise, read off the project

A brief for the whole tree at once is a document nobody reads rather than a
task anybody starts. One promise at a time also means each test is checked in
the suite before the next is written on top of it -- and it composes into a
loop, which is why the listing of untranslated promises has a bare-slug form
([RFC 0010](0010-outcome-tree.md)).

Everything in the brief is read off the tree and the config beside it, never
assumed. A brief describing the wrong runner has somebody write a test nothing
starts.

The prompt goes in **in full**, not as its headline: the prose under the
headline is where a promise says which cases it covers and -- just as binding
-- what it deliberately does not claim.

Both an agent session and a person read the same brief. That is also what
keeps it proofread.

### The one rule a check can hold: wait on state, never on the clock

A multi-service outcome test is the most flake-prone thing a project runs, and
a sleep is how it becomes one. It holds on the machine it was written on and
fails wherever the browser is slower, reporting a promise as broken because
something was slow.

A promise whose test does that is worse off than one with no test at all: it
spends real time, and it teaches whoever sees it to read past red.

Under Seal's own runner that has exactly one spelling, so the check
refuses it -- in a translation and in a shared helper alike, and harder in a
helper, since every outcome importing it inherits the wait. Waiting on the
thing itself instead is not merely better practice: a retrying assertion gives
up only when the state never arrives, which is the failure worth reporting.

A group whose runner the project brought is taken at its word here, for the
same reason it is about what can run at all
([RFC 0011](0011-outcome-runners.md)): a sleep-detector for every language a
`Dockerfile` might run would be a lint pretending to be a rule.

### What the brief asks for, and a reviewer checks

The rest is judgement, which is why a person approves it:

- **Assert the promise, not the implementation.** A prompt is written in the
  application's own terms; a test that pins a specific which could change
  without the promise changing will fail for something that was never
  promised.
- **Leave withheld what the prompt withholds.** Asserting on something a
  promise explicitly does not claim is not thoroughness -- it is a promise the
  project never made, enforced as though it had.
- **Own the data it asserts on.** Outcomes run one at a time against the same
  application, each starting from whatever the one before it left.
- **Say where it came from, in the file itself** -- which prompt, and which
  choices the prompt left open were made here and why. That paragraph is what
  a reviewer reads first, and it is what separates a test somebody can check
  from one they can only run.

### First authorship and a rewrite are different asks

Both reach a human -- the whole tree is owned -- but the reviewer's question
is not the same one. For a first translation it is "does this encode the
promise?". For a rewrite it is "what does this reading assert that the
committed one didn't, and is that a better reading of the same promise or a
*different promise*?" -- and if it is the second, the prompt is what should be
changing.

Saying which it is has to happen when the brief is asked for. Left to the
diff, it is the reviewer who has to work out which of the two they are looking
at, from a change that looks identical either way.

The flag is consent rather than description: what the brief says about the
committed translation it reads off the tree, so asking for a rewrite where
there is nothing to replace simply briefs first authorship.

### The review renders both, and summarises neither

A change that only adds a translation shows the test and not the prompt: the
prompt didn't change, so it isn't in the diff at all. The reviewer's whole
question is whether the one encodes the other, and that needs both in front of
them.

So the rendering is the promise in full, every file of the translation -- with
a fixture that isn't text named rather than rendered, since what a test seeds
itself from is as much a part of what it asserts as the assertions are -- and
then two lists: what has already been checked, and what is left to the
reviewer.

**What has been checked is read from the code the check runs**, not restated.
A summary that disagreed with the gate would be worse than no summary, because
it spends the reviewer's attention on re-deriving what they were just told.

**What is left is said plainly**: does the test assert the promise or an
implementation detail that happens to be true today, does it leave withheld
what the prompt withholds, would a promise-breaking change actually make it
red, and does the file say which choices the prompt left open were made here.

**It does not summarise what the test asserts.** A summary is a second thing
to review rather than less to review, and one that read the test more
generously than the test reads is the single failure this cannot afford.

### What this deliberately does not touch

The gate itself. `CODEOWNERS` is what makes the review mandatory and branch
protection is what makes `CODEOWNERS` blocking
([RFC 0009](0009-outcome-tests.md)). Nothing here opens a pull request, writes
into the tree, or starts a session: what an agent session did is not something
a checkout can verify ([RFC 0001](0001-library-boundary.md)).

What was missing was never enforcement -- the review is already mandatory --
but the material to review *with*.

## Consequences

- **Every translation costs a human's attention once.** That is the price of
  the tests being trustworthy enough to merge on.
- **A brief is only as good as the project it reads.** A misdeclared runner
  produces a confidently wrong brief, which is why the config is checked
  ([RFC 0011](0011-outcome-runners.md)).
- **Most of what makes a translation good is unenforced**, on purpose. The one
  mechanical rule is held by a check; the rest is what the reviewer is for.

## Alternatives considered

**Generating the test and having Seal approve it.** It would remove the
one review on the green path, and with it the only thing standing between a
failing test and a rewritten one.

**Summarising the translation for the reviewer.** Less to read, and the
failure mode is a summary more generous than the test -- which is precisely
the thing the reviewer was there to catch.

**A lint for every rule the brief states.** Assertions about implementation
detail, or a promise over-asserted, cannot be recognised mechanically. A check
that half-recognised them would train reviewers to trust it.
