---
name: seal-machine
description: What has to be true of the machine before a Seal command can run -- the CLI, Tilt, kubectl, rsync, a container runtime whose daemon is actually running, a local cluster the context points at, and reachable image registries -- and how an agent establishes those itself when the machine is a throwaway it owns rather than somebody's workstation. Use at the start of a session that will run seal up, seal ci or an outcome suite, when a command fails with a tool not found, a daemon that is not running, no current context, or an image that will not pull, and when a session in an ephemeral container needs to get to a cluster on its own.
---

# The machine a run needs

Seal is a library that drives other things: Tilt builds and deploys,
Kubernetes runs what it deployed, a container runtime is underneath both.
None of that is Seal, and none of it is checked into a project. So a
command's real prerequisite is often two layers below the message it fails
with -- a missing daemon surfaces as a readiness timeout, which reads like
an application bug.

This is the layer beneath everything the other skills describe. Establish
it first, in order, verifying each step.

## First: whose machine is this?

The answer decides whether you install anything at all, and the two answers
lead to opposite actions.

**Somebody's own workstation.** Report what is missing and let them choose.
A container runtime, a cluster, or a change to which context `kubectl`
points are decisions about a machine that outlives your session and holds
work that is not yours. Name what is missing and stop.

**A throwaway you own** -- an ephemeral container built for this session, a
CI runner, a fresh devcontainer. Nothing on it outlives the session, there
is nobody to interrupt, and there is nothing to damage. Establish what is
missing yourself, then say plainly what you installed and at which
versions.

Signals you are on a throwaway: the working tree was cloned when the
session started; you are the only user and hold full privileges; nothing is
running that you did not start; the environment is documented as rebuilt
per session.

**If you cannot tell, treat it as somebody's.** The cost of asking is a
message. The cost of guessing wrong is somebody else's machine.

## What each command actually needs

Each row is the row above plus more, so establishing them in this order
means the first failure is the real one.

| To run | It needs |
| --- | --- |
| `seal outcomes` | The CLI and a checkout. Nothing else -- listing what a project promises reads the tree. |
| `seal check` | The above, plus `kubectl`: the overlay check builds a project's manifests the way Tilt does, by shelling out to it. |
| `seal outcomes run`, where a group's runner runs on the machine | The CLI, plus whatever that group's own runner needs. A project whose groups all run on the machine needs no cluster to report a verdict. |
| `seal up` | Tilt, a container runtime with a **running** daemon, a local cluster, and `kubectl`'s current context pointed at it. |
| `seal run -- <cmd>` | A session already up: it runs the command against the container that was deployed, not a copy of it. |
| `seal outcomes run`, where a group's runner is a container | A session already up, because that runner is deployed into it. |
| `seal ci` | All of the above, plus `rsync`, which is how results are copied back out of the containers that produced them. Without it a suite runs and reports nothing. |

## Establishing it, in order

Do not move on from a step you have not verified. Each check below is
chosen to fail for the right reason rather than to look reassuring.

**1. The `seal` CLI.** See `seal-install`. `seal` with no
arguments prints usage and exits non-zero, which is enough to say it is
there.

**2. The tools Seal drives.** Tilt, `kubectl`, `rsync`. Each answers
a version query when present. A project also needs its own store's CLI, but
only if one of its `.env` files actually references a scheme that project
declares -- see `seal-doctor` for what that failure looks like.

**3. A container runtime whose daemon is running.** Installed is not
running: an image can ship the client, the daemon and the runtime and start
none of them. Verify by asking the daemon something -- `docker info` or the
equivalent -- and not by asking the binary its version, which answers
without a daemon and tells you nothing.

**4. A local cluster, with the context pointed at it.** Check what you are
pointed at before running anything that deploys:

```sh
kubectl config current-context
```

Tilt refuses to deploy to a context it does not recognise as local. That
refusal is a guard against putting a development session on a real cluster,
so treat it as a correct answer to a wrong context. **Never** force or
relabel a context to get past it. If there is no cluster, create a local
one; on a throwaway, the pair the reusable CI workflow uses is a reasonable
default precisely because it is built to be created and destroyed per run.

**5. A cluster that runs a pod, not one that merely answers.** A node
reports `Ready` once its kubelet registers, which is before anything has
asked it to start a container. So the verification is a pod that reaches
`Running`, and the whole of it fits in one command:

```sh
kubectl run machine-check --image=<a small image> --restart=Never --command -- true
```

Two properties of the host decide whether that pod ever starts, and
neither shows up in a version query:

- **The cgroup version.** A current kubelet refuses outright to run on a
  cgroup v1 host. It says so in its own log, while whatever created the
  cluster reports only that the control plane never came up.
- **What the host lets a container do.** Where the host withholds a
  capability the runtime needs, every sandbox fails and the message names
  a pipe, a shim or a missing PID -- never the capability. What turns
  that into an answer is running the failing container's own spec through
  the runtime directly, then removing one field at a time until it
  starts.

A cluster stuck this way looks alive from every angle except the one that
matters: the context resolves, the node is `Ready`, and every pod sits in
`ContainerCreating`.

**6. Registries you can actually pull from.** On a restricted network this
is the step that looks fine and is not. A registry's API and its blob
storage are usually **different hosts**, and an allowlist covering the
first but not the second fails only once layers start downloading: the
manifest resolves, the pull begins, and it dies partway with a forbidden
URL pointing at a host nobody thought to allow. Verify by pulling a small
image to completion, not by reaching the registry.

Verify it once per puller, though, rather than once per machine. At least
three of them pull, and they share neither a trust store nor a position on
the network: the daemon that builds images, the container runtime inside
the cluster, and each image build, which reaches for a package index of
its own. A network that re-terminates TLS breaks the second and the third
while the first keeps working, and reports it as `x509: certificate signed
by unknown authority` -- naming neither the certificate to trust nor the
client that has to trust it.

## When a step cannot be established

Say which step failed, what it blocks, and stop there. A machine that is
half-ready is worth more than a run that fails three layers up.

If the obstacle is the network, **name the exact host that was refused**,
not "the registry": whoever can change an allowlist needs the hostname, and
the useful one is usually the blob host from the failing URL rather than
the registry you set out to reach.

If the obstacle is a certificate rather than an allowlist, name the client
that rejected it as well as the host. The fix goes into one client's trust
store, and which client it is decides where: a daemon's configuration, a
cluster node's, or a base image the build starts from.

- **Never report a suite as passing that a missing prerequisite kept from
  running.** Nothing ran, so nothing was established; that is the one thing
  a verdict must never say.
- **Never narrow a suite to what the machine happens to support.** The
  whole suite with no arguments is what a merge rests on, and a subset says
  nothing about what it left out.
- **Never work around a missing prerequisite by changing the project.**
  Deleting a service, weakening a probe or skipping a group to get a green
  run on an incomplete machine changes what the project promises in order
  to hide what the machine lacks.

## Nothing you install here survives

A throwaway machine is rebuilt for the next session, so the tools, the
daemon you started and the cluster you created are all gone by then. Two
consequences worth holding on to:

- This is a routine at the start of a session, not a one-off. Check rather
  than assume, every time.
- **Anything that must outlive the session belongs in the repository** --
  committed and pushed. A cluster you brought up to establish something is
  evidence, not a result.
