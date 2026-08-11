# docs/

The user documentation. Pages are
[MyST](https://myst-parser.readthedocs.io/) Markdown, the same dialect the
rest of the repository is written in.

It is published twice from the same sources: to GitHub Pages by
`.github/workflows/internal-docs.yml`, which deploys from `main` the very
artifact it built on the pull request, and with
[Read the Docs](https://about.readthedocs.com/) from `.readthedocs.yaml` at
the repository root, which additionally renders the PDF.

This directory is for somebody building a project *on* seal. The
reasoning behind the design -- why outcome tests exist, what the trust
mechanism rests on, what each decision costs -- lives in `/rfcs/`, and is
for somebody changing seal itself.

## Building it locally

```sh
uv run --with-requirements docs/requirements.txt \
  sphinx-build -b html -W docs docs/_build/html
```

Then open `docs/_build/html/index.html`. `-W` turns warnings into errors,
which is what the published build does too (`fail_on_warning` in
`.readthedocs.yaml`): a broken cross-reference is a page that sends a reader
nowhere, which is worse than a page that doesn't build.

`docs/_build/` is generated and git-ignored.

## Layout

| Path | What's in it |
| --- | --- |
| `conf.py` | Sphinx configuration. |
| `requirements.txt` | What the docs build installs. |
| `index.md` | The landing page, and every toctree. |
| `installation.md`, `quickstart.md`, `concepts.md` | Getting started, in reading order. |
| `guides/` | One deep dive per subject: services, credentials, state, outcomes, runners, translation, the merge gate, the regression loop, CI, coding agents. |
| `reference/` | The CLI, the Tilt extensions, environment variables, troubleshooting. |

A new page has to be listed in a toctree in `index.md`, or the build fails
-- an unreachable page is one nobody finds.

## Writing conventions

The same as everywhere else in this repository (see `/CLAUDE.md`): describe
the current design and its rationale, never the journey that got here. No
issue or pull-request references.

Two conventions specific to this directory:

- **Link to repository files by full URL**, not by a relative path out of
  `docs/`. A relative link that works in a checkout 404s on the rendered
  site.
- **Link between pages with relative `.md` paths** (`../guides/outcomes.md`)
  and to sections with MyST anchors (`outcomes.md#the-layout`). Both are
  checked at build time, so a rename that breaks one fails the build rather
  than the reader.
