# Outcome-test runners

What actually runs an outcome test, how you say which promises run under
which runner, what Seal's own runner gives you, and how to bring your
own.

Read [Outcome tests](outcomes.md) first for the tree these run against.

## What a runner is

An image built from the outcome tree, run as a container against the
environment `seal ci` (or `seal up`) has brought up, and told
which outcomes to run.

A container rather than a script on somebody's machine, because of where an
outcome test has to run: it drives several services at once, so it has to
reach them, and from inside the cluster it reaches each by name the same way
the services reach each other. The alternative is a port-forward, which
exists only while a Tilt session is up and is a different thing to arrange
in CI, locally, and inside a regression loop.

## Groups: one runner, the promises it runs

A project's promises aren't all of one kind, and neither are the things that
test them. A promise about what somebody *sees* is only really tested
through a browser; a promise an API-only service makes is tested by talking
to the API.

So outcomes are **grouped**, one group per runner, and a group is the
directory above an epic:

```
outcomes/
  seal-test-config.json    # what runs each group
  ui/                      # a group
    helpers/               # what this group's tests share
    todo-list/             # an epic
      an-item-survives-a-reload/
        prompt.md
        an-item-survives-a-reload.spec.ts
  api/                     # another group, another runner
    Dockerfile
    billing/
      an-invoice-is-issued-once/
        prompt.md
        check.py
```

**One runner per group, not one per outcome.** A run is one container per
group either way, and it's told which outcomes to run -- so the image is
built once and the browser installed in it once, however many promises the
group holds. That's what makes running a single outcome while you work on it
cheap enough to actually do.

**Groups run one after another,** for the same reason outcomes inside one
do: they drive the same application.

## `seal-test-config.json`

At the outcome tree's root. Two fields: `runner`, with an entry per group,
and `loop`, where the regression loop stops.

```json
{
  "runner": [
    { "name": "ui", "runner_type": "playwright" },
    {
      "name": "api",
      "runner_type": "custom",
      "dockerfile": "api/Dockerfile",
      "runner_args": ["--strict"]
    }
  ]
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | The group directory this runner drives, relative to the outcome tree. A slug, like an epic or an outcome. |
| `runner_type` | yes | `playwright` or `tap` for the runners Seal supplies, `custom` for a `Dockerfile` you bring. |
| `dockerfile` | `custom` only | What to build, relative to the outcome tree. Defaults to `<name>/Dockerfile`. |
| `dockerfile_context` | `custom` only | What to build it from, relative to the outcome tree. Defaults to the group's own directory, which is what puts that group's epics in the build context. |
| `runner_args` | no | What this runner needs said to it, ahead of the outcomes it's told to run. |

Neither build path may reach outside the tree: an image built from a
checkout's surroundings is one whose contents depend on where it was built.

This file is the one thing about an outcome tree a walk can't answer --
nothing about a directory of promises says what starts them. It's therefore
also the one place the tree and a declaration can drift apart, so `seal
check` refuses a group directory no runner names, and a runner naming a
directory that isn't there.

Which outcomes exist is still the tree's own business: one added later is
covered by having been added.

### `loop`: where a regression loop stops

Optional, and one object for the project however many runners it has:

```json
{
  "runner": [ { "name": "ui", "runner_type": "playwright" } ],
  "loop": { "max_iterations": 10, "max_minutes": 180 }
}
```

| Field | Default | Meaning |
| --- | --- | --- |
| `max_iterations` | 10 | Rounds of the whole suite, since the last one in which every promise held. |
| `max_minutes` | 180 | Minutes the loop has spent iterating -- its first round to its last, not the time since it started. |

Both are whole numbers above zero, and both are **backstops rather than
measurements**. Nothing has measured your loop, and the defaults are chosen
to sit past one that's converging by a wide enough margin that a project
which has never thought about them isn't fighting them. Once you've measured
your own, this is the one place to say so.

Reaching one changes no verdict and refuses nothing -- it's a reason to stop
attached to a report. See [Getting a red outcome suite back to
green](regression-loop.md#where-to-stop).

## How a run is started

The runner is started with its own arguments, then `--`, then one outcome
per argument:

```
<runner_args...> -- <epic>/<outcome> <epic>/<outcome> ...
```

Two things follow from that.

**Outcomes are named from inside the group.** A runner is built from one
group and never has to know the others exist, so it's told
`todo-list/an-item-survives-a-reload`, not
`ui/todo-list/an-item-survives-a-reload`. Seal adds the group back on the
way out, when results come home.

**Seal always names them explicitly.** It knows which outcomes have been
translated and your runner doesn't, so a runner that resolved "everything in
the group" for itself would start promises nobody has written a test for and
report them failed.

The separator is there so a runner that takes no arguments still reads its
outcomes from one fixed place, and one that does never has to tell a flag
from a slug.

:::{warning}
A `custom` runner must declare an **`ENTRYPOINT`**. Kubernetes `args`
replace an image's `CMD` rather than adding to it, so a runner whose work is
in a `CMD` would be started without it.
:::

## The contract a container runner meets

Five things, for a runner deployed as a container -- `playwright`, and a
`custom` one of your own. Seal's own does all of them for you; a
`Dockerfile` of your own implements them.

A [`tap`](#the-tap-runner-promises-about-the-machine) group is not deployed
and meets none of this: it prints a stream and Seal does the rest. Its
contract is in its own section below.

1. **Run the outcomes named in the arguments after `--`.** A runner you
   start by hand with none should run everything it finds.
2. **Write each one's verdict to
   `/outcome-results/<epic>/<outcome>/passed`** -- `1` if the promise held,
   `0` if it didn't. Anything else in that file, or no file at all, is a
   *failure* rather than a pass: a test that didn't run is exactly what a
   green suite must not be able to claim on a promise's behalf.
3. **Leave everything else worth keeping beside it** -- logs, reports,
   screenshots. The whole of `/outcome-results/` comes back to your project
   as `tests-results/outcomes/<group>/`, so an outcome's own directory
   arrives as `tests-results/outcomes/<group>/<epic>/<outcome>/`, which is
   where a failing outcome's report points somebody.
4. **Write `/outcome-results/done` when the whole run has finished** --
   anything at all; it's the file existing that says so. One container
   answers for several promises, so "the run finished" has to be
   distinguishable from "it died after the third of twenty", and no count of
   verdicts can tell you which. It's also what Seal's readiness probe
   watches.
5. **Stay up afterwards.** Results are copied out of the *running*
   container, so one that exits takes them with it -- and the Deployment
   behind it would then start the run over. Sleep at the end.

:::{danger}
**Failing by exiting is the one thing a runner must not do.** A container
that exits non-zero takes its own resource down with it and stops the run
before the outcomes behind it have said anything -- which is the suite
reporting one test instead of every promise, the exact failure the whole
suite exists to prevent. Catch each failure, write `0`, carry on to the next
outcome, and stay up.
:::

Printing each log to stdout *as well as* to a file is worth doing: it's what
makes `tilt` and `kubectl logs` show why a promise wasn't kept, without
anybody fetching an artifact first.

## What Seal passes in

A container runner gets:

- **`SEAL_BASE_URL`** -- where the application answers, as your project
  declared it in `register_outcome_runner(base_url=...)`. Seal knows nothing
  about your service names or ports, so this is the one address a runner
  should need.
- **The arguments described above** -- this runner's own, then `--`, then
  the outcomes this run covers, in the group's own order.
- **A `readinessProbe`** on the container, checking for
  `/outcome-results/done`. Seal writes it, so "Ready" means "this run has
  finished". Nothing is asked of your `Dockerfile` here.
- **The environment the pod carries.** Nothing else is injected -- an
  outcome test drives the application from outside, the way a person does,
  so it shouldn't need the application's own credentials.

Outcomes have to run **one at a time**, and with one container per group
that's the runner's job. Each outcome therefore starts from whatever the one
before it left, so write tests that own the data they assert on.

## The `playwright` runner

Write spec files; Seal supplies the rest:

```
outcomes/
  seal-test-config.json    # { "runner": [ { "name": "ui",
  ui/                      #                "runner_type": "playwright" } ] }
    todo-list/
      an-item-survives-a-reload/
        prompt.md
        an-item-survives-a-reload.spec.ts
```

You get `@playwright/test` pinned to an exact version, the Chromium build
that release drives, and a generated `playwright.config.js` wiring up:

- `baseURL` from `SEAL_BASE_URL`, so a spec navigates with `page.goto('/')`;
- `workers: 1`, which is what keeps two outcomes off the application at
  once;
- a `junit` reporter writing each outcome's `junit.xml`, which is what puts
  outcome results in the same CI report as each service's own;
- an `html` reporter and Playwright's own artifacts, beside it;
- Chromium's sandbox off and `/dev/shm` unused -- properties of running a
  browser in a pod, not of any one project.

It works through the outcomes it was given one at a time, running each
outcome's directory on its own, so that outcome's report and verdict land in
its own directory and one red promise doesn't take the rest of the run with
it. Anything in `runner_args` reaches `playwright test` ahead of the
outcome's path.

**What counts as a test** is Playwright's own default: `*.spec.ts`,
`*.test.ts` and the `.js`/`.tsx` spellings of both, at any depth under the
outcome. Everything else in the directory is part of the translation too --
helpers, fixtures, config -- it just isn't what starts it.

**What several outcomes share** goes in the group's `helpers/`, and is in
the image for free: the build context is the group's own directory, so a
spec reaches it as an ordinary relative import
(`../../helpers/todo-page`). A spec file *in* there is refused -- a run is
pointed at one outcome's directory at a time, so nothing would collect it
(see [Outcomes](outcomes.md#helpers-what-a-groups-tests-share)).

One version pins both the framework and the browser, because the two can't
be allowed to drift: a browser a framework doesn't recognise refuses to
launch, which reads as a promise failing.

Only Chromium is installed, which is all that config launches. The official
all-browser image would carry Firefox and WebKit as freight, paid for three
times over -- the daemon that builds the image, the registry it's pushed to,
and the node that pulls it -- which on a CI runner already holding a cluster
is the difference between a run and a runner that dies partway through one.

What it deliberately doesn't do: retry a failing test, run more than one
browser, or shard. A retry would paper over exactly the flakiness the
environment layer exists to remove; the rest is a decision that wants a
project's evidence behind it.

## The `tap` runner: promises about the machine

Reach for this when a promise is about the layer *underneath* a session --
bringing an environment up, a command refusing to start, a CLI you ship, an
installer, a build. Nothing running inside a session can answer whether
`seal up` brings that session up, so these promises cannot be tested
from a container in the cluster under test.

A `tap` group is started **on the machine**, as a subprocess of `seal
outcomes run`. Declare the type and put an executable called `run` at the
group's root:

```
outcomes/
  seal-test-config.json   # { "runner": [ { "name": "cli",
  cli/                          #                "runner_type": "tap" } ] }
    run                         # executable -- what starts this group
    gating/
      a-broken-promise-cannot-merge/
        prompt.md
        check.sh                # ...whatever your `run` starts
```

**It is started once for the whole group**, not once per promise, and told
which outcomes to cover exactly as a container runner is:

```
<runner_args...> -- <epic>/<outcome> <epic>/<outcome> ...
```

That is the point of this runner. A group whose promises each need an
expensive setup -- a cluster, a fixture repository, a build -- pays for it
once and reports on all of them.

### What your `run` has to do

**Print [TAP](https://testanything.org/) on stdout, one test point per
outcome, described by the slug as you were given it:**

```
1..2
ok 1 - gating/a-broken-promise-cannot-merge
not ok 2 - gating/an-unowned-tree-is-refused
  ---
  message: check exited 0, expected non-zero
  ...
```

That is the whole contract. There is no verdict file to write, no `done`
marker, and nothing to stay up for -- the stream is what Seal reads,
and it may exit however it likes.

A worked `run`, in shell:

```sh
#!/bin/sh
# Arguments up to `--` are this runner's own; everything after is an outcome
# to cover. One point per outcome, named exactly as it was given.
while [ $# -gt 0 ] && [ "$1" != "--" ]; do shift; done
[ "$1" = "--" ] && shift

echo "1..$#"
number=0
for slug in "$@"; do
  number=$((number + 1))
  if "outcomes/cli/$slug/check.sh"; then
    echo "ok $number - $slug"
  else
    echo "not ok $number - $slug"
  fi
done
```

Started from the project root, with the environment you invoked
`seal outcomes run` in and nothing added.

### What Seal does with the stream

Each point becomes that outcome's verdict, under
`tests-results/outcomes/<group>/<epic>/<outcome>/` -- the same place a
container runner's results sync back to, so everything else works the same:
the report, quarantine, `--confirm`, the regression loop.

Three things are **never** read as a promise being kept:

- **A point you never emitted.** Left with no verdict, which the suite
  reports as a test that did not run.
- **`# SKIP` or `# TODO`.** A skipped point is written `ok` by convention and
  established nothing, so it leaves no verdict either.
- **`Bail out!`, or an exit before you finish.** Every point you did emit is
  read; the promises you never reached keep no verdict rather than being
  recorded as failures nothing tested.

A point naming a slug the run did not ask about is reported against the run
and filed under nothing.

### What it costs

A `tap` group runs on whatever machine invoked it, which is the dependence
the container model exists to remove. That is deliberate and it is bounded:
`tap` is for promises **about** that layer. A promise about your
application's own behaviour belongs in the cluster, where every runner sees
the same environment.

## The `custom` runner: bringing your own

Reach for this when a group's outcomes aren't browser-shaped -- an API-only
service, a worker, a scheduled job, a command-line tool, anything with no
page to open. Declare the group's `runner_type` as `custom` and put a
`Dockerfile` in it:

```
outcomes/
  seal-test-config.json    # { "runner": [ { "name": "billing",
  billing/                 #                "runner_type": "custom" } ] }
    Dockerfile             # runs every outcome in this group
    run.sh
    invoicing/
      an-invoice-is-issued-once/
        prompt.md
        check.py
```

The build context is the group's own directory, so every outcome in it is
available to `COPY` along with anything you keep beside the `Dockerfile`.
Files at the group's level are the runner's; directories are epics, save
`helpers/`, which is what this group's tests share and holds no outcomes to
run. Point `dockerfile`/`dockerfile_context` elsewhere in the tree when two
groups should share one image -- which is also how two groups share helpers.

```dockerfile
FROM python:3.12-slim

COPY . /outcomes

ENTRYPOINT ["/outcomes/run.sh"]
```

```sh
#!/bin/sh
# The contract, in one loop. Arguments up to `--` are this runner's own;
# everything after is an outcome to run. Write each outcome's verdict, print
# the log where `tilt` and `kubectl logs` show it, say when the whole run has
# finished, then stay up so the results can be copied out. Never exit on
# failure.
while [ $# -gt 0 ] && [ "$1" != "--" ]; do shift; done
[ "$1" = "--" ] && shift

for slug in "$@"; do
  results=/outcome-results/$slug
  mkdir -p "$results"
  if python "/outcomes/$slug/check.py" > "$results/log.txt" 2>&1; then
    verdict=1
  else
    verdict=0
  fi
  cat "$results/log.txt"
  echo "$verdict" > "$results/passed"
done

touch /outcome-results/done
sleep infinity
```

`check.py` reads `SEAL_BASE_URL` from its environment and exits non-zero
when the promise doesn't hold -- the wrapper turns that into the verdict, so
the test itself stays an ordinary program that fails the ordinary way.

Note the *shape* rather than the language: the loop is over the arguments
after `--`, each outcome reports into its own directory, and the run says
`done` at the end. How a slug becomes something to run is yours.

A `Dockerfile` *inside* an outcome isn't picked up. A test that builds an
image of its own is doing something ordinary, and what starts a run is the
one path the config names rather than whichever one a walk reaches first.

## What `seal check` refuses

Alongside the tree's own rules:

- **A group no runner names, and a runner naming no group.**
- **A `tap` group with no `run` at its root, or a `run` that isn't
  executable.** Nothing could start the group, and every promise under it
  would be reported untested for a reason no listing explains. Git records
  the executable bit -- `chmod +x` it, and commit that.
- **A `runner_type` Seal has no runner for**, a `dockerfile` on a runner
  whose image is Seal's, a misspelled field, two runners naming one group, a
  build path reaching outside the tree, or a `custom` runner whose
  `Dockerfile` isn't there.
- **A `loop` limit that isn't a whole number above zero**, or a misspelled
  field inside it. A limit Seal can't read is a backstop nobody has, and a
  misspelled one reads as a default nobody asked for.
- **A translation the group's runner can't run** -- files that are plainly a
  test, in a `playwright` group, with no spec file among them. That last one
  is the failure a suite can't catch for itself: it would report the promise
  as untested while a test sits right there in the tree.
- **A promise or a test filed under a group's `helpers/`** -- nothing walks
  that directory for outcomes, and a `playwright` run never looks in it.

A `custom` group answers that last question by existing, so the rule stops
applying to it: Seal has no reading of what your runner starts, which
is the whole point of bringing one, and it takes your project at its word.
The same goes for waiting on the clock.

An outcome with *no* translation at all is untouched by any of this.
