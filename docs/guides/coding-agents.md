# Coding agents

Seal's long-term goal is a merge gate reliable enough that a coding
agent's pull request can merge on the strength of the tests rather than on
somebody's reading of them. That only works if the agent proposing the
change uses the project the way the gate assumes: `seal up` rather
than `tilt up`, a fixed application rather than an edited test, a promise
written down before a test is written from it.

So Seal ships that as instructions the agent reads, installed into your
repository beside the code.

## What gets installed

A set of skills and subagents, under `.claude/` in your project:

| Skill | What it covers |
| --- | --- |
| `seal` | The entry point: what Seal guarantees, which `seal` command replaces which `tilt` command, the rules, and where to go next. |
| `seal-install` | Adopting Seal: the CLI, these skills, registering the extensions, the layout, verifying it. |
| `seal-machine` | What a command needs of the machine -- daemon, cluster, registries -- and when an agent may establish it itself. |
| `seal-dev-loop` | `seal up`, reset triggers, running one outcome, `seal run`, and what `seal ci` adds. |
| `seal-add-service` | `services/<name>/`, `seal_service()`, the `.env` schema, readiness probes, reset scripts. |
| `seal-outcome` | Promises, translating one into a test, running and reviewing it, runners and `seal-test-config.json`. |
| `seal-merge-gate` | `CODEOWNERS`, the branch protection Seal can't apply, and the reusable CI workflow. |
| `seal-regression-loop` | Getting a red outcome suite back to green: run it all, confirm each failure, fix the application, repeat. |
| `seal-doctor` | Error message to root cause. |

And five subagents for the parts that run long enough, or need context of
their own, to be worth handing off whole: `seal-outcome-translator`
(write one translation and iterate until it runs),
`seal-outcome-reviewer` (check a translation against its promise,
read-only), `seal-ci-doctor` (diagnose a red run, changing nothing),
`seal-app-fixer` (make one confirmed failure pass by changing the
application, never the test), and `seal-loop-triager` (decide what to
do about a regression loop that has stopped converging -- a separate session
by design, never the one that was in it).

Each one restates what this documentation says, in the form an agent acts on
rather than reads: the rules stated as prohibitions with their reasons, and
the commands to verify each step with.

## Installing them

```sh
git clone --depth 1 https://github.com/vdel/autologate /tmp/seal
/tmp/seal/bin/install-seal-skills --target .
```

That copies every skill and agent into `<target>/.claude/`, and maintains a
short block in your `CLAUDE.md` pointing at them. Commit both: a teammate who
pulls gets the skills with no install step of their own, and so does every
agent session opened against the repository.

| Option | What it does |
| --- | --- |
| `--target DIR` | Where to install. Defaults to the git repository you're in. |
| `--from DIR` | Install from this checkout of Seal instead of cloning. |
| `--ref REF` | Which revision to clone when there's nothing local. Defaults to `main`. |
| `--check` | Report what's out of date and exit non-zero, writing nothing. What a CI job wants. |
| `--link` | Symlink back to the checkout instead of copying, for working on the skills themselves. |
| `--uninstall` | Remove every skill, agent and `CLAUDE.md` block it put there. |

Re-running it upgrades in place: files are replaced, a skill Seal no
longer ships is removed, and the `CLAUDE.md` block is refreshed. Everything
it touches is named `seal` or `seal-<something>`, so your own
skills and your own `CLAUDE.md` prose are never in question.

Pinning the revision you install from is worth doing where the instructions
should change when you decide rather than when Seal does:

```sh
/tmp/seal/bin/install-seal-skills --target . --ref v1.2.3
```

## Keeping them current

`--check` writes nothing and exits non-zero when anything is out of date, so
a job on your own CI can say so:

```sh
git clone --depth 1 https://github.com/vdel/autologate /tmp/seal
/tmp/seal/bin/install-seal-skills --target . --check
```

Whether that's a failing check or an advisory one is your project's call. The
instructions describe a CLI and a set of extensions your project is already
pinned to; the risk they carry is being *stale* against those, which is
exactly what this reports.

## What the instructions insist on

Three of them are worth knowing without opening a skill, because they are the
ones that look locally reasonable and are globally wrong:

- **`seal up` and `seal ci`, never `tilt up`/`tilt ci`.** The
  objects an overlay annotates are filled just before Tilt starts, and a
  bare `tilt` run does not refuse -- it deploys them empty -- see
  [Credentials](credentials.md).
- **Never edit an outcome test to make a run green.** A suite passes
  identically whether the application was fixed or the test was rewritten,
  and telling those two apart is the whole of what the gate is for. An agent
  that can't find an application fix is told to say the promise looks wrong
  and leave it to a code owner -- see [The merge gate](merge-gate.md).
- **Never wait on the clock.** `seal check` refuses `waitForTimeout` under
  the `playwright` runner, and the instructions give the alternative rather
  than only the prohibition -- see
  [Wait on the state](translating-promises.md#wait-on-the-state-never-on-the-clock).

None of this is enforcement: instructions are read, not applied. What
enforces is `seal check`, the outcome suite, and `CODEOWNERS` over the
outcome tree. The skills exist so that an agent doing the right thing doesn't
have to rediscover it from the shape of the repository, and so that one doing
the wrong thing hits a rule with a reason attached rather than a surprise.

## Working on the skills themselves

They live in
[`.claude/`](https://github.com/vdel/autologate/tree/main/.claude) in the
Seal repository, alongside the `tilt/` and `python/` halves they
describe, and that directory's own `README.md` covers the conventions
they're written to. `--link` installs them into a project as symlinks back
to your checkout, so a session in that project reads your edits as you make
them.
