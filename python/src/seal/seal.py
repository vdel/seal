#!/usr/bin/env python3
"""`seal` -- one system for handling credentials and the Tilt entry point,
dev and CI alike.

- `seal run -- <cmd> [args...]`: run an arbitrary command (from inside
  services/<name>/, or a subdirectory of it) with that service's
  services/<name>/.env resolved into its environment.
- `seal up [tilt-up args...]`: from the project root, generate every
  service's Kubernetes Secret from its .env (the same way `seal run`
  resolves one), then run `tilt up`, forwarding every argument (including a
  '--', if given) exactly as passed -- see cmd_up() below for why, unlike
  `seal run`, this one must NOT strip a leading '--'.
- `seal check [--credentials_env ENV] [--k8s-dir DIR] [--outcomes-dir DIR]`: from
  the project root, statically check five things a `seal ci` run's own claims
  rest on. That the Kubernetes manifests can report readiness honestly, or
  "everything is ready" means less than it says (checks.py). That every
  service's `.env` matches what the project declared in
  seal-credentials-config.json -- an undeclared scheme, an unmapped
  environment, or a `${` a project meant to expand, each caught before a
  real run reaches a store to find out (credentials.py). That every key a
  service declares has a source in every overlay, or a container starts
  without a value it needs and finds out wherever the application first
  reads it (pod_environment.py). That the outcome
  tree is laid out so every test traces back to the promise it was
  translated from, is in a group some runner declared in
  seal-test-config.json, can be run at all, and waits on the application
  rather than on the clock -- or "every outcome test passes" is a claim about
  tests nobody can review the intent of, that nothing ever ran, or that a
  slow browser can turn red (outcomes.py). And that CODEOWNERS covers that
  tree, or a green suite is a gate anything can walk through by editing the
  test that failed (codeowners.py, /rfcs/0009-outcome-tests.md). `seal ci`
  runs all five itself before starting Tilt, so a project gets them without
  opting in; `seal up` runs none of them, so half-finished work never
  blocks local dev. Manifests are read from ./k8s and outcomes from
  ./outcomes, or from $SEAL_K8S_DIR/$SEAL_OUTCOMES_DIR where a
  project keeps them elsewhere; CODEOWNERS is read from wherever GitHub
  itself would read it, in the enclosing repository; the credentials
  environment is selected the same way `seal run`/`up`/`ci` select one.
- `seal outcomes [--outcomes-dir DIR] [--untranslated]`: from the project
  root, list every outcome the project declares -- its slug,
  whether a test has been translated from its prompt yet, and the prompt's
  own headline. The tree is the only registry there is (see outcomes.py),
  so this is how tooling asks what a project promises without importing
  seal itself. `--untranslated` narrows that to the promises nothing has
  been written from, as bare slugs: the one question here with a caller
  that parses an answer, which is `seal outcomes translate`, a promise at
  a time.
- `seal outcomes run [--outcomes-dir DIR] [--results-dir DIR] [--reset]
  [--all] [--confirm] [slug...]`:
  the whole outcome suite's verdict, read from what every outcome's test
  container left behind (outcome_suite.py). Every outcome at once,
  deliberately: a fix scoped to one test can break another nobody re-ran, so
  what has to be reportable is "every promise this project has translated
  still holds". This is what `seal ci` gates on, and it names no slugs.
  Naming slugs runs those outcomes now, against the session already up, and
  reports only them -- the loop somebody iterating on one translation wants,
  and never what a merge rests on. `--reset` puts every service that declares
  one back to its baseline first, so what a run measures is the application
  rather than the application plus what the last run left in it. Asked for
  rather than assumed: a session somebody is working in is one whose state
  they may be looking at. `--all` runs every promise the tree holds, here and
  now, against that same session -- the whole suite's claim, about a run this
  command performed rather than one it found, which is what a loop iterating
  towards green re-runs each time round without paying for a cluster.
  `--confirm` runs each promise that failed again on its own, from a reset,
  and says whether that reproduced: a failure that doesn't is a test that
  isn't deterministic or doesn't own its data, and sending an agent at the
  application for one produces a change that fixes nothing.
- `seal outcomes translate [--outcomes-dir DIR] [--rewrite] <slug>`: from
  the project root, everything needed to compile one promise into a
  low-level test -- the prompt in full, the directory the translation goes
  in, whichever runner its group declares, and what the result has to
  satisfy (translation.py). seal poses the task and checks the answer; it
  writes nothing and starts no agent, because what an agent session did is
  not something a checkout can verify. An outcome that already has a
  translation needs `--rewrite`: a replacement and a first authorship are
  both reviewed by a human, but they are different things to review.
- `seal outcomes review [--outcomes-dir DIR] <slug>`: from the project
  root, one translation and the promise it claims to encode, side by side,
  plus what has already been settled mechanically -- what runs it, which
  files start a test, how it waits, who can change it (translation.py). The
  mandatory review is the only place a human is asked anything on the
  everything-is-green path, and a translation-only change does not carry
  the prompt in its diff.
- `seal outcomes touched [--outcomes-dir DIR] [--since REF]`: from the
  project root, every path under the outcome tree this change reaches
  (outcome_changes.py), and a non-zero exit where there is one. The rule a
  regression loop turns on is that a fix goes in the application and never
  in the test; CODEOWNERS enforces that at the merge, and this is the part
  of it a checkout can answer for itself, in the round it happened rather
  than in a review nobody was expecting. It reports rather than refusing:
  changing a promise is a legitimate thing to do, and what it costs is a
  human's approval.
- `seal outcomes loop [--outcomes-dir DIR]`: from the project root, the
  regression loop this project is in -- how many rounds of the whole suite
  it has run since the last one in which every promise held, over how long,
  what broke and what was fixed in each, and whether it has a reason to stop
  (outcome_loop.py). Two reasons: a promise fixed and broken again inside
  the loop, which no further round settles by itself, and the backstop the
  project declares in seal-test-config.json. The exit code says whether
  there is one, so a loop can branch on it without reading the prose. What
  it produces is the material a fresh-context agent triages with -- never
  the session that has been looping, which has committed to a narrative
  about which promise is at fault -- and it reaches no conclusion of its
  own: which promise is stale is a judgement, and the change it leads to is
  a code owner's to approve like any other.
- `seal ci [tilt-ci args...]`: from the project root, generate every
  service's Secret the same way `seal up` does, then run `tilt ci`,
  forwarding arguments the same way `seal up` does. Used by CI instead of
  `seal up`; the two differ only in which `tilt` subcommand runs, and in
  which store each service's `.env` resolves against, which is
  `--credentials_env`'s to say (see providers.py) -- credential resolution
  itself is identical in every scope (see
  /rfcs/0006-credential-resolution.md).

There's no separate schema file (no env.json): a service's `.env` -- its key
names, regardless of scope -- *is* the schema. A value names an item, never
the store holding it: which store a run reads is declared once per project
and selected by `--credentials_env`. See
/rfcs/0006-credential-resolution.md at the repo root for the full picture.

The project's entry Tiltfile is a real, checked-in file: it registers this
repo's tilt/ extensions itself and include()s every service's own Tiltfile
directly (see /tilt/README.md and examples/angular-django/Tiltfile for a
worked example) -- there's no separate services list to keep in sync with
it. `seal up`/`seal ci` find each service by asking Tilt itself which
images the project builds (see tilt_discovery.py); plain `tilt up`/`tilt
ci`, run without this CLI, works the same way except it won't generate a
service's Secret first.
"""

import argparse
import dataclasses
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from seal.checks import (
    configured_k8s_dir_name,
    missing_readiness_probes,
    overlays_in,
    render,
)
from seal.codeowners import (
    CODEOWNERS_FILENAME,
    CODEOWNERS_LOCATIONS,
    find_codeowners,
    find_repository_root,
)
from seal import providers, reporting, tap_group
from seal.credentials import (
    Context,
    EMIT_ENV_SUBCOMMAND,
    SealError,
    claimable_keys,
    declaration_problems,
    discover_service_env_files,
    env_file_path,
    exec_resolved,
    find_seal_root,
    SERVICES_DIR_NAME,
    find_service,
    parse_env_file,
    resolve,
)
from seal.junit import read_run_tests, read_service_tests
from seal.outcome_suite import (
    CONFIRMED,
    DEFAULT_RESULTS_DIR_NAME,
    FAILED,
    NO_VERDICT,
    OUTCOMES_RESULTS_SUBDIR,
    PASSED,
    UNCONFIRMED,
    UNTRANSLATED,
    VERDICT_FILENAME,
    RUN_PURPOSE,
    SELECTION_FILE,
    SYNCBACK_PURPOSE,
    SYNCBACK_TRIGGER_PURPOSE,
    resource_name,
    reset_resources,
    report,
    OutcomeResult,
    result_for,
    results_dir_for,
    select,
    suite_results,
    summary,
)
from seal.fill import write_filled
from seal.pod_environment import unaccounted_keys
from seal.stubs import claims, stubs_in
from seal.outcome_changes import touched
from seal.outcome_history import (
    RECENT_RUNS,
    flips,
    record,
    recorded_runs,
    recorded_verdicts,
)
from seal.outcome_loop import ITERATION_CAP, TIME_CAP, loop, stops
from seal.outcomes import (
    HELPERS_DIR_NAME,
    Outcome,
    configured_outcomes_dir_name,
    discover_outcomes,
    outcome_layout_problems,
    unowned_outcomes,
)
from seal.runners import (
    CONFIG_FILENAME,
    LOOP_FIELD,
    MAX_ITERATIONS_FIELD,
    MAX_MINUTES_FIELD,
    read_loop_limits,
)
from seal.translation import (
    already_translated,
    nothing_to_review,
    review,
    translation_brief,
)

USAGE = (
    "Usage: seal run [--credentials_env ENV] -- <cmd> [args...]  |  "
    "seal up [--credentials_env ENV] [tilt-up args...]  |  "
    "seal ci [--credentials_env ENV] [tilt-ci args...]  |  "
    "seal check [--credentials_env ENV] [--k8s-dir DIR] [--outcomes-dir DIR]  |  "
    "seal outcomes [--outcomes-dir DIR] [--untranslated]  |  "
    "seal outcomes run [--outcomes-dir DIR] [--results-dir DIR] [--reset] [--all] "
    "[--confirm] [slug...]  |  "
    "seal outcomes translate [--outcomes-dir DIR] [--rewrite] <slug>  |  "
    "seal outcomes review [--outcomes-dir DIR] <slug>  |  "
    "seal outcomes touched [--outcomes-dir DIR] [--since REF]  |  "
    "seal outcomes loop [--outcomes-dir DIR]"
)


# How a Tiltfile invokes this same CLI again from inside the session it
# started -- what runs the outcome suite (see /tilt/seal/outcomes.Tiltfile).
# Announced rather than assumed: `seal` reaches a project through `uvx`, a
# checkout's own virtualenv or an installed package, and only the process
# already running it knows which. A plain `tilt up`, started without this
# CLI, falls back to the name on PATH.
SEAL_CLI_ENV_VAR = "SEAL_CLI"

# Whether this run is a gate: something whose whole point is a verdict on
# what a project promises. `seal ci` is that and `seal up` is not, which is
# what the Tilt session reads to decide whether the outcome suite runs on
# its own (tilt/seal/outcomes.Tiltfile). Deliberately not derived from what
# is being built: a run against a production-shaped overlay builds images
# carrying no test suite at all and is still a gate.
SEAL_CI_ENV_VAR = "SEAL_CI"


def _announce_seal_cli() -> None:
    """Put this interpreter's way of running `seal` where the Tilt session
    about to start can find it. setdefault, so a caller that knows better --
    a pipeline with a wrapper of its own -- keeps the say."""
    os.environ.setdefault(SEAL_CLI_ENV_VAR, f"{shlex.quote(sys.executable)} -m seal.seal")


def _announce_gate() -> None:
    """Tell the Tilt session about to start that its result is a verdict.
    Only `seal ci` calls this: a session somebody is about to work in is not
    a gate, and spending a whole outcome suite on every start of one is how
    a local loop stops being used."""
    os.environ[SEAL_CI_ENV_VAR] = "1"


def _generated_env_dir(seal_root: Path, service_name: str) -> Path:
    return seal_root / ".workspace" / "seal-env" / service_name


def _credentials_context(
    seal_root: Path, service_name: str, credentials_env: str | None
) -> Context:
    """What this run reads credentials with: the project's declarations, and
    which of its environments was named.

    A malformed declaration stops the run here rather than at the first
    reference that needs it -- every service resolves through the same file,
    so a problem with it is a problem with all of them.
    """
    declaration, problems = providers.read_config(seal_root)
    if problems:
        listed = "\n".join(f"  - {problem}" for problem in problems)
        raise SealError(f"Error: {providers.config_path(seal_root)}\n{listed}")
    return Context(
        declaration=declaration,
        environment=providers.select_environment(declaration, credentials_env),
        service_name=service_name,
    )


def cmd_run(args: list[str]) -> int:
    credentials_env, args = providers.take_credentials_env(args)
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        print(USAGE, file=sys.stderr)
        return 1

    seal_root = find_seal_root(Path.cwd())
    service_name, service_dir = find_service(seal_root, Path.cwd())
    env_path = env_file_path(service_dir)
    values = parse_env_file(env_path)
    context = _credentials_context(seal_root, service_name, credentials_env)

    exec_resolved(resolve(context, values), args)  # never returns on success
    return 1  # pragma: no cover -- only reached if exec somehow returns


def cmd_emit_env(args: list[str]) -> int:
    """Internal: the command a `run`-form provider wraps.

    That form is the one that cannot hand values back -- it puts them in a
    child process's environment and runs something there. So the something
    is this: it writes the keys it was asked for to a file the parent reads,
    which is how resolution returns values rather than a process.

    Not meant to be run directly. Every other form writes its values to
    stdout itself and never reaches here.
    """
    parser = argparse.ArgumentParser(prog=f"seal {EMIT_ENV_SUBCOMMAND}")
    parser.add_argument("--keys", default="", help="Comma-separated key names.")
    parser.add_argument("--out", required=True)
    parsed = parser.parse_args(args)

    keys = [key for key in parsed.keys.split(",") if key]
    missing = [key for key in keys if key not in os.environ]
    if missing:
        # A key the provider was asked for and did not set. Reported rather
        # than written as an empty string: an empty environment variable is
        # a service starting with a blank where a secret should be, which
        # fails somewhere far from here.
        raise SealError(
            "Error: the provider resolved nothing for "
            f"{', '.join(sorted(missing))}."
        )

    Path(parsed.out).write_text(
        json.dumps({key: os.environ[key] for key in keys}), encoding="utf-8"
    )
    return 0


def cmd_tests_verdict(args: list[str]) -> int:
    """Internal: one service's own test run, read from the JUnit report it
    left behind (junit.py). Invoked by the `seal_tests_verdict_<service>`
    resource seal registers for every tested service (see
    tilt/seal/tests.Tiltfile), which is how a failed suite fails `tilt ci`
    -- one resource per service, so the run points at whichever service
    failed rather than at a single combined check. Not meant to be run
    directly.
    """
    parser = argparse.ArgumentParser(prog="seal _tests-verdict")
    parser.add_argument("service_name")
    parser.add_argument("--results-dir", required=True)
    parsed = parser.parse_args(args)

    tests = read_service_tests(parsed.service_name, Path(parsed.results_dir))
    print(tests.summary())
    return 0 if tests.passed else 1


# How many failed test names one source of reports contributes to the
# rendering `seal _tests-results` produces. What carries that rendering has a
# size limit on it, and a suite where three hundred cases failed has told a
# reader what they need by the fiftieth. The count is rendered whole
# alongside, so a capped listing is never readable as a shorter one.
MAX_RENDERED_FAILURES = 50


def cmd_tests_results(args: list[str]) -> int:
    """Internal: what every run of a pipeline found, as JSON on stdout.

    The CI action (actions/ci/action.yml) calls this to hand its results
    to whoever used it, so a caller can report on them without
    downloading an artifact and parsing XML -- and without this repository
    deciding how a project's results are presented.

    Two readers, each owning what it already decided during the run. A
    service's own tests are read by junit.py, the module `seal ci`'s
    per-service verdict comes from; the outcome suite is read by
    outcome_suite.py, where a promise's verdict comes from -- its own file
    per promise, not a JUnit report, because a `tap` or `custom` runner
    writes none (see /rfcs/0011-outcome-runners.md). A reading that parsed
    the reports itself would be a second answer to a question the gate
    already answered, free to disagree with it.

    Each `--run NAME=DIR` is one results directory and the name to file it
    under. The names are the caller's -- the workflow passes the overlay each
    run deployed -- because what distinguishes two runs of the same project
    is not something this command can see from their results.

    Not meant to be run directly. It renders; it never decides. The exit code
    is about whether the results could be rendered, not about what they say:
    the run that produced them already failed, or didn't.
    """
    parser = argparse.ArgumentParser(prog="seal _tests-results")
    parser.add_argument("--run", action="append", metavar="NAME=DIR", required=True)
    parser.add_argument(
        "--outcomes-dir",
        default=None,
        help=(
            "the project's outcome tree, relative to the project root. Every "
            "promise it declares is reported, which is what lets a promise "
            "that left no verdict be told from one that was never asked for."
        ),
    )
    parsed = parser.parse_args(args)

    outcomes_dir = Path(
        parsed.outcomes_dir or configured_outcomes_dir_name(os.environ)
    )
    # Read once, not per run: the tree is the same for every shape a
    # pipeline verified -- what differs between them is the verdicts, which
    # each run's own results directory holds.
    declared = discover_outcomes(outcomes_dir)

    runs = {}
    for entry in parsed.run:
        name, separator, directory = entry.partition("=")
        if not name or not separator or not directory:
            raise SealError(f"Error: --run takes NAME=DIR, got '{entry}'.")
        if name in runs:
            raise SealError(
                f"Error: --run names '{name}' twice, so one run's results would "
                "silently replace the other's."
            )
        runs[name] = _rendered_run(Path(directory), declared)

    print(json.dumps(runs, separators=(",", ":")))
    return 0


def _rendered_run(results_root: Path, declared: list[Outcome]) -> dict:
    """One run as the plain data a consumer reads: the verdict, the counts, a
    line per source of reports, and a line per promise.

    Written on one line of JSON, and deliberately small. What carries it has
    a size limit -- a workflow output, a pull-request comment, a summary --
    so the failed test *names* are capped while the failed test *count* never
    is: a listing that quietly got shorter is worse than one that says how
    much it left out.

    Every promise is listed, uncapped, and that asymmetry is on purpose: one
    broken thing produces hundreds of failed cases, while how many promises
    a project has declared is bounded by what people wrote down and grows a
    line at a time. A listing that dropped one would be indistinguishable
    from a tree that never declared it, which is the claim /rfcs/0010 exists
    to refuse.
    """
    run = read_run_tests(results_root, exclude=(OUTCOMES_RESULTS_SUBDIR,))
    outcomes = _rendered_outcomes(results_root, declared)
    return {
        # Both halves, because a run is green only if both were: the
        # services' own tests and every promise the suite read.
        "passed": run.passed and outcomes["passed"],
        # The services' own, not the suite's. An outcome's verdict is a
        # promise kept or not, and adding it to a count of test cases would
        # be adding two different units together.
        "cases": run.cases,
        "skipped": run.skipped,
        "failed": run.failed,
        "problems": list(run.problems),
        "sources": [
            {
                "name": source.service,
                "passed": source.passed,
                "cases": source.cases,
                "skipped": source.skipped,
                "failed": list(source.failed[:MAX_RENDERED_FAILURES]),
                "failed_omitted": max(0, len(source.failed) - MAX_RENDERED_FAILURES),
                "problems": list(source.problems),
            }
            for source in run.sources
        ],
        "outcomes": outcomes,
    }


def _rendered_outcomes(results_root: Path, declared: list[Outcome]) -> dict:
    """Every promise, and what this run found out about it.

    Named by headline as well as by slug: the headline is what the project
    actually promises and the slug is only how the tree spells it, so a
    reader who has never opened the tree can still tell what went red.

    A promise that failed carries whatever its own results directory says
    about *which* case failed, where its runner wrote a JUnit report. That is
    extra detail rather than the verdict -- the verdict is the file
    outcome_suite.py read -- so a runner writing no report is not a problem
    here, which is exactly how it differs from a service whose tests came
    back silent (see junit.py).
    """
    results = suite_results_for(declared, results_root)
    counts = {
        state: sum(1 for result in results if result.state == state)
        for state in (PASSED, FAILED, NO_VERDICT, UNTRANSLATED)
    }
    problems = _outcome_result_problems(results_root, results)
    return {
        # A problem is as much a reason this is not green as a failure is:
        # it says the verdicts cannot be believed, and "cannot be believed"
        # must never render as "held".
        "passed": not problems and not any(result.is_failure for result in results),
        "counts": {state: count for state, count in counts.items() if count},
        "quarantined": sum(1 for result in results if result.outcome.quarantined),
        "problems": problems,
        "promises": [
            {
                "slug": result.outcome.slug,
                "headline": result.outcome.headline,
                "state": result.state,
                "quarantined": result.outcome.quarantined,
                "failed": [
                    case
                    for case in read_service_tests(
                        result.outcome.slug, result.results_dir
                    ).failed[:MAX_RENDERED_FAILURES]
                ]
                if result.state == FAILED
                else [],
            }
            for result in results
        ],
    }


def suite_results_for(
    declared: list[Outcome], results_root: Path
) -> list[OutcomeResult]:
    """What one run found out about every promise, in the tree's own order.

    Takes the tree already discovered rather than discovering it again,
    which is what lets several runs of one pipeline be read against one
    reading of the tree they all verified.
    """
    return [result_for(outcome, results_root) for outcome in declared]


def _outcome_result_problems(
    results_root: Path, results: list[OutcomeResult]
) -> list[str]:
    """Reasons this run's promise-level results cannot be believed.

    There is one, and it is the case where the tree and the results disagree
    about whether the project has an outcome suite at all: a run that synced
    verdicts back while nothing declares a promise means the report is being
    rendered against a different tree from the one that ran. Reported rather
    than passed over, because the alternative reads as a project that
    promises nothing -- and a suite nobody declared is exactly what a green
    gate must not be able to claim on a project's behalf.
    """
    if results:
        return []
    if (results_root / OUTCOMES_RESULTS_SUBDIR).is_dir():
        return [
            "an outcome suite's results came back from this run and no promise is "
            "declared -- the tree read here is not the one that ran"
        ]
    return []


def cmd_report(args: list[str]) -> int:
    """Internal: what `seal _tests-results` printed, rendered for a person.

    The page and the comment a pipeline publishes, written from the same
    data the gate handed back (reporting.py). It is a separate command
    from the reading above for the same reason reporting.py is a separate
    module: reading a report is what decides a verdict, and rendering one
    must never be in a position to reach a different one.

    Nothing here talks to anything. It reads JSON and writes files, so the
    same rendering can be uploaded as an artifact, written to a job
    summary, or posted as a comment by whatever has the scopes to -- which
    is the project's decision and not this command's (see
    /rfcs/0015-reporting-what-a-run-found.md).

    Not meant to be run directly.
    """
    parser = argparse.ArgumentParser(prog="seal _report")
    parser.add_argument(
        "--results",
        required=True,
        metavar="FILE",
        help="what `seal _tests-results` printed; '-' reads stdin.",
    )
    parser.add_argument("--html", metavar="FILE", default=None)
    parser.add_argument("--markdown", metavar="FILE", default=None)
    parser.add_argument(
        "--title",
        default=reporting.DEFAULT_TITLE,
        help="the heading both renderings carry.",
    )
    parser.add_argument(
        "--source",
        default="",
        help=(
            "what identifies the run this came from -- a commit, a branch, a "
            "URL. Rendered verbatim on the page: only the caller knows what "
            "names a run in whatever performed it."
        ),
    )
    parsed = parser.parse_args(args)

    if not parsed.html and not parsed.markdown:
        raise SealError(
            "Error: seal _report renders nothing unless --html or --markdown "
            "names where to write it."
        )

    raw = sys.stdin.read() if parsed.results == "-" else Path(parsed.results).read_text(
        encoding="utf-8"
    )
    try:
        runs = json.loads(raw or "{}")
    except ValueError as error:
        raise SealError(
            f"Error: the results are not JSON ({error}). They are what "
            "`seal _tests-results` printed; a run that died before it could "
            "print any hands back an empty string, which is reported as no "
            "runs rather than rendered."
        ) from error
    if not isinstance(runs, dict):
        raise SealError(
            "Error: the results are a JSON object keyed by run, and this is "
            f"a {type(runs).__name__}."
        )

    if parsed.html:
        Path(parsed.html).write_text(
            reporting.render_html(runs, title=parsed.title, source=parsed.source),
            encoding="utf-8",
        )
    if parsed.markdown:
        Path(parsed.markdown).write_text(
            reporting.render_markdown(runs, title=parsed.title), encoding="utf-8"
        )
    return 0


def _resolved_for(
    seal_root: Path, service_name: str, service_dir: Path, credentials_env: str | None
) -> dict[str, str]:
    """One service's `.env`, resolved. The keys of the result are exactly
    the keys a stub may claim: `resolve()` returns every value seal
    supplies and no `k8s://` marker, which the manifests declare
    individually and no filled object is entitled to."""
    values = parse_env_file(env_file_path(service_dir))
    context = _credentials_context(seal_root, service_name, credentials_env)
    return resolve(context, values)


def _fill_declared_objects(
    label: str, seal_root: Path, args: list[str], credentials_env: str | None = None
) -> None:
    """Fill every object any overlay says seal fills -- shared by
    `seal up` and `seal ci` alike.

    Every overlay, not the one this run selected. Which overlay Tilt
    deploys is `select_k8s_overlay()`'s answer, computed in Starlark from
    `--k8s_overlay` and a `default_overlay` the project's own root Tiltfile
    passes -- an argument this process never sees. Reproducing that
    selection here would mean a second implementation of it, in another
    language, against an input it does not have. So each overlay's objects
    are filled beside it and the Tiltfile reads the one it picked, which
    keeps the selection in exactly one place.

    It is cheap: only an overlay that carries stubs has anything filled at
    all (a real environment's carries whatever populates its objects there
    instead), and each service resolves once however many overlays name it.

    The only thing that differs between dev and CI/stag/prod is *which*
    store each reference resolves against -- the credentials environment
    this run selected (see providers.py). `label` is for the progress
    messages (e.g. 'seal up').
    """
    del args  # the overlay is not this process's to choose; see above
    k8s_dir = seal_root / configured_k8s_dir_name(os.environ)
    if not k8s_dir.is_dir():
        return

    by_service = dict(discover_service_env_files(seal_root))
    resolved_by_service: dict[str, dict[str, str]] = {}

    for overlay in overlays_in(k8s_dir):
        found = stubs_in(render(overlay))
        if not found:
            continue
        for stub in found:
            if stub.service in resolved_by_service or stub.service not in by_service:
                continue
            print(f"{label}: resolving '{stub.service}' for overlay '{overlay.name}'...")
            resolved_by_service[stub.service] = _resolved_for(
                seal_root, stub.service, by_service[stub.service], credentials_env
            )

        claimed, problems = claims(
            found, {service: list(values) for service, values in resolved_by_service.items()}
        )
        if problems:
            listed = "\n".join(f"  - {problem}" for problem in problems)
            raise SealError(
                f"Error: overlay '{overlay.name}' cannot be filled\n{listed}"
            )
        if write_filled(
            seal_root, overlay.name, overlay, claimed, resolved_by_service
        ) is not None:
            print(f"{label}: filled {len(claimed)} object(s) for overlay '{overlay.name}'.")


def cmd_up(args: list[str]) -> int:
    # Forwarded to `tilt up` verbatim, '--' included when present: unlike
    # `seal run` (where '--' only ever separates seal's own args from an
    # arbitrary wrapped command), a '--' here is *tilt's own* separator
    # between tilt-cli flags and Tiltfile config args (e.g.
    # `seal up -- --build_type test`) -- stripping it would silently
    # turn a Tiltfile arg into an invalid tilt-cli flag.
    credentials_env, args = providers.take_credentials_env(args)
    seal_root = find_seal_root(Path.cwd())
    if Path.cwd().resolve() != seal_root:
        raise SealError(f"Error: run `seal up` from the project root ({seal_root}), not {Path.cwd()}.")

    _fill_declared_objects("seal up", seal_root, args, credentials_env)

    tilt = shutil.which("tilt")
    if tilt is None:
        raise SealError("Error: 'tilt' not found on PATH. See https://tilt.dev for install instructions.")
    _announce_seal_cli()
    print("seal up: starting `tilt up`...")
    os.execvpe(tilt, [tilt, "up"] + args, os.environ.copy())  # never returns on success
    return 1  # pragma: no cover


def cmd_ci(args: list[str]) -> int:
    # See the comment in cmd_up() -- forwarded to `tilt ci` verbatim, '--'
    # included when present. Credentials resolve through the project's
    # declared providers here exactly as they do in cmd_up(); CI never
    # populates the process environment itself -- see
    # /rfcs/0006-credential-resolution.md.
    credentials_env, args = providers.take_credentials_env(args)
    seal_root = find_seal_root(Path.cwd())
    if Path.cwd().resolve() != seal_root:
        raise SealError(f"Error: run `seal ci` from the project root ({seal_root}), not {Path.cwd()}.")

    # Before anything expensive: a manifest that can't report readiness
    # honestly, an outcome tree whose tests don't trace back to a promise, or
    # one nobody has to review a change to, each makes this whole run's
    # result untrustworthy -- and all three cost a directory walk to find
    # out.
    code = _run_checks(
        seal_root,
        configured_k8s_dir_name(os.environ),
        configured_outcomes_dir_name(os.environ),
        "seal ci",
        credentials_env,
    )
    if code != 0:
        return code

    _fill_declared_objects("seal ci", seal_root, args, credentials_env)

    tilt = shutil.which("tilt")
    if tilt is None:
        raise SealError("Error: 'tilt' not found on PATH. See https://tilt.dev for install instructions.")
    _announce_seal_cli()
    _announce_gate()
    print("seal ci: starting `tilt ci`...")
    os.execvpe(tilt, [tilt, "ci"] + args, os.environ.copy())  # never returns on success
    return 1  # pragma: no cover


def _check_readiness(seal_root: Path, k8s_dir_name: str, label: str) -> int:
    """Shared by `seal check` and `seal ci`. Returns a process exit code, and
    prints what's wrong rather than raising, so a project sees every offending
    container at once instead of fixing them one failed run at a time."""
    k8s_dir = seal_root / k8s_dir_name
    if not k8s_dir.is_dir() and not (seal_root / SERVICES_DIR_NAME).is_dir():
        # A project that deploys nothing has no container to check. That is
        # an ordinary shape -- a project whose promises are all run on the
        # machine states them and runs them without a cluster (see
        # /rfcs/0014-seal-on-seal.md) -- and reporting on a
        # convention it has not adopted, on every run, is what trains people
        # to read past this output.
        #
        # A project with services and no manifests is a different thing
        # entirely, and still says so: it deploys, and there is nothing here
        # saying what.
        return 0
    missing = missing_readiness_probes(k8s_dir)
    if not missing:
        print(f"{label}: every Deployment under {k8s_dir_name}/ declares a readinessProbe.")
        return 0

    print(
        f"{label}: {len(missing)} container(s) have no readinessProbe. Kubernetes reports "
        "a container without one Ready as soon as its process starts, so `tilt ci` can "
        "call the environment up before it can serve -- and a test suite run against it "
        "is not testing what it looks like it is.",
        file=sys.stderr,
    )
    for problem in missing:
        print(f"  {problem.describe(seal_root)}", file=sys.stderr)
    return 1


def _check_outcome_layout(seal_root: Path, outcomes_dir_name: str, label: str) -> int:
    """Shared by `seal check` and `seal ci`, and shaped like _check_readiness()
    above: prints every offender rather than raising, so a project puts its
    tree right in one pass.

    A project with no outcome tree passes silently -- there is nothing to say
    about a convention it hasn't adopted, and saying it on every run would
    train people to read past this check's output."""
    outcomes_dir = seal_root / outcomes_dir_name
    if not outcomes_dir.is_dir():
        return 0

    problems = outcome_layout_problems(outcomes_dir)
    if not problems:
        print(
            f"{label}: every outcome under {outcomes_dir_name}/ pairs a prompt with a test "
            "the suite can run and can trust."
        )
        return 0

    print(
        f"{label}: {len(problems)} problem(s) in {outcomes_dir_name}/. An outcome test is "
        "only reviewable against the promise it was translated from, and only a gate if "
        "the suite can actually run it -- so the layout pairs each prompt with its own "
        "test, and fixes the one file that starts it. See /rfcs/0010-outcome-tree.md.",
        file=sys.stderr,
    )
    for problem in problems:
        print(f"  {problem.describe(seal_root)}", file=sys.stderr)
    return 1


def _suggested_codeowners_rule(repo_root: Path, outcomes_dir: Path) -> str:
    """The one line that would put a whole outcome tree behind review, spelled
    from the repository root the way CODEOWNERS reads a pattern -- which is
    not where `seal check` was run from when a project sits inside a larger
    repository."""
    try:
        where = outcomes_dir.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        where = outcomes_dir.name
    return f"/{where}/ @your-team"


def _check_outcome_ownership(seal_root: Path, outcomes_dir_name: str, label: str) -> int:
    """Shared by `seal check` and `seal ci`. Whether a change to an outcome
    has to be reviewed by a human -- which on GitHub means whether CODEOWNERS
    covers it.

    This is the check the whole outcome-test design leans on. A suite an
    agent can turn green by editing the test that failed is not a merge gate,
    and nothing about a green run distinguishes the two: the difference is
    entirely in who has to approve the diff. See /rfcs/0009-outcome-tests.md,
    including the half of the gate that lives in a repository's settings and
    so cannot be checked from inside a checkout at all.

    A project with no outcomes declares nothing to gate and passes silently,
    the same way the layout check does. One that has written promises down
    and left them ungated is exactly the state this exists to surface, so a
    missing CODEOWNERS is a failure rather than a project that has not opted
    in yet."""
    outcomes_dir = seal_root / outcomes_dir_name
    if not discover_outcomes(outcomes_dir):
        return 0

    # CODEOWNERS belongs to the repository, not the project: a project nested
    # inside a larger repo (an example, a monorepo package) is governed by
    # that repo's file, at paths carrying its own directory prefix.
    repo_root = find_repository_root(seal_root) or seal_root
    codeowners = find_codeowners(repo_root)
    if codeowners is None:
        locations = ", ".join(
            f"{location}/{CODEOWNERS_FILENAME}" if location != "." else CODEOWNERS_FILENAME
            for location in CODEOWNERS_LOCATIONS
        )
        print(
            f"{label}: {repo_root} has no CODEOWNERS, so nothing makes a change to "
            f"{outcomes_dir_name}/ need a human's approval. An outcome test an agent can "
            "edit to make its own failure go away is not a merge gate. Create one of "
            f"{locations} with a rule covering the tree, e.g.\n"
            f"  {_suggested_codeowners_rule(repo_root, outcomes_dir)}",
            file=sys.stderr,
        )
        return 1

    unowned = unowned_outcomes(outcomes_dir, codeowners)
    if not unowned:
        print(
            f"{label}: every outcome under {outcomes_dir_name}/ needs a code owner's "
            "review to change."
        )
        return 0

    print(
        f"{label}: {len(unowned)} path(s) under {outcomes_dir_name}/ that a change could "
        f"reach without a human's approval, per {codeowners.source}. An outcome test an "
        "agent can edit to make its own failure go away is not a merge gate. See "
        "/rfcs/0009-outcome-tests.md.",
        file=sys.stderr,
    )
    for problem in unowned:
        print(f"  {problem.describe(seal_root)}", file=sys.stderr)
    print(
        "  Covering the whole tree takes one rule: "
        f"{_suggested_codeowners_rule(repo_root, outcomes_dir)}",
        file=sys.stderr,
    )
    return 1


def _check_credentials(seal_root: Path, label: str, credentials_env: str | None) -> int:
    """Shared by `seal check` and `seal ci`. Every service's `.env` checked
    against what the project declared in seal-credentials-config.json, without
    resolving anything -- see declaration_problems() in credentials.py and
    /rfcs/0006-credential-resolution.md.

    A malformed declaration stops this check here, the same way
    `_credentials_context()` stops a real run: every service reads the same
    file, so a problem with it is a problem with all of them."""
    declaration, config_problems = providers.read_config(seal_root)
    if config_problems:
        print(f"{label}: {providers.config_path(seal_root)}", file=sys.stderr)
        for problem in config_problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    environment = providers.select_environment(declaration, credentials_env)
    problems = declaration_problems(seal_root, declaration, environment)
    if not problems:
        print(f"{label}: every service's .env matches what {providers.CONFIG_FILENAME} declares.")
        return 0

    print(
        f"{label}: {len(problems)} problem(s) between a service's .env and its declared "
        "providers. A `.env` value names an item, never a store -- see "
        "/rfcs/0006-credential-resolution.md.",
        file=sys.stderr,
    )
    for problem in problems:
        print(f"  {problem.describe()}", file=sys.stderr)
    return 1


def _check_pod_environment(seal_root: Path, k8s_dir_name: str, label: str) -> int:
    """Shared by `seal check` and `seal ci`. Whether every key a
    service's `.env` declares actually reaches the container that needs it,
    in every overlay a run could deploy -- see pod_environment.py and
    /rfcs/0007-credential-delivery.md's "Accounting for a pod's environment".

    A project whose `.env` files reach no overlay object says nothing, the
    way the other checks stay quiet about a convention nobody adopted."""
    unconsumed, unsourced = unaccounted_keys(
        seal_root / k8s_dir_name, claimable_keys(seal_root)
    )
    if not unconsumed and not unsourced:
        print(f"{label}: every key a service declares has a source in every overlay.")
        return 0

    print(
        f"{label}: {len(unconsumed) + len(unsourced)} key(s) an overlay does not "
        "account for. A container whose sources supply nothing for a key its "
        "service declares starts without it, and finds out wherever the "
        "application first reads it. See /rfcs/0006-credential-resolution.md.",
        file=sys.stderr,
    )
    for problem in unconsumed:
        print(f"  {problem.describe()}", file=sys.stderr)
    for problem in unsourced:
        print(f"  {problem.describe()}", file=sys.stderr)
    return 1


def _run_checks(
    seal_root: Path,
    k8s_dir_name: str,
    outcomes_dir_name: str,
    label: str,
    credentials_env: str | None = None,
) -> int:
    """Every static check, all of them run. Deliberately not short-circuiting
    on the first failure: these are independent problems in different parts
    of a project, and stopping at the first would hide the rest behind as
    many runs as it takes to fix them one by one."""
    readiness = _check_readiness(seal_root, k8s_dir_name, label)
    credentials = _check_credentials(seal_root, label, credentials_env)
    environment = _check_pod_environment(seal_root, k8s_dir_name, label)
    outcomes = _check_outcome_layout(seal_root, outcomes_dir_name, label)
    ownership = _check_outcome_ownership(seal_root, outcomes_dir_name, label)
    return readiness or credentials or environment or outcomes or ownership


def cmd_check(args: list[str]) -> int:
    credentials_env, args = providers.take_credentials_env(args)
    parser = argparse.ArgumentParser(prog="seal check", add_help=False)
    parser.add_argument("--k8s-dir", default=configured_k8s_dir_name(os.environ))
    parser.add_argument("--outcomes-dir", default=configured_outcomes_dir_name(os.environ))
    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print(USAGE, file=sys.stderr)
        return 1

    seal_root = find_seal_root(Path.cwd(), parsed.outcomes_dir)
    return _run_checks(
        seal_root, parsed.k8s_dir, parsed.outcomes_dir, "seal check", credentials_env
    )


# What an untranslated outcome is marked with. Named rather than absent:
# "which promises have no test yet" is the question this listing exists to
# answer, so the answer has to be visible in the column, not inferred from
# a blank.
_TRANSLATED = "translated"
_UNTRANSLATED = "no test yet"


def cmd_outcomes(args: list[str]) -> int:
    """Every outcome the project declares, read straight off the tree.

    This is discovery's way in for anything that isn't Python: a person
    asking what this project actually promises, and -- with
    `--untranslated` -- whatever is working through the promises nothing
    has been written from yet.

    The listing itself stays human-readable. `--untranslated` is the one
    question with a caller that parses an answer (`seal outcomes
    translate`, one promise at a time), so it is the one that got a form
    for one; the rest would be guessing at a shape nothing has asked
    for."""
    parser = argparse.ArgumentParser(prog="seal outcomes", add_help=False)
    parser.add_argument("--outcomes-dir", default=configured_outcomes_dir_name(os.environ))
    parser.add_argument("--untranslated", action="store_true")
    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print(USAGE, file=sys.stderr)
        return 1

    seal_root = find_seal_root(Path.cwd(), parsed.outcomes_dir)
    outcomes = discover_outcomes(seal_root / parsed.outcomes_dir)
    if parsed.untranslated:
        # Slugs and nothing else, including when there are none. A count, a
        # heading or an explanatory line is something every caller has to
        # strip, and one that forgot to would feed it back as an outcome
        # name -- so a tree with every promise translated says so by having
        # nothing to say.
        for outcome in outcomes:
            if not outcome.translated:
                print(outcome.slug)
        return 0

    if not outcomes:
        # Not a failure: a project that has adopted seal without adopting
        # outcome tests is in a perfectly ordinary state.
        print(f"seal outcomes: no outcomes declared under {parsed.outcomes_dir}/.")
        return 0

    width = max(len(outcome.slug) for outcome in outcomes)
    for outcome in outcomes:
        state = _TRANSLATED if outcome.translated else _UNTRANSLATED
        headline = outcome.headline or "(no headline -- see `seal check`)"
        print(f"{outcome.slug:<{width}}  {state:<{len(_UNTRANSLATED)}}  {headline}")

    translated = sum(1 for outcome in outcomes if outcome.translated)
    print(f"\n{len(outcomes)} outcome(s), {translated} translated.")
    _report_unsettled(seal_root, outcomes)
    return 0


def _indented(text: str, indent: str = "  ") -> str:
    """Somebody's own prose, printed under a line of seal's. A quarantine's
    reason is as long as it needs to be, and a second line starting at column
    zero reads as this command's own output rather than as theirs."""
    return "\n".join(f"{indent}{line}" if line else "" for line in text.splitlines())


def _report_unsettled(seal_root: Path, outcomes: list[Outcome]) -> None:
    """Name the promises whose verdict has been changing, and the ones the
    suite has been told not to gate on.

    Under the listing rather than in it: what earns a line is a promise that
    has been both red and green lately without anything deciding which, and
    most trees hold none of those. A column carrying "nothing to say" beside
    every outcome is a column people stop reading.

    Nothing here concludes anything. Whether a promise that keeps flipping is
    a test that is not deterministic, an application that genuinely is, or an
    environment problem is a judgement -- and the change it leads to is one a
    code owner approves like any other."""
    verdicts = recorded_verdicts(seal_root)
    changing = [
        (outcome, flips(verdicts.get(outcome.slug, [])), len(verdicts.get(outcome.slug, [])))
        for outcome in outcomes
    ]
    changing = [entry for entry in changing if entry[1]]
    if changing:
        print(f"\nChanging their mind, over the last {RECENT_RUNS} runs recorded here:")
        for outcome, changes, runs in changing:
            print(f"  {outcome.slug}: {changes} change(s) of verdict in {runs} run(s)")
        print(
            "  A promise that has been red and green lately with nothing deciding which "
            "is not one to send a fix at until something has. `seal outcomes run "
            "--confirm` re-runs a failure on its own from a reset, which is what tells a "
            "test that does not own its data from one that is not deterministic."
        )

    quarantined = [outcome for outcome in outcomes if outcome.quarantined]
    if quarantined:
        print("\nQuarantined, so a failure there does not fail a run:")
        for outcome in quarantined:
            print(f"  {outcome.slug}:")
            print(_indented(outcome.quarantine, "    "))


def _no_such_outcomes(
    unknown: list[str], outcomes: list[Outcome], outcomes_dir_name: str, command: str
) -> int:
    """A slug that names nothing, said out loud along with the ones that do.

    Skipping it silently would leave a typo reporting a green subset of
    nothing, which is indistinguishable from a run where every promise was
    kept -- the one claim these commands must never make by accident. The
    same answer serves whoever asked, so it is worded once."""
    print(
        f"{command}: no outcome named {', '.join(unknown)} under "
        f"{outcomes_dir_name}/. An outcome is named by the three directories that "
        "spell it, `<group>/<epic>/<outcome>`, which is what the tree holds:",
        file=sys.stderr,
    )
    for outcome in outcomes:
        print(f"  {outcome.slug}", file=sys.stderr)
    return 1


def cmd_outcomes_translate(args: list[str]) -> int:
    """Everything needed to compile one promise into a test.

    seal poses the task and checks the answer; it does not write the test,
    and does not start anything that would. A translation is reviewed by a
    code owner either way (/rfcs/0009-outcome-tests.md), so what is actually worth
    seal's doing here is making the task well-posed -- the promise in full,
    the one directory the pairing allows, whichever runner its group
    declares -- and then holding the answer to what can be checked
    mechanically (`seal check`, `seal outcomes run`).

    An outcome that already has a translation needs `--rewrite` said out
    loud. The flag is consent rather than description: what the brief says
    about a replacement it reads off the tree, so asking for one where
    there is nothing to replace simply briefs first authorship."""
    parser = argparse.ArgumentParser(prog="seal outcomes translate", add_help=False)
    parser.add_argument("--outcomes-dir", default=configured_outcomes_dir_name(os.environ))
    parser.add_argument("--rewrite", action="store_true")
    parser.add_argument("slug")
    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print(USAGE, file=sys.stderr)
        return 1

    seal_root = find_seal_root(Path.cwd(), parsed.outcomes_dir)
    outcomes_dir = seal_root / parsed.outcomes_dir
    outcomes = discover_outcomes(outcomes_dir)
    selected, unknown = select(outcomes, [parsed.slug])
    if unknown:
        return _no_such_outcomes(
            unknown, outcomes, parsed.outcomes_dir, "seal outcomes translate"
        )

    outcome = selected[0]
    replacing = bool(outcome.translation)
    if replacing and not parsed.rewrite:
        for line in already_translated(outcome, seal_root):
            print(line, file=sys.stderr)
        return 1

    for line in translation_brief(outcome, outcomes_dir, seal_root, rewrite=replacing):
        print(line)
    return 0


def _unowned_within(seal_root: Path, outcomes_dir: Path, outcome: Outcome):
    """Which paths this outcome's test rests on that a change could reach
    without a human, or None where the repository has no CODEOWNERS at all.

    Its own directory, and the helpers its group shares: a translation
    importing one is as editable as the helper is, so a review that reported
    only the outcome's own files would call a test gated that isn't.

    Read through the same code `seal check` runs, and against the enclosing
    repository rather than the project: a project nested inside a larger repo
    is governed by that repo's file (see codeowners.py, /rfcs/0009-outcome-tests.md).
    A review that answered this question its own way would be telling a
    reviewer something the gate does not agree with."""
    repo_root = find_repository_root(seal_root) or seal_root
    codeowners = find_codeowners(repo_root)
    if codeowners is None:
        return None
    reachable = (outcome.directory, outcomes_dir / outcome.group / HELPERS_DIR_NAME)
    return tuple(
        unowned.path
        for unowned in unowned_outcomes(outcomes_dir, codeowners)
        if any(
            unowned.path == directory or directory in unowned.path.parents
            for directory in reachable
        )
    )


def cmd_outcomes_review(args: list[str]) -> int:
    """A translation and the promise it claims to encode, side by side.

    The mandatory review is the only place a human is asked anything on the
    everything-is-green path, so what it is spent on matters. A change that
    only adds a translation shows the test and not the prompt -- the prompt
    did not change, so it is not in the diff -- while the reviewer's whole
    question is whether the one encodes the other.

    So this renders both, then says what has already been settled
    mechanically -- what runs the test, which files start one, how it waits,
    who can change it -- from the code `seal check` runs rather than from a
    second opinion about the same rules. What it does not do is summarise
    what the test asserts: that is a second thing to review rather than less
    to review, and a summary more generous than the test is the one failure
    a review cannot afford."""
    parser = argparse.ArgumentParser(prog="seal outcomes review", add_help=False)
    parser.add_argument("--outcomes-dir", default=configured_outcomes_dir_name(os.environ))
    parser.add_argument("slug")
    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print(USAGE, file=sys.stderr)
        return 1

    seal_root = find_seal_root(Path.cwd(), parsed.outcomes_dir)
    outcomes_dir = seal_root / parsed.outcomes_dir
    outcomes = discover_outcomes(outcomes_dir)
    selected, unknown = select(outcomes, [parsed.slug])
    if unknown:
        return _no_such_outcomes(
            unknown, outcomes, parsed.outcomes_dir, "seal outcomes review"
        )

    outcome = selected[0]
    if not outcome.translation:
        for line in nothing_to_review(outcome):
            print(line, file=sys.stderr)
        return 1

    unowned = _unowned_within(seal_root, outcomes_dir, outcome)
    for line in review(outcome, outcomes_dir, seal_root, unowned):
        print(line)
    return 0


# How long a run gets to finish before this stops waiting on it. Generous,
# because what is being waited for is a browser driving a real application,
# one outcome at a time: a wait that ran out early would report tests that
# are still running as ones that left no verdict, which reads as broken
# tests. Running out is not fatal either way -- every outcome is reported
# with whatever it had written by then, which for a test still running is
# nothing.
OUTCOME_RUN_TIMEOUT_SECONDS = 600.0

# How long a reset gets. Shorter than a run, because what it waits for is one
# script putting one service's data back rather than a browser working through
# a suite -- but not instant either: a reset that empties and re-migrates a
# database is doing real work before it reports.
RESET_TIMEOUT_SECONDS = 300.0

# How long the results get to come back. Shorter again, because what it waits
# for is a copy out of a container that has finished writing -- files, not
# work. Kept generous enough for a group that leaves traces and video behind,
# and no more: a wait that runs out here is one every run in a session pays,
# and a run is read from what arrived either way.
RESULTS_TIMEOUT_SECONDS = 120.0


def _tilt_run(tilt: str, args: list[str]) -> int:
    """One `tilt` subcommand, its output left going to this terminal: what it
    prints is progress on somebody's own test, and swallowing it would make a
    slow run indistinguishable from a hung one."""
    return subprocess.run([tilt, *args], check=False).returncode


# How often a wait asks the session where it has got to, and how long it
# gives a trigger to start being acted on. A trigger returns as soon as Tilt
# has accepted it, and a resource that was already Ready is still Ready in
# the moment after -- so a wait has to see the work start before it can
# usefully wait for it to finish. Short, because this is the gap between
# "accepted" and "under way", not the work itself; and never fatal, since a
# trigger that changed nothing settles without ever looking busy.
SESSION_POLL_SECONDS = 0.25
STARTING_GRACE_SECONDS = 15.0

# What Tilt reports for a resource with work outstanding, on either half:
# what it takes to update it, and what it takes for what was updated to be
# serving.
BUSY = ("pending", "in_progress")


def _resource_status(tilt: str, resource: str) -> dict:
    """What the session says about one resource, or an empty reading where it
    cannot say. Captured rather than watched, like every other question asked
    of a session."""
    result = subprocess.run(
        [tilt, "get", "uiresource", resource, "-o", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}
    try:
        return (json.loads(result.stdout) or {}).get("status") or {}
    except json.JSONDecodeError:
        return {}


def _is_busy(status: dict) -> bool:
    return status.get("updateStatus") in BUSY or status.get("runtimeStatus") in BUSY


def _wait_for_trigger(
    tilt: str, resource: str, timeout_seconds: float, before: dict | None = None
) -> None:
    """Wait for what a trigger asked for, rather than for the state it was
    already in.

    `tilt wait --for=condition=Ready` is satisfied by a resource that is
    Ready *now*, which a resource triggered a moment ago still is: the run
    then reads results the run it just asked for has not produced, and
    reports a promise as having left no verdict. That is the one thing this
    layer must never do by accident, so the wait watches for the work to
    start and then for it to finish.

    `before` is what the resource looked like before it was asked to work,
    for the case where the asking went through something else -- a reading
    taken after the fact would already carry the change it is watching for.

    A trigger that changes nothing never looks busy, and that is not an
    error: after the grace below, a settled resource is taken at its word.
    """
    started = time.monotonic()
    if before is None:
        before = _resource_status(tilt, resource)
    while time.monotonic() - started < STARTING_GRACE_SECONDS:
        now = _resource_status(tilt, resource)
        if _is_busy(now) or now.get("lastDeployTime") != before.get("lastDeployTime"):
            break
        time.sleep(SESSION_POLL_SECONDS)

    while time.monotonic() - started < timeout_seconds:
        if not _is_busy(_resource_status(tilt, resource)):
            return
        time.sleep(SESSION_POLL_SECONDS)

    # Not fatal, for the reason the timeouts above are not: what a run
    # reports is what each promise actually left behind, and a wait that ran
    # out has not established that anything went wrong.
    print(
        f"seal outcomes run: {resource} was still working after "
        f"{timeout_seconds:.0f}s; reading what it has left so far.",
        file=sys.stderr,
    )


def _select_outcomes(seal_root: Path, slugs: list[str]) -> None:
    """Tell the running session which outcomes a run covers. Tilt watches
    this file, so writing it re-evaluates the Tiltfile and narrows the run;
    an empty file is the whole tree, which is what a session left alone
    runs."""
    selection = seal_root / SELECTION_FILE
    selection.parent.mkdir(parents=True, exist_ok=True)
    selection.write_text("".join(f"{slug}\n" for slug in slugs), encoding="utf-8")


def _session_resources(tilt: str) -> list[str]:
    """Every resource the running session declares, by name.

    Asked of the session rather than worked out from the project, because
    only the evaluated Tiltfile knows which services declared a reset (see
    reset_resources()). Its output is captured rather than left going to the
    terminal, unlike every other `tilt` call here: this one is read, not
    watched."""
    result = subprocess.run(
        [tilt, "get", "uiresource", "-o", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SealError(
            "Error: could not ask the Tilt session what it is running. `--reset` puts "
            "a project's services back inside a session that is already up -- start "
            "one with `seal up` first, and see /rfcs/0004-deterministic-state.md."
        )
    try:
        declared = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SealError(f"Error: could not parse `tilt get uiresource` output: {error}")
    return [
        name
        for item in (declared.get("items") or [])
        if (name := (item.get("metadata") or {}).get("name"))
    ]


def _reset_services(tilt: str) -> None:
    """Put every service that declares a reset back to its baseline, and say
    which ones.

    Said out loud because a reset that found nothing to do and a reset that
    worked look identical from the outside, and the difference is the whole
    reason the next run's result means anything: an outcome run against
    whatever the last one left is measuring both.

    A reset that fails stops the run. An outcome test against a half-restored
    environment reports a promise as broken for something the application
    never did, which is the least useful red there is."""
    resources = reset_resources(_session_resources(tilt))
    if not resources:
        print(
            "seal outcomes run: no service declares a reset, so there is nothing to put "
            "back. A service declares one with `seal_service(reset=...)` -- see "
            "/rfcs/0004-deterministic-state.md."
        )
        return

    print(f"seal outcomes run: resetting {', '.join(resources)}...")
    for resource in resources:
        if _tilt_run(tilt, ["trigger", resource]) != 0:
            raise SealError(
                f"Error: `tilt trigger {resource}` failed, so the run was not started. "
                "An outcome test against a half-reset environment reports a promise as "
                "broken for something the application never did."
            )
        _wait_for_trigger(tilt, resource, RESET_TIMEOUT_SECONDS)


def _tilt_or_fail() -> str:
    """Where a run needs Tilt. Resolved when a container group is actually
    about to be started, rather than up front: a project whose groups all run
    on the machine has no session, and asking it for one before finding out
    whether it needs one would refuse a run that was never going to."""
    tilt = shutil.which("tilt")
    if tilt is None:
        raise SealError(
            "Error: 'tilt' not found on PATH. See https://tilt.dev for install "
            "instructions."
        )
    return tilt


def _run_outcomes(
    seal_root: Path,
    outcomes_dir: Path,
    outcomes: list[Outcome],
    results_root: Path,
    reset: bool = False,
) -> None:
    """Run these outcomes now and bring their results back.

    A group deployed as a container is asked of Tilt, which does exactly what
    a full run does: deploy that group's runner, wait for the `done` its
    readinessProbe watches for, then sync its results out. A `tap` group is
    started here instead, once, and its stream read into the same verdicts
    (see /rfcs/0014-seal-on-seal.md) -- which is why what follows
    is a dispatch rather than a sequence of `tilt` calls.

    A group at a time, in the tree's own order. Outcome tests drive the same
    application, so two groups running at once is the same interference two
    outcomes running at once would be -- each asserting on state the other is
    changing (see /rfcs/0011-outcome-runners.md).

    `reset` puts every service that declares one back to its baseline first,
    so what the run measures is this application rather than this application
    plus whatever the last run left in it. Off unless asked for: this is the
    loop somebody is working in, and throwing away the state they were looking
    at because they re-ran a test is why the reset resource is manual in the
    first place (see /rfcs/0004-deterministic-state.md).

    The local results go next. They are what the report is read from, so a
    verdict left by a previous run is one this run would present as its own --
    and a test that has stopped running at all is exactly when that would
    happen.

    The selection is put back afterwards whatever happens. It exists only
    while a narrowed run is in flight: left behind, it would quietly narrow
    the next run somebody triggered from the Tilt UI, which is the kind of
    surprise that makes a green run mean less than it says."""
    by_group: dict[str, list[Outcome]] = {}
    for outcome in outcomes:
        by_group.setdefault(outcome.group, []).append(outcome)
    deployed = [group for group in by_group if not by_group[group][0].runner.is_tap]

    if reset:
        if deployed:
            _reset_services(_tilt_or_fail())
        else:
            # Nothing here is deployed, so there is no session holding a
            # service whose state a reset would put back. Said rather than
            # done silently: somebody who asked for a baseline and did not
            # get one should hear so before they read the verdicts.
            print(
                "seal outcomes run: nothing in this run is deployed, so there is "
                "no session to reset. A group that runs on the machine starts from "
                "whatever it sets up for itself."
            )

    for outcome in outcomes:
        shutil.rmtree(results_dir_for(results_root, outcome), ignore_errors=True)

    _select_outcomes(seal_root, [outcome.slug for outcome in outcomes])
    try:
        for group, covered in by_group.items():
            runner = covered[0].runner
            if runner.is_tap:
                problems = tap_group.run(
                    runner, covered, seal_root, outcomes_dir, results_root
                )
                for problem in problems:
                    # Reported, and the run carries on. What is wrong with a
                    # runner is not a verdict on any promise, and the
                    # verdicts it did leave are still what the suite reads.
                    print(
                        f"seal outcomes run: {group}'s runner {problem}",
                        file=sys.stderr,
                    )
                continue
            tilt = _tilt_or_fail()
            # What the copy looked like before this run asked for one, so the
            # wait below can tell this run's from the one before it.
            syncback = resource_name(SYNCBACK_PURPOSE, group)
            before_syncback = _resource_status(tilt, syncback)
            for purpose in (RUN_PURPOSE, SYNCBACK_TRIGGER_PURPOSE):
                resource = resource_name(purpose, group)
                if _tilt_run(tilt, ["trigger", resource]) != 0:
                    raise SealError(
                        f"Error: `tilt trigger {resource}` failed. `seal outcomes run "
                        "<slug>` runs an outcome against a session that is already up -- "
                        "start one with `seal up` first, and see "
                        "/rfcs/0010-outcome-tree.md."
                    )
                _wait_for_trigger(tilt, resource, OUTCOME_RUN_TIMEOUT_SECONDS)
            # And then the copy itself. The resource above only asks for one:
            # `tilt trigger` returns as soon as the session has accepted the
            # request, so it is finished while the copy is still going. What
            # a run reads is what the copy brought back, and reading first is
            # reading a directory this run's verdicts have not reached yet --
            # which is reported as promises that left no verdict, about tests
            # that ran and passed.
            _wait_for_trigger(
                tilt, syncback, RESULTS_TIMEOUT_SECONDS, before=before_syncback
            )
    finally:
        _select_outcomes(seal_root, [])


def _confirm_failures(
    seal_root: Path,
    outcomes_dir: Path,
    results: list[OutcomeResult],
    results_root: Path,
) -> list[OutcomeResult]:
    """Run each failing promise again, on its own, from a reset environment,
    and say of each whether it reproduced.

    Both halves of "again" carry weight. From a reset, because a failure
    retried in place is one retried against the state that may have caused it
    -- which is how a shared-state bug gets papered over rather than found. On
    its own, because outcomes run one at a time against the same application,
    each starting from what the one before it left: a promise that fails in
    the suite and holds by itself is a test that doesn't own the data it
    asserts on, which is a third thing again, and neither a regression nor a
    matter of chance.

    Only what was red. A confirmation costs a whole run each, and a passing
    promise has nothing to reproduce.

    Once, never until it passes. Re-running a red test until it goes green is
    the retry this whole layer exists to refuse -- what a second run buys is a
    reason attached to the failure, not a way out of it.

    The first run's results are kept rather than written over. An outcome's
    own directory is where a report sends somebody, and answering "did this
    reproduce?" by destroying what happened the first time leaves the most
    interesting case -- the one that didn't -- with nothing to compare."""
    confirmed = []
    for result in results:
        if not result.is_failure:
            confirmed.append(result)
            continue

        shutil.rmtree(result.first_run_dir, ignore_errors=True)
        if result.results_dir.is_dir():
            result.results_dir.rename(result.first_run_dir)

        print(
            f"seal outcomes run: {result.outcome.slug} did not hold -- running it again "
            "on its own, from a reset, to see whether that reproduces."
        )
        _run_outcomes(
            seal_root, outcomes_dir, [result.outcome], results_root, reset=True
        )
        again = result_for(result.outcome, results_root)
        confirmed.append(
            dataclasses.replace(
                result,
                confirmation=CONFIRMED if again.is_failure else UNCONFIRMED,
            )
        )
    return confirmed


def cmd_outcomes_run(args: list[str]) -> int:
    """What the outcome suite found, one line per promise.

    With no slug named, this reads verdicts rather than running containers:
    what runs them is the Tilt resource that puts each test in front of the
    environment it has to drive, and by the time this is invoked they have
    run and synced their results back (see outcome_suite.py,
    /rfcs/0010-outcome-tree.md). That is the form `seal ci` gates on.

    Naming slugs runs those outcomes first, through the same Tilt resources,
    and reports only them. It is a local loop and nothing else: a subset says
    nothing about the promises it left out, so the report says so in as many
    words rather than leaving a green listing to imply otherwise.

    `--all` runs every promise the tree holds, through those same resources,
    and so leaves nothing out -- the suite's own claim, made about a run this
    command performed rather than one it found. That distinction is the
    reason the two forms say different things about themselves: what `seal
    ci` gates on is the reading, and a form that started containers would
    make the gate's own command mean something different depending on when it
    was called.

    `--confirm` puts a second run behind every failure before anything acts
    on one. It changes no verdict -- a promise this run did not see kept is
    one it did not see kept -- and attaches to each failure whether it
    reproduced, which is what tells a regression from a test nothing can fix
    in the application.

    The exit code is the run's own verdict, which is what makes this usable
    as a gate rather than a listing."""
    parser = argparse.ArgumentParser(prog="seal outcomes run", add_help=False)
    parser.add_argument("--outcomes-dir", default=configured_outcomes_dir_name(os.environ))
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR_NAME)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("slugs", nargs="*")
    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print(USAGE, file=sys.stderr)
        return 1

    seal_root = find_seal_root(Path.cwd(), parsed.outcomes_dir)
    outcomes_dir = seal_root / parsed.outcomes_dir
    results_root = seal_root / parsed.results_dir

    if parsed.all and parsed.slugs:
        # Two different asks, and no reading of the pair that isn't a guess.
        # Guessing "every outcome" spends a run nobody wanted; guessing "the
        # ones named" reports a subset under a flag that says otherwise,
        # which is the one thing this command must never do by accident.
        print(
            "seal outcomes run: `--all` runs every promise the tree holds, so there is "
            "nothing for a slug to add. Name outcomes to run those, or pass `--all` to "
            "run all of them -- not both.",
            file=sys.stderr,
        )
        return 1

    ran_now = parsed.all or bool(parsed.slugs)
    if not ran_now:
        # This form reads verdicts and starts nothing, so a flag about how to
        # run has nothing to act on. Refused rather than ignored: a reset or a
        # confirmation somebody believes happened is one that every verdict
        # read afterwards inherits.
        idle = [
            flag
            for flag, asked in (("--reset", parsed.reset), ("--confirm", parsed.confirm))
            if asked
        ]
        if idle:
            print(
                f"seal outcomes run: {', '.join(idle)} needs outcomes to run. With none "
                "named and no `--all` this reads the verdicts a run already left behind "
                "and starts nothing.",
                file=sys.stderr,
            )
            return 1
        results = suite_results(outcomes_dir, results_root)
        declared = None
        # Unused where nothing ran: this form says only what it found, and
        # makes no claim about where.
        drove_a_session = True
    else:
        outcomes = discover_outcomes(outcomes_dir)
        if parsed.all:
            # Every promise, so nothing is left out and the report carries no
            # caveat -- the same claim the bare form makes, about a run this
            # command performed rather than one it found.
            selected, declared = outcomes, None
        else:
            selected, unknown = select(outcomes, parsed.slugs)
            if unknown:
                return _no_such_outcomes(
                    unknown, outcomes, parsed.outcomes_dir, "seal outcomes run"
                )
            declared = len(outcomes)

        # A promise nothing has been translated from yet has no test to run.
        # Reported rather than refused: "no test yet" is what the listing
        # below already says about it, and it is an ordinary state for a
        # project to be in (see /rfcs/0010-outcome-tree.md).
        runnable = [outcome for outcome in selected if outcome.translated]
        # Whether anything here was deployed, which is what the report may
        # claim about where these promises were checked. A group started on
        # the machine has no session to have been up.
        drove_a_session = any(not outcome.runner.is_tap for outcome in runnable)
        results = [result_for(outcome, results_root) for outcome in selected]
        if runnable:
            _run_outcomes(
                seal_root, outcomes_dir, runnable, results_root, reset=parsed.reset
            )
            results = [result_for(outcome, results_root) for outcome in selected]
            if parsed.confirm:
                results = _confirm_failures(
                    seal_root, outcomes_dir, results, results_root
                )

    if not results:
        # The same non-failure `seal outcomes` treats it as: outcome tests
        # are something a project adopts, not a precondition for running.
        print(f"seal outcomes run: no outcomes declared under {parsed.outcomes_dir}/.")
        return 0

    # Before the report rather than after it, so a run whose report is piped
    # into something that closes the pipe still leaves what it found. What is
    # recorded is per outcome and per run; how often a promise's verdict
    # changed across them is what `seal outcomes` reads back, and the rounds
    # of the loop they make up is what `seal outcomes loop` reads back.
    #
    # `declared` is None exactly where this covered every promise the tree
    # holds -- both the form that read what a run left behind and the one
    # that ran them all -- which is the difference between a round of a loop
    # and somebody iterating on one translation.
    record(seal_root, results, whole_suite=declared is None)

    for line in report(results):
        print(line)
    print(
        f"\n{summary(results, declared, ran_now=ran_now, drove_a_session=drove_a_session)}"
    )

    for result in results:
        if not result.outcome.quarantined:
            continue
        print(
            f"\nseal outcomes run: {result.outcome.slug} is quarantined, so a failure "
            "there did not fail this run. The reason given:"
        )
        print(_indented(result.outcome.quarantine))

    failures = [result for result in results if result.is_failure]
    if not failures:
        return 0

    print(
        f"\nseal outcomes run: {len(failures)} outcome(s) this project promises are not "
        "being kept. An outcome test is the promise itself, not a proxy for one, so this "
        "is the application to fix -- editing a test to agree with it needs a code owner "
        "(see /rfcs/0009-outcome-tests.md).",
        file=sys.stderr,
    )
    for failure in failures:
        where = failure.results_dir.relative_to(seal_root)
        if failure.state == NO_VERDICT:
            print(
                f"  {failure.outcome.slug}: no {VERDICT_FILENAME} to read in {where}/. "
                "Nothing here knows this test ran at all, which a green suite must never "
                "be able to claim on its behalf.",
                file=sys.stderr,
            )
        else:
            print(f"  {failure.outcome.slug}: failed -- see {where}/.", file=sys.stderr)
        if failure.confirmation == CONFIRMED:
            print(
                "    It failed again on its own from a reset, so this is the "
                "application to fix.",
                file=sys.stderr,
            )
        elif failure.confirmation == UNCONFIRMED:
            print(
                "    It held on its own from a reset, so what failed here is not "
                "something an application fix will settle: either the test does not own "
                "the data it asserts on, or it is not deterministic. The run that failed "
                f"is kept in {failure.first_run_dir.relative_to(seal_root)}/, beside the "
                "one that held.",
                file=sys.stderr,
            )

    # A round of a loop is a run of the whole suite; a run naming slugs says
    # nothing about the promises it left out, so it is a round of nothing and
    # gets none of this.
    if declared is None:
        _report_loop_stop(seal_root, outcomes_dir)
    return 1


def _minutes(elapsed) -> int:
    return int(elapsed.total_seconds() // 60)


def _current_loop(seal_root: Path, outcomes_dir: Path):
    """The loop this project is in, the limits it declares, and whatever
    reason that loop has to stop.

    Read from the record every run of the suite appends, so the answer is
    the same whether a run just asked or somebody asked afterwards. A
    mis-declared limit falls back to the backstop here rather than failing:
    `seal check` is where a project is told its config is wrong, and a loop
    reporting nothing because of a typo in a number is a loop nobody hears
    about."""
    limits, _ = read_loop_limits(outcomes_dir)
    current = loop(recorded_runs(seal_root))
    return current, limits, stops(current, limits)


def _why_it_should_stop(current, limits, stops: tuple[str, ...]) -> list[str]:
    """One line per reason this loop has to stop, said plainly enough to be
    read out of the middle of a failing run's output."""
    lines = []
    if current.cycles:
        lines.append(
            "Going in circles: "
            + ", ".join(current.cycles)
            + " -- fixed, and then broken again inside this loop. Keeping one "
            "promise is breaking another, which no number of further rounds settles "
            "by itself."
        )
    if ITERATION_CAP in stops:
        lines.append(
            f"At the backstop: {current.iterations} round(s), which is the limit this "
            f"project declares ('{LOOP_FIELD}.{MAX_ITERATIONS_FIELD}' in "
            f"{CONFIG_FILENAME}, {limits.max_iterations})."
        )
    if TIME_CAP in stops:
        lines.append(
            f"At the backstop: {_minutes(current.elapsed)} minute(s) of looping, which "
            f"is the limit this project declares ('{LOOP_FIELD}.{MAX_MINUTES_FIELD}' "
            f"in {CONFIG_FILENAME}, {limits.max_minutes})."
        )
    return lines


# What a loop with a reason to stop is for. Said the same way wherever it is
# said, because it is the one instruction that matters here: the next round
# is not what settles this, and the session that has been looping is not who
# decides why.
TRIAGE = (
    "Another round is not what settles this. What the sequence needs is a session that "
    "has not been in this loop -- the one that has is the one that has already decided "
    "which promise is at fault. Its conclusion is either that a translation is stale, "
    "which is a change to the tree a code owner approves like any other, or that this "
    "should be satisfiable and isn't, which is a human's to unblock. The instructions "
    "for it ship with seal, as the `seal-loop-triager` subagent; the reasoning is in "
    "/rfcs/0013-regression-loop.md."
)


def _sequence(current) -> list[str]:
    """The loop round by round: what each one fixed, then what that cost.

    The round's number against its first line only. What this is looked at
    for is the shape of the sequence, and a column of repeated numbers is
    what hides it."""
    lines = []
    for number, step in enumerate(current.steps, start=1):
        changed = [("fixed", slug) for slug in step.fixed]
        changed += [("broke", slug) for slug in step.broke]
        if not changed:
            lines.append(f"{number:>3}  nothing changed")
            continue
        for index, (label, slug) in enumerate(changed):
            lines.append(
                f"{number:>3}  {label}  {slug}" if not index else f"     {label}  {slug}"
            )
    return lines


def _report_loop_stop(seal_root: Path, outcomes_dir: Path) -> None:
    """Say, in the middle of a failing run, that this run is part of a loop
    that has a reason to stop -- and carry the sequence, rather than only
    naming the command that would print it.

    Only where there is one. A loop converging normally is what most red runs
    are part of, and a note under every one of them is a note people stop
    reading. Where there is one, this is the moment the state has to be
    surfaced with its reason: a session that has to think of asking a second
    question is a session that goes round again instead."""
    current, limits, stops = _current_loop(seal_root, outcomes_dir)
    if not stops:
        return
    print(file=sys.stderr)
    for line in _why_it_should_stop(current, limits, stops):
        print(f"seal outcomes run: {line}", file=sys.stderr)
    print(file=sys.stderr)
    for line in _sequence(current):
        print(line, file=sys.stderr)
    print(f"\n{TRIAGE}", file=sys.stderr)


def cmd_outcomes_loop(args: list[str]) -> int:
    """What the regression loop this project is in has been doing.

    A loop is derived rather than declared: the rounds of the whole suite
    since the last one in which every promise held. Nothing starts one and
    nothing finishes one, because the bookkeeping cannot depend on the
    session that is thrashing -- the same session that gets no say in triage,
    for the same reason.

    What this produces is evidence, and the report says so by reaching no
    conclusion. Which promise is stale, and whether the application should be
    able to keep all of them at once, is a judgement; the change it leads to
    is a code owner's to approve, like every other change to the tree.

    The exit code is whether this loop has a reason to stop, so a loop can
    branch on it without reading the prose. It is not a verdict on anything:
    the suite's own is what `seal outcomes run` exits with, and a run that
    has gone in circles is red already."""
    parser = argparse.ArgumentParser(prog="seal outcomes loop", add_help=False)
    parser.add_argument("--outcomes-dir", default=configured_outcomes_dir_name(os.environ))
    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print(USAGE, file=sys.stderr)
        return 1

    seal_root = find_seal_root(Path.cwd(), parsed.outcomes_dir)
    outcomes_dir = seal_root / parsed.outcomes_dir
    current, limits, stops = _current_loop(seal_root, outcomes_dir)

    if not current.in_progress:
        # One line for two states that are the same state as far as this is
        # concerned: a project whose suite is passing, and one that has never
        # run it. Neither has anything to triage.
        print(
            "seal outcomes loop: no loop in progress. A loop is the rounds of the "
            "whole suite since the last one in which every promise held, and the "
            "record here holds no round the application still owes anything to."
        )
        return 0

    print(
        f"seal outcomes loop: {current.iterations} round(s) of the whole suite over "
        f"{_minutes(current.elapsed)} minute(s), since the last one in which every "
        "promise held."
    )
    print()
    for line in _sequence(current):
        print(line)

    print("\nStill red after the last round:")
    for slug in current.red:
        print(f"  {slug}")

    if not stops:
        # Said out loud rather than left to the absence of a warning: a loop
        # nobody is watching is exactly the one somebody asks this about, and
        # "no reason to stop yet" is the answer, not silence.
        print(
            f"\nNo reason to stop yet: no promise has been fixed and broken again in "
            f"this loop, and it is inside the backstop this project declares "
            f"({limits.max_iterations} round(s), {limits.max_minutes} minute(s))."
        )
        return 0

    print()
    for line in _why_it_should_stop(current, limits, stops):
        print(line)
    print(f"\n{TRIAGE}")
    return 1


def cmd_outcomes_touched(args: list[str]) -> int:
    """Whether this change has reached the outcome tree.

    The one part of "fix the application, never the test" a checkout can
    answer for itself. CODEOWNERS is what enforces it, at the merge; this is
    what says so now, so a session iterating towards green finds out in the
    round it happened rather than in a review it wasn't expecting.

    It reports. Touching the tree is an ordinary thing to do -- a translation
    has to be written, a promise has to be able to change -- and what it costs
    is a human's approval, not correctness. The exit code says whether
    anything was named, so a loop can branch on it without reading the
    prose."""
    parser = argparse.ArgumentParser(prog="seal outcomes touched", add_help=False)
    parser.add_argument("--outcomes-dir", default=configured_outcomes_dir_name(os.environ))
    parser.add_argument("--since")
    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print(USAGE, file=sys.stderr)
        return 1

    seal_root = find_seal_root(Path.cwd(), parsed.outcomes_dir)
    outcomes_dir = seal_root / parsed.outcomes_dir
    if not outcomes_dir.is_dir():
        # Nothing to touch. The same non-failure every other outcome command
        # treats an unadopted convention as.
        print(
            f"seal outcomes touched: no outcome tree under {parsed.outcomes_dir}/, so "
            "there is nothing here a change could reach."
        )
        return 0

    repo_root = find_repository_root(seal_root)
    if repo_root is None:
        raise SealError(
            f"Error: {seal_root} is not inside a git repository, so there is no change "
            "to read. What a diff would have said is enforced by CODEOWNERS at the "
            "merge either way -- see /rfcs/0009-outcome-tests.md."
        )

    changed = touched(repo_root, outcomes_dir, parsed.since)
    if not changed:
        print(
            "seal outcomes touched: this change reaches nothing under "
            f"{parsed.outcomes_dir}/, so nothing about it needs a code owner on that "
            "account."
        )
        return 0

    print(
        f"seal outcomes touched: {len(changed)} path(s) under {parsed.outcomes_dir}/ "
        "this change reaches:",
    )
    for path in changed:
        print(f"  {path.relative_to(repo_root)}")
    print(
        "\nThat is not a mistake -- a promise has to be able to change, and a "
        "translation has to be written. It is what it costs: this change cannot merge "
        "unattended any more, because a code owner has to approve every one of those "
        "(see /rfcs/0009-outcome-tests.md). If what was wanted was a fix to the "
        "application, the fix is not there yet."
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    if not argv:
        print(USAGE, file=sys.stderr)
        return 1

    subcommand, rest = argv[0], argv[1:]
    try:
        if subcommand == "run":
            return cmd_run(rest)
        if subcommand == "up":
            return cmd_up(rest)
        if subcommand == "ci":
            return cmd_ci(rest)
        if subcommand == "check":
            return cmd_check(rest)
        if subcommand == "outcomes":
            if rest and rest[0] == "run":
                return cmd_outcomes_run(rest[1:])
            if rest and rest[0] == "translate":
                return cmd_outcomes_translate(rest[1:])
            if rest and rest[0] == "review":
                return cmd_outcomes_review(rest[1:])
            if rest and rest[0] == "touched":
                return cmd_outcomes_touched(rest[1:])
            if rest and rest[0] == "loop":
                return cmd_outcomes_loop(rest[1:])
            return cmd_outcomes(rest)
        if subcommand == EMIT_ENV_SUBCOMMAND:
            return cmd_emit_env(rest)
        if subcommand == "_tests-verdict":
            return cmd_tests_verdict(rest)
        if subcommand == "_tests-results":
            return cmd_tests_results(rest)
        if subcommand == "_report":
            return cmd_report(rest)
        print(USAGE, file=sys.stderr)
        return 1
    except SealError as error:
        print(error, file=sys.stderr)
        return 1
    except OSError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
