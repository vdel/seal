# seal (Python helpers)

The Python half of the `seal` package (see the root
[`README.md`](../README.md) for the full picture and the `tilt/` Starlark
half). A standard "src layout" package (see `pyproject.toml`): the
installable package is named `seal`, so its modules import as
`from seal.credentials import ...`, etc.

Exposes one console script:

- `seal` — `seal run -- <cmd>` / `seal up` / `seal ci` / `seal check` /
  `seal outcomes` / `seal outcomes run` / `seal outcomes translate` /
  `seal outcomes review`:
  resolves a
  service's `.env` (see `../rfcs/0006-credential-resolution.md` at the repo
  root)
  before starting `tilt up`/`tilt ci`; `up`/`ci` additionally generate every
  service's Kubernetes `Secret` first, discovering the project's services by
  running `tilt alpha tiltfile-result` against its root Tiltfile (see
  `../rfcs/0002-declaration-by-structure.md`) -- there's no separate
  services list to
  parse. `seal ci` additionally runs `seal check` first, which is why a
  project gets the readiness guarantee described in
  `../rfcs/0003-readiness.md` without opting in. `seal outcomes` lists what
  a project promises and which of those promises have a test yet; `seal
  outcomes run` reports the whole outcome suite -- every translated promise
  at once, since a fix scoped to one test can break another nobody re-ran --
  and exits on the suite's own verdict (see `../rfcs/0010-outcome-tree.md`).
  `seal outcomes run <slug>...` runs just those outcomes against a session
  already up and reports only them, which is a local loop rather than
  anything a merge rests on; `--all` runs the whole tree against that same
  session, `--reset` puts every service that declares one back to its
  baseline first, and `--confirm` re-runs each failure on its own to say
  whether it reproduces (see `../rfcs/0013-regression-loop.md`).
  `seal outcomes translate` hands whoever is
  writing a test everything needed to compile one promise into one, and
  `seal outcomes review` puts that promise beside the result for the code
  owner who has to approve it (see `../rfcs/0012-translation-and-review.md`).
  `seal outcomes touched` names every path under the tree a change reaches,
  which is the part of "fix the application, never the test" a checkout can
  answer for itself.
  Implementation in `credentials.py` (credential resolution),
  `tilt_discovery.py` (service discovery), `checks.py` (static manifest
  checks), `outcomes.py` (the outcome tree), `runners.py` (what runs each
  group of outcomes), `outcome_suite.py` (the suite's verdict),
  `outcome_history.py` (what each run found, kept across runs),
  `outcome_changes.py` (what a change reaches in the tree),
  `translation.py` (the brief and the review), and `seal.py` (the CLI).

Install with `uv sync`, or run it straight from a checkout with
`uvx --from <path-to-this-directory> seal ...` (see the root
`README.md` and `Makefile` for examples).

## Tests

```sh
uv sync --group dev
make test
```

`tests/` exercises `seal` itself -- both halves of it, including the
Starlark in `../tilt/`, which `test_seal_tilt_resources.py` checks by
evaluating a Tiltfile through a real `tilt alpha tiltfile-result` rather
than restating its behaviour in Python. Everything here is a library other
projects adopt (see the root `README.md`), so a test asserts against a
fixture project it builds in `tmp_path` -- what it checks then stays true
for any project, not just for however the bundled example happens to be
laid out. Tests needing a tool that isn't installed (`tilt`, Docker) skip
rather than fail.

The one exception is `seal run`'s isolation guarantee: that a
developer can work on a service outside the cluster (see
`examples/angular-django/services/api/README.md`'s "Running in isolation"
section and `/rfcs/0006-credential-resolution.md` at the repo root) is only
really
proven by running a real Django management command through it, which needs a
real service to run. That test uses `examples/angular-django`, needs Docker
(to stand up a throwaway Postgres), and is skipped if it isn't available.
