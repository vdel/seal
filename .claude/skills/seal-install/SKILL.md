---
name: seal-install
description: Install Seal into a repository -- the seal CLI, the Tilt extension registration in the root Tiltfile, the project layout, the outcome tree, CODEOWNERS and the CI workflow -- and install these skills so every agent and teammate working in that repository discovers Seal the same way. Use when asked to adopt, add, set up, bootstrap or upgrade Seal, when seal is not on PATH, or when a repository has services but no seal up.
---

# Installing Seal

Two things get installed, and they are independent: **the `seal`
CLI**, on whatever machine runs it, and **the agent skills**, into the
repository so they travel with it. A project also *registers* the Tilt
extensions, which is not an install at all -- Tilt fetches them.

Work through whichever of the five parts below the repository is missing.
Check first; each part is idempotent, but a repository half-adopted in an
unknown way is worth reading before writing to.

## 1. The `seal` CLI

```sh
uv tool install "git+https://github.com/vdel/seal#subdirectory=python"
seal            # prints usage and exits non-zero: that is enough to say it is installed
```

`uv tool install` puts `seal` on `PATH`. In a one-off shell or a CI
job, `uvx` runs it without installing:

```sh
uvx --from "git+https://github.com/vdel/seal#subdirectory=python" seal up
uvx --from ../../python seal up          # from a checkout of Seal itself
```

`uv tool install` and `uv tool uninstall`/`upgrade` all key on the
distribution name, `seal`.

What Seal drives rather than what Seal is -- Docker, Tilt,
kubectl, uv, `rsync`, and a provider's own CLI only if a `.env` actually
references that provider's scheme -- installs the way it normally would on
the platform. Do not install these silently on somebody's machine: report
what is missing and let them choose.

Tilt also needs a local cluster with `kubectl`'s current context pointed at
it (Docker Desktop's `docker-desktop`, minikube, k3d, kind -- any of them).
Confirm which one before running anything that deploys:

```sh
kubectl config current-context
```

## 2. The agent skills, into the repository

This is what makes Seal discoverable to the next agent that opens the
repository, rather than only to this session:

```sh
git clone --depth 1 https://github.com/vdel/seal /tmp/seal
/tmp/seal/bin/install-seal-skills --target .
```

It copies every `seal-*` skill and agent into `<target>/.claude/`, and
maintains a short block in the repository's `CLAUDE.md` pointing at them.
Re-running it upgrades in place and removes skills that no longer ship;
`--check` reports drift without writing, which is what a CI job or a
teammate's shell wants. `--link` symlinks back to the checkout instead of
copying, for working on the skills themselves.

Commit `.claude/` and the `CLAUDE.md` block. That is the whole distribution
mechanism: a teammate who pulls gets the skills, with no install step of
their own.

## 3. Registering the Tilt extension

The Starlark half is not installed. The project's own root `Tiltfile`
registers this repository as a Tilt extension repo, once, near the top:

```python
v1alpha1.extension_repo(name='seal', url='https://github.com/vdel/seal')
v1alpha1.extension(name='seal', repo_name='seal', repo_path='tilt/seal')

load('ext://seal', 'seal_service', 'select_k8s_overlay')
```

Registration is session-wide: every Tiltfile the root one `include()`s
afterwards, at any nesting depth, can `load('ext://seal', ...)` directly.

- A project developing against a local checkout points `url` at a `file://`
  path instead, and picks up uncommitted edits.
- A project that forked Seal points `url` at its own fork.

## 4. The project layout

The fastest correct route is to copy the worked example
(`examples/angular-django/` in the Seal repository) and replace its
contents. Whichever route, the project root ends up with:

| Path | What it is | Skill |
| --- | --- | --- |
| `Tiltfile` | The entry point, and the service list. Registers the extension, `include()`s each service, then `select_k8s_overlay(k8s_dir=..., default_overlay=...)` last. | `seal-add-service` |
| `services/<name>/` | One directory per service: `Tiltfile`, `Dockerfile`, source, tests, `.env`. | `seal-add-service` |
| `k8s/<overlay>/` | One kustomize overlay per manifest shape -- not per environment; which credentials resolve is `--credentials_env`, chosen separately. Every Deployment container needs a `readinessProbe`. | `seal-add-service` |
| `seal-credentials-config.json` | Only if a `.env` references a store: the providers the project declares, their environments, and its own `default_env`. | `seal-add-service` |
| `outcomes/` | The promises, the tests translated from them, and `seal-test-config.json`. | `seal-outcome` |
| `CODEOWNERS` | A rule covering the whole outcome tree. | `seal-merge-gate` |
| `.github/workflows/<project>.yml` | Boilerplate using the `ci` action against this project. | `seal-merge-gate` |

A minimal root `Tiltfile`:

```python
v1alpha1.extension_repo(name='seal', url='https://github.com/vdel/seal')
v1alpha1.extension(name='seal', repo_name='seal', repo_path='tilt/seal')

load('ext://seal', 'select_k8s_overlay', 'publish_images', 'register_outcome_runner')

if publish_images:
    default_registry('ghcr.io/your-org')      # must run before any include()

include('services/api/Tiltfile')
include('services/ui/Tiltfile')

select_k8s_overlay(k8s_dir='k8s', default_overlay='dev')

register_outcome_runner(base_url='http://<service>:<port>')
```

Two directories can live elsewhere, and say so through the environment
rather than a flag: `SEAL_K8S_DIR` for the manifests,
`SEAL_OUTCOMES_DIR` for the outcome tree. `seal ci` hands every
argument it is given straight to `tilt ci`, which leaves it none of its own
to spend.

## 5. Verifying the adoption

In this order, because each one is cheap next to the one after it:

```sh
seal check                       # readiness probes, the outcome tree, CODEOWNERS
seal up                          # the stack comes up locally
seal outcomes                    # every promise, and which have tests
seal ci -- --build_type test  # what a merge would run
```

`seal check` reports every offender at once, so the tree gets put
right in one pass. `seal up` deliberately runs **no** checks -- a
half-finished manifest should not stand between somebody and their cluster
-- so `seal ci` failing where `seal up` worked is the design,
not a regression.

Adoption is complete when `seal ci` exits zero and the repository's
branch protection makes the outcome tree's `CODEOWNERS` rule blocking. The
second half is a repository setting rather than repository contents, so
Seal cannot apply or verify it -- see `seal-merge-gate`.

## What Seal will not do, however it is asked

Saying so early saves looking for a feature that was never going to be here.
It never deploys to a named environment, never applies a repository's
settings, never writes a test, and knows nothing about any application -- no
default port, path, framework or service name. Where Seal needs something
only the project can say, the project says it.
