# Translating a promise

How an outcome prompt becomes a low-level test, what Seal hands whoever
writes one, and what the reviewer sees.

## What Seal does here, and what it doesn't

A prompt is what the application promises. A test is one reading of that
promise against the implementation as it stands, and the reading is lossy:
the same prompt yields different tests in different hands, each pinning
implementation choices the prompt never made. That's why a translation needs
a person to approve it -- not because the writer isn't trusted, but because
*which reading this is* isn't something the test can attest to about itself.

So Seal doesn't write the test. It does the three things around it:

- **Poses the task.** `seal outcomes translate` gathers everything a
  translation needs, read off the project it's invoked in.
- **Checks the answer.** `seal check` refuses what's mechanically wrong, and
  `seal outcomes run <slug>` says whether it runs.
- **Puts it in front of the reviewer.** `seal outcomes review` renders the
  promise beside the translation, and says what's already been settled -- so
  the review is spent on intent.

:::{note} **Nothing here starts an agent.** What an agent session did isn't
something a checkout can verify, and a capability Seal can't verify
from a checkout is one it doesn't claim. Whatever is writing the test reads
the brief: an agent session, or a person. Both read the same thing, which is
also what keeps the brief proofread. :::

## Asking for a brief

From the project root:

```sh
seal outcomes translate ui/todo-list/an-item-survives-a-reload
```

An outcome is named by the three directories that spell it,
`<group>/<epic>/<outcome>`. A slug that names nothing is an error listing
the ones that do, rather than a brief for nothing.

What comes back is prose on stdout, in sections:

- **The promise** -- the whole of `prompt.md`, not just its headline. The
  prose under the headline is where a promise says which cases it covers
  and, just as bindingly, what it deliberately doesn't claim.
- **Where the translation goes** -- the outcome's own directory. That
  pairing is the traceability the review rests on. Alongside it, the group's
  `helpers/`: what this group's tests already share, and where to put
  anything the next one would repeat.
- **What will run it** -- this group's runner. The `playwright` one and
  exactly which files it collects; the `tap` group's own `run`, started once
  for the whole group and read off the stream it prints; or your group's own
  `Dockerfile` and the contract Seal holds it to. Read off the tree and
  the config beside it, never assumed: a brief describing the wrong runner
  has somebody write a test nothing starts.
- **How the test reaches the application** -- `SEAL_BASE_URL`, and where its
  value comes from. A `tap` group is told about neither: it runs on the
  machine, and has no cluster to address until something in it has brought
  one up.
- **What the translation has to do**, and **how to check it**.

## What a translation has to be

Most of what makes a translation good is judgement, which is why a person
approves it. One part isn't, and `seal check` holds that one.

### Wait on the state, never on the clock

A multi-service outcome test is the most flake-prone thing a project runs,
and a sleep is how it becomes one: it holds on the machine it was written on
and fails wherever the browser is slower, reporting a promise as broken
because something was slow. A promise whose test does that is worse off than
one with no test at all -- it spends real time, and it teaches whoever sees
it to read past red.

Under the `playwright` runner that has exactly one spelling,
`waitForTimeout`, and `seal check` refuses it. Wait on the thing itself
instead: a web-first assertion (`expect(locator).toBeVisible()`) or
`locator.waitFor()` retries until it holds, and gives up only when it never
does.

A group run by a `custom` runner is taken at its word here, the same way it
is about what can run at all. A sleep-detector for every language a
`Dockerfile` might run would be a lint pretending to be a rule.

### The rest, which a reviewer checks

**Assert the promise, not the implementation.** A prompt is written in the
application's own terms; the specifics are the translation's to choose, and
one that pins a specific which could change without the promise changing
will fail for something that was never promised.

**Leave withheld what the prompt withholds.** Where a promise says it claims
nothing about something, asserting on it anyway isn't thoroughness -- it's a
promise the project never made, enforced as though it had.

**Own the data it asserts on.** Outcomes run one at a time against the same
application, each starting from whatever the one before it left.

**Share the plumbing, keep the claim.** What several outcomes repeat --
signing in, reaching a page, reading a value back -- belongs in the group's
[`helpers/`](outcomes.md#helpers-what-a-groups-tests-share), imported as
`../../helpers/<name>`. What the promise turns on stays in the test: a code
owner approves it by reading it against the prompt, and a claim moved behind
a helper is one they'd have to go looking for.

**Say where it came from, in the file itself** -- which prompt, and which
choices the prompt left open were made here and why. That paragraph is what
a reviewer reads first, and it's what separates a test somebody can check
from one they can only run.

## Working through what hasn't been translated

Which promises have nothing written against them is the question `seal
outcomes` opens with, and it reports it as bare slugs, which is what makes
the whole of it a loop:

```sh
seal outcomes --untranslated | while read -r slug; do
  seal outcomes translate "$slug"
  # ...write the test, then:
  seal check && seal outcomes run --reset "$slug"
done
```

One promise at a time, deliberately. A brief for the whole tree at once is a
document nobody reads rather than a task anybody starts, and each test has
to be checked in the suite before the next one is written on top of it.

## First authorship and a rewrite are different asks

An outcome that already has a translation is refused unless `--rewrite` says
so:

```sh
seal outcomes translate --rewrite ui/todo-list/an-item-survives-a-reload
```

Both cases reach a human -- the whole tree is under `CODEOWNERS` -- but the
reviewer's question isn't the same one:

- For a **first translation**: "does this encode the promise?"
- For a **rewrite**: "what does this reading assert that the committed one
  didn't, and is that a better reading of the same promise, or a *different
  promise*?" -- and if it's the second, the prompt is what should be
  changing.

Saying which it is has to happen when the brief is asked for. Left to the
diff, it's the reviewer who has to work out which of the two they're looking
at, from a change that looks identical either way.

The flag is consent rather than description: what the brief says about the
committed translation it reads off the tree, so asking for a rewrite where
there's nothing to replace simply briefs first authorship.

## Reviewing a translation

```sh
seal outcomes review ui/todo-list/an-item-survives-a-reload
```

A change that only adds a translation shows the test and not the prompt --
the prompt didn't change, so it isn't in the diff at all. The reviewer's
whole question is whether the one encodes the other, and that needs both in
front of them.

So the rendering is:

- **The promise**, in full.
- **The translation**, every file of it. A fixture that isn't text is named
  rather than rendered -- what a test seeds itself from is as much a part of
  what it asserts as the assertions are.
- **What's already been checked**: which runner is in force, which files
  that runner actually starts a test from, whether the translation waits on
  state or on the clock, and whether `CODEOWNERS` reaches every file of it.
  Each read from the code `seal check` runs, not restated -- a summary that
  disagreed with the gate would be worse than no summary.
- **What's left to the reviewer**, said plainly: does the test assert the
  promise or an implementation detail that happens to be true today; does it
  leave withheld what the prompt withholds; would a promise-breaking change
  actually make it red; and does the file say which choices the prompt left
  open were made here.

**It doesn't summarise what the test asserts.** A summary is a second thing
to review rather than less to review, and one that read the test more
generously than the test reads is the single failure this can't afford.

A promise with no translation yet is refused rather than reviewed -- there's
nothing to check the prompt against, and what to ask for instead is the
brief.

## What this doesn't touch

The gate itself. `CODEOWNERS` is what makes the review mandatory, and branch
protection is what makes `CODEOWNERS` blocking -- see
[The merge gate](merge-gate.md). Nothing here reaches your forge, opens a
pull request, or writes into the tree.
