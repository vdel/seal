# A project's outcome tests, as Tilt resources.
#
# An outcome test runs as a container (see /rfcs/0010-outcome-tree.md), driving the
# running environment and leaving a verdict behind. This is what puts those
# containers in front of an environment that is actually up, and what gathers
# what they left.
#
# One runner per group of outcomes, not one per outcome. A run is one
# container per group either way, and it is told which outcomes to run: the
# whole group under `seal ci`, or the ones somebody named under
# `seal outcomes run`. That is what makes a subset cheap -- the image is
# built once, and the browser installed in it once, however many promises a
# group holds.
#
# A project's promises are not all of one kind, so neither are the images that
# test them. `seal-test-config.json` at the outcome tree's root lists one
# runner per group directory: 'playwright' is seal's own -- Chromium, a pinned
# framework and the reporting below -- and 'custom' builds a Dockerfile the
# project brings, for a group whose outcomes are not browser-shaped.
#
# Walking the tree is still what finds the outcomes, here as in the Python
# half -- an outcome added later is covered by having been added. The config
# answers only what a walk cannot: which image to build for a directory.
#
# One resource reports the whole run, separate from the ones that perform it.
# `tilt ci` stops at the first resource that fails, and "every promise still
# holds" has to be distinguishable from "the one test somebody was looking at
# passed" -- so every outcome's verdict is read together, by
# `seal outcomes run`, after every group has finished.
load('./config.Tiltfile', 'run_outcomes', 'PROJECT_ROOT', 'seal_cli')
load('./resources.Tiltfile', 'seal_resource_name')
load('./tests.Tiltfile', 'LOCAL_TESTS_RESULTS', 'SYNCBACK_RSYNC_OPTIONS')
load('ext://__seal_syncback', 'syncback')  # After config: it registers this alias, and allow_k8s_contexts

# Where the tree is, and what the layout fixes inside it. The same names the
# Python half reads (python/src/seal/outcomes.py,
# python/src/seal/runners.py)
# -- a project that moves its tree tells both through one environment
# variable, since `seal ci` hands every argument it is given straight to
# `tilt ci` and has none of its own to spend.
OUTCOMES_DIR_ENV_VAR = 'SEAL_OUTCOMES_DIR'
DEFAULT_OUTCOMES_DIR = 'outcomes'
CONFIG_FILENAME = 'seal-test-config.json'
DOCKERFILE_FILENAME = 'Dockerfile'

# The two files in an outcome's directory that are seal's rather than the
# translation's: the promise, and the note saying this outcome is quarantined.
# Skipped when working out whether there is a test here, the same way
# python/src/seal/outcomes.py skips them -- a promise carrying nothing but one
# of these would otherwise be started as though something had been written
# from it.
PROMPT_FILENAME = 'prompt.md'
QUARANTINE_FILENAME = 'quarantine.md'
SEAL_S_OWN_FILES = [PROMPT_FILENAME, QUARANTINE_FILENAME]

# What a group's tests share, at the group's root. It holds no promises, so
# nothing below it is an outcome to run -- and a run told to start one would
# be pointed at a directory its runner collects nothing from.
#
# Nothing has to put it in the image: a runner is built from the group's own
# directory, so this is in the build context already, beside every outcome
# that imports it.
HELPERS_DIR_NAME = 'helpers'

# The fields a runner declares, and the two kinds there are. 'playwright' is
# an image seal builds; 'custom' is one the project brings. A runner_type
# this doesn't know is skipped here and reported by `seal check`, which is
# the half that can explain itself.
RUNNER_FIELD = 'runner'
NAME_FIELD = 'name'
RUNNER_TYPE_FIELD = 'runner_type'
DOCKERFILE_FIELD = 'dockerfile'
DOCKERFILE_CONTEXT_FIELD = 'dockerfile_context'
RUNNER_ARGS_FIELD = 'runner_args'
PLAYWRIGHT_RUNNER = 'playwright'
CUSTOM_RUNNER = 'custom'

# The runner types this file builds a container for. A 'tap' group is
# deliberately not among them: seal starts it on the machine, once for
# the whole group, and reads its verdicts off a stream (see
# /rfcs/0014-seal-on-seal.md). There is no image to build and no
# Deployment to declare, so a session registers nothing for it and
# `seal outcomes run` starts it without Tilt.
#
# Skipped by name rather than by falling through the unknown-type branch, so
# a group nothing here registers is a decision a reader can find rather than
# something that happens to work out.
CONTAINER_RUNNERS = [PLAYWRIGHT_RUNNER, CUSTOM_RUNNER]

# What the 'playwright' runner collects, which is Playwright's own default
# testMatch. The same rule python/src/seal/outcomes.py applies when it
# decides whether an outcome has been translated -- one that disagreed would
# have the run start an outcome the listing calls untranslated, or skip one
# it calls translated.
SPEC_SUFFIXES = [
    '.{}.{}'.format(kind, extension)
    for kind in ['spec', 'test']
    for extension in ['ts', 'js', 'mjs', 'cjs', 'mts', 'cts', 'tsx', 'jsx']
]

# What a runner writes, and where. Fixed rather than declared: seal defines
# what an outcome test is, so it can define where one puts its result --
# unlike a service's own test stage, where there is no one convention every
# project's Dockerfile already follows.
#
# One directory per outcome, named `<epic>/<outcome>` -- the runner's own
# half of a slug, since a runner is built from one group and never has to
# know the others exist. What keeps two groups' results apart is that each
# group syncs back into its own directory below.
#
# A run that finished has to be distinguishable from one that died after the
# third of twenty, which is what the `done` marker says and nothing else can.
CONTAINER_RESULTS_DIR = '/outcome-results/'
VERDICT_FILENAME = 'passed'
DONE_FILENAME = 'done'

# Where those results reach the project: beside each service's own, so one
# artifact carries both (see /rfcs/0005-service-tests.md).
LOCAL_OUTCOMES_RESULTS = os.path.join(LOCAL_TESTS_RESULTS, 'outcomes')

# Where the application answers, as an outcome test reaches it from inside
# the cluster. The project says it -- seal knows nothing about an app's own
# service names or ports -- and every runner gets it, its own as much as
# seal's, so a test never has to hardcode an address to be reachable.
BASE_URL_ENV_VAR = 'SEAL_BASE_URL'

# What separates a runner's own arguments from the outcomes it has to run.
# The container is started with `<runner_args...> -- <slug...>`, so a runner
# that takes no arguments still reads its outcomes from one fixed place, and
# one that does never has to tell a flag from a slug.
#
# Named explicitly rather than left for the runner to resolve: seal knows
# which outcomes have been translated and the runner does not, and a runner
# that resolved "everything in the group" for itself would start promises
# nobody has written a test for yet and report them failed.
ARGUMENT_SEPARATOR = '--'

# How `seal outcomes run <slug>...` narrows a run without restarting the
# session: it writes the slugs here and Tilt re-evaluates, because a file
# read through read_file() is a file Tilt watches. A Tiltfile argument would
# be the other way, and `tilt args` replaces every argument a session was
# started with -- including the `--build_type test` that decides what
# `seal ci` is even building.
#
# Under .workspace/, which is where everything seal generates into a project
# already goes, and which a project already ignores.
SELECTION_FILE = os.path.join('.workspace', 'seal', 'outcomes-selection')

# What every Kubernetes object a run needs is called, one per group. A
# DNS-1123 label: a group name is lowercase letters, digits and single
# hyphens (`seal check` refuses anything else), so this needs nothing done
# to it.
K8S_NAME_PREFIX = 'seal-outcomes-'

RUN_PURPOSE = 'outcome_tests'
SYNCBACK_PURPOSE = 'outcome_syncback'
SYNCBACK_TRIGGER_PURPOSE = 'outcome_syncback_trigger'

# The one resource there is only ever one of per project, whatever a project
# has runners: what the whole suite found (see resources.Tiltfile).
REPORT_RESOURCE = seal_resource_name('outcomes')

# The 'playwright' runner's framework, and through it the browser: Playwright
# installs the build of Chromium that this release drives, so one version
# spells both and a mismatch is a browser that refuses to launch rather than
# a promise that fails.
PLAYWRIGHT_VERSION = '1.62.1'

# A slim Node base with Chromium installed into it, rather than the official
# `mcr.microsoft.com/playwright` image. That image carries Chromium, Firefox
# and WebKit -- around 2.2GB -- and the config below launches Chromium and
# nothing else, so two of the three are freight.
#
# Freight that is paid for three times over on one machine: the daemon that
# builds the image, the registry it is pushed to, and the node that pulls it.
# On a CI runner already holding a Kubernetes cluster, a build cache and the
# application's own images, that is the difference between a run and a runner
# that dies partway through one.
PLAYWRIGHT_BASE_IMAGE = 'node:22-bookworm-slim'

# Which directory the generated config reports into, named per outcome by the
# entrypoint below.
RESULTS_ENV_VAR = 'SEAL_OUTCOME_RESULTS'

# What every runner has to do, and what the 'playwright' one does so a
# project using it never has to: run each outcome it was given, write that
# outcome's verdict, print the log where `tilt` and `kubectl logs` show it,
# say when the whole run has finished, and stay up so the results can be
# copied out.
#
# Never exit on failure -- that would take the run's own resource down with
# it and stop at the first red promise, which is exactly the run reporting
# one test instead of all of them.
#
# The arguments before `--` reach `playwright test` as words. They are flags
# a project wrote for a command line, which is what a command line does with
# them; the outcomes after it stay exactly as given, and those are the part
# seal generates.
#
# The trailing slash on the path filter is what keeps `a-deleted-item` from
# also running `a-deleted-item-and-more`: Playwright matches a positional
# argument against the whole file path, so an outcome's directory has to be
# spelled as a directory.
#
# A raw string: every backslash in here is the Dockerfile's own -- a line
# continuation, or the `\n` printf writes -- and Starlark would otherwise
# read them as escapes and hand Docker one long line with real newlines in
# the middle of a format string.
PLAYWRIGHT_DOCKERFILE = r'''
FROM {base_image}

WORKDIR /outcome

# --with-deps installs the system libraries Chromium needs on this base, so
# the image is self-contained without pulling in the other two browsers.
RUN npm init -y > /dev/null \
 && npm install --no-audit --no-fund --save-exact @playwright/test@{version} \
 && npx playwright install --with-deps chromium

# Where this outcome's results go is read at run time rather than baked in:
# one container runs several outcomes, each reporting into its own directory.
#
# A failure leaves a video and a screenshot behind, under `outputDir` and so
# inside the results that sync back to the project. What a red promise costs
# somebody is working out what the browser actually did, and a recording of
# it answers that in a way a stack trace cannot -- an assertion that timed
# out waiting for a selector says the same thing whether the page never
# loaded, loaded the wrong thing, or loaded the right thing behind a dialog.
#
# On failure only, so a green suite pays a recording it deletes and nothing
# else. A `trace` is deliberately not on: it is the better debugging tool and
# it is megabytes per test, viewable only by loading it into Playwright's own
# viewer -- so it is left to a project that wants it, through
# `runner_args: ["--trace", "retain-on-failure"]` in its seal-test-config.json.
RUN printf '%s\n' \
  "const results = process.env.{results_var} || '{results}';" \
  "module.exports = {{" \
  "  testDir: '/outcome/tests'," \
  "  outputDir: results + '/artifacts'," \
  "  workers: 1," \
  "  use: {{" \
  "    baseURL: process.env.{base_url_var}," \
  "    launchOptions: {{ args: ['--no-sandbox', '--disable-dev-shm-usage'] }}," \
  "    video: 'retain-on-failure'," \
  "    screenshot: 'only-on-failure'," \
  "  }}," \
  "  reporter: [" \
  "    ['list']," \
  "    ['junit', {{ outputFile: results + '/junit.xml' }}]," \
  "    ['html', {{ outputFolder: results + '/report', open: 'never' }}]," \
  "  ]," \
  "}};" \
  > /outcome/playwright.config.js

# The contract every runner meets, in one loop. Written to a file rather than
# spelled into ENTRYPOINT so it can quote what it has to quote -- a JSON exec
# form is one string, and a quote inside it would end it.
RUN printf '%s\n' \
  '#!/bin/sh' \
  'args=' \
  'while [ $# -gt 0 ] && [ "$1" != "{separator}" ]; do args="$args $1"; shift; done' \
  '[ "$1" = "{separator}" ] && shift' \
  'for slug in "$@"; do' \
  '  results={results}$slug' \
  '  mkdir -p $results' \
  '  if {results_var}=$results npx playwright test $args tests/$slug/ > $results/log.txt 2>&1; then' \
  '    verdict=1' \
  '  else' \
  '    verdict=0' \
  '  fi' \
  '  cat $results/log.txt' \
  '  echo $verdict > $results/{verdict}' \
  'done' \
  'touch {results}{done}' \
  'sleep infinity' \
  > /outcome/run.sh \
 && chmod +x /outcome/run.sh

COPY . /outcome/tests/

ENTRYPOINT ["/outcome/run.sh"]
'''


def _outcomes_dir():
    return os.path.join(
        PROJECT_ROOT, os.getenv(OUTCOMES_DIR_ENV_VAR, '') or DEFAULT_OUTCOMES_DIR,
    )


# How far below an outcome this will look for a file belonging to it. A test
# keeping its fixtures and helpers beside itself is ordinary; twenty levels of
# them is a tree that has gone wrong, and Starlark has no unbounded loop to
# walk one with anyway.
_MAX_NESTING = 20


def _outcome_containing(path, group_dir):
    """The `[epic, outcome]` this file belongs to within its group, or None
    where it sits at a depth the layout has no reading for. Walks up rather
    than splitting a prefix off, so nothing here depends on `listdir()`
    spelling a path the same way the caller spelled the directory."""
    directory = os.path.dirname(path)
    for _ in range(_MAX_NESTING):
        if directory == group_dir:
            return None
        parent = os.path.dirname(directory)
        if parent == group_dir or parent == directory:
            # Directly inside an epic, or run off the top of the group.
            return None
        if os.path.dirname(parent) == group_dir:
            return [os.path.basename(parent), os.path.basename(directory)]
        directory = parent
    return None


def _is_spec(filename):
    for suffix in SPEC_SUFFIXES:
        if filename.endswith(suffix):
            return True
    return False


def _runner_name(runner):
    return runner[0]


def _runner_args(entry):
    """What this runner needs said to it, ahead of the outcomes it has to
    run. Only strings: these reach a container as arguments, and anything
    else is a field `seal check` explains rather than something to guess a
    spelling for."""
    declared = entry.get(RUNNER_ARGS_FIELD, [])
    if type(declared) != 'list':
        return []
    return [argument for argument in declared if type(argument) == 'string']


def _path_field(entry, field, default):
    """A path a runner declared, relative to the outcome tree, or the default
    it stands in for. Anything that is not a string is the default: what a
    misspelled path means is `seal check`'s to say, and a session that will
    not load is the worst way to hear it."""
    value = entry.get(field, default)
    return value if type(value) == 'string' and value else default


def _runners(outcomes_dir):
    """Every runner the project declares, as `[name, runner_type, dockerfile,
    context, args]`, by group name.

    By name rather than in the order the config lists them, because that
    order is also the order the groups run in -- and which promises are
    checked before which others should not depend on how somebody happened
    to write the file down.

    Read through read_file() so Tilt watches the file: a group added to the
    config is a session that re-evaluates rather than one somebody has to
    restart.

    An entry this cannot read is skipped rather than failing the Tiltfile.
    `seal check` reads the same file and says what is wrong with it, in a
    place that can explain itself -- and a session that will not load is the
    worst way to learn that a field is misspelled. What it cannot skip past
    is a file that is not JSON at all, since there is then nothing to read
    an entry out of.
    """
    config = decode_json(
        str(read_file(os.path.join(outcomes_dir, CONFIG_FILENAME), default='{}')),
    )
    if type(config) != 'dict':
        return []
    runners = {}
    declared = config.get(RUNNER_FIELD, [])
    if type(declared) != 'list':
        return []
    for entry in declared:
        if type(entry) != 'dict':
            continue
        name = entry.get(NAME_FIELD)
        runner_type = entry.get(RUNNER_TYPE_FIELD)
        if type(name) != 'string' or runner_type not in CONTAINER_RUNNERS:
            # A 'tap' group runs on the machine and has nothing to register
            # here; any other value is a runner_type seal has no runner
            # for, which `seal check` explains in a place that can.
            continue
        if name in runners:
            # A group has one runner. Which of two entries naming it was
            # meant is `seal check`'s to ask about, and building both would
            # be two images under one name.
            continue
        args = _runner_args(entry)
        if runner_type == CUSTOM_RUNNER:
            dockerfile = _path_field(
                entry, DOCKERFILE_FIELD, os.path.join(name, DOCKERFILE_FILENAME),
            )
            context = _path_field(entry, DOCKERFILE_CONTEXT_FIELD, name)
        else:
            dockerfile = None
            context = name
        runners[name] = [name, runner_type, dockerfile, context, args]
    return sorted(runners.values(), key=_runner_name)


def _translated_outcomes(group_dir, runner_type):
    """Every outcome in this group something can run, as `<epic>/<outcome>`
    in path order -- the runner's own spelling of a slug.

    Under the 'playwright' runner that means an outcome holding a file it
    collects. Under a 'custom' one it means an outcome holding anything at
    all: seal has no reading of what somebody else's runner starts, which is
    the whole point of declaring one."""
    found = {}
    for path in listdir(group_dir, recursive=True):
        outcome = _outcome_containing(path, group_dir)
        if outcome == None:
            continue
        if outcome[0] == HELPERS_DIR_NAME:
            # What this group's tests share, not a promise: a directory
            # under it is somewhere a helper is kept, and starting it would
            # have the run report a verdict on something nobody promised.
            continue
        if os.path.basename(path) in SEAL_S_OWN_FILES:
            continue
        if runner_type == CUSTOM_RUNNER or _is_spec(os.path.basename(path)):
            found[outcome[0] + '/' + outcome[1]] = True
    return sorted(found.keys())


def _selected_outcomes():
    """The outcomes somebody named, as full `<group>/<epic>/<outcome>` slugs,
    or an empty list meaning every group in full.

    Read through read_file() so Tilt watches the file and re-evaluates when
    `seal outcomes run <slug>...` writes it -- which is what lets a subset be
    asked for without restarting the session."""
    raw = str(read_file(os.path.join(PROJECT_ROOT, SELECTION_FILE), default=''))
    return [line.strip() for line in raw.split('\n') if line.strip()]


def _outcomes_to_run(group, group_dir, runner_type, selected):
    """What this group's run covers, as the runner spells it: the outcomes
    named, or every translated one.

    A named outcome nothing can run is dropped rather than failing the
    Tiltfile. `seal outcomes run` refuses an unknown slug before writing the
    file, so what reaches here is already checked -- and a stale file left by
    an older tree should not stop a session from loading."""
    translated = _translated_outcomes(group_dir, runner_type)
    if not selected:
        return translated
    return [slug for slug in translated if group + '/' + slug in selected]


def _playwright_dockerfile():
    """seal's own runner: Playwright, the browser that release drives, and
    the reporting every project would otherwise repeat. A group using it
    holds spec files and nothing else."""
    return PLAYWRIGHT_DOCKERFILE.format(
        base_image=PLAYWRIGHT_BASE_IMAGE,
        version=PLAYWRIGHT_VERSION,
        results=CONTAINER_RESULTS_DIR,
        results_var=RESULTS_ENV_VAR,
        base_url_var=BASE_URL_ENV_VAR,
        separator=ARGUMENT_SEPARATOR,
        verdict=VERDICT_FILENAME,
        done=DONE_FILENAME,
    )


def _deployment(k8s_name, base_url, arguments):
    """The manifest that runs one group's outcome tests.

    Its readinessProbe is the run having finished: Ready means every outcome
    this group was given has had its say, which is what lets `tilt ci` wait
    for it the same way it waits for everything else. seal writes the probe
    rather than asking the project for one -- the manifest is seal's, so
    there is nothing here for `seal check`'s readiness rule to catch.

    The arguments reach the image's ENTRYPOINT, which is why a runner a
    project brings has to declare one: Kubernetes `args` replace an image's
    CMD rather than adding to it, so a runner whose work is in a CMD would be
    started without it.

    A Deployment, so the container is still there to copy results out of. It
    has to stay up after writing its verdicts for that reason, which is part
    of the contract /rfcs/0011-outcome-runners.md states: a container that exits
    takes its own results with it, and a Deployment would start it over."""
    selector = {'app': k8s_name}
    return {
        'apiVersion': 'apps/v1',
        'kind': 'Deployment',
        'metadata': {'name': k8s_name, 'labels': selector},
        'spec': {
            'replicas': 1,
            'selector': {'matchLabels': selector},
            'template': {
                'metadata': {'labels': selector},
                'spec': {
                    'containers': [
                        {
                            'name': k8s_name,
                            'image': k8s_name,
                            'args': arguments,
                            'env': [
                                {'name': BASE_URL_ENV_VAR, 'value': base_url},
                            ],
                            'readinessProbe': {
                                # `test` rather than a shell: the image is
                                # whatever a project's runner needed, and
                                # nothing here should assume it has one.
                                'exec': {
                                    'command': [
                                        'test', '-f',
                                        os.path.join(CONTAINER_RESULTS_DIR, DONE_FILENAME),
                                    ],
                                },
                                'periodSeconds': 2,
                            },
                        },
                    ],
                },
            },
        },
    }


def _register_group(runner, outcomes_dir, base_url, resource_deps, outcomes, auto):
    """One group's runner, the run it performs, and the results coming back.

    Returns the syncback resource the report waits on."""
    name, runner_type, dockerfile, context, runner_args = runner
    k8s_name = K8S_NAME_PREFIX + name

    if runner_type == CUSTOM_RUNNER:
        docker_build(
            k8s_name,
            context=os.path.join(outcomes_dir, context),
            dockerfile=os.path.join(outcomes_dir, dockerfile),
        )
    else:
        docker_build(
            k8s_name,
            context=os.path.join(outcomes_dir, context),
            dockerfile_contents=_playwright_dockerfile(),
        )

    arguments = runner_args + [ARGUMENT_SEPARATOR] + outcomes
    k8s_yaml(encode_yaml(_deployment(k8s_name, base_url, arguments)))

    run_resource = seal_resource_name(RUN_PURPOSE, name)
    syncback_resource = seal_resource_name(SYNCBACK_PURPOSE, name)
    trigger_resource = seal_resource_name(SYNCBACK_TRIGGER_PURPOSE, name)
    local_dir = os.path.join(PROJECT_ROOT, LOCAL_OUTCOMES_RESULTS, name) + '/'

    k8s_resource(
        k8s_name,
        new_name=run_resource,
        labels=['outcomes'],
        auto_init=auto,
        trigger_mode=TRIGGER_MODE_AUTO if auto else TRIGGER_MODE_MANUAL,
        resource_deps=resource_deps,
    )

    syncback(
        syncback_resource,
        k8s_object='deploy/' + k8s_name,
        container=k8s_name,
        src_dir=CONTAINER_RESULTS_DIR,
        target_dir=local_dir,
        labels=['outcomes'],
        rsync_options=SYNCBACK_RSYNC_OPTIONS,
    )

    # syncback is manually triggered, so something has to fire it. The
    # directory is made here rather than by a resource of its own: one
    # command that cannot run before what it depends on, wherever the results
    # tree happens to be.
    local_resource(
        trigger_resource,
        cmd='mkdir -p {} && tilt trigger {}'.format(
            shlex.quote(local_dir), shlex.quote(syncback_resource),
        ),
        labels=['outcomes'],
        auto_init=auto,
        trigger_mode=TRIGGER_MODE_AUTO if auto else TRIGGER_MODE_MANUAL,
        resource_deps=[run_resource],
    )
    return [run_resource, syncback_resource]


def register_outcome_runner(base_url, resource_deps=[]):
    """Wire this project's whole outcome tree in. Call it once, from the
    project's own root Tiltfile, after every service is include()d.

    `base_url` is where the application answers, as an outcome test reaches
    it from inside the cluster (e.g. 'http://web:8000'). The project says it
    because only the project can: seal knows nothing about an app's own
    service names or ports. It reaches every runner as SEAL_BASE_URL, and the
    'playwright' one makes it Playwright's `baseURL`.

    `resource_deps` is what a run waits for, and it is the project's to name
    for the same reason: which of its resources have to be serving before a
    test means anything, and which of its services have to be at a known
    baseline first. A service's reset is named through reset_resource_name()
    rather than spelled out -- the resource name is the contract (see
    /rfcs/0002-declaration-by-structure.md), and an end-to-end test resource
    naming it is exactly what that contract is for.

    seal deliberately doesn't infer this. It knows which services declared a
    reset, but not which ones an outcome actually reads, and a dependency
    nobody asked for is a slower run at best and a cycle at worst.

    A project with no outcome tree, one whose config declares no runner it
    can read, or one holding no promises yet, gets nothing: outcome tests are
    something a project adopts, not a precondition for running seal.

    The run happens on its own only when this session's result is a verdict
    -- `run_outcomes`, which is what makes `seal ci` gate on it. Deliberately
    not read off what is being built: a run against a production-shaped
    overlay builds images carrying no test suite and is a gate all the same.
    Elsewhere everything here is registered and triggered by hand: `seal up`
    starts a session somebody is about to work in, and spending a whole
    outcome suite on every start of one is how a local loop stops being
    used."""
    outcomes_dir = _outcomes_dir()
    if not os.path.exists(outcomes_dir):
        return

    auto = run_outcomes
    selected = _selected_outcomes()
    syncbacks = []
    # Each group waits for the one before it, on top of whatever the project
    # named. Outcome tests drive the same application, so two groups running
    # at once is the same interference two outcomes running at once would be:
    # each asserting on state the other is changing.
    #
    # Only where the suite runs on its own. A session somebody is working in
    # triggers a group by hand, and a group waiting on another nobody
    # triggered would never start; `seal outcomes run` serialises them itself
    # for that reason (python/src/seal/seal.py).
    waits_for = list(resource_deps)
    for runner in _runners(outcomes_dir):
        name, runner_type, dockerfile = runner[0], runner[1], runner[2]
        group_dir = os.path.join(outcomes_dir, name)
        if not os.path.exists(group_dir):
            continue
        if runner_type == CUSTOM_RUNNER and not os.path.exists(
            os.path.join(outcomes_dir, dockerfile),
        ):
            # `seal check` says what a group whose Dockerfile is not there
            # should do about it; there is nothing here to build until it is.
            continue
        outcomes = _outcomes_to_run(name, group_dir, runner_type, selected)
        if not outcomes:
            continue
        registered = _register_group(
            runner, outcomes_dir, base_url, waits_for, outcomes, auto,
        )
        syncbacks.append(registered[1])
        if auto:
            waits_for = list(resource_deps) + [registered[0]]

    if not syncbacks:
        return

    local_resource(
        REPORT_RESOURCE,
        cmd='{} outcomes run'.format(seal_cli()),
        dir=PROJECT_ROOT,
        labels=['outcomes'],
        auto_init=auto,
        trigger_mode=TRIGGER_MODE_AUTO if auto else TRIGGER_MODE_MANUAL,
        resource_deps=syncbacks,
    )
