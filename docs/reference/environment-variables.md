# Environment variables

Every variable Seal reads or sets, and who is expected to set it.

## Read from your environment

### `SEAL_K8S_DIR`

Where your Kubernetes manifests live, when they aren't in `./k8s`. Read by
`seal check` and `seal ci`, and it should name the same
directory you pass to `select_k8s_overlay(k8s_dir=...)`.

It's an environment variable rather than a flag because `seal ci` hands
every argument it's given straight to `tilt ci`, leaving it none of its own
to spend. `seal check` also takes `--k8s-dir` for a one-off.

### `SEAL_OUTCOMES_DIR`

Where your outcome tree lives, when it isn't in `./outcomes`. Read by
`seal check`, `seal outcomes` and its subcommands, all of which
also take `--outcomes-dir` for a one-off.

:::{note}
There's no equivalent for `CODEOWNERS`. It's read from wherever the platform
itself would read it, and a file the platform never reads owns nothing -- an
escape hatch there would only let a project pass a check while having no
gate.
:::

### `SEAL_CREDENTIALS_ENV`

Which credentials environment a run reads: the key into every declared
provider's `environments` map, deciding which store each reference resolves
against. `--credentials_env` overrides it, and the project's own
`default_env` applies when neither is set.

Named for Seal rather than called `ENV`: a one-word name claimed out
of a developer's shell collides with whatever else set it, and a collision
here resolves silently towards the wrong store.

A deploy pipeline sets it to that environment's own name. Seal's
reusable CI workflow leaves it at the project's own default, since nothing
it runs reaches a real environment. Which Kubernetes overlay gets deployed
is a separate choice, made independently of this one -- neither implies the
other.

See [Credentials](../guides/credentials.md#which-environment-a-run-reads).

### `SEAL_BUILDX_CACHE`

Set to `1` to make `seal_service()` build through
`cached_docker_build()` -- a buildx build with a GitHub Actions layer cache
-- instead of Tilt's native `docker_build()`. Only the reusable CI workflows
set it; local `tilt up` never does.

### `SEAL_IMAGE_TAG` and `SEAL_BUILD_ID`

Set by whatever pipeline actually publishes a build, to get a stable,
externally-discoverable registry tag alongside Tilt's own
content-digest-derived one.

- **`SEAL_IMAGE_TAG`** -- the git SHA being deployed. Its presence is what
  turns the second push on at all.
- **`SEAL_BUILD_ID`** -- a zero-padded, monotonically increasing build
  identifier, whose prefix is what makes plain lexicographic tag comparison
  a correct recency comparison.

Together they produce
`<registry>/<ref>:$SEAL_BUILD_ID-$SEAL_IMAGE_TAG`. Local `tilt
up` and Seal's own CI set neither. See [Stable image
tags](../guides/project-layout.md#stable-image-tags-for-a-publishing-pipeline).

### `IS_BUILD_OR_TEST`

`1` means this is a build or unit-test scope, in which nothing has supplied
a service's credentials and the application injects its own fakes in code.
Seal sets it itself during the service-discovery pass, which evaluates
your Tiltfile before a session exists -- so a project's own Tiltfile may
branch on it to skip anything that pass has no cluster for.

An application reads it where its own settings need to distinguish a
unit-test run from a deployed one.

---

## Set by Seal, for something else to read

### `SEAL_BASE_URL`

Where the application answers, as an outcome test reaches it from inside the
cluster. Seal passes it into every outcome runner's container, from your
`register_outcome_runner(base_url=...)`.

This is the one address a runner should need. The `playwright` runner makes
it Playwright's `baseURL`, so a spec navigates with `page.goto('/')` rather
than an address it would have to keep in agreement with the manifests. A
`custom` runner reads it from its own environment.

### `SEAL_CI`

That this run's result is a verdict -- which is what makes the outcome suite
run on its own at the end of it. `seal ci` sets it before starting Tilt;
`seal up` doesn't, because a session somebody is about to work in isn't a
gate and spending a whole suite on every start of one is how a local loop
stops being used.

A plain `tilt up`/`tilt ci`, started without the CLI, leaves it unset and
gets no suite. `--run_outcomes true`/`false` overrides it either way, for a
run that knows better than the command that started it -- a build whose only
job is to publish is not a gate however it was started.

Deliberately not derived from what's being built: a run against a
production-shaped overlay builds images carrying no test suite at all and is
a gate all the same.

### `SEAL_CLI`

How to invoke the `seal` CLI again from inside the Tilt session it
started -- which is what runs the outcome suite. `seal up`/`seal
ci` announce it rather than letting the Tiltfile assume, because
`seal` reaches a project through `uvx`, a checkout's virtualenv or an
installed package, and only the process already running it knows which.

A plain `tilt up`, started without the CLI, falls back to whatever
`seal` is on `PATH`. A pipeline with a wrapper of its own can set this
and keep the say.

---

## Not environment variables

Two things that look like they might be:

- **`--k8s_overlay`, `--build_type`, `--publish_images`, `--run_outcomes`,
  `--allowed_k8s_contexts`** are Tilt config flags, passed after `--`. See
  the [Tilt extension reference](tilt-extensions.md#tilt-config-flags).
- **`provider_token`** is a CI secret, set on a GitHub Environment rather
  than in a shell. It reaches your `provider_setup` script as
  `$SEAL_PROVIDER_TOKEN`. See
  [Continuous integration](../guides/continuous-integration.md#secrets).
