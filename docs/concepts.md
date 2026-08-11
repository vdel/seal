# How Seal fits together

One page for the model behind everything else: what Seal considers a
project, what each piece is responsible for, and where the line between
"yours" and "Seal's" falls.

## A project is a directory with a Tiltfile and services

`seal run`, `seal up` and `seal ci` all walk up from where
you invoke them looking for a directory with **both** its own `Tiltfile` and
a `services/` subdirectory. That directory is the project root. A service's
own directory has a `Tiltfile` too, but never its own nested `services/`, so
the search is unambiguous.

Everything else is relative to that root:

```
my-project/
  Tiltfile                 # the entry point -- and the service list
  services/
    api/
      Tiltfile             # this service's build, tests, reset
      Dockerfile
      .env                 # this service's credentials schema
    ui/
      ...
  third-party/
    nginx/Tiltfile         # off-the-shelf services with no source to build
  k8s/
    dev/                   # one kustomize overlay per manifest shape
  outcomes/
    seal-test-config.json  # what runs each group of promises
    <group>/helpers/       # what a group's tests share
    <group>/<epic>/<outcome>/
      prompt.md            # the promise
      quarantine.md        # optional: why a failure here doesn't fail a run
      ...                  # the test translated from it
  tests-results/           # where results land, generated
```

## There is no config file, anywhere

This is the single idea most worth internalising. Seal never keeps a
registry that has to be kept in agreement with the tree:

- **Which services exist** is whatever your root `Tiltfile` `include()`s.
  `seal up`/`seal ci` discover them by asking Tilt itself to evaluate that
  Tiltfile (`tilt alpha tiltfile-result`) and reading back the image builds.
- **Which credentials a service needs** is whatever key names appear in its
  own `services/<name>/.env`. There's no separate schema file, and the same
  file is the schema in dev, CI, staging and production alike.
- **Which promises a project makes** is whatever directories exist under
  `outcomes/`. Walking the tree is the whole discovery mechanism.
- **Where a service's files are** is wherever its own `Tiltfile` is. Tilt
  resolves a relative path against whichever Tiltfile is executing, so
  Seal's helpers read `.env` with a bare relative path and get *that*
  service's own.

The one thing a walk can't answer is which image runs a directory of
promises, and that's the whole of what `outcomes/seal-test-config.json`
declares -- so it's also the one place the tree and a declaration can drift,
which is why `seal check` compares them.

## The two halves

**`ext://seal`** (Starlark) is what your Tiltfiles call -- the one
extension a project registers:

- `seal_service()` -- one call per service, wiring up its image
  build, its test-result syncback and its reset. Not its credentials: which
  object carries those is the overlay's to say, not this call's.
- `select_k8s_overlay()` -- deploys one of `<k8s_dir>/`'s overlays.
- `register_outcome_runner()` -- turns your whole outcome tree into Tilt
  resources.
- `reset_resource_name()`, `k8s_overlay`, `publish_images` -- the names and flags a project
  needs to refer to the above.

See the [Tilt extension reference](reference/tilt-extensions.md).

**`seal`** (the CLI) is what you run instead of `tilt`:

| Command | What it's for |
| --- | --- |
| `seal up` | Local development. Credentials, then `tilt up`. |
| `seal ci` | The gate. Checks, credentials, `tilt ci`, then the outcome suite. |
| `seal run -- <cmd>` | One command with a service's `.env` injected. |
| `seal check` | The three static checks, on their own. |
| `seal outcomes ...` | List, run, translate and review promises, and say what a change reaches in the tree. |

See the [CLI reference](reference/cli.md).

## Two kinds of test, and only one of them is the gate

**A service's own tests** run inside that service's own running container,
built from its Dockerfile's test stage -- which is what lets them use its
real database and credentials. Declaring `test_stage=` on
`seal_service()` turns on the copy-back of their results and a
per-service resource that fails the run unless the JUnit report they left
says every test passed -- so CI points at whichever service actually broke.

**Outcome tests** live at the project root, not under any one service,
because driving several services at once is what makes them outcome tests.
Each one sits beside the promise it was translated from. They run as one
container per group, from inside the cluster, one outcome at a time.

The gate rests on the second kind, and on two properties of it:

1. **Every promise runs, in one pass.** A fix scoped to the test somebody
   was looking at can break one nobody re-ran, so what has to be reportable
   is "every promise this project has translated still holds" -- which is
   why `seal ci` runs the whole suite and names no subset.
2. **No test can be edited without a human.** `CODEOWNERS` over the outcome
   tree plus branch protection is what makes "the tests pass" mean the
   application was fixed rather than the test rewritten.

`seal check` refuses a tree that breaks either -- an outcome with no
prompt to trace it back to, or an outcome the repository's `CODEOWNERS`
doesn't reach.

## Red is fixed in the application, not in the test

Those two properties decide what a *green* suite means. The other half of
the model is what a *red* one is for.

A suite passes identically whether the application was fixed or the test was
rewritten, and that difference is the whole gate. So getting back to green is
a loop with the test held still: run the whole suite from a known baseline,
confirm each failure, fix the application, run the whole suite again.

```sh
seal outcomes run --reset --all --confirm
```

Three things in that command, each answering a way a loop goes wrong:

- **`--reset`** puts every service that declared one back to its baseline
  first, so this run measures the application rather than the application
  plus whatever the last iteration left in it.
- **`--all`** runs every promise, because a fix scoped to the one that was
  red can break another nothing re-ran.
- **`--confirm`** re-runs each failure on its own, from a reset. A promise
  that then holds is not something an application fix will settle -- the test
  either doesn't own the data it asserts on or isn't deterministic -- and
  chasing it costs real time for nothing.

`seal outcomes touched` says whether an iteration stayed inside the
application. It reports rather than refusing: changing a promise is a
legitimate thing to do, and what it costs is a code owner's approval.

**Quarantine is the one declared exception.** A `quarantine.md` in an
outcome's own directory, whose content is the reason, makes a failure there
non-blocking while somebody fixes the test's determinism. It is still run and
still reported, and never counted as passed. It lives inside the outcome so
the `CODEOWNERS` rule over the tree already covers it -- which is what stops
it being a way to a green suite that never went near the application.

See [Getting back to green](guides/regression-loop.md).

## One credential path, four scopes

Local development, CI, staging and production all resolve the same
`services/<name>/.env`, the same way. The only thing that differs is which
credentials environment a run selects, and so which store each reference is
read from -- the `.env` line itself is identical everywhere, because it
names an item and never a store.

That's deliberate: separate resolution paths per scope drift, and a value
that can be edited somewhere disconnected from the store's own sharing and
audit story is a value nobody really owns. See
[Credentials](guides/credentials.md).

## What your project owns

Seal knows nothing about your application: no default port, path,
framework or service name. Where the generic side needs something only you
can say, you say it -- through your Tiltfile, your `.env`, or an environment
variable like `SEAL_K8S_DIR`.

Concretely, these are yours and Seal never guesses at them:

- the address an outcome test reaches your application at
  (`register_outcome_runner(base_url=...)`);
- which resources have to be serving, and which services at a known
  baseline, before an outcome test means anything (`resource_deps=`);
- what putting a service's state back actually involves (`reset=`);
- which readiness probe is right for a container;
- your registry, your manifests, your promises.
