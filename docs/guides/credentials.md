# Credentials

How every service gets its secrets and config -- in local development, CI,
staging and production alike -- with one schema, one resolution path and no
per-scope copy to keep in sync.

## The short version

- Each service that needs credentials has a **`services/<name>/.env`**,
  committed to git. Every value is one of three things:
  - a **plain literal**, for config genuinely identical in every scope;
  - a **`<scheme>://<item>`** reference, naming an item in some store;
  - **`k8s://`**, meaning the Kubernetes manifests supply this key directly
    and Seal never touches it.
- **A reference names an item, never a store.** Which vault, project or
  folder holds that item is declared once per project, in
  **`seal-credentials-config.json`** at the project root, with a
  mapping per environment.
- **`.env`'s key names are the schema.** There is no `env.json`. Whether a
  key exists, and for which service, is entirely defined by which `.env`
  files mention it.
- `seal run -- <cmd>` runs one command with a service's `.env`
  resolved into its environment.
- `seal up` resolves *every* service's `.env` and fills the Kubernetes
  objects each overlay says Seal fills, then starts `tilt up`. Use it
  instead of `tilt up`.
- `seal ci` is the same, wrapping `tilt ci`.

A `.env` is safe to commit: it holds a reference to where a secret lives,
never a resolved secret.

## Why one system rather than several

Independent credential paths per scope invite three failure modes, and all
three are expensive to find: dev, CI, staging and production drift apart
with nothing checking they agree; duplicated key definitions go stale
because nothing keeps them in sync; and a secret's *actual* value ends up
somewhere disconnected from the store's own sharing and audit story --
copied into a CI provider's secret store, say, editable by anyone with write
access to the repository's settings.

One `.env` per service, resolved identically everywhere, removes all three
by construction. There's no second list of key names anywhere, in any scope.

## Writing a `.env`

Standard dotenv format -- `KEY=VALUE` lines, `#` comments, blank lines
ignored:

```sh
# services/api/.env
DEBUG=0
DJANGO_SECRET_KEY=pass://django-secret-key/password
DATABASE_URL=k8s://
```

### Plain literals

Only for config that is genuinely identical in every scope. There is no
separate dev-only override file, so a literal here is the value
*everywhere*, production included. Where a key would be dangerous somewhere,
pick the safest value: `DEBUG=0`, never `DEBUG=1`.

### References

Only a project whose `.env` files actually use these needs its provider's
CLI on `PATH`; a project whose values are all literals and `k8s://` markers
reaches no store at all, and declares no provider.

```
DJANGO_SECRET_KEY=pass://django-secret-key/password
```

The scheme (`pass://`) says which of the project's declared providers
resolves this value. Everything after it is the **item**, in whatever shape
that provider wants -- here an item name and a field within it.

:::{important}
A reference names the item and nothing else. It never names the vault, and
it is never a template.
:::

That is what makes the same line valid in every environment. Which vault the
item is read from is the project's declaration, not this value -- see
[Declaring where a store is](#declaring-where-a-store-is) below. A value
containing `${` is rejected by
[`seal check`](../reference/cli.md#seal-check): a value that
expands is a value whose meaning depends on where it is read, which is the
property this format exists to avoid.

There is **no fallback** when an item doesn't exist or you aren't logged in.
Seal fails loudly, on purpose: this same `.env` is what production
resolves too, so a silent insecure fallback here would be a silent insecure
fallback there.

### `k8s://`

```
DATABASE_URL=k8s://
```

This key is supplied directly by the Kubernetes deployment manifests -- a
literal `env:` entry, typically pointing at an in-cluster service like a
bundled dev Postgres. Seal never resolves or injects it, in any scope.
There's nothing to fill in; the marker is there so the `.env` still names
every key the service needs.

## Declaring where a store is

`seal-credentials-config.json`, at the project root beside the
`Tiltfile`. A project whose `.env` files are all literals and `k8s://`
markers needs no such file at all.

```json
{
  "default_env": "dev",
  "provider": [
    {
      "scheme": "pass://",
      "name": "Proton Pass",
      "cli": "pass-cli",
      "install_hint": "https://proton.me/pass/download",
      "form": "run",
      "reference": "pass://{vault}/{item}",
      "command": ["pass-cli", "run", "--env-file", "{env_file}",
                  "--", "{command}"],
      "environments": {
        "dev":  { "vault": "project-seal-dev" },
        "prod": { "vault": "project-seal-prod" }
      }
    }
  ]
}
```

Three fields carry the whole difference between one store and the next:

**`environments`** maps the credentials environment a run selects to whatever
this provider calls a scope. A mapping rather than a template, because a
scope is not always derivable from an environment's name: one store scopes
by a vault named after the environment, another by a UUID that no string
built from the word `prod` will ever produce.

**`reference`** rebuilds the provider-native reference from the item the
`.env` declared plus that scope. It is what lets a store whose scope lives
inside the URI work without the `.env` carrying it. A store that names its
scope on the command line instead leaves this at its default, `{item}`, and
puts the mapping's values in `command`.

**`command`** is the invocation, in the form the store supports. `form` says
which of four that is:

| `form` | How the CLI hands values over |
| --- | --- |
| `run` | Wraps a command, putting the values in its environment. |
| `resolve` | Reads a file of references and writes it back, resolved. |
| `fetch` | Dumps a whole scope; Seal keeps only what was asked for. |
| `get` | One item in, one value out, invoked once per reference. |

All four are implemented. `get` is the one every surveyed product supports,
so a store with no wrapping form at all is still declarable.

Placeholders are a closed set. Seal substitutes names and never
interprets what it substituted.

:::{note}
Because a store is *declared* rather than coded for, adding one is a change
to your project, not to Seal. Nothing in `python/` or `tilt/` names a
product -- a test greps the deliverable to keep it that way.
:::

### Which environment a run reads

In order: the `--credentials_env` flag, then the
`SEAL_CREDENTIALS_ENV` environment variable, then the config's
`default_env`.

```sh
seal up --credentials_env prod
```

:::{important}
This is independent of `--k8s_overlay`.
:::

Which store the values come from and which manifests they land in are
separate choices, and a run states each. Neither flag implies the other.

The flag is read from Seal's own arguments, before any `--`, so it
never reaches Tilt or a wrapped command.

## The objects a service's values land in

Seal fills objects your overlay already declares, rather than
inventing one. Mark an object with the service whose `.env` fills it:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: example-api-secrets
  annotations:
    seal-test.dev/fill-from: api
type: Opaque
```

That object claims every key `services/api/.env` declares which no other
object claims -- so adding a secret stays one line in the `.env`.

To split a service across several objects, name keys on one of them:

```yaml
metadata:
  name: example-api-config
  annotations:
    seal-test.dev/fill-from: api
    seal-test.dev/keys: DEBUG
```

It then claims exactly those, and the object naming no keys takes the rest.
Splitting is opt-in, and only a split object names its keys.

Both kinds work: a `Secret`'s values are base64-encoded, a `ConfigMap`'s are
plain. Which an object is decides RBAC and what `kubectl describe` prints,
so it is your manifest's call, not Seal's.

Values arrive as a **strategic-merge patch**, so exactly one object reaches
the cluster -- yours, with its own name, labels and annotations intact and
only `data` supplied. A project that would rather run its own operator in
the session cluster marks no objects at all: Seal then fills nothing,
and the overlay deploys exactly as written.

`seal check` reports any container whose sources supply nothing for a
key its service declares, in *every* overlay -- so a service wired into one
overlay and forgotten in another fails before it deploys. An overlay that
splits a service across objects has to repoint every container that reads
it, not just one.

## `seal run -- <cmd>`

Run from inside `services/<name>/` (or a subdirectory of it), to work on a
service outside the cluster:

```sh
cd services/api
uv sync --group dev
seal run -- uv run python src/manage.py migrate
seal run -- uv run pytest tests/
```

What it does:

1. Finds the project root -- searching upward for a directory with both a
   `Tiltfile` and a `services/` subdirectory.
2. Works out which service you're in from your current directory.
3. Reads that service's `.env` and drops any `k8s://` keys.
4. Resolves what's left: a literal as itself; a reference through whichever
   provider declares its scheme, against the store that provider's
   `environments` map names for this run. A purely literal/`k8s://` `.env`
   reaches no provider, and needs no CLI installed at all.
5. Runs your command with the result.

An already-set environment variable wins over `.env` for values injected
directly.

## `seal up` and `seal ci`

```sh
seal up                          # from the project root
seal ci -- --build_type test     # what CI runs
```

Conceptually `seal run -- tilt up`, except there's no `.env` at the
project root. Instead, before starting Tilt, it resolves each service's
`.env` once and fills every overlay's annotated objects with the result,
writing the patches under `.workspace/seal-env/<overlay>/`.

Every overlay, not just the one this run deploys: which overlay Tilt selects
is computed in the Tiltfile from `--k8s_overlay` and the project's own
`default_overlay`, so the values are put beside each one and the Tiltfile
reads whichever it picked. It's cheap -- only an overlay carrying
annotations has anything filled, and each service resolves once however many
overlays name it.

Then it execs `tilt up` (or `tilt ci`), forwarding every argument you passed
through unchanged.

:::{warning}
A plain `tilt up`, without ever having run `seal up`, does **not**
refuse. It deploys the annotated objects empty, so containers start without
their credentials and the failure surfaces as a readiness timeout or an
application error, well away from the cause. **If you edit a `.env`, re-run
`seal up`** -- `Ctrl-C` the running session first.
:::

`seal ci` differs from `seal up` in two ways: which `tilt`
subcommand it runs, and that it runs
[`seal check`](../reference/cli.md#seal-check) first -- a
manifest that cannot report readiness honestly, a `.env` that disagrees with
the declaration, or a key no container sources each make the whole run's
result untrustworthy, and all of them cost a directory walk to find out.
Both take `--credentials_env`.

## CI, staging and production

CI resolves credentials the same way local development does -- `seal
ci` calls the same code `seal up` does. Only two pieces are
CI-specific, and neither names your store:

**Installing and authenticating the provider's CLI**, once per job, before
`seal ci` runs. The reusable workflow takes a `provider_setup` script
for this, and one `provider_token` secret that reaches it as
`$SEAL_PROVIDER_TOKEN`. What that token opens, and which store, is
your project's business:

```yaml
provider_setup: |
  curl -fsSL https://example.invalid/install.sh | bash
  echo "$SEAL_PROVIDER_TOKEN" | its-cli login
secrets:
  provider_token: ${{ secrets.WHATEVER_IT_CALLS_ITS_TOKEN }}
```

Set the secret on the **GitHub Environment** the job binds to (**Settings →
Environments → `<name>` → Secrets**), not as a repository secret -- one per
environment, each scoped to only what that environment should read.

:::{warning}
The passthrough matters as much as the value. A reusable-workflow job
resolves an Environment-scoped secret only if the caller names it in its own
`secrets:` block -- omit it and the value silently arrives empty even with
the secret correctly set.
:::

Promoting to production still requires clearing GitHub's own Environment
protection rules -- required reviewers and the rest -- before that
environment's token, and therefore its secrets, is reachable at all.

**Setting `credentials_env`**, which selects the environment whose stores
this run reads. Seal's reusable workflow leaves it at the project's
own default, since nothing it runs reaches a real environment. A deploy
pipeline sets it to that environment's own name. Which Kubernetes overlay
gets deployed is a separate input, set independently.

:::{note}
A CI provider's own secret store is **not** part of app credential
resolution. The one thing it holds is infrastructure-level rather than app
config: the provider token above.
:::

Because the reusable workflow resolves each service's own `.env` directly,
it never needs to know your application's variable names -- so your CI file
never enumerates them. See
[Continuous integration](continuous-integration.md).

## Deploying to a real environment

`seal up`/`seal ci` produce real, plaintext values and hand them
to Tilt to apply live. That's fine for local development and for CI, which
only ever run against a throwaway cluster. A real staging or production
deploy never goes through `seal ci` or Tilt at all, and never has a
plaintext `Secret` applied to it from outside the cluster.

That's a deployment concern rather than Seal's. What matters here is
only that the resolution is the *same* resolution: a service's credentials
in a real environment are whatever its own `.env` says they are, resolved
against that environment's own store. The standard destination is a [Sealed
Secret](https://github.com/bitnami-labs/sealed-secrets) -- a `Secret`
encrypted against an in-cluster controller's public cert, committed to git
like any other manifest and reviewed through a normal pull request.

An environment that provisions its secrets some other way -- an
ExternalSecret, a CSI-driver target, an operator -- simply doesn't annotate
those objects in its own overlay. Seal fills nothing there, and the
consuming Deployment doesn't change at all.

## Adding a new secret

1. Add `KEY=` to the relevant `services/<name>/.env`, as a reference or a
   safe-by-default plain literal. Never a real secret value as a literal.
2. If it's a reference, create the matching item in the store each
   environment's mapping names.

`seal up`, `seal run` and `seal ci` all pick it up
immediately. The object annotated for that service claims it without being
touched, and there is nothing else to keep in sync.

## Using a different store

Declare it. Add a provider to `seal-credentials-config.json` with the
scheme your `.env` files will use, the CLI, the `form` its CLI supports, the
`command` that invokes it, and an `environments` mapping.

There is no list inside Seal to add it to, and no code to change. If
its CLI can do any one of `run`, `resolve`, `fetch` or `get`, it is
declarable -- and `get` is the form every surveyed product supports.

`seal check` validates the declaration, and `seal ci` runs it
before anything expensive: a value naming a
scheme no provider declares, a provider some `.env` reaches with no mapping
for the selected environment, and a template naming a placeholder Seal
cannot supply are each reported by name.
