# 🦭 Seal

**Sealed expected end-to-end outcomes for autonomous agentic development.**

A reusable base for developing and deploying multi-service applications with
[Tilt](https://tilt.dev) + Kubernetes, plus a worked example so you can see
it running end to end before adapting it. Full documentation -- the goals
behind Seal, installation, a quickstart, and a deep dive per subject -- is
in [`docs/`](docs/index.md), published with Read the Docs.

## Install

```sh
uv tool install "git+https://github.com/vdel/seal#subdirectory=python"
```

See [Installation](docs/installation.md) for prerequisites (Docker, Tilt,
kubectl, a local Kubernetes cluster) and registering the Tilt extension in
your own project's `Tiltfile`.

## Quick start

```sh
git clone https://github.com/vdel/seal
cd seal/examples/angular-django
seal up
```

That brings the worked example -- a Django API, an Angular UI and an nginx
reverse proxy -- up against your local cluster. See
[Quickstart](docs/quickstart.md) for the full walkthrough: running the
outcome suite, running what a merge gate runs, and adapting this repo for
your own project.

## Repository layout

- **`tilt/`** and **`python/`** are the deliverable: the Tilt extensions and
  the `seal` CLI.
- **`.claude/`** is the agent-facing half: skills an adopting project
  installs so a coding agent discovers and uses Seal correctly.
- **`examples/angular-django/`** is the worked example and starting
  template.
- **`docs/`** is the user documentation; **`rfcs/`** is the design record.

See [`CLAUDE.md`](CLAUDE.md) for guidance on contributing to this repo.
