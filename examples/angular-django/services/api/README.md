# api

The example's Django backend: it stores the todo list and serves it over
HTTP. It ships with:

- A `config` project package (settings, URLs, WSGI/ASGI entry points, Celery app).
- A `core` Django app holding the `Todo` model and the endpoints below, all
  exposed under `/api/` through nginx (see
  `k8s/dev/web/nginx/nginx-config.yaml`).
- Celery wired up for background tasks, matching the `celery-worker` /
  `celery-beat` deployments in `k8s/dev/celery/`.

| Method   | Path                | What it does                                  |
| -------- | ------------------- | --------------------------------------------- |
| `GET`    | `/api/`             | Health check, also used by the k8s probes      |
| `GET`    | `/api/todos`        | Every todo, oldest first                       |
| `POST`   | `/api/todos`        | Adds one, from `{"title": "..."}`              |
| `PATCH`  | `/api/todos/<id>`   | Updates `title` and/or `done`                  |
| `DELETE` | `/api/todos/<id>`   | Removes one                                    |

Plain Django views returning `JsonResponse`, not a REST framework: this
example exists to exercise the environment, so its API keeps the dependency
list short and its behaviour readable in one file. There is no user
management, so the write endpoints are `csrf_exempt` -- a request carries no
identity for a cross-site form to borrow. An app with sessions must not copy
that; see the comment in `src/core/views.py`.

## Running locally

From the project root (`examples/angular-django/`):

```sh
seal up
```

This builds the Docker image, applies the Kubernetes manifests to your local
cluster, and forwards the service ports (see `services/api/Tiltfile` and
`third-party/nginx/Tiltfile`).

## Running in isolation

From this directory:

```sh
uv sync --group dev
IS_BUILD_OR_TEST=1 uv run python src/manage.py migrate
uv run pytest tests/
```

`IS_BUILD_OR_TEST=1` makes `config.env_utils.load_secrets()` inject fake
secrets (see `BUILD_SCOPE_FAKES`) and falls back to an in-memory SQLite
database, so the test suite runs without any external dependency.

That is the isolated version of a run. `seal ci` runs the same suite
through `make unit-tests` inside this service's container instead, against
the Postgres it is configured with -- `tilt trigger
seal_tests_run_example_api` does one against a session that is already
up.

To instead run something against this service's real dev credentials (e.g.
`runserver` against a real local Postgres) without going through Tilt at
all, use `seal run` -- it resolves `.env` in this directory the same way
`seal up` does for the whole project:

```sh
seal run -- uv run python src/manage.py runserver
```

See `/rfcs/0006-credential-resolution.md` at the repo root.

## Environment variables

`.env` in this directory declares every secret/variable this service needs,
once -- its key names *and* how to resolve them are the schema, in every
scope (there's no separate env.json). `.env` itself is resolved directly for
local dev (via `seal run`), or via the Kubernetes Secret `seal
up`/`seal ci` generates from it (`tilt/seal`, at the repository
root) once deployed -- local dev and CI/stag/prod alike, both via Proton
Pass. See `/rfcs/0006-credential-resolution.md` and
`examples/angular-django/README.md` for the full picture.
