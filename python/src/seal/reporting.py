"""What a pipeline's runs found, rendered for somebody to read.

`seal _tests-results` reads every report a run left behind and prints what
they say as plain data (see seal.py). This module turns that data into the
two forms a person actually reads: a self-contained HTML page, and a
Markdown summary short enough to live in a pull-request comment or a job
summary.

It renders; it never reads a report and never decides anything. That split
is the whole reason it is a module of its own: the verdict a reader sees has
to be the verdict the gate reached, and the only way to guarantee that is
for there to be exactly one thing that reads a report (junit.py for a
service's own tests, outcome_suite.py for a promise) and for everything
downstream to render what it said. A renderer that re-read the reports would
be a second answer to a question already answered, free to disagree.

Two audiences, one source. The page has no size limit and shows everything:
every promise the project declares, every service, every failed case name,
every problem. The Markdown has a hard one -- GitHub truncates a comment
past 65536 characters -- so it leads with what went wrong and collapses what
held into a count. Both are rendered from the same data, so they cannot
disagree about a verdict; they disagree only about how much detail there is
room for.

The page is one file with nothing fetched. An HTML report is read from an
artifact download -- often offline, often long after the run -- so a
stylesheet or a font from somewhere else is a page that renders wrong
exactly when somebody needs it. Everything is inline, and there is no
script at all.

Everything interpolated is escaped. A failed test's name, a promise's
headline and a problem's text are all strings somebody else wrote -- a test
name is whatever a developer typed, and a report's text can come from a
service under test -- so none of them may reach the page as markup or the
comment as an injected directive.
"""

import html
from datetime import datetime, timezone

from seal.outcome_suite import (
    FAILED,
    NO_VERDICT,
    PASSED,
    RECORDING_KINDS,
    UNTRANSLATED,
)

# Which kinds a pipeline can have published under an address of their own,
# and so which ones a per-failure link makes redundant in the listing under
# it. The same set the CLI selects for publishing (see
# outcome_suite.RECORDING_KINDS), read from there rather than restated.
PUBLISHED_KINDS = RECORDING_KINDS

# The states a promise can be reported in, in the order a reader wants them:
# what broke first, what nobody can vouch for next, then what held and what
# was never translated. A listing ordered by the tree would bury the one
# line somebody opened the report for.
STATE_ORDER = (FAILED, NO_VERDICT, UNTRANSLATED, PASSED)

# How far the Markdown goes before it starts saying "and N more" instead.
# GitHub truncates an issue comment past 65536 characters, and a truncated
# report is worse than a short one: it stops mid-sentence with no indication
# that it did. These caps are what keep the rendering well inside that,
# whatever a project's suite looks like -- and every one of them is
# accompanied by the full count, so a capped listing can never be read as a
# complete one.
MAX_LISTED_PROMISES = 40
MAX_LISTED_CASES = 10
MAX_LISTED_PROBLEMS = 10
# How many of a promise's recordings the comment names. The page lists every
# one and plays the videos; a comment can do neither, so it names the few a
# reader would go and fetch and says how many it left out.
MAX_LISTED_EVIDENCE = 3

# What the page and the comment call themselves. The page's title is what a
# browser tab shows when somebody opens the artifact; the heading is what
# they read first.
DEFAULT_TITLE = "Seal test results"


def render_html(runs: dict, title: str = DEFAULT_TITLE, source: str = "") -> str:
    """One self-contained page for every run, holding everything.

    `source` is whatever names the run this came from -- a commit, a branch,
    a workflow run's URL. Optional, and rendered verbatim when given: only
    the caller knows what identifies a run in the system that performed it.
    """
    body = [
        "<h1>{}</h1>".format(html.escape(title)),
        _html_provenance(source),
        _html_overview(runs),
    ]
    for name, run in runs.items():
        body.append(_html_run(name, run))
    return _HTML_DOCUMENT.format(
        title=html.escape(title), style=_STYLE, body="\n".join(part for part in body if part)
    )


def render_markdown(
    runs: dict,
    title: str = DEFAULT_TITLE,
    recordings: dict | None = None,
    artifact_url: str = "",
) -> str:
    """The same runs, short enough to be a comment.

    Leads with the verdict, because the verdict is why somebody is reading
    it: a reviewer scrolling a pull request has to be able to tell a green
    gate from a red one without expanding anything.

    `recordings` maps what a pipeline published to where it published it
    (see recording_key()). Where a failure's own recording is in there, the
    comment links it directly -- which is the whole point of publishing one
    on its own, since a file inside an archive has no address and a reader
    would otherwise be downloading one to go looking.

    `artifact_url` is the archive itself, for everything that was not
    published on its own: the screenshots, the logs, and the page that plays
    the recordings where they sit.
    """
    recordings = recordings or {}
    lines = ["## {}".format(title), ""]
    lines.append(_markdown_overview(runs))
    lines.append("")
    for name, run in runs.items():
        lines.extend(_markdown_run(name, run, recordings))
    if artifact_url and any(
        evidence(name, promise)
        for name, run in runs.items()
        for promise in failed_promises(run)
    ):
        lines.append(
            "Everything a failure left behind is in the [results artifact]({}), and "
            "its `index.html` plays the recordings where they sit.".format(artifact_url)
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# -- what a run says, independent of how it is rendered ---------------------


def run_passed(run: dict) -> bool:
    """Whether this run is green: every service's own tests, and every
    promise the suite read.

    Read off the rendered data rather than recomputed from reports, and the
    two halves are combined here rather than anywhere downstream -- a
    renderer that decided this for itself is how a page comes to disagree
    with the gate that produced it.
    """
    return bool(run.get("passed"))


def outcomes_read(run: dict) -> bool:
    """Whether this run went looking at the promises at all.

    A run can be asked for the faster half of the gate -- each service's own
    tests and readiness, and nothing about what the application promises.
    From the results alone that is indistinguishable from a suite where
    every promise left no verdict, which is a failure; the reading says
    which it was, and this is where that reaches a reader.
    """
    return bool(run.get("outcomes", {}).get("read", True))


def outcome_counts(run: dict) -> dict[str, int]:
    """How many promises this run found in each state, whatever the listing
    had room for."""
    return dict(run.get("outcomes", {}).get("counts", {}))


def promises(run: dict) -> list[dict]:
    """Every promise this run read, worst state first -- see STATE_ORDER."""
    listed = run.get("outcomes", {}).get("promises", [])
    order = {state: index for index, state in enumerate(STATE_ORDER)}
    return sorted(
        listed,
        key=lambda promise: (order.get(promise.get("state"), len(order)), promise.get("slug", "")),
    )


def failed_promises(run: dict) -> list[dict]:
    """The promises that are a reason this run is red.

    A quarantined failure is listed here too: it failed, and a listing that
    dropped it would turn a green run into a claim about a promise nobody
    saw kept. What quarantine changes is the verdict, not the reporting (see
    outcome_suite.OutcomeResult.is_failure).
    """
    return [
        promise
        for promise in promises(run)
        if promise.get("state") in (FAILED, NO_VERDICT)
    ]


def recording_key(run_name: str, slug: str) -> str:
    """How a published recording is looked up: by the run it came from and
    the promise it is about.

    Both halves, because two shapes verified in one pipeline can break the
    same promise, and a report that showed one shape's recording under the
    other's failure would be worse than showing none.
    """
    return "{}/{}".format(run_name, slug)


def evidence(run_name: str, promise: dict) -> list[dict]:
    """What a promise left behind to open, as paths inside the results
    artifact.

    The reading gives each path relative to its own run's results; the
    artifact files each run under its name, so prefixing it here is what
    turns one into the other. Done in the renderer because the artifact's
    layout is a fact about what uploaded it, not about what the run found.
    """
    return [
        {**item, "href": "{}/{}".format(run_name, item.get("path", ""))}
        for item in promise.get("evidence", [])
    ]


def failed_sources(run: dict) -> list[dict]:
    return [source for source in run.get("sources", []) if not source.get("passed")]


def problems(run: dict) -> list[str]:
    """Every reason this run's results cannot be believed -- the run's own,
    and the outcome suite's.

    Gathered into one list because they say the same thing to a reader: not
    "a test failed" but "what follows is not a verdict you can act on".
    Where they came from is a fact about which module noticed, not about
    what somebody has to do next.
    """
    return [
        str(problem)
        for problem in [*run.get("problems", []), *run.get("outcomes", {}).get("problems", [])]
    ]


def _totals(runs: dict) -> tuple[int, int]:
    """How many runs there are, and how many of them passed."""
    return len(runs), sum(1 for run in runs.values() if run_passed(run))


def _cases(count: int) -> str:
    return "{} test{}".format(count, "" if count == 1 else "s")


def _failed_count(source: dict) -> int:
    """How many of a source's cases failed -- the whole number, not how many
    of their names the data had room for."""
    return len(source.get("failed", [])) + int(source.get("failed_omitted", 0))


# -- HTML -------------------------------------------------------------------


_HTML_DOCUMENT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{style}
</style>
</head>
<body>
<main>
{body}
</main>
</body>
</html>
"""

# Deliberately small, and deliberately not a framework. The page has to
# render from a file:// URL with no network, so everything is inline -- and
# the colours are defined for both schemes because an artifact gets opened
# in whichever one the reader's machine is set to.
_STYLE = """
:root {
  --bg: #ffffff; --fg: #1b1f23; --muted: #57606a; --line: #d8dee4;
  --panel: #f6f8fa; --pass: #1a7f37; --fail: #cf222e; --warn: #9a6700;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --line: #30363d;
    --panel: #161b22; --pass: #3fb950; --fail: #f85149; --warn: #d29922;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
main { max-width: 60rem; margin: 0 auto; padding: 2rem 1rem 4rem; }
h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
h2 { font-size: 1.25rem; margin: 2.5rem 0 .5rem; padding-bottom: .3rem; border-bottom: 1px solid var(--line); }
h3 { font-size: 1rem; margin: 1.5rem 0 .5rem; }
p.provenance { color: var(--muted); margin: 0 0 1.5rem; overflow-wrap: anywhere; }
p.counts { color: var(--muted); margin: 0 0 .5rem; }
table { width: 100%; border-collapse: collapse; margin: .5rem 0 1rem; }
th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); font-weight: 600; }
td.numeric, th.numeric { text-align: right; font-variant-numeric: tabular-nums; }
code, .slug { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .88em; }
.verdict { font-weight: 700; }
.verdict.pass { color: var(--pass); }
.verdict.fail { color: var(--fail); }
.verdict.unknown { color: var(--warn); }
.state { white-space: nowrap; font-weight: 600; }
.state.pass { color: var(--pass); }
.state.fail { color: var(--fail); }
.state.unknown { color: var(--warn); }
.state.absent { color: var(--muted); }
.note { color: var(--muted); font-weight: 400; }
ul.cases, ul.problems { margin: .3rem 0 0; padding-left: 1.2rem; }
ul.cases li, ul.problems li { overflow-wrap: anywhere; }
ul.problems li { color: var(--fail); }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: .8rem 1rem; margin: 0 0 1rem; }
.empty { color: var(--muted); }
video.recording { display: block; max-width: 100%; margin: .5rem 0; border: 1px solid var(--line); border-radius: 6px; background: #000; }
ul.evidence .kind { display: inline-block; min-width: 4.5rem; color: var(--muted); font-size: .82em; text-transform: uppercase; letter-spacing: .04em; }
"""

# Which colour a state is rendered in. A promise nobody translated is not a
# warning -- it is an ordinary state a project sits in (see
# /rfcs/0010-outcome-tree.md), so it reads as neither good news nor bad.
_STATE_CLASS = {
    PASSED: "pass",
    FAILED: "fail",
    NO_VERDICT: "unknown",
    UNTRANSLATED: "absent",
}


def _html_provenance(source: str) -> str:
    """What this page is a report of, and when it was written.

    The timestamp answers the one question an artifact downloaded later
    always raises -- "is this the run I think it is?" -- and it is in UTC
    because a reader is not necessarily in the timezone of whatever produced
    it.
    """
    written = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [html.escape(source)] if source else []
    parts.append("rendered {}".format(written))
    return '<p class="provenance">{}</p>'.format(" &middot; ".join(parts))


def _html_overview(runs: dict) -> str:
    total, passed = _totals(runs)
    if not runs:
        return (
            '<div class="panel"><span class="verdict fail">no runs</span> &mdash; '
            "nothing reported what it found, so nothing here says whether anything "
            "holds.</div>"
        )
    verdict = "pass" if passed == total else "fail"
    headline = "all {} passed".format(_shapes(total)) if passed == total else (
        "{} of {} failed".format(total - passed, _shapes(total))
    )
    return '<div class="panel"><span class="verdict {}">{}</span></div>'.format(
        verdict, html.escape(headline)
    )


def _shapes(count: int) -> str:
    return "{} run{}".format(count, "" if count == 1 else "s")


def _html_run(name: str, run: dict) -> str:
    passed = run_passed(run)
    parts = [
        '<h2>{} <span class="verdict {}">{}</span></h2>'.format(
            html.escape(name),
            "pass" if passed else "fail",
            "passed" if passed else "FAILED",
        ),
    ]
    listed_problems = problems(run)
    if listed_problems:
        parts.append(_html_problems(listed_problems))
    parts.append(_html_outcomes(name, run))
    parts.append(_html_services(run))
    return "\n".join(parts)


def _html_problems(problems: list) -> str:
    """A run's own problems -- a results directory that isn't there, a report
    that didn't parse. Rendered first and in the failure colour: a problem is
    a reason the rest of the page cannot be believed, so reading it after the
    numbers would be reading it too late."""
    return '<ul class="problems">{}</ul>'.format(
        "".join("<li>{}</li>".format(html.escape(str(problem))) for problem in problems)
    )


def _html_outcomes(run_name: str, run: dict) -> str:
    """Every promise this run read, by state.

    The whole tree, not just what broke: "these 47 promises still hold" is
    the claim a green gate is making, and a page that only ever listed
    failures would never show it being made.
    """
    listed = promises(run)
    counts = outcome_counts(run)
    if not outcomes_read(run):
        return (
            "<h3>Promises</h3>"
            '<p class="empty">This run was not asked to read them, so nothing '
            "here says whether they still hold.</p>"
        )
    if not listed and not counts:
        return (
            "<h3>Promises</h3>"
            '<p class="empty">This project declares no promises.</p>'
        )

    summary = ", ".join(
        "{} {}".format(counts[state], _state_label(state))
        for state in STATE_ORDER
        if counts.get(state)
    )
    rows = []
    for promise in listed:
        state = promise.get("state", "")
        note = " <span class=\"note\">(quarantined)</span>" if promise.get("quarantined") else ""
        cases = promise.get("failed", [])
        detail = ""
        if cases:
            detail = '<ul class="cases">{}</ul>'.format(
                "".join("<li>{}</li>".format(html.escape(str(case))) for case in cases)
            )
        detail += _html_evidence(run_name, promise)
        rows.append(
            '<tr><td class="slug">{slug}</td><td class="state {css}">{state}{note}</td>'
            "<td>{headline}{detail}</td></tr>".format(
                slug=html.escape(str(promise.get("slug", ""))),
                css=_STATE_CLASS.get(state, "absent"),
                state=html.escape(state),
                note=note,
                headline=html.escape(str(promise.get("headline", "")) or "—"),
                detail=detail,
            )
        )
    return (
        "<h3>Promises</h3>"
        '<p class="counts">{summary}</p>'
        "<table><thead><tr><th>Outcome</th><th>State</th><th>What it promises</th>"
        "</tr></thead><tbody>{rows}</tbody></table>"
    ).format(summary=html.escape(summary or "none declared"), rows="".join(rows))


def _html_evidence(run_name: str, promise: dict) -> str:
    """What this promise recorded, playable where it can be.

    A video is embedded rather than linked, because the page is read from an
    extracted artifact with the recording sitting beside it -- and what a red
    browser test costs somebody is working out what the browser actually did.
    `preload="none"`, so a page listing six recordings fetches nothing until
    somebody presses play.

    A promise that held gets its player too, where a project asked for one:
    watching a suite pass is how somebody finds out it passes through the
    wrong page.

    Everything else is a link. Relative, for the same reason: these paths are
    inside the artifact this page travels in, and an absolute one would name
    a directory on whichever machine produced it.
    """
    found = evidence(run_name, promise)
    if not found:
        return ""
    parts = []
    for item in found:
        href = html.escape(item["href"])
        if item.get("kind") == "video":
            # The fallback inside the element, not a line of its own beside
            # it: a browser that plays this shows the player and a browser
            # that cannot shows the link, and a reader sees one of the two
            # rather than the same file twice.
            parts.append(
                '<video class="recording" controls preload="none" src="{}">'
                '<a href="{}">{}</a></video>'.format(href, href, href)
            )
    # Everything the player above did not already offer. The path shown is
    # the one inside the artifact, because that is what somebody who has
    # extracted it is looking for.
    links = "".join(
        '<li><span class="kind">{}</span> <a href="{}">{}</a></li>'.format(
            html.escape(str(item.get("kind", "file"))),
            html.escape(item["href"]),
            html.escape(item["href"]),
        )
        for item in found
        if item.get("kind") != "video"
    )
    omitted = int(promise.get("evidence_omitted", 0))
    if omitted:
        links += '<li class="empty">and {} more file(s)</li>'.format(omitted)
    if links:
        parts.append('<ul class="cases evidence">{}</ul>'.format(links))
    return "".join(parts)


def _state_label(state: str) -> str:
    """What a count of a state is called in prose. The states themselves are
    what a listing shows (`PASS`, `FAIL`); a count reads as a sentence."""
    return {
        PASSED: "passed",
        FAILED: "failed",
        NO_VERDICT: "with no verdict",
        UNTRANSLATED: "with no test yet",
    }.get(state, state)


def _html_services(run: dict) -> str:
    sources = run.get("sources", [])
    if not sources:
        return (
            "<h3>Service tests</h3>"
            '<p class="empty">No service tests came back from this run.</p>'
        )
    rows = []
    for source in sources:
        detail = []
        if source.get("problems"):
            detail.append(_html_problems(source["problems"]))
        if source.get("failed"):
            omitted = int(source.get("failed_omitted", 0))
            items = "".join(
                "<li>{}</li>".format(html.escape(str(case))) for case in source["failed"]
            )
            if omitted:
                items += '<li class="empty">and {} more</li>'.format(omitted)
            detail.append('<ul class="cases">{}</ul>'.format(items))
        rows.append(
            '<tr><td>{name}</td><td class="state {css}">{state}</td>'
            '<td class="numeric">{cases}</td><td class="numeric">{failed}</td>'
            '<td class="numeric">{skipped}</td></tr>'.format(
                name=html.escape(str(source.get("name", ""))),
                css="pass" if source.get("passed") else "fail",
                state="ok" if source.get("passed") else "FAILED",
                cases=source.get("cases", 0),
                failed=_failed_count(source),
                skipped=source.get("skipped", 0),
            )
        )
        if detail:
            rows.append('<tr><td colspan="5">{}</td></tr>'.format("".join(detail)))
    return (
        "<h3>Service tests</h3>"
        "<table><thead><tr><th>Service</th><th>State</th>"
        '<th class="numeric">Tests</th><th class="numeric">Failed</th>'
        '<th class="numeric">Skipped</th></tr></thead><tbody>{rows}</tbody></table>'
    ).format(rows="".join(rows))


# -- Markdown ---------------------------------------------------------------


def _markdown_overview(runs: dict) -> str:
    if not runs:
        return (
            "**No runs reported what they found**, so nothing here says whether "
            "anything holds."
        )
    total, passed = _totals(runs)
    if passed == total:
        return "**All {} passed.**".format(_shapes(total))
    return "**{} of {} failed.**".format(total - passed, _shapes(total))


def _markdown_run(name: str, run: dict, recordings: dict | None = None) -> list[str]:
    """One run, worst news first.

    Everything here is capped, and every cap is stated: a comment is the one
    carrier of this rendering with a hard size limit, and a listing that
    quietly got shorter is worse than one that says how much it left out.
    """
    passed = run_passed(run)
    lines = [
        "### {} — {}".format(name, "passed" if passed else "**FAILED**"),
        "",
    ]

    counts = outcome_counts(run)
    headline_lines = len(lines)
    if not outcomes_read(run):
        lines.append(
            "Promises: not read by this run, so nothing here says whether they "
            "still hold."
        )
    elif counts:
        lines.append(
            "Promises: {}.".format(
                ", ".join(
                    "{} {}".format(counts[state], _state_label(state))
                    for state in STATE_ORDER
                    if counts.get(state)
                )
            )
        )
    services = run.get("sources", [])
    if services:
        lines.append(
            "Service tests: {}, {} failed, {} skipped.".format(
                _cases(run.get("cases", 0)),
                run.get("failed", 0),
                run.get("skipped", 0),
            )
        )
    if len(lines) > headline_lines:
        lines.append("")

    listed_problems = problems(run)
    for problem in listed_problems[:MAX_LISTED_PROBLEMS]:
        lines.append("- ⚠️ {}".format(problem))
    omitted = max(0, len(listed_problems) - MAX_LISTED_PROBLEMS)
    if omitted:
        lines.append("- ⚠️ and {} more problem(s)".format(omitted))
    if listed_problems:
        lines.append("")

    broken = failed_promises(run)
    if broken:
        lines.append("**Promises this run did not see kept**")
        lines.append("")
        for promise in broken[:MAX_LISTED_PROMISES]:
            note = " _(quarantined)_" if promise.get("quarantined") else ""
            lines.append(
                "- `{}` — {}{}{}".format(
                    promise.get("slug", ""),
                    promise.get("state", ""),
                    note,
                    ": {}".format(promise["headline"]) if promise.get("headline") else "",
                )
            )
            # Where the recording of this failure was published, when it
            # was: one click, no archive to open. This is the line the whole
            # arrangement exists for.
            published = (recordings or {}).get(
                recording_key(name, promise.get("slug", ""))
            )
            if published:
                lines.append("  - ▶ [watch this failure]({})".format(published))
            # And what else it left, named rather than linked: a file inside
            # a CI artifact has no address of its own, so the path is what
            # lets somebody find it once the archive is open.
            #
            # The recording itself drops out of that listing once it has a
            # link of its own -- naming a path to the file somebody was just
            # offered in one click is noise.
            recorded = [
                item
                for item in evidence(name, promise)
                if not (published and item.get("kind") in PUBLISHED_KINDS)
            ]
            for item in recorded[:MAX_LISTED_EVIDENCE]:
                lines.append(
                    "  - {}: `{}`".format(item.get("kind", "file"), item["href"])
                )
            left = len(recorded) - MAX_LISTED_EVIDENCE + int(
                promise.get("evidence_omitted", 0)
            )
            if left > 0:
                lines.append("  - and {} more file(s)".format(left))
        if len(broken) > MAX_LISTED_PROMISES:
            lines.append("- and {} more".format(len(broken) - MAX_LISTED_PROMISES))
        lines.append("")

    for source in failed_sources(run):
        lines.append(
            "**{}** — {} of {} failed".format(
                source.get("name", ""), _failed_count(source), _cases(source.get("cases", 0))
            )
        )
        lines.append("")
        for problem in source.get("problems", [])[:MAX_LISTED_PROBLEMS]:
            lines.append("- ⚠️ {}".format(problem))
        for case in source.get("failed", [])[:MAX_LISTED_CASES]:
            lines.append("- `{}`".format(case))
        left = _failed_count(source) - min(
            len(source.get("failed", [])), MAX_LISTED_CASES
        )
        if left > 0:
            lines.append("- and {} more".format(left))
        lines.append("")

    return lines
