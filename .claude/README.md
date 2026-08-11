# .claude/

The agent-facing half of Seal: what a coding agent reads to discover
Seal in a repository and use it correctly, rather than inferring it
from the shape of whatever project it lands in.

Like `tilt/` and `python/`, this is a deliverable. It is installed *into* a
project built on Seal -- `bin/install-seal-skills` copies it
there and maintains a pointer block in that project's `CLAUDE.md` -- and it
is also live in this repository, so an agent working on Seal itself,
or on the worked example, reads the same instructions an adopting project's
agent does. One copy, proofread by being the one everybody uses.

## What's here

| Path | What it is |
| --- | --- |
| `skills/seal/` | The entry point: what Seal guarantees, which `seal` command replaces which `tilt` command, the rules, and where to go next. |
| `skills/seal-install/` | Adopting Seal in a repository: the CLI, these skills, the extension registration, the layout, and how to verify it. |
| `skills/seal-machine/` | What has to be true of the machine before a command runs, and how an agent establishes it on a throwaway it owns. |
| `skills/seal-dev-loop/` | `seal up`, resets, running one outcome, `seal run`, and what `seal ci` adds. |
| `skills/seal-add-service/` | `services/<name>/`, `seal_service()`, the `.env` schema, readiness probes, reset scripts. |
| `skills/seal-outcome/` | Promises, translating one into a test, running and reviewing it, runners and `seal-test-config.json`. |
| `skills/seal-merge-gate/` | `CODEOWNERS` over the outcome tree, the branch protection Seal can't apply, and the reusable CI workflow. |
| `skills/seal-regression-loop/` | Getting a red outcome suite back to green: run it all, confirm each failure, fix the application, repeat. |
| `skills/seal-doctor/` | Error message to root cause. |
| `agents/seal-outcome-translator.md` | Writes one translation and iterates until it runs. Never touches a prompt. |
| `agents/seal-outcome-reviewer.md` | Checks one translation against its promise. Read-only. |
| `agents/seal-ci-doctor.md` | Diagnoses a red run and reports the evidence. Changes nothing. |
| `agents/seal-app-fixer.md` | Makes one confirmed failure pass by changing the application. Never touches `outcomes/`. |
| `agents/seal-loop-triager.md` | Decides what to do about a loop that has stopped converging. Never the session that was in it. |

Skill names are `seal` or `seal-<something>`, and nothing else
is ever touched in a target repository -- which is what lets the installer
replace and remove its own files without having to guess whether a project's
own skills are safe to overwrite.

## Writing rules

The same as everywhere else here (`/CLAUDE.md`), plus three that are specific
to instructions an agent acts on:

- **Say what to do, and what never to do.** The rules that matter most are
  the ones that look locally reasonable and are globally wrong: `tilt up`
  instead of `seal up`, a `waitForTimeout` to settle a flake, an outcome test
  edited to make a run green. Each of those is stated as a prohibition with
  the reason beside it, because an agent that knows only the rule will find a
  way around it.
- **Keep every claim checkable from a checkout.** These describe what the
  CLI, the extensions and the checks actually do. A skill that promises
  behaviour Seal doesn't have is worse than a missing skill.
- **Know nothing about any application.** No framework, port, path or service
  name -- these are read by projects that share none of the example's
  choices. The worked example is referenced as a place to look, never as the
  shape a project has to take.

Each skill's `description` is what decides whether it gets read at all, so it
carries the symptoms and the phrasings that should reach for it, not a
summary of the body.

## Changing them

`python/tests/test_agent_skills.py` covers what ships (every skill and agent
declares its own name, and the entry skill routes to all of them) and what
the installer does to a synthetic project. Run it with the rest:

```sh
cd python && uv run pytest tests/
```

A new skill needs a row in the table above, a mention in `skills/seal/`'s
routing table, and a line in `docs/guides/coding-agents.md`.
