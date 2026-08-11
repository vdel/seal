# Installation

Seal has two halves, and a project adopts both: an `seal`
command you install on your machine, and a Tilt extension your project's
Tiltfiles load straight from this repository. Only the first one is an
install in the usual sense -- Tilt fetches the second for you.

## Prerequisites

Everything below is what Seal drives rather than what Seal is,
so install them the way you normally would on your platform.

| Tool | Why it's needed |
| --- | --- |
| [Docker](https://docs.docker.com/get-started/get-docker/) | Builds every service's image. |
| [Tilt](https://docs.tilt.dev/install.html) | What `seal up`/`seal ci` actually run. |
| [kubectl](https://kubernetes.io/docs/tasks/tools/) | Talks to the cluster; reset scripts use it too. |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Installs and runs the `seal` CLI. |
| `rsync` | Copies test results out of the running containers. Present on most systems already. |
| Your store's own CLI | Only if a service's `.env` actually references a provider your project declares. Which CLI that is, and where to get it, are the `cli` and `install_hint` fields of your own `seal-credentials-config.json` -- see [Credentials](guides/credentials.md). |

You also need **a local Kubernetes cluster**, with `kubectl`'s current
context pointed at it. Docker Desktop ships one -- enable *Kubernetes* in
its settings and the `docker-desktop` context appears; minikube, k3d, Rancher
Desktop and kind all work the same way. Tilt refuses to deploy to a context
it doesn't recognise as local, so an accidental `kubectl config
use-context` doesn't put your work on a real cluster.

Check what you're pointed at before the first run:

```sh
kubectl config current-context
```

:::{note}
CI is where the cluster is throwaway rather than yours, so it creates one
per run rather than reusing a developer's: the [reusable
workflow](guides/continuous-integration.md) uses
[ctlptl](https://github.com/tilt-dev/ctlptl#readme) +
[kind](https://kind.sigs.k8s.io/). Nothing about a project depends on which
of the two shapes it's running against.
:::

## Installing the `seal` CLI

The repository is public, so `uv` can install the CLI straight from it. The
package lives in the repository's `python/` subdirectory:

```sh
uv tool install "git+https://github.com/vdel/autologate#subdirectory=python"
```

Check it worked:

```sh
seal
```

With no arguments `seal` prints its usage and exits non-zero, which is
enough to tell you it's installed.

:::{note}
The distribution is currently published under the name `my-system-helpers`
while the command it installs is `seal`. That name is what
`uv tool uninstall` and `uv tool upgrade` want.
:::

### Without installing

`uvx` runs the CLI from a temporary environment, which is worth reaching for
in a one-off shell or a CI job that already has `uv`:

```sh
uvx --from "git+https://github.com/vdel/autologate#subdirectory=python" seal up
```

### From a checkout

If you're working inside a clone of Seal itself -- or developing
against a fork -- point `uvx` at the directory instead, so you always run
the code as it is on disk:

```sh
uvx --from ../../python seal up      # from examples/angular-django/
```

Pinning a version works the way it does for any git dependency:

```sh
uv tool install "git+https://github.com/vdel/autologate@v1.2.3#subdirectory=python"
```

## Registering the Tilt extension

The Starlark half isn't installed. Your project's own root `Tiltfile`
registers this repository as a [Tilt extension
repo](https://docs.tilt.dev/extensions.html) once, near the top, and Tilt
fetches it:

```python
v1alpha1.extension_repo(name='seal', url='https://github.com/vdel/autologate')
v1alpha1.extension(name='seal', repo_name='seal', repo_path='tilt/seal')

load('ext://seal', 'seal_service', 'select_k8s_overlay')
```

That is the whole registration. Anything else Seal needs -- the
official `syncback` extension, its own CI-cached build helper -- it reaches
for itself, under names of its own, so the name you pick here is free and
nothing you register can collide with it.

Registration is session-wide: every Tiltfile your root one `include()`s
afterwards, at any nesting depth, can `load('ext://seal', ...)`
directly with no relative-path bookkeeping.

### Developing the extension itself

Point `url` at a `file://` path and Tilt picks up local, uncommitted edits:

```python
v1alpha1.extension_repo(name='seal', url='file:///path/to/seal')
```

The worked example does exactly this, computed from `config.main_dir` rather
than hardcoded, because it lives inside this repository. A project that
forked Seal into its own repository uses its fork's URL instead.

## Installing the agent skills

Optional, and it installs into your repository rather than onto a machine: a
repository built on Seal can carry the instructions a coding agent
reads to use it -- what replaces `tilt up`, what an outcome test is, what
never to edit.

```sh
git clone --depth 1 https://github.com/vdel/autologate /tmp/seal
/tmp/seal/bin/install-seal-skills --target .
```

Commit what that writes and every teammate, and every agent session, gets
them. See [Coding agents](guides/coding-agents.md).

## Next

[Quickstart](quickstart.md) runs the worked example end to end.
