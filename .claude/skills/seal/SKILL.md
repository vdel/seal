---
name: seal
description: The entry point for any work in a repository that builds on Seal (a root Tiltfile beside a services/ directory, a Tiltfile that loads ext://seal, or an outcomes/ tree with seal-test-config.json). Explains what Seal guarantees, which seal command replaces which tilt command, the rules a change here is held to, and which seal-* skill or agent to reach for next. Use it before running tilt, before touching outcomes/, and whenever seal up, seal ci, seal check or seal outcomes appears in a task.
---

# Seal

**Sealed expected end-to-end outcomes for autonomous agentic
development.** Seal is a library for developing and testing
multi-service applications on [Tilt](https://tilt.dev) and Kubernetes. It
gives a project one way to bring its services up, one way to resolve their
credentials, and one way to run the tests a merge rests on -- the same way
locally as in CI.

The point of that consistency is a merge gate that can be left unattended.
A green run means the environment finished coming up *and* every promise the
project has written a test for still holds; and those tests cannot be edited
without a human approving the diff. That is what lets a change -- a person's
or an agent's -- merge on the strength of the tests rather than on somebody's
reading of them. Everything below serves that.

## Are you in a Seal project?

Walk up from where you are looking for a directory that has **both** its own
`Tiltfile` and a `services/` subdirectory. That directory is the **project
root**, and every `seal` command finds it the same way:

```sh
seal outcomes    # from anywhere inside the project; errors out if you aren't in one
```

Two more signals: the root `Tiltfile` registers `ext://seal`, and an
`outcomes/` tree holds `seal-test-config.json`. If `seal` is not
on `PATH`, see [seal-install](../seal-install/SKILL.md).

## The shape of a project

```
my-project/
  Tiltfile                 # the entry point -- and the service list
  services/<name>/         # Tiltfile, Dockerfile, source, tests, .env
  third-party/<name>/      # off-the-shelf services with no source to build
  k8s/<overlay>/           # one kustomize overlay per manifest shape
  outcomes/                # what the application promises, and the tests translated from them
    seal-test-config.json
    <group>/<epic>/<outcome>/{prompt.md, <the test>}
  tests-results/           # generated; where every result lands
```

**There is no config file anywhere.** Which services exist is whatever the
root `Tiltfile` `include()`s; which credentials a service needs is whatever
keys appear in its own `.env`; which promises the project makes is whatever
directories exist under `outcomes/`. Nothing has to be kept in agreement with
a registry, so do not go looking for one to update -- and do not add one.
The single exception is `outcomes/seal-test-config.json`, which says what
*runs* each group of promises, because no walk of the tree can answer that.

## Commands

Run these from the project root unless noted.

| Command | What it is for |
| --- | --- |
| `seal up` | Local development. Resolves credentials, then `tilt up`. |
| `seal ci` | The gate. Checks, credentials, `tilt ci`, then the whole outcome suite. |
| `seal run -- <cmd>` | One command with a service's `.env` injected. Run from inside `services/<name>/`. |
| `seal check` | The three static checks (readiness probes, outcome tree, CODEOWNERS). |
| `seal outcomes` | List every promise and whether a test has been translated from it. |
| `seal outcomes run [--reset] [--all] [--confirm] [slug...]` | The whole suite's verdict; `--all` re-runs it against a running session, slugs run just those. |
| `seal outcomes translate <slug>` | The brief for compiling one promise into a test. |
| `seal outcomes review <slug>` | A promise beside its translation, for review. |
| `seal outcomes touched` | Which paths under `outcomes/` this change reaches. Non-zero if any. |
| `tilt trigger seal_reset_<service>` | Put one service's state back to its baseline. |

Arguments after `--` go straight through to Tilt: `seal ci --
--build_type test`.

## Rules

These are the ones that are expensive to get wrong. Follow them without
asking.

- **Never run `tilt up` or `tilt ci` directly.** Seal resolves every
  service's `.env` and fills the objects the overlay annotates just before
  Tilt starts. A bare `tilt up` does not refuse -- it deploys those objects
  empty, so containers come up without their credentials and what you get
  back is a readiness timeout or an application error, well away from the
  cause. Editing a `.env` means stopping the session and re-running
  `seal up`.
- **Never edit an outcome test to make a run green.** A suite passes
  identically whether the application was fixed or the test was rewritten,
  which is exactly the difference the gate exists to preserve. Fix the
  application, and check with `seal outcomes touched` that you did. If the
  promise itself is genuinely wrong, say so and change `prompt.md` -- a code
  owner has to approve that, and should.
- **Never make a test wait on the clock.** No `waitForTimeout`, no sleep.
  Wait on the state: `expect(locator).toBeVisible()` or `locator.waitFor()`
  retries until it holds. `seal check` refuses the alternative.
- **Never reach for a subset when reporting the suite.** `seal outcomes run`
  with no arguments is what a merge rests on. Naming slugs is a local loop
  and says nothing about the promises it left out.
- **Never put behaviour in a project that belongs in Seal.** If this
  repository *is* Seal, read `/CLAUDE.md`: `tilt/` and `python/` are the
  deliverable, and `examples/` is a consumer of them, never where a
  capability lives.

## Where to go next

| The task | Skill |
| --- | --- |
| Adopt Seal in a repository, or install the CLI and these skills | `seal-install` |
| Get a machine ready to run anything: the daemon, a cluster, reachable registries | `seal-machine` |
| Bring the stack up, iterate, reset state, run one outcome | `seal-dev-loop` |
| Add a service, its manifests, its credentials, its readiness probe | `seal-add-service` |
| Write a promise, translate it into a test, review one | `seal-outcome` |
| Make the merge gate real: CODEOWNERS, branch protection, CI | `seal-merge-gate` |
| Outcome tests are red and the job is to get them green | `seal-regression-loop` |
| Something failed and the message is not obvious | `seal-doctor` |

Five subagents do the long-running parts on their own:
`seal-outcome-translator` (write and iterate one translation until it
runs), `seal-outcome-reviewer` (check a translation against its
promise), `seal-ci-doctor` (diagnose a red `seal ci` without
changing anything), `seal-app-fixer` (make one confirmed failure pass
by changing the application, never the test), and `seal-loop-triager`
(decide what to do about a regression loop that has stopped converging --
with fresh context, never the session that was in it).

## Reading further

The user documentation is at
<https://github.com/vdel/autologate/tree/main/docs> -- `installation.md`,
`quickstart.md` and `concepts.md` first, then one guide per subject. The
reasoning behind each rule is in the RFCs at
<https://github.com/vdel/autologate/tree/main/rfcs>, which is what to read
before changing Seal itself.
