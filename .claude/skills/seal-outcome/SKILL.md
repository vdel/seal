---
name: seal-outcome
description: Work with what a Seal project promises -- write an outcome prompt, translate a promise into a low-level test, run and review one, wire a group into a runner through seal-test-config.json, or bring a custom runner. Use whenever outcomes/, a prompt.md, an outcome test, seal outcomes translate/review, a spec under a group/epic/outcome directory, or "what does this project promise" comes up, and before adding any end-to-end test to a Seal project.
---

# Outcomes: promises, and the tests translated from them

## The prompt is the source of truth

An outcome prompt is a promise, written the way somebody *using* the
application would put it:

> an item I add is still on the list after a reload

A test is one reading of that promise against the implementation as it
stands. Translating is lossy -- the same prompt yields different tests in
different hands, each pinning implementation choices the prompt never made.
So the prompt is what the project actually promises, the test is a reading of
it, and a human has to be able to check the one against the other. That
requirement is what shapes everything below.

## The tree

**A prompt and its translation share a directory.**

```
outcomes/
  seal-test-config.json    # what runs each group
  <group>/                 # one runner drives a group
    helpers/               # what this group's tests share
    <epic>/
      <outcome>/
        prompt.md          # the promise
        ...                # the test translated from it, and its fixtures
```

- A group holds only epic directories, plus `helpers/`; an epic holds only
  outcome directories. (A `custom` group's own level also holds files: they
  are its runner's build context.)
- `helpers/` is what a group's tests share -- signing in, reaching a page,
  reading a value back. It holds no promises: `helpers` is not a name an epic
  can have, and a `prompt.md` or a spec file under it is refused, because
  nothing walks it for outcomes and a run never looks in it. A spec imports
  it relatively (`../../helpers/<name>`); nothing has to put it in the image,
  since a runner is built from the group's own directory.
- Slugs are lowercase letters, digits and single hyphens, at all three
  levels: a slug is a path component, a test identifier in a report and a
  `CODEOWNERS` pattern at once.
- The tree sits at the project root, not under any one service -- driving
  several services at once is what makes a test an outcome test. Elsewhere
  means naming that directory in `SEAL_OUTCOMES_DIR`.

## Writing a prompt

`prompt.md`, whose first non-blank line is an ATX H1:

```markdown
# an item I add is still on the list after a reload

Adding an item is the one thing this list is for, and a list that forgets it
on the next page load is broken however good the rest of it looks. Reload
means a fresh page load against the same running environment, not a re-seeded
one.
```

The headline is the only part read mechanically -- it names the outcome in
every report, rather than the slug. Everything under it is for whoever
translates the prompt: context, edge cases worth covering, and what the
promise deliberately does **not** claim.

- **Write it in the application's own terms and no lower.** An endpoint, a
  selector, a table or a service name in a prompt is an implementation choice
  that belongs in the translation, where it can change without the promise
  changing.
- **Promise something about the application, to whoever uses it** -- never
  something about the test harness. "The list starts from the same three
  items every run" is the reset mechanism's contract, already guaranteed
  elsewhere; restating it as a promise spends a human review on test
  infrastructure.

A prompt with no translation yet is a legitimate state: reported as `no test
yet`, counted, and not a failure.

## Translating a promise

```sh
seal outcomes --untranslated                        # bare slugs, one per line
seal outcomes translate <group>/<epic>/<outcome>    # the brief for one of them
```

The brief is prose on stdout: the promise in full, the directory the
translation goes in, whichever runner the group declares and exactly which
files it collects, how the test reaches the application, and what the result
has to satisfy. **Read the brief before writing the test** -- the runner is
read off the tree rather than assumed, and a test nothing starts is reported
as an untranslated promise.

Seal poses the task and checks the answer. It writes nothing and
starts no agent, so what goes in the file is yours.

Then:

```sh
seal check                                          # what is mechanically wrong
seal outcomes run <group>/<epic>/<outcome>          # does it actually run
```

One promise at a time, deliberately: each test has to be checked in the suite
before the next is written on top of it. For more than one, hand each slug to
the **`seal-outcome-translator`** subagent, which runs that loop to
completion on its own.

An outcome that already has a translation needs `--rewrite`. That flag is
consent rather than description: a first authorship and a rewrite are both
reviewed by a human, but the reviewer's question differs -- "does this encode
the promise?" against "is this a better reading of the same promise, or a
*different promise*?" If it is the second, the prompt is what should be
changing.

## What a translation has to be

One rule is mechanical and `seal check` holds it:

**Wait on the state, never on the clock.** A sleep holds on the machine the
test was written on and fails wherever the browser is slower, reporting a
promise as broken because something was slow -- worse than no test at all,
because it teaches whoever sees it to read past red. Under the `playwright`
runner that has exactly one spelling, `waitForTimeout`, and `seal check`
refuses it. Wait on the thing itself: `expect(locator).toBeVisible()` or
`locator.waitFor()` retries until it holds and gives up only when it never
does.

The rest is judgement, which is why a person approves it:

- **Assert the promise, not the implementation.** Pinning a specific that
  could change without the promise changing buys a test that fails for
  something never promised.
- **Leave withheld what the prompt withholds.** Asserting on what a promise
  says it does not claim is not thoroughness; it enforces a promise the
  project never made.
- **Own the data it asserts on.** Outcomes run one at a time against the same
  application, each starting from whatever the one before it left. A full run
  resets each service that declared one *before* the run, not between
  outcomes.
- **Share the plumbing, keep the claim.** What several outcomes repeat goes
  in the group's `helpers/`; what the promise turns on stays in the test. A
  code owner approves the test by reading it against the prompt, and a claim
  moved behind a helper is one they have to go looking for.
- **Say where it came from, in the file itself** -- which prompt, and which
  choices the prompt left open were made here and why. That paragraph is what
  separates a test somebody can check from one they can only run.

## Running and reporting

```sh
seal outcomes run                            # the whole suite; the exit code is its verdict
seal outcomes run <slug> [<slug>...]         # just these, against a running session
```

| Verdict | Meaning |
| --- | --- |
| `PASS` / `FAIL` | The test ran and said so. |
| `no verdict` | A translated outcome left nothing to read. **A failure** -- every way a test silently fails to run looks like an absent file from here. |
| `no test yet` | A promise nothing has been translated from. Not a failure. |

**Every outcome, every run.** A fix scoped to the one test somebody was
looking at can break another nobody re-ran, so a listing that leaves an
outcome out is indistinguishable from one where it passed. CI never names a
subset.

## Reviewing a translation

```sh
seal outcomes review <group>/<epic>/<outcome>
```

A change that only adds a translation does not contain the prompt -- it did
not change, so it is not in the diff. This renders both, plus what has
already been settled mechanically, so the review is spent on intent. It
deliberately does not summarise what the test asserts: a summary that read
the test more generously than the test reads is the one failure this cannot
afford.

The **`seal-outcome-reviewer`** subagent does this pass and reports
what is left to a human.

## Wiring a group to a runner

One entry per group in `outcomes/seal-test-config.json`:

```json
{
  "runner": [
    { "name": "ui", "runner_type": "playwright" },
    {
      "name": "api",
      "runner_type": "custom",
      "dockerfile": "api/Dockerfile",
      "runner_args": ["--strict"]
    }
  ]
}
```

`runner_type` is `playwright` or `tap` for the runners Seal supplies,
`custom` for a `Dockerfile` the project brings. `dockerfile` and
`dockerfile_context` are `custom`-only and default to
`<name>/Dockerfile` and the group's own directory; neither may reach outside
the tree. This file is the one thing about an outcome tree a walk cannot
answer, so it is also the one thing that can drift -- `seal check`
refuses a group no runner names and a runner naming no group.

And one call in the root Tiltfile, after every service is `include()`d:

```python
load('ext://seal', 'register_outcome_runner', 'reset_resource_name')

register_outcome_runner(
    base_url='http://<service>:<port>',
    resource_deps=[reset_resource_name('<service>')],
)
```

`base_url` is where the application answers **from inside the cluster**;
Seal knows nothing about service names or ports, so the project says
it. It reaches every runner as `SEAL_BASE_URL`, and the `playwright`
runner makes it Playwright's `baseURL`, so a spec navigates with
`page.goto('/')`. `resource_deps` is what every outcome test waits for --
which resources have to be serving, and which services at a known baseline.

### A group that runs on the machine

`runner_type: "tap"`, for a promise about the layer *underneath* a session --
bringing an environment up, a command refusing to start, a CLI the project
ships. Nothing running inside a session can answer whether `seal up`
brings that session up, so these cannot be tested from a container in the
cluster under test.

Put an executable called `run` at the group's root. Seal starts it
**once for the whole group**, from the project root, as
`<runner_args...> -- <epic>/<outcome> ...` -- the same arguments a container
runner gets. It prints [TAP](https://testanything.org/) on stdout, one test
point per outcome, described by the slug exactly as it was handed:

```
1..2
ok 1 - gating/a-broken-promise-cannot-merge
not ok 2 - gating/an-unowned-tree-is-refused
```

That is the whole contract: no verdict file, no `done` marker, nothing to
stay up for, and it may exit however it likes. Seal turns each point
into that outcome's verdict, so the report, quarantine, `--confirm` and the
regression loop all work unchanged.

Never read as a promise being kept: a point that was never emitted, one
carrying `# SKIP` or `# TODO`, and any promise a run bailed out before
reaching. Each keeps no verdict, which the suite reports as a test that did
not run.

`seal check` refuses a `tap` group with no `run`, or one whose `run` is
not executable -- git records the bit, so `chmod +x` it and commit that.

What it costs: the group runs on whatever machine invoked it, which is the
dependence the container model exists to remove. Bounded on purpose -- `tap`
is for promises *about* that layer, and a promise about the application's own
behaviour belongs in the cluster.

### Bringing a custom runner

A container started as `<runner_args...> -- <epic>/<outcome> ...`, with
outcomes named from *inside* the group. Five obligations:

1. Run the outcomes named after `--`; with none, run everything it finds.
2. Write each verdict to `/outcome-results/<epic>/<outcome>/passed` -- `1` or
   `0`. Anything else, or no file, is a failure.
3. Leave logs, reports and screenshots beside it. The whole of
   `/outcome-results/` comes back as `tests-results/outcomes/<group>/`.
4. Write `/outcome-results/done` when the run has finished -- that is what
   Seal's readiness probe watches, and what distinguishes "finished" from
   "died after the third of twenty".
5. Stay up afterwards, and declare an `ENTRYPOINT`: results are copied out of
   the running container, and Kubernetes `args` replace a `CMD` rather than
   adding to it.

**Failing by exiting is the one thing a runner must not do.** A container
that exits non-zero takes its resource down with it and stops the run before
the promises behind it have said anything. Catch each failure, write `0`,
carry on, stay up.

## Quarantining a promise whose test is the problem

Where a promise keeps failing for a reason no application fix will settle --
the test doesn't own the data it asserts on, or it isn't deterministic --
a `quarantine.md` in the outcome's own directory, whose whole content is the
reason, says so:

```markdown
The delete button races the list re-render, so this fails about one run in
five on a loaded runner. Being rewritten to wait on the row disappearing.
```

It still runs and is still reported, as `FAIL (quarantined)`. What changes is
that a failure there doesn't fail the run.

- **Never quarantine to get a run green.** It is the same move as editing the
  test, and it is gated the same way: the note lives in the outcome's
  directory, so `CODEOWNERS` covers it and a code owner has to approve it.
  Propose one, with the reason, and let them decide.
- **Never report a quarantined failure as a pass.** It isn't one. A green
  suite has to stay a claim about promises that were kept.
- A quarantine with no reason is refused by `seal check`: a test somebody
  switched off and one whose determinism somebody is fixing look identical
  from the tree.

`seal outcomes` names what has been changing its mind lately, from the
record each run appends under `.workspace/seal/` -- evidence that a
promise may need this, never a conclusion that it does.

## What `seal check` refuses

An outcome directory with no `prompt.md`; a `prompt.md` with no H1; a file
where the layout has only directories; a promise or a test filed under a
group's `helpers/`; a group no runner names or a runner naming no group; a
translation the group's runner cannot start; a `waitForTimeout`, in a
translation or in a helper; a quarantine with no reason; a name that is not
a slug; and an outcome the repository's `CODEOWNERS` does not cover. Every
offender at once.

Two things are deliberately not failures: a prompt with no translation yet,
and a project with no outcome tree at all.
