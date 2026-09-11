# RFC 0015: Reporting what a run found

| | |
| --- | --- |
| **Status** | Accepted |
| **Related** | [0001](0001-library-boundary.md), [0009](0009-outcome-tests.md), [0010](0010-outcome-tree.md), [0011](0011-outcome-runners.md), [0013](0013-regression-loop.md) |
| **How-to** | [Continuous integration](../docs/guides/continuous-integration.md) |

## Context

A gate run establishes two things: the environment came up, and every promise
the project has translated still holds ([RFC 0009](0009-outcome-tests.md)).
Somebody then has to find out *what* it established, and the two audiences
for that want very different things.

A workflow wants data: keyed by shape, parseable, small enough to pass
between jobs. It already had it -- the `results` output of `actions/ci`.

A person wants a page. A reviewer on a pull request wants to know whether the
promises held before they read the diff; somebody opening a failed run a week
later wants to know which promise gave way and on which shape. What they got
was a directory of JUnit XML in an artifact, plus whatever reporting the
project wired up for itself out of the `results` output.

Three things were wrong with that, and only the third is about convenience.

**A promise's verdict was being read by the wrong module.** An outcome's
verdict is a file its container writes, one per promise -- not a JUnit report
([RFC 0011](0011-outcome-runners.md)): a `playwright` runner happens to write
XML as well, and a `tap` or `custom` runner writes none at all. The reading
handed back to a caller went through `junit.py` for everything under a run's
results directory, the outcome suite included. So for any project not using
the `playwright` runner, the results said its outcome suite had come back
silent -- a failure -- while the gate itself had passed. The bundled example
uses `playwright`, which is why nothing here noticed.

**The promises were invisible even where it worked.** Read as JUnit, a suite
of promises is a list of test-case names. The thing a project actually
promises is a prompt's headline, and the states a promise can be in are not
pass/fail: a promise with no test yet is an ordinary state, and a translated
promise that left no verdict is a failure of a different kind
([RFC 0010](0010-outcome-tree.md)). None of that survived.

**And nothing rendered.** Every adopting project had to write its own
presentation, from a JSON shape it had to learn, or reach for a third-party
action and grant it scopes. That is a capability every project needs and
nobody should have to build -- while *which* presentation, published *where*,
genuinely is theirs to choose.

## Decision

**Seal renders. The repository publishes.**

- One reader per kind of result, and it is the one whose answer the gate
  used: `junit.py` for a service's own tests, `outcome_suite.py` for a
  promise. `seal _tests-results` reads through both and hands back what they
  say -- now including a line per promise, by slug and by headline, in
  whichever of the four states it is in.
- One renderer, downstream of that reading and of nothing else:
  `seal _report` writes a self-contained HTML page and a Markdown summary
  from the reading's own output.
- A promise that failed is reported with what it left behind to look at --
  for the `playwright` runner, a video of the browser and a screenshot,
  recorded on failure only. The page plays them, because it sits in the same
  archive. And because a file inside a CI artifact has no address of its
  own, each broken promise's recording is *also* uploaded as an unarchived
  artifact of its own, so the comment can link one per failure.
- `actions/ci` renders the page into the results artifact it already
  uploads. It still publishes nothing: no check, no comment, no status, not
  even a job summary.
- `actions/report` is a separate, opt-in action that writes the rendering to
  a job summary and keeps one pull-request comment updated in place. A caller
  puts it in a job of its own, and that job grants the
  `pull-requests: write` the comment needs.

## Rationale

### Why the verdict and the rendering are separate commands

A report that disagrees with the gate is worse than no report: it is a green
headline over a red run, or the reverse, and whichever way round it is, one of
them will be believed.

The only structural way to prevent that is for there to be exactly one thing
that reads a report and decides, and for everything else to render what it
said. So `seal _report` takes the output of `seal _tests-results` and cannot
reach a report at all -- there is no path by which it could form a second
opinion. `reporting.py` likewise takes plain data and has no filesystem
access to the results.

That is also why the promise-level reading went into the command that already
hands results back, rather than into the renderer where it was needed: the
renderer is not allowed to know how to read a verdict.

### Why a page in the artifact is not "publishing"

The line this repository holds is that an adopting project should not inherit
somebody else's reporting -- the tools, the scopes those tools need, and the
platform they assume ([RFC 0001](0001-library-boundary.md), and
`/outcomes/library/the-merge-gate/how-results-are-presented-is-my-repositorys-decision`).

A page written into the artifact the project already receives crosses none of
that. Nobody outside the run is told anything, no scope is required, no
third-party action is pinned, and no runner is assumed beyond the one the
action is already running on. What changes is only that the results a project
was handed can be read by a person as well as parsed by a workflow.

`actions/ci` writing a job summary would have been the next smallest step,
and it is deliberately not taken. A job summary is a presentation, on a page
somebody looks at, that a project did not ask for -- and the argument for it
("it needs no scope") is the argument that would have justified the check run
too, one scope later. The boundary is easier to hold at "publishes nothing"
than at "publishes only the harmless things".

### Why the comment is a published action and not an example snippet

The other half of the boundary is that a capability a project would have to
copy out of `examples/` is a capability in the wrong place. A sticky
pull-request comment is exactly that kind of capability: it is thirty lines
of API plumbing, every project wants the same thing from it, and the
interesting parts are the ones that are easy to get wrong and quiet when they
are.

So it ships as `actions/report`, at the same revision as the CLI that renders
for it, and it is reached for only by a caller that names it. An adopting
project that wants no comment does not use it and inherits nothing -- not the
scope, not the behaviour.

Two of those quiet parts are worth naming, because they are what the action
is really for:

- **The comment is found by a marker, over every page of comments.** The
  report is the *oldest* comment on a long-running pull request, since it was
  written on the first run. A lookup that reads one page starts adding a
  report per run at precisely the point a pull request has had enough
  discussion for anybody to care -- and nothing fails.
- **A refusal means two different things.** GitHub gives a workflow triggered
  by a fork's pull request a read-only token whatever the job's `permissions`
  say, so a refused comment there is the platform working as intended;
  anywhere else it is a scope the caller did not grant. The first is a
  warning, the second fails the job. Collapsing them either way is wrong:
  warn on both and a misconfigured repository silently never reports; fail on
  both and every outside contribution fails over a comment that was never
  possible.

### Why the report carries a recording, and how it comes to have a link

A verdict says a promise broke. It does not say what the browser did, and
for a browser-driven test that is most of the work: an assertion that timed
out waiting for a selector reads identically whether the page never loaded,
loaded the wrong thing, or loaded the right thing behind a dialog.

So the `playwright` runner records a video and a screenshot
`retain-on-failure` -- nothing kept on a green run -- into the promise's own
results directory, which is already what syncs back and already what the
artifact carries. Nothing new is uploaded; what changes is that the report
says where the recording is, and the page plays it.

That the page *can* play it is a property of where the page lives. It is
written to the artifact's root, and the recordings sit under it, so a
relative `src` resolves once somebody extracts the archive -- no server, no
network, no viewer to install.

**A file inside a CI artifact has no address of its own.** An artifact is one
archive, fetched whole, so a link to a video inside one is a download to go
looking through. That is the platform, not a decision.

What can be given an address is an artifact. So each broken promise's
recording is *also* uploaded as an artifact of its own, unarchived -- which
`actions/upload-artifact` allows for a single file, and which makes the
artifact's name the file's name. The link then reaches the recording rather
than an archive containing it, and the comment carries one per failure.

Three things follow, and each is a cost accepted rather than avoided.

**The names have to be made up.** Every runner calls its recording
`video.webm`, and two artifacts in one run cannot share a name -- so each is
staged under `<overlay>--<group>--<epic>--<outcome>.webm` before it is
uploaded. That turns the run's artifact list into a list of what broke,
which is worth more than the file's original name was.

**The number is fixed.** A composite action cannot loop a `uses:` step, and
how many promises broke is not known until the run has finished, so the
uploads are unrolled and there are five of them. The cap is pinned in two
files at once, which is the kind of agreement that goes quietly wrong -- one
step too many never runs, one too few publishes nothing and says nothing --
so a test reads both. Five, because the number that matters is one: a branch
where five promises broke is one somebody reads the whole report for.

**The bytes travel twice.** The recording stays in the results artifact as
well, because that is where the page that plays it lives, and a page that
linked out to a separate artifact per video would be a page that only works
online. `publish_recordings: false` keeps the page and skips the uploads.

What the comment still names, rather than links, is everything else a
failure left: the screenshot, the log, the runner's own report. Those are
read beside a report rather than watched, and the page shows them together
-- so they stay in the archive and the comment points at it.

What is reported as evidence is deliberately *not* a list of filenames any
runner was told to produce. A runner writes whatever it writes -- seal has
no reading of it beyond the verdict
([RFC 0011](0011-outcome-runners.md)) -- so what came back is classified by
what opening it does: video, image, trace, page, log. A project's own runner
that leaves an `.mp4` and a `.log` behind is reported exactly like the one
seal supplies, without having been told about either.

Two things are excluded from it on purpose. The verdict file, because it is
the answer the suite already read and reported. And the JUnit report,
because its detail is already reported as the failed case names beside it --
listing it again as "something to open" would bury the recording, which is
the part that is actually new.

A `trace` is not recorded by default. It is the better debugging tool and it
is megabytes per test, viewable only by loading it into Playwright's own
viewer -- so it is a project's to ask for through `runner_args`, and it is
reported like anything else that comes back.

### Why the rendering is capped, and where

GitHub truncates an issue comment past 65536 characters and says nothing
about having done so. The renderer therefore caps what the Markdown lists --
failing promises, failed case names, problems -- and states every cap
alongside the full count, so a shortened listing can never be read as a
smaller failure. The page has no such limit and lists everything, including
the promises that held: "these 47 promises still hold" is the claim a green
gate is making, and a report that only ever showed failures would never show
it being made.

The promise listing in the reading itself is *not* capped, unlike the failed
case names beside it. One broken thing produces hundreds of failed cases;
how many promises a project has declared is bounded by what people wrote
down and grows a line at a time. A promise dropped from the listing would be
indistinguishable from one the tree never declared.

## Consequences

- The `results` output gained an `outcomes` key, and its `sources` list no
  longer carries an `outcomes` entry. A caller that was reading the outcome
  suite as a service's test results reads it under `outcomes` instead --
  where it is a list of promises rather than a list of case names.
- A run is green only if both halves are: every service's own tests, and
  every promise the suite read. That was already the intent; for a
  non-`playwright` project it was not what the output said.
- `actions/report` is GitHub-specific in a way the rest of the library is
  not. That is the same trade `actions/ci` already makes, and it is confined
  to the same place: nothing in `python/` or `tilt/` knows that GitHub
  exists, and the rendering it consumes is platform-neutral text.
- A promise that fails now costs a video in the artifact, an upload of its
  own, and that video's bytes twice. A suite where several fail costs
  several. Bounded by `retain-on-failure` (a green run keeps and uploads
  nothing), by the five-address cap, and by the artifact retention a project
  sets -- and `publish_recordings: false` drops the second copy.
- A project wanting its results somewhere Seal does not render for -- a
  dashboard, a chat channel, a check run with per-test annotations -- still
  builds that from `results` and the artifact, exactly as before. Nothing
  here narrows what a caller can do; it only stops them having to.

## Alternatives considered

**Put the comment in `actions/ci`, behind an input.** One action to use, one
thing to configure. Rejected: an input defaulting to off is a capability
nobody finds, and defaulting to on is a comment on pull requests a project
never asked for -- along with a `pull-requests: write` that the gate job then
has to hold, which is precisely the scope creep the separate job exists to
avoid.

**Render in the reporting job from the downloaded artifact's XML.** It would
have kept `actions/ci` untouched. Rejected: it puts a second reader of the
reports downstream of the gate, which is the one thing this design refuses --
and it cannot see the outcome tree at all, so the promises would still have
been a list of case names.

**Keep reading the outcome suite through `junit.py` and require every runner
to write a JUnit report.** It would have made one reader do. Rejected: it
makes every project's runner responsible for a format it has no other use
for, and it makes the verdict a report rather than the file the runner
already writes -- two answers to one question again, one layer down.

**Publishing every recording as one extra archive rather than one artifact
each.** One upload instead of five, and a smaller download than the whole
results artifact. Rejected: it is still an archive, so it still cannot be
linked per failure -- which is the entire thing a reader wanted.

**Selecting the files to publish with a glob in the workflow.** It would
have removed the `--recordings-list` flag and the staging step. Rejected
twice over: the classification of what counts as a recording lives beside
the verdict it belongs to, and a `find` by extension in YAML is a second
answer to it -- and a glob would also root the artifact wherever the matched
files' common ancestor happens to be, and pick up a screenshot from a
service's own test results.

**Recording always rather than on failure.** Simpler to explain, and a
passing run's video is occasionally interesting. Rejected: it is a video per
test on every green pull request, uploaded and retained, to answer a
question nobody asked -- and the run somebody actually goes looking through
is the red one.

**A third-party reporting action, documented as the recommended one.** It is
what the worked example uses for its per-shape check run, and it is a good
tool. Rejected as the answer to *this*: it reports test cases, and the thing
this project most needs reported is a promise, which is not one.

## Open questions

None.
