# examples/angular-django

A minimal, working example project built on the shared `tilt/` extensions
and `python/` package at the repository root (see the root `README.md` for
what's generic vs. project-specific). The app itself is a todo list --
small enough to read in a sitting, but real enough to exercise a browser, an
HTTP API and a database together. It ships:

- **`services/api`** — a Django project serving the todo API (with Celery
  wired up for background tasks).
- **`services/ui`** — an Angular app for the list itself.
- **`third-party/nginx`** — a reverse proxy in front of both, so the whole
  stack is reachable behind a single port.

There is deliberately no user management: one shared list, no sign-in, no
per-item ownership. The point of the example is the environment around the
app, and accounts would only add surface that has nothing to do with it.

Everything is wired together with [Tilt](https://tilt.dev) for local
development and Kubernetes for deployment, so you can add new services and
have them build, test, and deploy the same way.

## Project layout

- **`services/<name>/`** — one directory per service. Each has its own
  `Dockerfile`, `Tiltfile`, and tests, and can be developed/tested in
  isolation.
- **`third-party/`** — off-the-shelf services (currently just nginx) that
  don't have their own source code to build.
- **`k8s/`** — Kubernetes manifests for the `dev` environment; see
  `k8s/README.md` for the structure, and for where an overlay targeting
  anything else belongs.
- **`Tiltfile`** (this directory) — this project's entry point and its whole
  service list in one: registers the repo root's `tilt/` directory as a
  Tilt extension repo, calls Tilt's own `default_registry()` directly,
  `include()`s every service, and deploys the `k8s/dev/` (or other
  environment's) overlay (see `/rfcs/0002-declaration-by-structure.md`).

## Getting started

From this directory:

```sh
seal up
```

(`seal up` resolves every service's `.env` into a dev Kubernetes `Secret`
and runs `tilt up` against this directory's own root `Tiltfile` -- see
`/rfcs/0006-credential-resolution.md` for why it's `seal up` and not
plain `tilt
up`.)

This builds every service's Docker image, deploys the `dev` Kubernetes
overlay to your local cluster, and forwards the relevant ports:

- `http://localhost:8000` — nginx, fronting the whole stack: the Django API at
  `/api/`, the Angular app everywhere else.
- `http://localhost:8888` — the Django API directly.
- `http://localhost:4200` — the Angular dev server directly.

Each service can also be developed and tested on its own; see
`services/api/README.md` and `services/ui/README.md`.

## Environment variables

Each service's `services/<name>/.env` declares every secret/variable it
needs, once -- its key names *and* how to resolve them are the schema, in
every scope (see `/rfcs/0006-credential-resolution.md` at the repo root for
the full
picture: `k8s://` markers, `<scheme>://<item>` references, the project-level
declaration that says which store each scheme reaches, and how `seal
run`/`seal up`/`seal ci` all resolve it the same way). This
example's own values are literals and `k8s://` markers -- it has no secret
to keep -- so nothing here reaches a store; `services/api/.env` shows the
reference shape in a comment, and `seal-credentials-config.json`
declares the provider it would resolve through, so both are parsed on every
CI run rather than being prose. It is consumed by:

`tilt/seal` (repo root) generates the per-service Kubernetes `Secret`
from what `seal up`/`seal ci` generated -- local dev and CI
alike, with no second, hand-maintained copy of each key anywhere.

## CI

`.github/workflows/internal-example.yml` (repo root) runs on every push/PR.
It's a thin project-specific caller: it just points the repo's reusable
`seal-ci.yml` workflow at this directory -- it doesn't enumerate this
project's credentials at all. That workflow runs each service's unit tests
inside its own container (`seal ci -- --build_type test`), against a
throwaway Kind cluster it creates and discards.

Reshaping this stack for a real environment -- nginx in front, static files
baked into the images, nothing mounted from the host -- means an overlay
layered on `k8s/dev`, which belongs to the deployment that owns it rather
than to this repo. `select_k8s_overlay()` deploys one of `k8s/`'s own
overlays, so such an overlay is deployed by name (`seal ci --
--k8s_overlay <name>`) once it's present in `k8s/`, with nothing here to
change.

## Adding a service

Create `services/<service_name>/` with a `Dockerfile`, a `Tiltfile` calling
`seal_service()` (copy the closest existing service's), a `.env` for
any credentials it needs (see `/rfcs/0006-credential-resolution.md`), and Kubernetes
manifests under `deploy/k8s/`. Then add
`include('services/<service_name>/Tiltfile')` to this directory's own
`Tiltfile` (see `/rfcs/0002-declaration-by-structure.md`).
