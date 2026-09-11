# Tilt extension reference

One extension, registered once in your project's root Tiltfile -- see
[Registering the Tilt
extension](../installation.md#registering-the-tilt-extension).

```python
load('ext://seal', 'k8s_overlay', 'publish_images', 'select_k8s_overlay',
     'seal_service', 'reset_resource_name', 'tests_run_resource_name',
     'register_outcome_runner')
```

Those seven are everything `ext://seal` exports. Everything else it
defines is wired together internally and never needed from outside.

---

## `ext://seal`

### `seal_service()`

```python
seal_service(
    service_name,
    context='.',
    dockerfile='Dockerfile',
    live_update=[...],
    development_stage=None,
    runtime_stage=None,
    test_stage=None,
    junit_tests_directory=None,
    test_command=None,
    k8s_resource_name=None,
    resource_dep=None,
    reset=None,
    use_cache=True,
    registry=None,
    **docker_build_kwargs,
)
```

One call per service, from that service's own Tiltfile. It is the one-call
version of the sequence you'd otherwise write by hand: build this service's
image and -- where asked -- wire up its test-result copy-back and its reset
resource. Not its credentials: which object carries those is the overlay's
to say, and the CLI fills it before Tilt starts (see
[Credentials](../guides/credentials.md)).

| Argument | Meaning |
| --- | --- |
| `service_name` | This service's name, and its image ref. |
| `development_stage`, `runtime_stage`, `test_stage` | This service's own Dockerfile stage names, one per `--build_type`. Each is optional: with no `runtime_stage` the Dockerfile's last stage is built; with no `development_stage` a session runs the runtime one; with no `test_stage` this service has no tests of its own and a `test` run builds what a session would. Giving `test_stage` is what turns on this service's result syncback and verdict resource. |
| `junit_tests_directory` | Where in the container that stage writes its results, which must include a JUnit report -- that report is the verdict. **Required whenever `test_stage` is given** -- Seal fails loudly rather than guessing. |
| `test_command` | What produces those results, run inside the running container once the service is ready (`kubectl exec`). **Required whenever `test_stage` is given**, and requires it in turn. Seal discards its exit code -- the report is the verdict. |
| `k8s_resource_name`, `resource_dep` | Both default to `service_name`, which is right when the service has its own Deployment. Override where several services share one Deployment or pod. |
| `reset` | A script putting the state this service owns back to a known baseline, relative to this service's Tiltfile. See [Deterministic test state](../guides/resetting-state.md). |
| `use_cache` | `True` (default) builds through `cached_docker_build()` when `SEAL_BUILDX_CACHE=1` is set, else through Tilt's native `docker_build()`. `False` always uses the latter. |
| `registry` | Your registry, duplicating your root Tiltfile's `default_registry()` value -- Tilt doesn't expose that value back to Starlark. |

Any other `docker_build()` argument (`build_args`, `extra_tag`, `ignore`,
`only`, `network`, `ssh`, `secret`, `platform`, ...) is forwarded as-is.

:::{note}
Tilt's native `docker_build()` understands all of those;
`cached_docker_build()`'s buildx command understands none of them and fails
loudly if given one.
:::

A service with no `services/<name>/.env` resolves nothing -- there's
nothing to opt out of.

### `select_k8s_overlay()`

```python
select_k8s_overlay(k8s_dir='k8s', default_overlay='dev')
```

Deploys one of `<k8s_dir>/`'s overlays as a kustomize overlay -- whichever
`--k8s_overlay` names, or the `default_overlay` you pass. Generating
`<project root>/.workspace/final-kustomize/kustomization.yaml` that selects
it and applying it with `k8s_yaml(kustomize(...))`.

Call it from your root Tiltfile, **after** every service is `include()`d.

### `register_outcome_runner()`

```python
register_outcome_runner(
    base_url='http://web:8000',
    resource_deps=[reset_resource_name('example-api')],
)
```

Called once, from your root Tiltfile, after every service is `include()`d.
Turns your whole outcome tree into Tilt resources.

- **`base_url`** -- where the application answers, as an outcome test
  reaches it from inside the cluster. Reaches every runner as
  `SEAL_BASE_URL`; the `playwright` runner makes it Playwright's `baseURL`.
- **`resource_deps`** -- what every outcome test waits for: which resources
  have to be serving, and which services at a known baseline.

The suite runs on its own only when this run's result is a verdict -- which
is what makes `seal ci` gate on it, since `seal ci` says so and
`seal up` does not. `--run_outcomes true` or `--run_outcomes false`
overrides either way. Everywhere else it's registered and triggered by hand.

See [Outcome tests](../guides/outcomes.md) and
[Outcome-test runners](../guides/runners.md).

### `reset_resource_name()`

```python
reset_resource_name('example-api')     # -> 'seal_reset_example_api'
```

Builds the name of a service's reset resource without hardcoding the
spelling, for naming it in another resource's `resource_deps`.

### `tests_run_resource_name()`

```python
tests_run_resource_name('example-ui')  # -> 'seal_tests_run_example_ui'
```

The same, for the resource that runs a service's own tests inside its
running container. It exists only for a service that declared a `test_stage`,
and only in a `--build_type test` run -- the run that builds the image
carrying that suite.

What names it is whatever must not overlap with that run. An outcome runner
driving a browser, on a node where a service's own suite drives a headless
one of its own, is two browsers competing for one machine: a slow outcome
test, and then a flaky one.

### `k8s_overlay`

The parsed value of the `--k8s_overlay` Tilt config flag -- **empty unless a
run names one**, since what a bare run means is your own `default_overlay`.
A service Tiltfile is `include()`d before `select_k8s_overlay()` resolves
that, so a project branching on the shape repeats its default:
`k8s_overlay or 'dev'`.

### `publish_images`

Whether this run pushes the images it builds to a real registry -- the
parsed value of `--publish_images`, off unless a run asks for it. Which
registry is yours to name; Seal never learns it:

```python
if publish_images:
    default_registry('ghcr.io/your-org')
```

---

## Tilt config flags

Defined by `ext://seal` and passed after `--`:

| Flag | Meaning |
| --- | --- |
| `--k8s_overlay` | Which of `k8s_dir`'s overlays `select_k8s_overlay()` deploys. Defaults to the `default_overlay` that call names. Naming one that isn't there fails, listing the ones that are. |
| `--publish_images` | Whether built images are pushed to a real registry. Off unless given. A bare `--publish_images` turns it on, and an explicit `=true` or `=false` sets it either way. |
| `--build_type` | Which kind of image to build: `development`, `test` or `runtime`. Defaults to `development`. `test` is what turns on each service's own test pipeline. |
| `--run_outcomes` | Whether the outcome suite runs on its own: `true` or `false`. Left unset it follows the run — `seal ci` is a gate, `seal up` is not. |
| `--record_outcome_video_on_failure` | Whether a promise the run doesn't see kept keeps a video of its browser: `true` or `false`. Defaults to `true` — a red promise is what somebody has to understand, and only a recording says what the browser actually did. Only the `playwright` runner records anything. |
| `--record_outcome_video_on_success` | Whether a promise the run *does* see kept keeps one too: `true` or `false`. Defaults to `false`: a video per passing test is footage of things working. Turn it on to check the suite exercises what you think it does. Asking for this without `--record_outcome_video_on_failure` is refused — nothing records a pass and discards a failure. |
| `--allowed_k8s_contexts` | Kubernetes contexts Tilt is allowed to deploy to, beyond the local ones it permits by default. |

```sh
seal ci -- --build_type test
seal up -- --k8s_overlay stag
```

---

## Resource names

Every Tilt resource Seal declares on your behalf is named
`seal_<purpose>[_<service_name>]`. Those land in the same flat namespace
as your project's own resources, so they say whose they are. Underscores
throughout, service names included, so the whole name reads as one token.

For a project whose service is `example-api` and whose outcomes are grouped
under `ui`:

| Resource | Declared by |
| --- | --- |
| `seal_reset_example_api` | `seal_service(reset=...)` |
| `seal_tests_results_dir` | once per project |
| `seal_tests_run_example_api` | `seal_service(test_command=...)` |
| `seal_tests_syncback_example_api` | `seal_service(test_stage=...)` |
| `seal_tests_syncback_trigger_example_api` | `seal_service(test_stage=...)` |
| `seal_tests_verdict_example_api` | `seal_service(test_stage=...)` |
| `seal_outcome_tests_ui` | `register_outcome_runner()`, per group |
| `seal_outcome_syncback_ui` | `register_outcome_runner()`, per group |
| `seal_outcome_syncback_trigger_ui` | `register_outcome_runner()`, per group |
| `seal_outcomes` | `register_outcome_runner()`, once per project |

`seal_reset_<service>` is the one of these a project has reason to name
itself -- it's the contract anything needing a service's state at a known
baseline depends on. Use `reset_resource_name()` to build it.

:::{note} A generated Kubernetes name for an outcome is
`seal-outcome-<epic>-<outcome>`. A slug long enough to push that past
the 63 characters a name may have fails loudly rather than being shortened:
two outcomes silently sharing one Deployment is worse than being told to
rename a directory. :::

---

## What Seal reaches for itself

Neither of these is something a project registers or names.

- **`cached_docker_build()`**, from Seal's own `tilt/docker_build`.
  Builds through a GitHub-Actions-cached buildx build instead of Tilt's
  native `docker_build()`. `seal_service()` decides when to reach for
  it -- `use_cache=True` **and** `SEAL_BUILDX_CACHE=1`, which only the
  reusable CI workflows set. It also implements the stable-tag push: when
  `SEAL_IMAGE_TAG` is set, it re-tags and pushes the already-built
  image a second time as
  `<registry>/<ref>:$SEAL_BUILD_ID-$SEAL_IMAGE_TAG`. See [Stable
  image
  tags](../guides/project-layout.md#stable-image-tags-for-a-publishing-pipeline).
- **`syncback`**, the official Tilt extension, for copying test results out
  of running containers. This is why `rsync` is a prerequisite. Seal
  registers tilt-dev/tilt-extensions under a private alias of its own rather
  than going through Tilt's built-in `default` repo, so what you call your
  own extension repo can never break this load.
