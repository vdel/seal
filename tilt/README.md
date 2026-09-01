# seal Tilt extensions

Starlark helpers packaged as [Tilt
extensions](https://docs.tilt.dev/extensions.html), following the same
one-directory-per-extension layout as the official
[tilt-extensions](https://github.com/tilt-dev/tilt-extensions) repo: each
subdirectory here is a self-contained extension with its own `Tiltfile` and
`README.md`.

| Extension | What it does |
| --- | --- |
| [`seal`](seal/README.md) | The one a project registers. Generic project config (`k8s_overlay`/`build_type`/`publish_images` flags, `PROJECT_ROOT`), test-result syncback/verdict reporting for CI, `seal_service()` (wires a service's own build/test-syncback/reset into one call), and `select_k8s_overlay()`, which deploys one of a project's `<k8s_dir>/` kustomize overlays. |
| [`docker_build`](docker_build/README.md) | `cached_docker_build()`, builds via a GitHub-Actions-cached buildx build. Reached by `seal_service()` itself, from the sibling directory, so a project never names it. |

It shares its name with the Python `seal` package (`/python/`) on
purpose: `seal up`/`seal ci` generate each service's dev
Kubernetes Secret (see `/rfcs/0006-credential-resolution.md`), discovering the
project's services by asking Tilt itself to evaluate its root Tiltfile (see
`/rfcs/0002-declaration-by-structure.md`) -- a project's entry Tiltfile is a real,
checked-in file (see `examples/angular-django/Tiltfile`) that `include()`s
each one directly.

`seal`'s `seal_service()` builds through `docker_build`'s
`cached_docker_build()` only when it's actually wanted -- `use_cache=True`
(the default) and `SEAL_BUILDX_CACHE=1`, set only by the reusable CI
workflows, never by local `tilt up` (see `seal/README.md`'s
`build.Tiltfile` section). It `load()`s the file by relative path within this
directory rather than through an `ext://` name, so the CI build path costs a
project nothing: registering `seal` is the whole of it.

## Using these extensions in a project

Register this repo as an extension repo once, near the top of your project's
own root `Tiltfile` (before any `include()`/`load('ext://...')` that needs
it), then load whichever helpers you need -- see
`examples/angular-django/Tiltfile` for a full worked example, including
`select_k8s_overlay()` (see `seal/README.md`), which deploys a project's
Kubernetes overlay:

```python
v1alpha1.extension_repo(name='seal', url='https://github.com/vdel/seal')
v1alpha1.extension(name='seal', repo_name='seal', repo_path='tilt/seal')

load('ext://seal', 'k8s_overlay')
```

The name is yours to pick, `default` included: `seal` reaches
tilt-dev/tilt-extensions through a private alias of its own
(`__seal_default_ext_repo`, registered in `seal/config.Tiltfile`)
rather than through Tilt's built-in `default` repo, so nothing it loads
depends on what a project called anything.

Registration is a one-time, session-wide call -- every Tiltfile the root
`Tiltfile` `include()`s afterwards (at any nesting depth) can
`load('ext://seal', ...)` directly, regardless of how deep it lives.

If you're developing these extensions themselves (e.g. from a checkout of
this repo, as `examples/angular-django` does), point `url` at a `file://`
path instead so Tilt picks up local, uncommitted edits:

```python
v1alpha1.extension_repo(name='seal', url='file:///path/to/seal')
```

`examples/angular-django/Tiltfile` does exactly this, computed from
`config.main_dir` instead of hardcoded, since it's this repo's own example
project -- a project that instead forked this template into its own,
unrelated repo would use its fork's URL (or the published one above)
verbatim.
