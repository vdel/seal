# RFC 0006: Credentials: one schema, many stores

| | |
| --- | --- |
| **Status** | Accepted |
| **Related** | [0001](0001-library-boundary.md), [0002](0002-declaration-by-structure.md), [0007](0007-credential-delivery.md), [0008](0008-run-axes.md) |
| **How-to** | [Credentials](../docs/guides/credentials.md) |

## Context

Every service needs secrets and config, in local development, CI, staging and
production alike. A `.env` file names what a service needs. Two further facts
have to be stated somewhere before that name becomes an environment variable
inside a running container: **which store holds the value**, and **which
Kubernetes object carries it into the pod**.

Both are deployment facts, and both are easy for a library to answer on a
project's behalf -- badly. This RFC covers the first; [RFC
0007](0007-credential-delivery.md) covers the second. They are the same
argument twice: `.env` declares, the project declares the rest, and Seal
reads both rather than deciding either.

The alternative shape -- a separate credential path per scope -- invites
specific failures: drift between what dev, CI, staging and production
actually read; no automated check keeping duplicated definitions in sync; and
an ownership gap wherever a secret's *actual* value can live somewhere
disconnected from the store's own sharing and audit story, such as copied
into a CI provider's secret store, editable by anyone with repository write
access.

## Decision

**One resolution path, in every scope.** `services/<name>/.env` is the
schema, and the same file resolves the same way locally, in CI, and for a
real environment.

- **`.env`'s key names are the schema.** There is no second list of key names
  anywhere.
- Each value is a plain literal, a `<scheme>://<item>` reference, or
  `k8s://`, meaning the manifests supply this key directly.
- **A reference names an item, never a store.** Which vault, project or
  folder holds it is declared once per project, in
  `seal-credentials-config.json`, with a mapping per environment.
- **A value is never a template.** `${` in one is refused.
- **A run selects one credentials environment**, on an axis of its own
  ([RFC 0008](0008-run-axes.md)), and that is the whole of what decides which
  store a reference is read from.
- **A provider is a CLI and a declaration**, in one of four forms. Nothing in
  the deliverable names a product.

## Rationale

### Which item is the application's fact; which store is not

Welding both into one reference -- a vault name and an item path in the same
string -- forces a per-environment deployment fact into a per-service
application file, and a substitution placeholder is the mechanism that
smuggles it there.

Splitting them is what makes the same committed line valid in every
environment. "This service needs a Django secret key" is the same sentence in
dev and in production; which vault holds it is not, and differs on an axis
the application knows nothing about.

The split also removes a rule a library cannot check. When a store's access
control scopes by vault, "put the environment in the vault name, never in the
item name" is a real constraint -- and one where a project that gets it wrong
gets a `.env` that resolves fine and a token scope that enforces nothing.
Moving the scope into a declaration Seal reads makes the constraint
structural instead of advisory.

### What a provider actually is

Seven products, and no two agree on how a value comes out:

| Product | Shape |
| --- | --- |
| Proton Pass (`pass-cli`) | wraps a command: `pass-cli run --env-file F -- CMD` |
| Bitwarden Secrets Manager (`bws`) | wraps a command: `bws run --project_id UUID -- CMD` |
| Infisical | wraps a command, and separately dumps a scope |
| Bitwarden Password Manager (`bw`) | one item at a time: `bw get password NAME` |
| GCP Secret Manager | one item at a time: `gcloud secrets versions access latest --secret=NAME` |
| AWS Secrets Manager | one item at a time: `aws secretsmanager get-secret-value --secret-id ID` |
| Azure Key Vault | one item at a time: `az keyvault secret show --vault-name V --name N` |

A "wrap my command and put the values in its environment" contract fits three
of the seven. The other four have no wrapping form at all. **One item in, one
value on stdout is the majority shape, not an edge case**, and a contract
that cannot express it is not a provider interface -- it is one product's
calling convention with a list attached.

They also disagree about *where* the store is named:

| Product | The store is | Named |
| --- | --- | --- |
| Proton Pass | a vault | inside the reference |
| Bitwarden SM | a project | as a flag, by **UUID** |
| Infisical | an environment slug plus a folder path | as flags |
| Bitwarden PM | the unlocked vault | implicitly, in the session |
| GCP | a GCP project | as a flag |
| AWS | an account and region | ambiently, from the caller's profile |
| Azure | a vault | as a flag |

This is the finding that shapes the design. A template like
`vault = "project-{env}"` handles two of them and fails on a store whose
scope is a UUID that no string built from the word `prod` will ever produce.
So what a project declares holds a **mapping** from an environment to that
provider's own idea of a scope, not a substitution rule.

### Three fields carry the whole difference between stores

- **`environments`** maps the credentials environment a run selects to
  whatever this provider calls a scope. Its keys become placeholders.
- **`reference`** rebuilds the provider-native reference from the item the
  `.env` declared plus that scope -- what lets a store whose scope lives
  inside the URI work without the `.env` carrying it. A store naming its scope
  on the command line leaves this at `{item}` and puts the mapping's values in
  `command`.
- **`command`** is the invocation, in the form the CLI supports.

Placeholders are a closed set. Seal substitutes names and never reads
what it substituted: there is no expansion engine and no reading of arbitrary
variables, because a template is a list of argv words with named holes, which
is all any surveyed product needs.

### Four forms, because four exist

| `form` | Contract |
| --- | --- |
| `run` | Wrap a command; values arrive in its environment. |
| `resolve` | Read a dotenv file of references, write resolved dotenv to stdout. |
| `fetch` | Given a scope, write a dotenv table to stdout; Seal keeps the keys the `.env` declared. |
| `get` | Given one item, write one value to stdout. Invoked once per reference. |

`get` is the slow one and the important one. It is the lowest common
denominator, and the only form four of the seven products support. It is also
what lets a project declare a homegrown script, or anything else with a CLI,
without Seal growing a line of code -- which is what makes "a provider
is at best a plugin" true rather than aspirational.

`fetch` returns a whole scope, so Seal matches the returned keys
against what the `.env` declared and ignores the rest. The `.env` stays
authoritative about what a service gets; a provider is fulfilment, not the
list.

### Resolution returns values

One function, both sinks: `seal run` execs a command with the result
merged into the environment, and `seal up`/`seal ci` fill the
Kubernetes objects from the same result ([RFC 0007](0007-credential-delivery.md)).

Three of the four forms hand values back on stdout, so this is the natural
shape rather than a clever one. Only `run` cannot, and for it Seal
supplies its own terminal command which writes the resolved values back to
the parent.

Because each key names exactly one provider through its scheme, merging
results is unambiguous and ordering has nothing to decide. Chaining one
manager's process inside another's -- so each passes the others' values
through untouched -- exists only in a design where resolution happens inside
a child process, and it buys nothing once resolution returns values.

### An item path is opaque, but a field within it is not

Most of these products store a record with several fields rather than a bare
string. So a reference names an item and optionally a field within it, and
the provider's `reference` template places each. External Secrets Operator
draws the same line, as `remoteRef.key` and `remoteRef.property`.

The item is written out rather than derived from the key it fills. Deriving
it is tempting, and Azure Key Vault settles it: its secret names permit only
alphanumerics and hyphens, so no underscored environment variable can name an
Azure secret at all. A convention that cannot express one provider's
namespace is worse than a path that says what it means.

### No fallback, in any scope

There is no safe fallback if an item doesn't exist or nobody is logged in.
Seal fails loudly, with the provider's own install hint, because this
same `.env` is what staging and production resolve: a silent insecure
fallback here would be a silent insecure fallback there.

A plain literal is for config genuinely identical in every scope, and it
should be the *safest* value where a key would otherwise be dangerous
somewhere -- there is no separate dev-only override file, so a literal is the
value everywhere, production included.

That is also why there is **no dev-only provider-optional mode**. A fresh
clone comes up with nothing installed because a `.env` of literals and
`k8s://` markers invokes no provider at all -- Seal reaches for one only
when a value names one. Most values that tempt a fallback are not secrets in
dev and belong in the file as literals; the rest genuinely require
credentials, and a fallback would exist to make that failure quiet.

### Which environment a run reads, and why it is named for Seal

In order: the flag, then `SEAL_CREDENTIALS_ENV`, then the project's own
`default_env`. Seal owns no default -- the project names its own, the
same move it makes for the overlay axis, so a bare run works because the
project said what a bare run means and Seal never learns that `dev` is
a word.

It is **independent of which overlay a run deploys**. The two coincide for a
real deployment and diverge everywhere else; verifying a production-shaped
overlay on a throwaway cluster is exactly the case the axes exist to serve,
and if the overlay chose the store, that run would either fail or reach
production secrets ([RFC 0008](0008-run-axes.md)). The unsafe direction must
not be the implicit one.

A one-word name like `ENV` claimed out of a developer's shell collides with
whatever else set it, and a collision here resolves silently towards the
wrong store.

### What CI has to supply

A provider's CLI is authenticated before Seal invokes it -- true of
every product surveyed, and what keeps credentials out of the declaration.
That is also a requirement somebody has to meet, and in CI that somebody is
the pipeline.

If the CI action installed and logged into one product, adding a
provider would be a change to Seal rather than a line in a project's
declaration -- the exact thing this design exists to stop. So the action
holds its caller to a contract instead: **by the time it runs `seal
ci`, every CLI the project's declarations name is on `PATH` and
authenticated.** It takes a shell input that runs before the gate, and one
token input that reaches it, and never names a store.

The token is passed by value rather than by name. An action runs inside the
calling job, so that job binds `environment:` and every `secrets.X` it reads
resolves there -- which is what makes one environment's run reach one
environment's store. A reusable workflow cannot be called from a job that
binds an Environment at all, and a per-environment credential could then only
be reached by handing the callee a secret's *name* to look up.

Deliberately shell rather than an action to `uses:`. A local action
reference resolves against the *caller's* checkout even from inside an
action, so it would work for a caller inside this repository and break every
caller outside it -- a difference no test here could catch.

Empty by default, and correct empty: a project whose `.env` files hold only
literals and `k8s://` markers reaches no provider and should not have to say
so.

A CI provider's own secret store is not part of app credential resolution. It
holds one infrastructure-level thing: a token for that setup step to
authenticate with.

### What `seal check` holds, and what it deliberately doesn't

Three rules about where values come from: every scheme a `.env` references is
declared by some provider; every declared provider a `.env` actually
references has a mapping for the environment the run selected; and no value
contains `${`.

Deliberately not a rule: resolving every reference to prove it exists.
`seal check` runs before credentials are established and would need
production access to check production, which is a worse trade than the failure
it prevents. Seal can check that a name is accounted for; never that a
store holds a value for it.

## Consequences

- **Adding a secret is a line in `.env` and an item in the store.** Nothing
  else to keep in sync, in any scope.
- **Adding a store is a declaration, not a change to Seal.** A store is
  declarable if its CLI supports any one of the four forms plus some form of
  non-interactive login.
- **A literal is a production value.** Which is a real constraint on what may
  be written as one, and the reason the rule is "pick the safest value".
- **`get` costs a round trip per key.** A service with twenty references
  feels it.
- **A real deployment does not go through this path at all.** `seal
  up`/`ci` produce plaintext values for a throwaway cluster; a real
  environment gets its values some other way, resolved from the same `.env`
  by whatever deploys there ([RFC 0007](0007-credential-delivery.md)).

## Alternatives considered

**A plugin system** -- entry points, dynamically imported provider packages.
Loading third-party code into the process that holds every one of a project's
secrets buys nothing the four forms cannot express.

**Being a secret store.** Seal reads. It never creates, writes or
rotates an item, and never provisions a vault.

**Per-developer overrides.** Personal-versus-shared secrets and machine
accounts are store features and need nothing from Seal.

**Per-service credentials environments.** One run selects one. A project
needing two stores for two services declares two providers.

**A vendor list inside Seal.** The honest version of that is a list
that is always one product short, and a project whose store is the missing
one has to change the library.

## Open questions

- **Whether `get` should run concurrently.** One invocation per reference is a
  serial round trip per key. Parallelism is easy and interleaves the failure
  output of many processes, which is the part that needs designing.
- **Where a provider's own environment variables are declared.** Several CLIs
  read a token from the environment, and one needs a command run first to
  obtain a session. Today whatever invokes Seal exports them, which is
  honest and gives a project one more thing to wire. A `pre` command in the
  declaration would cover it, and would also be a second place credentials
  come from.
- **The deployment toolkit reads these files too.** It builds a real
  environment's secrets from the same `.env`, so it needs the same
  declarations and the same resolution. Either it depends on Seal for
  that, or the two grow separate readers of one format -- the first is right
  and the second is what happens by default.
