# Declaring your services

How a project says which services make it up, what each one declares, and
how Seal finds them without a registry to keep in agreement.

## Your root Tiltfile *is* the service list

There is no `seal.json`, no services array, no path registry. A project's
own root `Tiltfile` is a real, checked-in file, and what it `include()`s is
what the project deploys:

```python
v1alpha1.extension_repo(name='seal', url='https://github.com/vdel/autologate')
v1alpha1.extension(name='seal', repo_name='seal', repo_path='tilt/seal')

load('ext://seal', 'select_k8s_overlay', 'publish_images')

if publish_images:
    default_registry('ghcr.io/your-org')

include('services/api/Tiltfile')
include('services/ui/Tiltfile')
include('third-party/nginx/Tiltfile')

select_k8s_overlay(k8s_dir='k8s', default_overlay='dev')
```

Reading it top to bottom:

- **The `v1alpha1.*` calls register Seal's extension**, once, session-wide.
  Every Tiltfile `include()`d afterwards can `load('ext://seal', ...)`
  directly. See
  [Registering the Tilt extension](../installation.md#registering-the-tilt-extension).
- **`default_registry()` is Tilt's own call, unmodified.** Whether to skip
  it -- in `dev`, say, where there's nothing to push to and no registry to
  log into -- is your project's choice. It has to run *before* any
  `include()`: Tilt only rewrites image refs for builds declared after it.
- **One `include()` per service.** Your own services, third-party ones,
  anything with a Tiltfile. Put a dependency ahead of what depends on it.
- **`select_k8s_overlay(k8s_dir=..., default_overlay=...)` goes last**, after every service is
  included. It deploys one of `<k8s_dir>/`'s overlays as a kustomize overlay
  -- whichever `--k8s_overlay` names, or the `default_overlay` you pass it.

If your outcome tree needs wiring in, `register_outcome_runner()` goes at
the very end -- see [Outcome tests](outcomes.md).

## A service's own Tiltfile

Each service declares itself in one call:

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
    reset='deploy/reset.sh',                     # omit if it owns no state
)
```

`seal_service()` is the one-call version of what you'd otherwise write by
hand: build this service's image and -- where asked for -- wire up its
test-result copy-back and its reset resource. It says nothing about
credentials; which object carries those is the overlay's to say. Every
argument is in the
[Tilt extension reference](../reference/tilt-extensions.md#seal_service).

A few of them are worth knowing before you write your first one:

- **`development_stage`, `runtime_stage`, `test_stage`** are this service's
  own Dockerfile stage names, one per `--build_type`. Seal names the kind of
  image a run wants; your service names what to build for it, so your
  Dockerfile can spell its stages however it likes. Each is optional, and
  leaving one out says something: no `runtime_stage` builds the Dockerfile's
  last stage (right for a single-stage service); no `development_stage`
  falls back to the runtime one (right for a worker that runs the same image
  everywhere); no `test_stage` means this service has no tests of its own.
  Giving `test_stage` is what turns on this service's result syncback and
  its own verdict resource -- so CI fails pointing at whichever service
  actually broke, rather than at one combined check.
- **`junit_tests_directory`** is required whenever `test_stage` is given.
  Seal fails loudly rather than guessing where your Dockerfile writes
  results. What it finds there has to include a JUnit report -- see
  [How a service's tests run](#how-a-services-tests-run).
- **`test_command`** is what Seal runs, inside the running container, to
  produce that report. Required whenever `test_stage` is given.
- **`reset`** is a script that puts the state this service owns back to a
  known baseline. See [Deterministic test state](resetting-state.md).

A service with no `services/<name>/.env` at all resolves nothing -- there's
nothing to opt out of.

## Adding a service

A service is a directory under `services/` and four things in it:

1. A `Dockerfile`, with a stage per kind of run.
2. A `Tiltfile` calling `seal_service()` -- copy the one above.
3. A `.env`, if it needs credentials -- see [Credentials](credentials.md).
4. Kubernetes manifests, under your `k8s/` overlay.

Then add `include('services/<name>/Tiltfile')` to your root `Tiltfile`.

A third-party service has no source to build, so it declares no
`seal_service()` at all: write `<wherever>/<name>/Tiltfile` by hand
and `include()` it the same way.

:::{tip}
A service you just added not showing up in Tilt almost always means your
root Tiltfile doesn't `include()` it. Tilt re-evaluates the whole Tiltfile
from scratch on every run, so there's nothing stale to clear.
:::

## Readiness, and what `seal ci` refuses to start without

`seal ci` exits successfully only once Tilt reports **every** resource
ready. That is exactly what makes it usable as a gate: green means the
environment finished coming up, not that it started to.

That guarantee is only as good as Kubernetes' idea of "ready" -- and a
container with no `readinessProbe` is marked Ready the instant its process
starts, before it can serve a request or run a task. One such Deployment
quietly turns the whole run's claim into a weaker one without ever failing.

So `seal ci` refuses to start until every Deployment your overlays deploy
declares a `readinessProbe` on every container.

Each overlay is built to find out, rather than its files read one by one. A
kustomize patch is a Deployment document too, and an entry in its
`containers` may be introducing a container, amending one a base declares,
or deleting it -- three things the file alone cannot tell apart. Building
settles it, and means a patch adding a volumeMount needn't restate a probe
that lives in the base. A finding names the overlay it came from: the same
container can be fine in the shape you work in and missing a probe in the
shape that ships.

The same check, on its own:

```sh
seal check                    # over ./k8s
seal check --k8s-dir deploy   # look somewhere else, just this once
```

Keep your manifests somewhere other than `k8s/`? Name it in
`SEAL_K8S_DIR`, which both commands read. It's an environment variable
rather than a flag because `seal ci` hands every argument it's given
straight through to `tilt ci`, leaving it none of its own to spend.

The check walks the manifest tree rather than consulting a list, so a
Deployment added later is covered by having been added. It reads the
documents as written rather than running kustomize, so a container a patch
introduces is checked where it's declared; documents that declare no
containers -- a patch that only changes `replicas` -- have nothing to say
about readiness and are left alone.

`seal up` runs none of these checks. A half-finished manifest should not
stand between you and your cluster.

Which probe is right is your service's business, not Seal's -- an HTTP
endpoint where there's a server, a command where there isn't:

```yaml
# a worker with no port to poll: ask the process itself
readinessProbe:
  exec:
    command: ["sh", "-c", "celery -A config inspect ping -d \"celery@$(hostname)\""]
```

What is deliberately *not* checked is which resource waits on which (Tilt's
`resource_deps`). Declaring those edges reduces crash-loop churn while an
environment comes up and is worth doing, but `tilt ci` waits for every
resource whatever order they started in -- so ordering isn't what makes the
signal trustworthy, and inferring the right edges would mean guessing at
dependencies the manifests only imply.

## How discovery actually works

Two mechanisms, and neither needs a path registry.

**From Starlark.** Every Tilt builtin that takes a relative path resolves it
against whichever Tiltfile's top-level code is currently executing -- not
the file where the calling function is *defined*. A plain function call
doesn't change that; only `include()`/`load()` do. So a Seal helper
several calls deep can read a bare relative path -- `seal_service()`'s
own `reset` script, for one -- and correctly reach *that service's own*
file. This is what lets a service's own directory be the only thing that
knows where it is.

**From Python.** `seal up`/`seal ci` need the same information
to fill each overlay's objects before Tilt starts. They get it by running `tilt
alpha tiltfile-result` against your root Tiltfile: that fully evaluates it
-- the same `include()`s and `seal_service()` calls `tilt up` would
run -- without needing a live cluster, and prints the resulting model as
JSON. Every image build appears as one `ImageTargets[]` entry whose selector
is the service's name and whose build context is its directory.

## Stable image tags for a publishing pipeline

Tilt always re-tags whatever it pushes under its own content-digest-derived
tag. That's invisible and fine for Tilt's own deploys, but it means nothing
*outside* Tilt -- a release-tracking tool watching a registry -- can reason
about a given build by its registry tag.

Two environment variables fix that, both set by whatever pipeline actually
publishes a build:

- **`SEAL_IMAGE_TAG`** -- the git SHA being deployed.
- **`SEAL_BUILD_ID`** -- a zero-padded, monotonically increasing build
  identifier.

When `SEAL_IMAGE_TAG` is set, `cached_docker_build()` re-tags and
pushes the already-built image a second time as
`<registry>/<ref>:$SEAL_BUILD_ID-$SEAL_IMAGE_TAG` -- cheap,
since the image is already in the local daemon. Local `tilt up` and
Seal's own CI set neither, so this only happens when something is
actually publishing.

The `SEAL_BUILD_ID` prefix is what makes plain lexicographic tag
comparison a correct recency comparison. A tool picking the newest image
usually sorts by each image's embedded build timestamp, but a fully
cache-hit rebuild reproduces an earlier build's timestamp exactly; those
ties break correctly only because of the prefix.

A build ID derived from a CI run identifier is pinned to the run it was
first assigned to: a re-run pushes the same tag, and the same digest, so
it's never a way to make a new build appear downstream. That needs a
genuinely new run.

:::{note}
`registry` has to be passed to each service's own `seal_service()` call,
duplicating your root Tiltfile's `default_registry()` value. Tilt doesn't
expose that value back to Starlark, and `cached_docker_build()` has no
business assuming any one project's registry.
:::

## Per-service test-result reporting

Giving `seal_service()` a `test_stage` and a `junit_tests_directory`
turns on that service's own result syncback and verdict check, entirely
self-contained -- no central registry has to know about it in advance. Each
tested service gets its own `seal_tests_verdict_<service_name>` Tilt
resource, so `tilt ci` fails pointing straight at whichever service's tests
actually failed.

Results land in `tests-results/<service_name>/`, beside where outcome
results land.

### How a service's tests run

Your test stage **carries** the suite. It doesn't run it:

```dockerfile
FROM development AS test
COPY ./tests /app/tests
COPY ./Makefile /app
```

Seal runs it, inside the container, once the service is ready:

```python
seal_service('example-api', test_stage='test',
             junit_tests_directory='/app/tests-results/',
             test_command='make unit-tests')
```

That gives the tests the container's own environment -- this service's
Secret, its database, its broker -- so a test needing any of them is an
ordinary test of this service instead of something that has to become an
outcome test to run at all.

The one thing your command has to do is leave a **JUnit report** in
`junit_tests_directory`. That report is the whole verdict -- Seal
reads it, not an exit code, not a status file -- and most runners take one
flag to produce it (`pytest --junit-xml=...`, karma-junit-reporter,
`--reporter junit`). No report, a report holding no test cases, and a report
that doesn't parse are each a *failure*, so a suite that never ran can't
pass for one that did.

What your command must *not* do is anything about failing. Seal
discards the suite's exit code itself: the results reach your project by
being copied out of the container after the run, so a run that stopped at a
failing test would take the report of what failed with it.

Where a service declares a `reset` too, Seal restores the baseline **on
both sides** of the run:

```
service ready → reset → this service's tests → reset → outcome tests
```

The first restore means your tests read this service's state from a known
starting point; the second means an outcome test does too, whatever your
tests did. You don't wire either.

A service that declares no `reset` has nothing putting its run ahead of the
outcome suite. Name it there if that matters:

```python
register_outcome_runner(
    base_url='http://web:8000',
    resource_deps=[
        reset_resource_name('example-api'),
        tests_run_resource_name('example-ui'),
    ],
)
```

:::{tip}
`tilt trigger seal_tests_run_<service>` re-runs one service's suite
against the session that's already up.
:::

