# Quickstart

This takes the worked example -- a Django API, an Angular UI and an nginx
reverse proxy -- from a clone to a running stack, then runs the tests a
merge would rest on. Most of the elapsed time is Docker building images the
first time.

You need the [prerequisites](installation.md#prerequisites), including a
local cluster with `kubectl`'s current context pointed at it -- Docker
Desktop's `docker-desktop` is the usual one. Everything below deploys into
that cluster, so make sure it's a throwaway:

```sh
kubectl config current-context
```

## 1. Clone the worked example

```sh
git clone https://github.com/vdel/seal
cd seal/examples/angular-django
```

Every command below runs from `examples/angular-django/`. That directory is
the **project root**: it has its own `Tiltfile` and a `services/`
subdirectory, which is how `seal` recognises one.

## 2. Bring the stack up

```sh
seal up
```

`seal up` is `tilt up` with the credential step in front of it: it
resolves every service's `.env`, fills the Kubernetes objects this
directory's overlay says Seal fills, and then starts Tilt against its
own root `Tiltfile`.

:::{important}
Use `seal up`, not `tilt up`. A bare `tilt up` does **not** refuse: it
deploys those objects with nothing in them, so containers start without
their credentials and the failure surfaces well away from its cause. See
[Credentials](guides/credentials.md).
:::

No value in the example names a store -- they're literals and `k8s://`
markers -- so nothing here asks you to log in anywhere, even though the
project declares a provider for the reference a real one would use.

When Tilt reports everything green, the stack is reachable:

| URL | What's there |
| --- | --- |
| <http://localhost:8000> | nginx, fronting the whole stack: the API under `/api/`, the Angular app everywhere else. |
| <http://localhost:8888> | The Django API directly. |
| <http://localhost:4200> | The Angular dev server directly. |

Open <http://localhost:8000> and you get a todo list with a few items
already in it. Those come from a checked-in fixture -- see
[Deterministic test state](guides/resetting-state.md).

## 3. Put the data back

Add and delete a few items, then put the list back to its baseline:

```sh
tilt trigger seal_reset_example_api
```

That runs the `api` service's own reset script (`deploy/reset.sh`), which
empties the tables it owns and reloads the fixture. Nothing fires it
automatically in a session you're working in -- resetting mid-keystroke is
how somebody loses what they were looking at -- so it's a trigger you ask
for, from the Tilt UI or the command line.

## 4. See what the project promises

```sh
seal outcomes
```

```
ui/todo-list/a-deleted-item-stays-deleted               translated   deleting an item takes it off the list for good
ui/todo-list/an-added-item-survives-a-reload            translated   an item I add is still on the list after a reload
ui/todo-list/ticking-an-item-off-updates-the-count      translated   ticking an item off updates how many are left

3 outcome(s), 3 translated.
```

Each line is a promise the application makes, written the way somebody using
it would put it, plus whether a test has been translated from it yet. The
promises live in `outcomes/`, one directory per outcome, with the prompt and
its test side by side. See [Outcome tests](guides/outcomes.md).

Run one against the session you have up:

```sh
seal outcomes run ui/todo-list/an-added-item-survives-a-reload
```

This builds the group's runner image -- a container with Playwright and
Chromium in it -- and drives the application from inside the cluster, the
same image and the same container CI would use. Reports land in
`tests-results/outcomes/<group>/<epic>/<outcome>/`.

## 5. Run what a merge would run

```sh
tilt down                          # free the cluster first
seal ci -- --build_type test
```

`seal ci` is the whole gate in one command. It:

1. Runs `seal check` -- refusing to start if a Deployment container has no
   `readinessProbe`, if the outcome tree doesn't pair every test with a
   prompt, or if `CODEOWNERS` doesn't cover that tree.
2. Resolves every service's credentials, exactly as `seal up` did.
3. Runs `tilt ci`, which builds each service's *test* stage, runs its unit
   tests inside its own container, and waits until every resource is ready.
4. Runs the whole outcome suite against the environment that just came up,
   and exits on its verdict.

It exits non-zero on the first thing that fails, and zero only when the
environment came up *and* every translated promise still holds. That is
exactly what the [reusable CI workflow](guides/continuous-integration.md)
runs.

The suite's report, on its own:

```sh
seal outcomes run
```

```
ui/todo-list/a-deleted-item-stays-deleted           PASS  deleting an item takes it off the list for good
ui/todo-list/an-added-item-survives-a-reload        PASS  an item I add is still on the list after a reload
ui/todo-list/ticking-an-item-off-updates-the-count  PASS  ticking an item off updates how many are left

3 outcome(s): 3 passed.
```

When it *isn't* green, the loop back is `seal outcomes run --reset
--all --confirm` against a session `seal up` already has up -- the
whole suite, from a known baseline, with each failure re-run on its own to
see whether it reproduces. See [Getting back to
green](guides/regression-loop.md).

## 6. Tear down

```sh
tilt down
```

## Starting your own project

Seal is a layer on Tilt, so the first step is Tilt's, not Seal's:
**make your project Tilt-ready** -- a Dockerfile per service, Kubernetes
manifests as one kustomize overlay per shape you deploy, and a root
`Tiltfile` that `include()`s each service and brings the stack up with plain
`tilt up`. Nothing about that step is Seal-specific, and Tilt's own
[getting started guide](https://docs.tilt.dev/tutorial.html) is the place
for it.

Then swap the relevant calls for Seal's:

1. **Register the extension** at the top of your root `Tiltfile` -- see
   [Registering the Tilt
   extension](installation.md#registering-the-tilt-extension).
2. **Replace each service's `docker_build()` with `seal_service()`**
   in that service's own Tiltfile. One call takes over the build, its
   `.env`, its own test run and the reset that puts its state back -- see
   [Declaring your services](guides/project-layout.md).
3. **Replace `k8s_yaml(kustomize(...))` with `select_k8s_overlay(k8s_dir=...,
   default_overlay=...)`**, naming the overlay a bare `seal up` should
   bring up. There's no default for that last one: the overlays are
   directories you made and named, so which one a bare run means is yours to
   say.
4. **Run `seal up` instead of `tilt up`.** At this point you have
   everything the example had at step 2 above.

What's left is the gate:

5. **Write down what your application promises** in `outcomes/`, and put the
   tree under a `CODEOWNERS` rule -- see [Outcome tests](guides/outcomes.md)
   and [The merge gate](guides/merge-gate.md).
6. **Point the `ci` action at your project** so every pull request
   runs `seal ci` -- see
   [Continuous integration](guides/continuous-integration.md).

Read [How Seal fits together](concepts.md) next for the model all of
that sits on.
