# seal

The project-facing half of this repo's Tilt extensions: generic project
config, credential-to-`Secret` resolution, and CI test-result reporting, all
grouped under one extension (see `/tilt/README.md` at the repo root for why
`docker_build` stays separate from it). Shares its name with the Python
`seal` package (`/python/`) on purpose -- see
`/rfcs/0002-declaration-by-structure.md` at the repo root for how a project
declares its
services, and `examples/angular-django/Tiltfile` for how a project's own,
checked-in entry Tiltfile uses this extension.

```python
load('ext://seal', 'k8s_overlay', 'publish_images', 'select_k8s_overlay', 'seal_service', 'reset_resource_name', 'register_outcome_runner')
```

Internally this is six files sharing one directory --
`v1alpha1.extension(name='seal', repo_path='tilt/seal')` loads
whichever one of them is asked for, and `Tiltfile` itself wires them
together and re-exports only the symbols above, the only ones a project's
own Tiltfile ever needs to call directly. Everything else these files define
(`register_syncback()`, `seal_resource_name()`, `PROJECT_ROOT`,
`build_type`) is wired
together between them directly and never needed from outside `seal`
itself -- see each section below for where.

## `resources.Tiltfile`

`seal_resource_name(purpose, service_name=None)` -- how every Tilt
resource seal declares on a project's behalf is named:

```
seal_<purpose>[_<service_name>]
```

Those resources land in the same flat namespace as the project's own, so
they say whose they are. `seal_` is the marker, and it needs no sigil in
front of it: the name is coined, so nothing a project calls a resource of its
own begins that way. The purpose comes before the service
so everything doing the same job sorts together whatever services a project
has, and a purpose names what the resource is *for*, never the tool it uses
to do it. Underscores throughout, service name included: these are
`local_resource`s rather than Kubernetes objects, so DNS-1123's ban on
underscores -- which is why a project's own resources are hyphenated --
doesn't apply, and one separator makes the whole name read as a single
token.

What that produces, for a project whose service is `example-api` and whose
outcomes are grouped under `ui`:

| Resource | Declared by |
| --- | --- |
| `seal_reset_example_api` | `seal_service(reset=...)` |
| `seal_tests_results_dir` | `tests.Tiltfile`, once per project |
| `seal_tests_run_example_api` | `register_syncback(test_command=...)` |
| `seal_tests_syncback_example_api` | `register_syncback()` |
| `seal_tests_syncback_trigger_example_api` | `register_syncback()` |
| `seal_tests_verdict_example_api` | `register_syncback()` |
| `seal_outcome_tests_ui` | `register_outcome_runner()`, per group |
| `seal_outcome_syncback_ui` | `register_outcome_runner()`, per group |
| `seal_outcome_syncback_trigger_ui` | `register_outcome_runner()`, per group |
| `seal_outcomes` | `register_outcome_runner()`, once per project |

`reset_resource_name(service_name)` is re-exported from `ext://seal`
for the one of these a project has a reason to name itself -- see
`build.Tiltfile` below.

## `config.Tiltfile`

- Defines the `--k8s_overlay`, `--build_type`, `--publish_images` and
  `--allowed_k8s_contexts` Tilt config flags, and parses them into
  `k8s_overlay` (empty unless a run names one -- what a bare run means is
  the project's own `default_overlay`, see `select_k8s_overlay()` below),
  `publish_images` (a boolean, off unless a run asks for it -- which registry
  it pushes to is the project's own to name through `default_registry()`) and
  `build_type` (`'development'`, `'test'` or `'runtime'`, defaulting to
  `'development'`).
- Exposes `PROJECT_ROOT`, the calling project's root directory (`config.main_dir`),
  so every helper anchors project-relative paths the same way regardless of
  how many `include()`/`load()` hops separate it from the root Tiltfile.
- Exposes `select_k8s_overlay(k8s_dir, default_overlay)`, which generates
  `<PROJECT_ROOT>/.workspace/final-kustomize/kustomization.yaml` selecting
  the selected `<k8s_dir>/` overlay and applies it with
  `k8s_yaml(kustomize(...))` itself. Call it from your project's own root
  Tiltfile, after `include()`ing every service (see
  `examples/angular-django/Tiltfile`).

- Registers tilt-dev/tilt-extensions as `__seal_default_ext_repo`, a
  private alias, and the official `syncback` extension as
  `ext://__seal_syncback` off it. Going through a name of seal's
  own rather than Tilt's built-in `default` repo means a project can call its
  own extension repo whatever it likes, `default` included, without breaking
  loads it never made.

Every other file in this extension loads `config.Tiltfile` first, so the
alias exists by the time anything reaches for it.

## Where a service's credentials come from

Nothing in this extension turns a service's `.env` into a Kubernetes
object any more, and no file here names one. **The overlay says which
object carries which values**, by annotating it:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: api-db
  annotations:
    seal-test.dev/fill-from: api
```

`seal up`/`seal ci` (not `tilt up`/`tilt ci` directly) read
every overlay, resolve each named service's `.env` through the providers
that project declared -- the same system `seal run` uses for
arbitrary commands, with `--credentials_env` picking a different store per
environment (see `python/src/seal/providers.py`) -- and write one
strategic-merge patch per annotated object under
`.workspace/seal-env/<overlay>/`, beside a kustomization naming that
overlay. `select_k8s_overlay()` deploys that when it exists, so one object
reaches the cluster: the project's own, with `data` supplied.

A stub naming no `seal-test.dev/keys` claims every key of that service's
`.env` no other object claims, so one four-line stub is the whole of what
a project writes. Splitting across a ConfigMap and one Secret per
credential group is opt-in, and only a split object names keys.

A project that annotates nothing has nothing filled, and its overlay
deploys exactly as written -- which is what running an operator or a CSI
driver in a session cluster looks like. See
`/rfcs/0007-credential-delivery.md` at the repo root for the full picture.

## `tests.Tiltfile`

Test-result syncback and verdict reporting for CI, used when
`build_type == 'test'`:

```python
# Called once per tested service, after its docker_build()/k8s_resource():
register_syncback(service_name, test_results_dir=...)
```

`register_syncback(service_name, ...)`:

- Registers a `seal_tests_run_<service_name>` `local_resource` that runs
  `test_command` inside the running container (`kubectl exec`) once the
  service is ready, and never fails on what the suite says -- the results
  are copied out downstream of it, so a run that stopped here would take the
  report of what failed with it. Where the service declares a `reset` too,
  that script runs on both sides of this: a `seal_tests_reset_<name>`
  resource ahead of the run, so its tests start from the baseline, and
  `seal_reset_<name>` after it, so the outcome suite does too.
  `tests_run_resource_name()` is the run's name, for a project sequencing
  something else behind it (a service with no reset of its own, most
  obviously).
- Copies `test_results_dir` (defaults to `/app/tests-results/` when not
  given -- `seal_service()` itself always passes one, see
  `build.Tiltfile` below) out of the running container back to
  `<PROJECT_ROOT>/tests-results/<service_name>/` once its tests have run,
  via the official `syncback` extension, which `config.Tiltfile` registers
  under a private name of seal's own (see `config.Tiltfile` above).
- Registers a `seal_tests_verdict_<service_name>` `local_resource` that
  fails the Tilt run (so `tilt ci`) unless the synced-back JUnit report says
  every test passed -- one per service, so CI fails pointing straight at
  whichever service actually failed instead of one combined check. It runs
  `seal _tests-verdict`, which reads the report (`python/src/seal/junit.py`)
  and treats no report, a report holding no cases, and one that doesn't
  parse as failures: nothing upstream of it fails on a failing suite, so
  nothing else distinguishes a service whose tests never ran from one whose
  tests all passed.

## `build.Tiltfile`

`seal_service(service_name, ...)` is the one-call version of the
sequence a service's own Tiltfile would otherwise write by hand --
`cached_docker_build()`/`docker_build()` -- plus, when `test_stage` is
given, `register_syncback()`, and when `reset` is given, this service's
reset resource -- which waits on `resource_dep` (or the service itself) and,
in a test run only, runs once at startup:

```python
load('ext://seal', 'seal_service')

seal_service(
    service_name,
    context='.',
    dockerfile='Dockerfile',
    live_update=[...],
    development_stage='development',                  # this service's own stage names, one per build type
    runtime_stage='runtime',                          # omit any this service doesn't have
    test_stage='test',                                # omit if it has no tests of its own
    junit_tests_directory='/app/tests-results/',      # required whenever test_stage is given
    test_command='make unit-tests',                      # required whenever test_stage is given
    reset='deploy/reset.sh',                          # this service's state back to a known baseline; omit if it owns none
)
```

- No Kubernetes object for this service's credentials is applied here at
  all: which object carries them is the overlay's own statement (see
  "Where a service's credentials come from" above), so a service needing
  none simply has no overlay annotating one.
- `use_cache=True` (default) builds with `cached_docker_build()` (see
  `/tilt/docker_build/README.md`) when `SEAL_BUILDX_CACHE=1` is set (only
  under the reusable CI workflows, never local `tilt up`), else with Tilt's
  native `docker_build()`; pass `use_cache=False` to always use the latter,
  even under `SEAL_BUILDX_CACHE=1`. `/tilt/docker_build/Tiltfile` is
  `load()`ed by relative path from its sibling directory, so a project
  registers nothing for it. It has to be a top-level `load()` rather than a
  `load_dynamic()` inside the function: Tilt resolves a relative path against
  whichever Tiltfile is *executing*, which inside `seal_service()` is
  the calling service's own directory, not this one.
- Any other `docker_build()` argument (`build_args`, `extra_tag`, `ignore`,
  `only`, `network`, `ssh`, `secret`, `platform`, ...) can be passed through
  as a keyword argument too, forwarded to `cached_docker_build()`/
  `docker_build()` as-is. Tilt's native `docker_build()` understands all of
  them; `cached_docker_build()`'s buildx command doesn't understand any of
  them, and fails loudly if given one -- see `/tilt/docker_build/README.md`.
- `development_stage`, `runtime_stage`, `test_stage` (each default `None`)
  are this service's own Dockerfile stage names, one per `--build_type`.
  seal names the kind of image a run wants; the service names what to build
  for it, so no project has to spell its stages the way seal would.
  Each `None` makes a claim worth reading:
  - **no `runtime_stage`** -- build with no `target`, so Docker takes the
    Dockerfile's last stage. That is the whole Dockerfile for a service
    built in one stage.
  - **no `development_stage`** -- falls back to `runtime_stage`: this
    service runs the same image in a session as in a real environment,
    which is true of a worker or a small sidecar. Deliberately not an
    independent fallback to "the last stage" -- in a multi-stage Dockerfile
    that *is* the runtime stage, so it would hand a session the production
    image without saying so.
  - **no `test_stage`** -- this service has no tests of its own. None of
    its test pipeline is registered, and a `test` run builds what a session
    would; the service still has to serve, for the outcome suite and for
    whatever other services test against it.

  Giving `test_stage` is what turns on this service's test pipeline.
- `test_command` (default `None`) is what produces this service's report,
  run inside the running container. **Required** whenever `test_stage` is
  given, and requires it in turn: the command runs in the deployed
  container, so the stage holding this service's tests has to be the stage
  that gets built.
- `junit_tests_directory` (default `None`) is forwarded to
  `register_syncback()` as `test_results_dir`. **Required** whenever
  `test_stage` is given -- `seal_service()` fails loudly if it's
  missing, rather than falling back to a guessed default that might not
  match where that service's own Dockerfile actually writes its output.
  What that directory has to hold is a JUnit report: it is the whole
  verdict on this service's tests (see `tests.Tiltfile` above).
- `k8s_resource_name`, `resource_dep` are forwarded to `register_syncback()`
  as-is -- both default to `service_name`, correct when the service has its
  own Deployment; override them when several services share one
  Deployment/pod (e.g. merged into a shared `'web'` resource, see
  `examples/angular-django/services/api/Tiltfile`).
  `register_syncback()`'s `container` argument is always `service_name`
  here, its first argument, not separately settable.

- `reset` (default `None`) is this service's own script for putting the
  state it owns back to a known baseline, as a path relative to the
  service's Tiltfile. Giving it registers a `local_resource` named
  **`seal_reset_<service_name>`** (hyphens in the service name written as
  underscores: `example-api` gives `seal_reset_example_api`) that runs the
  script from the service's own directory, once `resource_dep` (or the
  service itself) is up. `TRIGGER_MODE_MANUAL`, so no file edit ever fires
  it, and the way to ask for one is a trigger
  (`tilt trigger seal_reset_<service_name>`, or the button in the Tilt UI).
  `auto_init` follows `build_type`: a test run starts a service from its
  baseline, and a session somebody is about to work in keeps whatever state
  they left.
  That resource name is the contract: anything needing a service's state at
  a known baseline before it runs names it in its own `resource_deps`.
  `reset_resource_name(service_name)` is exported alongside `seal_service()`
  for building that name without hardcoding the spelling. One script, not a
  clean step and a separate seed step -- see `/rfcs/0004-deterministic-state.md`.

## `outcomes.Tiltfile`

`register_outcome_runner()` -- a project's whole outcome tree as Tilt
resources. Called once, from the project's own root Tiltfile, after every
service is `include()`d:

```python
load('ext://seal', 'register_outcome_runner', 'reset_resource_name')

register_outcome_runner(
    base_url='http://web:8000',
    resource_deps=[reset_resource_name('example-api')],
)
```

`base_url` is where the application answers, as an outcome test reaches it
from inside the cluster. The project says it because only the project can --
seal knows nothing about an app's own service names or ports. It reaches
every runner as `SEAL_BASE_URL`, and the `playwright` one makes it
Playwright's `baseURL`.

`resource_deps` is what every outcome test waits for, and the project names
it for the same reason: only the project knows which of its resources have
to be serving before a test means anything, and which of its services have
to be at a known baseline first. seal knows which services declared a
reset, not which ones an outcome reads, and a dependency nobody asked for is
a slower run at best and a cycle at worst.

Outcome tests run as one container per group of outcomes, built from the
outcome tree, driving the running environment and leaving a verdict per
outcome behind (see `/rfcs/0010-outcome-tree.md` for the layout,
`/rfcs/0011-outcome-runners.md` for the runner contract). Walking the tree
is still what finds the outcomes here too, so one added later is covered by
having been added -- there's nothing to keep in agreement with it.

What a walk can't answer is which image to build for a directory, and that's
the whole of what `seal-test-config.json` at the tree's root declares:
one runner per group directory. `playwright` is seal's own -- a pinned
Playwright version, the Chromium build that release drives, and a generated
config carrying `baseURL`, `workers: 1` and the JUnit/HTML reporters -- and
the translation is spec files. `custom` builds a `Dockerfile` the project
brings, for a group whose outcomes aren't browser-shaped.

For each declared group `<g>`, this registers:

- `seal_outcome_tests_<g>` -- a `docker_build()` of that group through the
  runner declared for it, and a Deployment running it, generated here rather
  than asked of the project. Its `readinessProbe` is the run having finished
  (`/outcome-results/done`), which is what lets `tilt ci` wait for it the
  same way it waits for everything else. Its container `args` are the
  runner's own arguments, then `--`, then the outcomes to run as
  `<epic>/<outcome>` -- named from inside the group, and named explicitly
  because seal knows which have been translated and the runner doesn't.
- `seal_outcome_syncback_<g>` -- the copy of that container's
  `/outcome-results/` to `<PROJECT_ROOT>/tests-results/outcomes/<g>/`, beside
  where each service's own results already land, plus the
  `seal_outcome_syncback_trigger_<g>` that fires it.

and once, whatever a project has runners:

- `seal_outcomes` -- the report, whose command is `seal outcomes run` and
  which waits on every group's syncback. Separate from the runs: `tilt ci`
  stops at the first resource that fails, and "every promise still holds" has
  to be distinguishable from "the one test somebody was looking at passed".

Outcomes run one at a time, and within a group that is the runner's job
rather than Tilt's: they drive the same application, and a promise that holds
shouldn't fail for what another test was doing. The `playwright` runner does
it with `workers: 1`. Across groups it is Tilt's job -- where the suite
runs on its own, each group's run waits for the one before it. A
session somebody is working in triggers a group by hand, where a group
waiting on another nobody triggered would never start, so
`seal outcomes run` serialises them itself instead.

The suite runs on its own only when this run's result is a verdict, which is
what makes `seal ci` gate on it: `seal ci` says so, `seal
up` does not, and `--run_outcomes true|false` overrides either way.
Deliberately not read off `build_type` -- a run against a production-shaped
overlay builds images carrying no test suite and is a gate all the same.
Everywhere else it's registered and triggered by hand -- `seal up`
starts a session somebody is about to work in, and spending a whole outcome
suite on every start of one is how a local loop stops being used.

Triggering by hand is what `seal outcomes run <slug>...` does for you: it
writes the outcomes it was given to `.workspace/seal/outcomes-selection`,
which this file reads through `read_file()` so Tilt re-evaluates and narrows
the run, then fires the run and its syncback, waiting for each, and reports
only those outcomes (see `/rfcs/0010-outcome-tree.md`). The selection is put
back afterwards, so a run triggered from the Tilt UI covers the whole tree.
The resource names it triggers are the ones above, so renaming one here
renames what that command reaches.

`seal up`/`seal ci` announce how to run the CLI again in
`SEAL_CLI` (`python/src/seal/seal.py`), so the suite runs
through the same interpreter that started the session; a plain `tilt up`
falls back to `seal` on `PATH`.

One constant pins the framework, and through it the browser: Playwright
installs the Chromium build that release drives, so the two can't drift
apart -- a mismatch would be a browser that refuses to launch, reading as a
promise failing. Only Chromium is installed, since that's all the generated
config launches; the official all-browser image would carry Firefox and
WebKit as freight, paid for on the daemon that builds the image, the
registry it's pushed to and the node that pulls it. Chromium's sandbox is
off and `/dev/shm` goes unused, both being properties of running a browser
in a pod rather than of any one project.

A generated Kubernetes name is `seal-outcome-<epic>-<outcome>`, and a
slug long enough to push it past the 63 characters a name may have fails
loudly rather than being shortened -- two outcomes silently sharing one
Deployment is worse than being told to rename a directory.

