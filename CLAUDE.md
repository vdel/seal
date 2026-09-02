# CLAUDE.md

Guidance for AI agents (and anyone else) contributing to this repo.

## What this repo is

A library. `tilt/` and `python/` are the deliverable;
`examples/angular-django/` consumes them and is never where a capability
lives. Before adding behaviour or a rule, read the "Seal is a library"
section below -- it is the standard a change here is held to, and code
written against the example passes every test while giving an adopting
project nothing.

## Seal is a library

`tilt/` and `python/` are the deliverable. `examples/angular-django/` is a
consumer of them -- a worked demonstration, and a template to start from --
never the place a capability lives.

That line is load-bearing and easy to lose, because code written against the
example works. It just doesn't work for anybody else: a guarantee that holds
only because of how the example is laid out is not a guarantee Seal
provides. So:

- **Behaviour goes in `tilt/` or `python/`.** If a project would have to copy
  something out of `examples/` to get a capability, that capability is in the
  wrong place. What a project genuinely owns -- its services, its manifests,
  its registry -- stays with the project; the machinery acting on it doesn't.
- **A rule enforced against the example is not a feature.** `seal check` is
  the shape to follow: the rule (every Deployment container declares a
  `readinessProbe`) lives in the CLI and runs against whatever project
  invokes it, so an adopting project gets it by adopting Seal rather than by
  copying a test.
- **Generic code is tested generically.** Tests for `tilt/` and `python/`
  exercise them against fixtures they build themselves. Asserting on
  `examples/angular-django/`'s own files tests the example, and says nothing
  about the next project -- the example earns its keep by being run end to
  end in CI, which is a different job.
- **Generic code knows nothing about any app.** Nothing in `tilt/`,
  `python/` or `.claude/` names Django, Angular, nginx, or a port or path an
  app chose. Where the generic side needs something only a project can say,
  the project says it -- through its Tiltfile, its `.env`, or a variable
  like `SEAL_K8S_DIR` -- rather than through a default that happens to fit
  the example.

The test to apply to any change here is a project that doesn't live in this
repo: would it get this?

Deploying to a named staging/production environment is deliberately out of
scope: nothing here knows about a cluster, a registry, an ingress or a
domain. Everything a build has to pass through *after* this repo's job is
done lives in a separate deployment toolkit, which consumes a project built
this way rather than the other way around.

The repo has four parts:

- **`tilt/`** — the generic, project-agnostic Tilt (Starlark) helpers,
  packaged as [Tilt extensions](https://docs.tilt.dev/extensions.html) (see
  `tilt/README.md`): `seal` (project config + per-project Kubernetes image
  rewriting, turning a service's `.env` into its Kubernetes `Secret`,
  test-result syncback/verdict reporting for CI, and the outcome suite's
  own resources) and `docker_build` (CI-cached `docker_build()`, reached by
  `seal` itself). Nothing in here knows about Django, Angular, or any
  other app.
- **`python/`** — a small Python CLI package (`seal`; see `python/README.md`)
  and the reusable GitHub Actions test workflow in
  `.github/workflows/seal-ci.yml`.
- **`.claude/`** — the agent-facing half (see `.claude/README.md`): skills
  and subagents that let a coding agent discover Seal in a repository and use
  it -- which `seal` command replaces which `tilt` one, what an outcome test
  is, what never to edit -- installed into an adopting project by
  `bin/install-seal-skills`.
- **`examples/angular-django/`** — a complete, working project built on top
  of `tilt/` and `python/`: a Django API, an Angular UI, an nginx reverse
  proxy, Kubernetes manifests, and the one project-specific CI file
  (`.github/workflows/internal-example.yml`). This is also the template:
  copy this directory (or start a new one alongside it, or replace it) to
  build your own project against the same helpers.

`docs/` is the user documentation -- installing seal, a quickstart
against the worked example, and a deep dive per subject -- published with
Read the Docs from `.readthedocs.yaml`. Start there if you're building a
project on seal; `examples/angular-django/README.md` covers running
the example itself. `rfcs/` is the other audience: the design record --
what was decided, why, what it costs and what was considered instead --
indexed in `rfcs/README.md`, and what to read before changing any of this.
The sections below cover what's generic vs. project-specific.

## What's generic

### `tilt/` — Tilt extensions

Each subdirectory of `tilt/` is a self-contained [Tilt
extension](https://docs.tilt.dev/extensions.html) (its own `Tiltfile` +
`README.md`), loaded the same way Tilt's official
[tilt-extensions](https://github.com/tilt-dev/tilt-extensions) are: register
this repo once as an extension repo, near the top of your project's root
`Tiltfile`, then `load('ext://<name>', ...)` whichever helpers you need --
see `tilt/README.md` for the exact snippet, and
`examples/angular-django/Tiltfile` for a full worked example. None of them
assume where a project lives on disk -- they anchor every project-relative
path on `config.main_dir`, Tilt's own path to whichever Tiltfile `tilt` was
invoked against.

Because registration happens once, in the project's root `Tiltfile`, every
Tiltfile it `include()`s afterwards -- at any nesting depth -- can
`load('ext://seal', ...)` etc. directly, with no relative-path
bookkeeping needed for *this* part. Local dev credentials are a separate
concern with their own wrapper (`seal up`/`seal ci`, not `tilt
up`/`tilt ci` directly) -- see `rfcs/0006-credential-resolution.md`.

### `python/` — the `seal` package

`python/` is a standard "src layout" Python package (see
`python/pyproject.toml` and `python/README.md`): the installable package is
named `seal`, so its modules import as `from seal.credentials
import ...`, etc. It exposes one console script:

- `seal` — `seal run -- <cmd>`, `seal up`, `seal ci`, `seal check`,
  `seal outcomes`, `seal outcomes run`, `seal outcomes translate`,
  `seal outcomes review`: credential resolution (see
  `rfcs/0006-credential-resolution.md`), including each service's dev Kubernetes
  `Secret` for `seal up`. The project's entry Tiltfile is a real, checked-in
  file (see `rfcs/0002-declaration-by-structure.md`), and the readiness
  check `seal ci` runs before it starts is `rfcs/0003-readiness.md`.
  `seal check` runs two more besides: that the outcome tree pairs
  every test with the promise it was translated
  from and puts every group of promises behind a runner that can start them
  (`rfcs/0010-outcome-tree.md`, `rfcs/0011-outcome-runners.md`), and that
  CODEOWNERS covers that tree, so a failing outcome test can't be merged
  away by editing it (`rfcs/0009-outcome-tests.md`). `seal outcomes run`
  reports the whole outcome suite -- every promise the project has
  translated, in one pass -- and exits on its verdict; naming outcomes runs
  just those, which is a local loop rather than anything a merge rests on
  (`rfcs/0010-outcome-tree.md`). `seal outcomes translate` and
  `seal outcomes
  review` are the two ends of writing one of those tests: everything needed
  to compile a promise into one, and the promise beside the result for the
  code owner who has to approve it (`rfcs/0012-translation-and-review.md`).
  `seal outcomes run --reset --all --confirm` is one iteration of the loop
  that gets a red suite back to green -- every promise, from a baseline every
  declared reset puts back, with each failure re-run on its own before
  anything acts on it -- and `seal outcomes touched` says whether an
  iteration stayed inside the application. `seal outcomes loop` says whether
  that loop is getting anywhere -- what each round fixed and what it cost,
  and whether a promise has been fixed and broken again or the loop has
  reached the backstop the project declares
  (`rfcs/0013-regression-loop.md`).

### `.claude/` — the agent skills

The instructions a coding agent reads to use Seal in whatever
repository it lands in: which `seal` command replaces which `tilt`
one, what an outcome test is and how one is written, how to get a red suite
back to green without touching one, what never to edit, and which error
means what (see `.claude/README.md`). `bin/install-seal-skills`
installs them into an adopting project's own `.claude/`, alongside a pointer
block in its `CLAUDE.md`, and `--check` reports when what's installed has
fallen behind.

They're held to the same standard as the rest of the generic side: every
claim in them is something the CLI, the extensions or the checks actually
do, and none of them knows anything about an application. They describe
Seal; they don't enforce it. What enforces is `seal check`, the
outcome suite, and CODEOWNERS over the outcome tree.

### `.github/workflows/seal-ci.yml`

A reusable workflow (`on: workflow_call`) implementing the generic build →
test pipeline: checkout, install Tilt/ctlptl/uv/pass-cli, spin up a
throwaway Kind cluster, run `seal ci` -- which runs each service's own
tests inside its running container -- run the project's outcome suite
against the environment that just came up, and hand back what every run
found -- as outputs a caller reports from, so how a project presents its
results, and whichever action it uses to do so, stays that project's own. So
a green run means two things: the environment came up, and every promise the
project has translated still holds (see `rfcs/0010-outcome-tree.md`). What
makes that a usable merge gate is `seal ci` exiting successfully only
once *every* resource is ready -- so it refuses to start at all until each
Deployment declares a `readinessProbe`, without which Kubernetes reports a
container Ready the instant its process starts (see
`rfcs/0003-readiness.md`). It never touches a real cluster. It takes a
`project_dir` and, optionally, one credential for whatever store the
project's `.env` files reference -- passed as `secrets.provider_token`, or
named by `provider_token_secret` when it should come from the run's own
GitHub Environment rather than repository scope. Which CLI opens that store
is the project's `provider_setup` to say: `seal ci` resolves an app's own
credentials straight from its `.env` files, the same way `seal up` does for
local dev, so this workflow never needs to know an app's variable names, or
its store's name (see `rfcs/0006-credential-resolution.md`).

Publishing an image to a real registry, deploying an overlay that names a
real environment, and sealing credentials for one are all part of the
deployment toolkit instead. `cached_docker_build()` (`tilt/docker_build`)
supports the first of those by reading
`SEAL_IMAGE_TAG`/`SEAL_BUILD_ID` when a publishing pipeline sets
them (see `rfcs/0008-run-axes.md`) -- the only place this repo's own code
meets that concern.

## What's project-specific

Everything a project built on `tilt/` and `python/` supplies for itself,
using `examples/angular-django/` as the reference:

- **`services/<name>/`** — one directory per service (Dockerfile, Tiltfile,
  source, tests, and a `.env` for any credentials it needs -- see
  `rfcs/0006-credential-resolution.md`; `.env`'s key names *are* the
  schema, there's no separate `env.json`).
- **`outcomes/`** — what the application promises, the tests translated
  from those promises, and a `seal-test-config.json` saying what runs each
  group of them — see `rfcs/0010-outcome-tree.md` and
  `rfcs/0011-outcome-runners.md`.
- **`third-party/`** — off-the-shelf services with no source to build
  (nginx, in the example).
- **`k8s/`** — Kubernetes manifests for the `dev` environment; see
  `examples/angular-django/k8s/README.md` for the structure, and for where an
  overlay targeting anything else belongs.
- **`Tiltfile`** (project root) — a real, checked-in file: registers the
  `tilt/` extensions, `include()`s every service, and deploys the right
  Kubernetes overlay -- see `rfcs/0002-declaration-by-structure.md`. This *is* the
  project's service list; there's no separate config file for it.
- **`.github/workflows/<project>.yml`** (`internal-example.yml` here) — the
  *only* project-specific CI file, and it's boilerplate copied as-is: it
  just points `seal-ci.yml` at the project directory. It doesn't enumerate the
  project's own credentials at all -- see `rfcs/0006-credential-resolution.md`.

## Adapting this for your own project

1. Copy `examples/angular-django/` to a new directory (or start fresh
   alongside it), and `.github/workflows/internal-example.yml` to a new
   workflow file pointing `project_dir` at it.
2. Replace `services/`, `third-party/`, and `k8s/` with your own. `tilt/`
   and `python/` don't need to change.
3. In your new project's root `Tiltfile` (copied from
   `examples/angular-django/Tiltfile`), point the `v1alpha1.extension_repo()`
   `url` at your own fork/remote of this repo (or leave the `file://`
   `config.main_dir` computation if you're developing alongside it in the
   same checkout), adjust the `default_registry()`/`select_k8s_overlay(k8s_dir=...)`
   calls to match your own registry/Kubernetes overlay directory, and
   `include()` your own services -- see `rfcs/0002-declaration-by-structure.md`.
4. Run `seal up` from your project's root to develop locally (see
   `rfcs/0006-credential-resolution.md` for how it resolves each service's
   `.env`).

## The agent skills

`.claude/` is part of the deliverable, not this repo's own configuration:
the skills and subagents there are what an adopting project installs (with
`bin/install-seal-skills`) so a coding agent working in *that* repository
discovers Seal and uses it correctly. They're live here too, so a session
working on Seal or on the worked example reads the same instructions.

Read `.claude/README.md` before changing them. Two rules matter most: every
claim in a skill has to be something the CLI, the extensions or the checks
actually do, and none of them may name an application's framework, port,
path or service. A skill promising behaviour Seal doesn't have is
worse than a missing skill.

## Comment style

Comments and docs describe the *current* design and its rationale —
never the journey that got here. Concretely:

- **No issue/PR references** (`#NN`, `owner/repo#NN`, `PR#NN`, issue/PR
  URLs). This repo may be forked, republished, or renumbered elsewhere; a
  citation to "this repo's own issue #59" is meaningless — or actively
  wrong — once that's no longer true, and it's dead weight even when it
  is: the reasoning belongs in the comment itself, not behind a link a
  reader has to go fetch.
- **Don't narrate history.** Avoid "X used to work this way", "no longer
  does Y", "replaces the old Z", "originally", "previously", "confirmed
  the hard way" — these describe a migration a reader of the current code
  never needs to reconstruct. State what the code does now and why, as if
  it had always been this way. If a past failure mode is still a live
  risk worth warning about (e.g. "a stale name mismatch here silently
  breaks anything that matches by name"), describe the mechanism and the
  risk directly — don't frame it as an anecdote about when it happened.
- **Present-tense comparisons between two things that both exist today**
  (e.g. "unlike ubuntu-latest", "unlike Postgres") are fine — that's not
  history, it's describing the current codebase's own structure.
- **Skip hedges about failure modes the current design already
  prevents.** If a comment exists only to reassure a reader that
  something *won't* go wrong, cut it, or replace it with the actual
  constraint that prevents it — don't narrate the near-miss.
- Functional values (a real `repoURL`, an image ref, a registry path, a
  `CODEOWNERS` entry) are not comments — this guidance doesn't ask you to
  genericize them, only to keep the prose around them focused on what's
  true now.

When editing a comment for another reason, fix nearby violations of this
in the same file rather than leaving them for later.
