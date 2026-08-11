# Seal

**Sealed expected end-to-end outcomes for autonomous agentic development.**

Seal is a library for developing and testing multi-service
applications on [Tilt](https://tilt.dev) and Kubernetes. It gives a project
one way to bring its services up, one way to resolve their credentials, and
one way to run the tests a merge rests on -- the same way locally as in CI.

The point of that consistency is a merge gate you can leave unattended. A
green run means the environment finished coming up *and* every promise the
project has written a test for still holds; and an outcome test can't be
edited without a human approving the diff. Together those two are what let a
change -- a person's or a coding agent's -- merge on the strength of the
tests rather than on somebody's reading of them.

Seal is a library, not a framework you generate a project from. It
ships two halves you adopt:

- **A Tilt extension** (`ext://seal`) that your project's own
  Tiltfiles load.
- **An `seal` CLI** you run instead of `tilt up`/`tilt ci`.

Your services, your manifests, your registry, and your promises stay yours.
Seal knows nothing about your application: no default port, path,
framework or service name. Where it needs something only your project can
say, your project says it.

## Start here

:::{tip} New to Seal?
[**Installation**](installation.md) gets the tools on your machine, then
[**Quickstart**](quickstart.md) takes the worked example from a clone to a
running stack with its outcome suite green -- about ten minutes, most of it
waiting for images to build.
:::

Once it's running, [**How Seal fits together**](concepts.md) is the
model behind what you just ran, and the deep dives in the sidebar cover one
piece each.

```{toctree}
:maxdepth: 2
:hidden:
:caption: Getting started

installation
quickstart
concepts
```

```{toctree}
:maxdepth: 2
:hidden:
:caption: Deep dives

guides/project-layout
guides/credentials
guides/resetting-state
guides/outcomes
guides/runners
guides/translating-promises
guides/merge-gate
guides/regression-loop
guides/continuous-integration
guides/coding-agents
```

```{toctree}
:maxdepth: 2
:hidden:
:caption: Reference

reference/cli
reference/tilt-extensions
reference/environment-variables
reference/troubleshooting
```
