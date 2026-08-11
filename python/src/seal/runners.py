"""What runs a group of outcome tests, and how a project declares it.

An outcome test is a container (see outcomes.py): an image built from the
outcome tree, run against the environment `seal ci` brought up, and told
which outcomes to run. What that image is depends on what the promises look
like -- a promise about what somebody sees is tested through a browser, and
a promise an API-only service makes is tested by talking to the API.

So a project's outcomes are grouped, one group per runner, and the grouping
is a directory:

    outcomes/
      seal-test-config.json
      <group>/
        <epic>/
          <outcome>/

`seal-test-config.json` is the whole declaration. Its `runner` list holds
one object per group, and the object's `name` is the directory that group's
epics sit in:

    {
      "runner": [
        {"name": "ui", "runner_type": "playwright"},
        {
          "name": "api",
          "runner_type": "custom",
          "dockerfile": "api/Dockerfile",
          "runner_args": ["--strict"]
        }
      ]
    }

The tree is still what declares the outcomes -- walking it is the whole of
discovery, and an outcome added later is covered by having been added. What
the config declares is the much smaller thing a walk cannot answer: which
image to build for a directory, since nothing about a directory of
promises says what runs them.

That the two have to agree is therefore a real cost, and it is paid where
it is cheapest to notice: `seal check` refuses a group directory no runner
names and a runner naming no directory, so a tree and a config that have
drifted apart fail before a run does.

`runner_args` is how a project says what its runner needs and seal does not
know: they reach the container ahead of the slugs it has to run (see
/rfcs/0011-outcome-runners.md for the argument list in full).
"""

import json
from dataclasses import dataclass
from pathlib import Path

# Where a project declares what runs each group of its outcomes. At the
# outcome tree's root, one file: a run of the suite builds every runner the
# project has, so what they are has to be readable in one place rather than
# gathered from a walk.
CONFIG_FILENAME = "seal-test-config.json"

# What the config carries. `runner` is singular and holds a list, because it
# reads as the kind of thing each entry is; `loop` is a single object, since
# a project has one regression loop however many runners it has.
RUNNER_FIELD = "runner"
LOOP_FIELD = "loop"

NAME_FIELD = "name"
RUNNER_TYPE_FIELD = "runner_type"
DOCKERFILE_FIELD = "dockerfile"
DOCKERFILE_CONTEXT_FIELD = "dockerfile_context"
RUNNER_ARGS_FIELD = "runner_args"

# A runner seal supplies: it builds the image, and a translation is whatever
# that image collects. One name per kind of promise, so a project that
# writes browser tests never writes a Dockerfile to get a browser.
PLAYWRIGHT = "playwright"

# A runner the project supplies, as a Dockerfile seal builds and nothing
# more. This is what keeps the tree language-agnostic rather than merely
# broad -- a worker, a command-line tool, anything with no page to open.
CUSTOM = "custom"

# A runner seal starts on the machine rather than in the cluster, once
# for the whole group, reading its verdicts off a TAP stream (see
# /rfcs/0014-seal-on-seal.md). It is for promises about the layer
# *beneath* a session -- bringing an environment up, refusing to start,
# resolving a `.env` before any pod exists -- which nothing running inside
# that session can answer.
#
# It is seal's in the sense `playwright` is: no image for a project to
# bring. It is the project's in the sense `custom` is: what the group's
# executable starts is the project's business, and seal reads the
# stream rather than the tree.
TAP = "tap"

# What a project declares about where its regression loop stops. Two limits,
# both backstops (see /rfcs/0013-regression-loop.md): cycle detection
# catches a loop ping-ponging between a few promises, and neither catches a
# chain where every round breaks something never seen before.
MAX_ITERATIONS_FIELD = "max_iterations"
MAX_MINUTES_FIELD = "max_minutes"

# What a project that declares nothing gets. These are not measurements --
# nothing has measured a loop, and a number picked before anything has is
# guidance dressed as a rule. They are chosen to sit past any loop that is
# converging, by a margin wide enough that a project which has never thought
# about them is not fighting them: a loop that is getting somewhere does it
# in a handful of rounds, and one still going after three hours is worth a
# person's attention whatever its round count says.
#
# A project that has measured its own loop replaces them in one place. That
# is the point of their being declared at all.
DEFAULT_MAX_ITERATIONS = 10
DEFAULT_MAX_MINUTES = 180

# The runners seal supplies an image or an invocation for, so a project
# declaring one brings no Dockerfile.
BUILT_IN_RUNNER_TYPES = (PLAYWRIGHT, TAP)
RUNNER_TYPES = (*BUILT_IN_RUNNER_TYPES, CUSTOM)

DOCKERFILE_FILENAME = "Dockerfile"

# What a 'tap' group is started through, at the group's own root. A
# convention rather than a field in the config, for the reason the tree is a
# tree: what a project declares is its structure, and a path named in two
# places is two places to keep in agreement (see
# /rfcs/0002-declaration-by-structure.md). A 'custom' group's Dockerfile is
# found the same way.
TAP_RUNNER_FILENAME = "run"

# What separates a runner's own arguments from the outcomes it has to run.
# Every runner is started with `<runner_args...> -- <slug>...`, so one that
# takes no arguments still reads its outcomes from one fixed place, and one
# that does never has to tell a flag from a slug (see
# /rfcs/0011-outcome-runners.md). The Starlark half spells it too, for the
# container runners it starts.
ARGUMENT_SEPARATOR = "--"


@dataclass(frozen=True)
class Runner:
    """One group of outcomes, and the image that runs them."""

    # The group directory this runner drives, relative to the outcome tree.
    name: str
    runner_type: str
    # What to build, both relative to the outcome tree's root, and both None
    # for a runner seal supplies. Resolved here rather than at each use: a
    # default spelled in two places is a default that stops agreeing.
    dockerfile: str | None
    dockerfile_context: str | None
    # What this runner needs said to it, ahead of the outcomes it is given.
    runner_args: tuple[str, ...]

    @property
    def is_custom(self) -> bool:
        """Does this runner's image come out of a Dockerfile the project
        brought? Only `custom` does, which is what makes the two build
        fields its alone."""
        return self.runner_type == CUSTOM

    @property
    def is_tap(self) -> bool:
        """Is this group started on the machine, once, and read off a
        stream?"""
        return self.runner_type == TAP

    @property
    def reads_its_own_translations(self) -> bool:
        """Does seal know what this runner would collect?

        True only for `playwright`, whose testMatch seal knows because
        it wrote the config. A `custom` runner's image and a `tap` group's
        executable are the project's, and what they start is theirs to say --
        which is the whole point of declaring either. So the rules that turn
        on seal being able to read a translation stop applying, and the
        project is taken at its word (see /rfcs/0011-outcome-runners.md).
        """
        return not (self.is_custom or self.is_tap)

    @property
    def keeps_files_beside_its_epics(self) -> bool:
        """May this group hold files at its own level, alongside its epics?

        A `custom` runner's build context is the group's directory and a
        `tap` group's executable sits in it, so for both the answer is yes.
        Under `playwright` a file there is one nothing would ever collect,
        which is why it is refused rather than passed over.
        """
        return self.is_custom or self.is_tap


@dataclass(frozen=True)
class Limits:
    """Where a project's regression loop stops, whether it said so or not."""

    max_iterations: int
    max_minutes: int


DEFAULT_LIMITS = Limits(
    max_iterations=DEFAULT_MAX_ITERATIONS, max_minutes=DEFAULT_MAX_MINUTES
)


def config_path(outcomes_dir: Path) -> Path:
    """Where a project declares its runners, whether or not it has yet."""
    return outcomes_dir / CONFIG_FILENAME


def _relative_path_problem(field: str, value: object) -> str | None:
    """Why this value can't be a path inside the outcome tree, or None.

    Absolute paths and `..` are refused rather than resolved. The build
    context is what a runner's image is made of, and one reaching outside
    the tree makes the image depend on a checkout's surroundings -- which is
    exactly the reproducibility the environment layer exists to give.
    """
    if not isinstance(value, str) or not value:
        return f"'{field}' has to be a path inside the outcome tree, as a string."
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return (
            f"'{field}' is {value!r}, which reaches outside the outcome tree. It has "
            "to be a relative path inside it, so the image is built from the tree "
            "and nothing around it."
        )
    return None


def _parse_runner(entry: object, index: int) -> tuple[Runner | None, list[str]]:
    """One `runner` entry, and everything wrong with it.

    Every problem with an entry is returned, not the first: a project should
    be able to put its config right in one pass.
    """
    where = f"{RUNNER_FIELD}[{index}]"
    if not isinstance(entry, dict):
        return None, [f"{where} is not an object."]

    problems: list[str] = []

    name = entry.get(NAME_FIELD)
    if not isinstance(name, str) or not name:
        problems.append(
            f"{where} has no '{NAME_FIELD}' -- the directory this runner's epics sit "
            "in, relative to the outcome tree."
        )
        name = None

    runner_type = entry.get(RUNNER_TYPE_FIELD)
    if not isinstance(runner_type, str) or not runner_type:
        problems.append(
            f"{where} has no '{RUNNER_TYPE_FIELD}' -- one of "
            f"{', '.join(RUNNER_TYPES)}."
        )
        runner_type = None
    elif runner_type not in RUNNER_TYPES:
        problems.append(
            f"{where}: '{RUNNER_TYPE_FIELD}' is {runner_type!r}, which seal has no "
            f"runner for. Known types are {', '.join(RUNNER_TYPES)}; '{CUSTOM}' is "
            "the one that takes a Dockerfile of the project's own."
        )
        runner_type = None

    dockerfile = entry.get(DOCKERFILE_FIELD)
    context = entry.get(DOCKERFILE_CONTEXT_FIELD)
    if runner_type is not None and runner_type != CUSTOM:
        for field, value in (
            (DOCKERFILE_FIELD, dockerfile),
            (DOCKERFILE_CONTEXT_FIELD, context),
        ):
            if value is not None:
                problems.append(
                    f"{where}: '{field}' is set on a '{runner_type}' runner, whose "
                    f"image is seal's. Only '{CUSTOM}' builds a Dockerfile the "
                    "project brings, so this line would be read by nothing."
                )
    else:
        for field, value in (
            (DOCKERFILE_FIELD, dockerfile),
            (DOCKERFILE_CONTEXT_FIELD, context),
        ):
            if value is None:
                continue
            problem = _relative_path_problem(field, value)
            if problem is not None:
                problems.append(f"{where}: {problem}")

    runner_args = entry.get(RUNNER_ARGS_FIELD)
    if runner_args is None:
        runner_args = []
    elif not isinstance(runner_args, list) or not all(
        isinstance(argument, str) for argument in runner_args
    ):
        problems.append(
            f"{where}: '{RUNNER_ARGS_FIELD}' has to be a list of strings -- they "
            "reach the container as arguments, ahead of the outcomes it is told to "
            "run."
        )
        runner_args = []

    unknown = sorted(
        key
        for key in entry
        if key
        not in (
            NAME_FIELD,
            RUNNER_TYPE_FIELD,
            DOCKERFILE_FIELD,
            DOCKERFILE_CONTEXT_FIELD,
            RUNNER_ARGS_FIELD,
        )
    )
    if unknown:
        problems.append(
            f"{where}: {', '.join(repr(key) for key in unknown)} is not something a "
            "runner declares. A misspelled field reads as a default nobody asked "
            "for, which is the one config mistake a run cannot report."
        )

    if problems:
        return None, problems

    if runner_type == CUSTOM:
        resolved_dockerfile = dockerfile or f"{name}/{DOCKERFILE_FILENAME}"
        resolved_context = context if context is not None else name
    else:
        resolved_dockerfile = None
        resolved_context = None

    return (
        Runner(
            name=name,
            runner_type=runner_type,
            dockerfile=resolved_dockerfile,
            dockerfile_context=resolved_context,
            runner_args=tuple(runner_args),
        ),
        [],
    )


def _document(outcomes_dir: Path) -> tuple[object | None, str | None]:
    """What the config file holds, whatever shape that turns out to be --
    None where the project has no config file, and a problem where there is
    one and it cannot be read.

    A tree with no config file at all is not a problem here. Whether that is
    a mistake depends on whether there is a tree to run, which is the
    caller's question and not this one's (see outcomes.py's
    outcome_layout_problems).
    """
    path = config_path(outcomes_dir)
    if not path.is_file():
        return None, None
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        return None, f"cannot be read as JSON: {error}"


def _limit_problem(field: str, value: object) -> str | None:
    """Why this value can't be a limit, or None.

    Whole units only, and above zero. A cap of zero is a loop that has
    already stopped before it started, and a negative one is a number nobody
    meant -- both read as "this project declared something" while behaving
    like nothing a project would ask for.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return (
            f"'{field}' has to be a whole number above zero. A loop is counted in "
            "rounds and in minutes, and both are whole."
        )
    if value <= 0:
        return (
            f"'{field}' is {value}, which is a loop that stops before it starts. It "
            "has to be above zero -- a project that wants no backstop at all is one "
            "declaring a number large enough to say so."
        )
    return None


def read_loop_limits(outcomes_dir: Path) -> tuple[Limits, list[str]]:
    """Where this project says its regression loop stops, and everything
    wrong with how it said it.

    A project that declares nothing gets seal's defaults and no problem: a
    backstop is not something an adopting project should have to write down
    before its first loop.

    Only the `loop` block's own problems are reported. A file that is not
    JSON, or not an object, is `read_runner_config`'s to complain about --
    reported here as well, it would be printed twice for one mistake.
    """
    document, _ = _document(outcomes_dir)
    if not isinstance(document, dict):
        return DEFAULT_LIMITS, []

    declared = document.get(LOOP_FIELD)
    if declared is None:
        return DEFAULT_LIMITS, []
    if not isinstance(declared, dict):
        return DEFAULT_LIMITS, [
            f"'{LOOP_FIELD}' has to be an object holding "
            f"'{MAX_ITERATIONS_FIELD}' and '{MAX_MINUTES_FIELD}'."
        ]

    problems: list[str] = []
    values = {
        MAX_ITERATIONS_FIELD: DEFAULT_MAX_ITERATIONS,
        MAX_MINUTES_FIELD: DEFAULT_MAX_MINUTES,
    }
    # Every problem, not the first: a project should be able to put its
    # config right in one pass, the same way a runner entry's are reported.
    for field in values:
        value = declared.get(field)
        if value is None:
            continue
        problem = _limit_problem(field, value)
        if problem is None:
            values[field] = value
        else:
            problems.append(f"{LOOP_FIELD}: {problem}")

    unknown = sorted(key for key in declared if key not in values)
    if unknown:
        problems.append(
            f"{LOOP_FIELD}: {', '.join(repr(key) for key in unknown)} is not "
            f"something it declares. It holds '{MAX_ITERATIONS_FIELD}' and "
            f"'{MAX_MINUTES_FIELD}'; a misspelled one reads as a default nobody "
            "asked for, which is the one config mistake a run cannot report."
        )

    return (
        Limits(
            max_iterations=values[MAX_ITERATIONS_FIELD],
            max_minutes=values[MAX_MINUTES_FIELD],
        ),
        problems,
    )


def read_runner_config(outcomes_dir: Path) -> tuple[list[Runner], list[str]]:
    """Every runner this project declares, and everything wrong with the
    declaration -- along with whatever is wrong with the file itself, which
    is reported here rather than by every reader of it.

    A tree with no config file at all comes back empty rather than as a
    problem (see _document above).
    """
    document, problem = _document(outcomes_dir)
    if problem is not None:
        return [], [problem]
    if document is None:
        return [], []

    if not isinstance(document, dict):
        return [], [
            f"is not a JSON object. It holds '{RUNNER_FIELD}', a list with one entry "
            f"per group of outcomes, and '{LOOP_FIELD}', where the regression loop "
            "stops."
        ]

    entries = document.get(RUNNER_FIELD)
    if entries is None:
        return [], [
            f"declares no '{RUNNER_FIELD}' -- the list of what runs each group of "
            "outcomes, one entry per directory in the tree."
        ]
    if not isinstance(entries, list):
        return [], [f"'{RUNNER_FIELD}' has to be a list, one entry per group."]

    unknown = sorted(key for key in document if key not in (RUNNER_FIELD, LOOP_FIELD))
    problems = (
        [
            f"{', '.join(repr(key) for key in unknown)} is not something this file "
            f"declares. It holds '{RUNNER_FIELD}' and '{LOOP_FIELD}', and nothing "
            "else."
        ]
        if unknown
        else []
    )

    runners: list[Runner] = []
    for index, entry in enumerate(entries):
        runner, entry_problems = _parse_runner(entry, index)
        problems.extend(entry_problems)
        if runner is not None:
            runners.append(runner)

    seen: dict[str, int] = {}
    for index, runner in enumerate(runners):
        if runner.name in seen:
            problems.append(
                f"{RUNNER_FIELD}[{index}] names '{runner.name}', which "
                f"{RUNNER_FIELD}[{seen[runner.name]}] already runs. A group of "
                "outcomes has one runner, so which of the two started a test would "
                "be whichever was read last."
            )
        else:
            seen[runner.name] = index

    return runners, problems
