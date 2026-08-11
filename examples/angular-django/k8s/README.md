# k8s Directory Structure

Two shapes of this application, both deployable on a local or CI Kubernetes
cluster:

- **`dev`** — what `seal up` brings up, and what the local loop runs. The ui
  is a container running Angular's dev server, so an edit is live-reloaded.
- **`non-dev`** — the same application shaped the way a real environment runs
  it: no dev server, the built bundle copied out by an initContainer and
  served by nginx, and the api's environment assembled from two objects
  rather than one — a ConfigMap of settings and a Secret of credentials,
  the split that decides RBAC and what `kubectl describe` prints. Layered
  on `dev` rather than restating it: it holds only what it changes.

`seal ci` verifies the same promises against both, which is the point of
having the second: a container removed, static files served differently and
a pod assembling its environment from a different set of objects are exactly
the kind of difference an outcome test can catch and a dev server can hide.

Neither names a cluster, a registry or a domain, and that is what lets them
both live here. An overlay for a *real deployment* adds those — an
externally provisioned database, an ingress, a resolvable registry path, a
domain — and lives with the deployment that owns it, layered on these the
same way `non-dev` is.

This folder is organized in 3 levels:

1. `env` (environment)
2. `pod` (workload/deployment group)
3. `service` (component manifests)

## 1) Environment (`env`)

Top-level folders are the overlays a run can name with `--k8s_overlay`, each
with its own `kustomization.yaml` entry point — the same entry point any
other environment's overlay would have, wherever it lives. `non-dev/` holds
only what it changes; everything else it takes from `dev/`.

## 2) Pod / Workload (`pod`)

Inside an environment, workloads are grouped by domain (for example
`dev/web/`). These folders define how multiple services are assembled
together.

## 3) Service (`service`)

Inside each workload folder, each service has its own subfolder:

- `api/`
- `ui/`
- `nginx/`

Due to the high variability of deployment between development and
production, the way services are aggregated may vary a lot.

## Image refs

These manifests declare bare, untagged image names (`image: example-api`,
`image: example-ui`) on purpose: they're only ever deployed by Tilt
(`seal up`/`seal ci`), whose own image injection matches a
manifest by that exact build selector, then rewrites it to whatever it just
built — independent of `default_registry()` in the root Tiltfile, which only
changes where Tilt pushes and pulls, not what string it looks for in the
YAML.

An overlay rendered by something other than Tilt — a real deploy, where a
plain `kustomize build` has to resolve a ref that actually exists — needs an
`images:` kustomize transformer renaming those selectors to a resolvable
registry path. Keeping that rename out of these manifests is what lets both
consumers work off the same base.
