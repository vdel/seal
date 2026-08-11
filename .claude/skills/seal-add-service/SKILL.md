---
name: seal-add-service
description: Add or change a service in a Seal project -- create services/<name>/, declare it with seal_service() in its own Tiltfile, include it from the root Tiltfile, give it a .env, and write Kubernetes manifests whose containers all declare a readinessProbe. Use when asked to add, wire up, rename or remove a service, a worker, a third-party dependency, a credential or an environment variable, or when seal ci refuses to start naming Deployments.
---

# Declaring a service

## What a service is

A directory under `services/`, in this order:

1. A `Dockerfile` with a stage per kind of run.
2. A `Tiltfile` calling `seal_service()` (below). Copy the closest
   existing service's rather than writing one from nothing.
3. `include('services/<name>/Tiltfile')` in the root `Tiltfile`.
4. A `.env`, if it needs credentials.
5. Kubernetes manifests, under the `k8s/` overlay.

A third-party service has no source to build, so it declares no
`seal_service()` at all: write `third-party/<name>/Tiltfile` by hand
and `include()` it the same way.

A service that does not show up in Tilt almost always means the root
`Tiltfile` does not `include()` it. Tilt re-evaluates the whole Tiltfile from
scratch on every run, so there is nothing stale to clear.

## The service's own Tiltfile

```python
load('ext://seal', 'seal_service')

seal_service(
    'example-api',
    context='.',
    dockerfile='Dockerfile',
    live_update=[...],
    development_stage='development',            # this service's own stage names
    runtime_stage='runtime',                    # omit any it doesn't have
    test_stage='test',                          # omit if it has no tests
    junit_tests_directory='/app/tests-results/',  # required with test_stage
    test_command='make unit-tests',                 # required with test_stage
    reset='deploy/reset.sh',                     # omit if it owns no state
)
```

One call does what would otherwise be written by hand: build this service's
image and, where asked, wire up its test-result copy-back and its reset
resource. It says nothing about credentials -- which object carries those is
the overlay's to say, and the CLI fills it before Tilt starts.

- **`development_stage`, `runtime_stage`, `test_stage`** are this service's
  own Dockerfile stage names, one per `--build_type`. Seal names the kind of
  image a run wants; the service names what to build for it, so a Dockerfile
  can spell its stages however it likes. Each is optional: no
  `runtime_stage` builds the Dockerfile's last stage, no
  `development_stage` falls back to the runtime one, and no `test_stage`
  means this service has no tests of its own. Giving `test_stage` turns on
  this service's result syncback and its own
  `seal_tests_verdict_<service_name>` resource -- so CI fails pointing at
  whichever service actually broke.
- **`junit_tests_directory`** is required whenever `test_stage` is given.
  Seal fails loudly rather than guessing where the Dockerfile writes results.
  That directory has to hold a **JUnit report**: it is the verdict Seal
  reads. No report, no test cases in it, or one that doesn't parse are each
  a failure, so nothing green can be claimed for a suite that never ran.
- **`test_command`** is what Seal runs, inside the running container and
  once the service is ready, to produce that report -- which is what lets
  the suite use the service's real database, broker and Secret. Required
  whenever `test_stage` is given. The test stage only *carries* the suite;
  it must not run it, and the command must not do anything about failing:
  Seal discards the exit code, because the results reach the project by
  being copied out of the container after the run. Where the service also
  declares a `reset`, Seal restores the baseline on **both sides** of the
  run (`reset -> tests -> reset -> outcome tests`), so the tests start from
  a known state and an outcome test does too whatever they did. A service
  that declares no `reset` has nothing putting its run ahead of the outcome
  suite -- name `tests_run_resource_name('<service>')` in
  `register_outcome_runner()`'s `resource_deps` if that matters.
- **`reset`** is a script putting the state this service owns back to a known
  baseline, relative to this service's Tiltfile.
- `registry` duplicates the root Tiltfile's `default_registry()` value, since
  Tilt does not expose it back to Starlark. `k8s_resource_name` and
  `resource_dep` both default to `service_name`; override them only where
  several services share one Deployment.
- Any other `docker_build()` argument is forwarded as-is. Under
  `SEAL_BUILDX_CACHE=1` the build goes through `cached_docker_build()`, whose
  buildx command understands none of them and fails loudly if given one.

## The root Tiltfile is the service list

There is no services array and no path registry. Order matters in one way
only: `default_registry()` before any `include()`, because Tilt rewrites
image refs only for builds declared after it; and
`select_k8s_overlay(k8s_dir=..., default_overlay=...)` plus
`register_outcome_runner()` after every `include()`.

## Credentials: the `.env` is the schema

`services/<name>/.env` is committed to git, and every value is one of three
things:

```sh
DEBUG=0                                     # a plain literal
SESSION_SIGNING_KEY=store://signing-key     # a reference into a store
DATABASE_URL=k8s://                         # the manifests supply this one
```

- **Literals** are the value in *every* scope, production included -- there
  is no dev-only override file. Where a key would be dangerous somewhere,
  pick the safest value.
- **A reference** names an *item*, and nothing else. Which store holds that
  item is the project's own declaration, not this line -- see below. There
  is no fallback when an item is missing or nobody is logged in: this same
  file is what production resolves.
- **`k8s://`** means the manifests supply the key directly. Seal never
  touches it; the marker is there so the `.env` still names every key the
  service needs.

A value is never a template. `${...}` in one is rejected by `seal
check`, because a value that expands is a value whose meaning depends on
where it is read.

## Which store: `seal-credentials-config.json`

At the project root, beside the `Tiltfile`. It maps a scheme to the store
behind it, and gives that store a scope per environment:

```json
{
  "default_env": "dev",
  "provider": [
    {
      "scheme": "store://",
      "name": "<the product, as a human would name it>",
      "cli": "<its binary>",
      "install_hint": "<where to get it>",
      "form": "run",
      "reference": "store://{vault}/{item}",
      "command": [
        "<its binary>", "run", "--env-file", "{env_file}", "--", "{command}"
      ],
      "environments": {"dev": {"vault": "..."}, "prod": {"vault": "..."}}
    }
  ]
}
```

`reference` is the shape the CLI wants, and `environments` supplies every
placeholder in it that the `.env` line does not. That split is the whole
point: `store://signing-key` is a valid line in every environment, and which
vault it reaches is decided here.

`form` says how the CLI is called -- `run`, `resolve`, `fetch` or `get`; all
four are implemented, so a store is declared rather than coded for.

Which environment a run reads is `--credentials_env`, else
`SEAL_CREDENTIALS_ENV`, else `default_env`. It is **independent of
`--k8s_overlay`**: which store the values come from and which manifests they
land in are separate choices, and a run states each.

`seal check` reads this file on every run: a value naming a scheme no
provider declares, a value carrying a `${`, and a provider some `.env`
reaches with no mapping for the selected environment are all reported by
name.

## The object a service's values land in

Seal fills objects the overlay already declares, rather than inventing
one. A service needing credentials wants an object in each overlay carrying:

```yaml
metadata:
  annotations:
    seal-test.dev/fill-from: <service>
```

That object claims every key the service's `.env` declares which no other
object claims. To split across several, add `seal-test.dev/keys: A,B` to
one -- it then claims exactly those, and the one naming no keys takes the
rest. Both `Secret` (values base64-encoded) and `ConfigMap` (plain) work,
and which an object is decides RBAC and what `kubectl describe` prints.

`seal check` reports a container whose sources supply nothing for a
key its service declares, in any overlay -- so a service wired into one
overlay and forgotten in another fails before it deploys.

Adding a secret is one line in the `.env` plus the matching item in the
store, and nothing else to keep in sync. Never commit a resolved secret as a
literal. After editing a `.env`, stop the session and re-run `seal
up`.

## Readiness, which `seal ci` refuses to start without

Every Deployment container in the manifests must declare a `readinessProbe`.
Without one, Kubernetes reports a container Ready the instant its process
starts -- and "every resource is ready" is the whole of what makes
`seal ci` usable as a gate.

```yaml
# a worker with no port to poll: ask the process itself, and let a non-zero
# exit be the "not ready" -- whatever your queue runner's own ping is
readinessProbe:
  exec:
    command: ["sh", "-c", "<your worker's own health command>"]
```

Which probe is right is the service's business. An HTTP endpoint where there
is a server, a command where there is not.

```sh
seal check                    # over ./k8s, or $SEAL_K8S_DIR
seal check --k8s-dir deploy   # somewhere else, just this once
```

Every offender is reported at once. The check reads documents as written
rather than running kustomize, so a container a patch introduces is checked
where it is declared, and a patch that declares no containers is left alone.

## Resetting the state a service owns

One script, registered as `reset='deploy/reset.sh'`, doing emptying and
seeding as one job -- an empty database is only half of a known baseline, and
splitting the two leaves their order for a caller to get wrong. It is
addressed to the service whose code puts the data there, never to a
datastore: flushing a broker belongs in the reset of the service that uses it
as one.

What makes seed data something a test can assert on:

- **Check the data in.** A fixture diffs as data; a script that creates rows
  diffs as a loop.
- **Pin every primary key**, or "todo 3" stops meaning the same row.
- **Pin anything time-derived**, or the seeded order depends on when the
  fixture loaded.
- **Seed something interesting.** A list where every item is already done
  cannot distinguish a working "remaining" count from a broken one.
- **Assume the tables were just emptied** -- the fixture loads at the end of
  the same script.

Anything that needs the reset first names
`seal_reset_<service_name>` in its own `resource_deps`;
`reset_resource_name('<service>')` builds that name without hardcoding the
spelling.
