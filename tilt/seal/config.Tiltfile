# Generic Tilt configuration shared by every project that uses this package.
#
# This file makes no assumption about where the calling project lives on
# disk relative to `resources/` -- it anchors every project-relative path on
# `config.main_dir`, Tilt's own path to the directory of the *root* Tiltfile
# (the one `tilt up`/`tilt ci` was invoked against), regardless of how many
# `include()`/`load()` hops separate it from this file. See
# https://docs.tilt.dev/api.html#modules.config.main_dir.
PROJECT_ROOT = config.main_dir

# Which of a project's Kubernetes overlays this run deploys. No default
# here: an overlay is a directory a project named, so the project says which
# of its own to reach for when a run doesn't (see select_k8s_overlay).
config.define_string('k8s_overlay')

# Which kind of image a run builds: a working session's, one a run that also
# executes a service's own tests needs, or the one a real environment runs.
config.define_string('build_type')

# Whether the images this run builds are pushed to a real registry. Off
# unless a run says otherwise, so a run against a production-shaped overlay
# on a throwaway cluster does not publish what it built just by virtue of
# the shape it deployed. Which registry is the project's own to name,
# through Tilt's default_registry() -- seal never learns it.
config.define_bool('publish_images')

# Whether this run reads the promises at the end of it. Left unset it
# follows the run: `seal ci` is a gate and says so (SEAL_CI, below), while a
# session somebody is about to work in is not. A run states it either way
# when it knows better -- a build whose only job is to publish is not a
# gate however it was started.
#
# A string rather than define_bool, which reports False for a flag nobody
# passed and so cannot tell "follow the run" from "definitely not".
config.define_string('run_outcomes')

# Whether an outcome's run is recorded, stated separately for the two things
# a recording can be about. A failure's recording is what a red promise costs
# somebody: an assertion that timed out waiting for a selector reads the same
# whether the page never loaded, loaded the wrong thing, or loaded the right
# thing behind a dialog. A passing run's is for checking the suite is
# exercising what somebody thinks it is.
#
# Strings rather than define_bool, for the reason run_outcomes is: a flag
# nobody passed reports False, which cannot be told from one passed as false.
config.define_string('record_outcome_video_on_failure')
config.define_string('record_outcome_video_on_success')

config.define_string_list('allowed_k8s_contexts')  # Used to restrict allowed Kubernetes contexts when deploying with Tilt.
cfg = config.parse()

k8s_overlay = cfg.get('k8s_overlay', '')

publish_images = cfg.get('publish_images', False)

BUILD_TYPES = ['development', 'test', 'runtime']

# 'development' whatever the environment is called. A build kind is not
# something an environment name gets to imply: a run against a
# production-shaped overlay may want development images, and a run that
# publishes says so itself.
build_type = cfg.get('build_type', '') or 'development'
if build_type not in BUILD_TYPES:
    fail("Invalid build_type '{}'. Must be one of {}.".format(build_type, ', '.join(BUILD_TYPES)))
print("Using build type: {}".format(build_type))

# What `seal ci` sets to say this run's result is a verdict (see
# python/src/seal/seal.py). A plain `tilt up`/`tilt ci`, started without the
# CLI, leaves it unset -- and gets no suite unless --run_outcomes asks.
SEAL_CI_ENV_VAR = 'SEAL_CI'

RUN_OUTCOMES_VALUES = {'true': True, 'false': False}

_run_outcomes = cfg.get('run_outcomes', '')
if _run_outcomes != '' and _run_outcomes not in RUN_OUTCOMES_VALUES:
    fail(
        "Invalid run_outcomes '{}'. Must be {}.".format(
            _run_outcomes, ' or '.join(sorted(RUN_OUTCOMES_VALUES)),
        )
    )

# Deliberately not read off build_type: a run against a production-shaped
# overlay builds images that carry no test suite and is a gate all the same,
# and a build whose only job is to publish builds the same images and is
# not.
run_outcomes = (
    RUN_OUTCOMES_VALUES[_run_outcomes] if _run_outcomes != ''
    else os.getenv(SEAL_CI_ENV_VAR, '') != ''
)

# What the two recording flags add up to, in the vocabulary the runner that
# implements them speaks. Only the `playwright` runner records anything; a
# `tap` or `custom` runner writes whatever it writes and this says nothing
# about it.
#
# Unset is a failure's recording and nothing else: a red promise is what
# somebody has to understand, and a green suite that kept a video per test
# would fill every artifact with footage of things working.
BOOLEAN_VALUES = {'true': True, 'false': False}

OUTCOME_VIDEO_OFF = 'off'
OUTCOME_VIDEO_ALWAYS = 'on'
OUTCOME_VIDEO_ON_FAILURE = 'retain-on-failure'


def _recording_switch(name, unset):
    value = cfg.get(name, '')
    if value == '':
        return unset
    if value not in BOOLEAN_VALUES:
        fail(
            "Invalid {} '{}'. Must be {}.".format(
                name, value, ' or '.join(sorted(BOOLEAN_VALUES)),
            )
        )
    return BOOLEAN_VALUES[value]


_video_on_failure = _recording_switch('record_outcome_video_on_failure', True)
_video_on_success = _recording_switch('record_outcome_video_on_success', False)

if _video_on_success and not _video_on_failure:
    # Nothing records a pass and discards a failure: a run is recorded or it
    # is not, and what the recording is kept for is decided afterwards. So
    # this combination is refused rather than quietly rounded up to keeping
    # both -- a project that asked to keep only the passes would otherwise
    # get every failure's video as well and never be told.
    # Starlark has no adjacent-string-literal concatenation, so a message
    # spanning lines joins with `+`.
    fail(
        "record_outcome_video_on_success without record_outcome_video_on_failure "
        + "asks to record a run and throw the recording away exactly when it is "
        + "worth having. Keeping the passes means keeping the failures too: "
        + "turn record_outcome_video_on_failure on as well, or record neither."
    )

outcome_video = (
    OUTCOME_VIDEO_ALWAYS if _video_on_success and _video_on_failure
    else OUTCOME_VIDEO_ON_FAILURE if _video_on_failure
    else OUTCOME_VIDEO_OFF
)

# Allow production contexts
for context in cfg.get('allowed_k8s_contexts', []):
    allow_k8s_contexts(context)


# The official tilt-dev/tilt-extensions repo, registered here under a name
# of seal's own rather than reached through Tilt's built-in `default`
# repo. A project is free to register an extension repo called `default`,
# which shadows the built-in one; going through a private name means
# seal's own loads (`ext://__seal_syncback`, below) don't care
# what a project called anything.
#
# Registered in this file because it is the one every other seal
# Tiltfile loads first, so the alias exists by the time any of them reach
# for the extension.
v1alpha1.extension_repo(
    name='__seal_default_ext_repo',
    url='https://github.com/tilt-dev/tilt-extensions',
)
v1alpha1.extension(
    name='__seal_syncback',
    repo_name='__seal_default_ext_repo',
    repo_path='syncback',
)


# How a Tiltfile invokes the `seal` CLI again from inside the session it
# started -- what runs the outcome suite (outcomes.Tiltfile) and what reads
# a service's own test report (tests.Tiltfile). `seal up`/`seal ci` announce
# it (python/src/seal/seal.py), so the session reports through the same
# interpreter that started it rather than through whatever a child process
# happens to find on PATH. A plain `tilt up`, run without the CLI, falls
# back to the name on PATH.
SEAL_CLI_ENV_VAR = 'SEAL_CLI'


def seal_cli():
    return os.getenv(SEAL_CLI_ENV_VAR, '') or 'seal'


def _overlays_under(k8s_dir):
    """Every directory directly under `k8s_dir`, which is what an overlay is.

    Derived from the files below it rather than listed directly: Tilt's
    listdir() returns files only, so a directory shows up here through
    something inside it. An empty one is not an overlay kustomize could build
    anyway, so it is no loss that it stays invisible."""
    root = os.path.join(PROJECT_ROOT, k8s_dir)
    names = []
    for path in listdir(root, recursive=True):
        relative = path[len(root):].lstrip('/')
        name = relative.split('/')[0]
        if name and name != relative and name not in names:
            names.append(name)
    return sorted(names)


def _fail_unless_overlay_exists(k8s_dir, overlay):
    """A named overlay that is not there is a misspelling, and saying so here
    is the only place it can be said in those terms. Left alone it reaches
    kustomize as a path that does not resolve, and what a reader gets back is
    an error about a directory rather than about the flag they typed."""
    if os.path.exists(os.path.join(PROJECT_ROOT, k8s_dir, overlay)):
        return

    available = _overlays_under(k8s_dir)
    fail(
        "No '{}' overlay in {}/. ".format(overlay, k8s_dir)
        + ("Available: {}.".format(', '.join(available)) if available
           else "That directory holds no overlays at all.")
        + " Name one with --k8s_overlay, or change this project's"
        + " select_k8s_overlay(default_overlay=...)."
    )


def select_k8s_overlay(k8s_dir, default_overlay):
    """Deploy one of `<k8s_dir>/`'s overlays (project-root-relative) as this
    session's Kubernetes manifests: whichever `--k8s_overlay` names, or
    `default_overlay` when a run doesn't say. Generates
    `<PROJECT_ROOT>/.workspace/final-kustomize/kustomization.yaml` selecting
    it, and applies it with `k8s_yaml(kustomize(...))` itself. Call this
    yourself, from your project's own root Tiltfile, after include()ing
    every service (see examples/angular-django/Tiltfile). Image
    naming/registry selection aren't handled here: each service's Tiltfile
    builds a plain, hardcoded image name (see services/<name>/Tiltfile in
    any project), and pushing it anywhere outside local dev is the calling
    project's own Tiltfile's job, via Tilt's native `default_registry()`.

    `default_overlay` is required and has no value seal would supply: the
    overlays are directories the project made and named, so which one a bare
    run means is the project's to say. A default here would be seal deciding
    that every project spells its working shape the same way."""
    overlay = k8s_overlay or default_overlay
    _fail_unless_overlay_exists(k8s_dir, overlay)

    # What seal filled for this overlay, if it filled anything: a
    # kustomization naming the overlay as its resource plus one
    # strategic-merge patch per object the overlay says seal fills
    # (see python/src/seal/fill.py). Deploying that instead of the
    # overlay directly is what puts the values in -- one object, the
    # project's own, with `data` supplied.
    #
    # Absent for a project that annotates nothing, which is a project
    # provisioning its objects some other way: then the overlay deploys as
    # written and seal fills nothing, which is the whole point of the
    # annotation being opt-in.
    filled = os.path.join(PROJECT_ROOT, '.workspace', 'seal-env', overlay)
    deploy_root = '../../{}/{}'.format(k8s_dir, overlay)
    if os.path.exists(os.path.join(filled, 'kustomization.yaml')):
        deploy_root = os.path.join('..', 'seal-env', overlay)

    generated_kustomize_dir = os.path.join(PROJECT_ROOT, '.workspace', 'final-kustomize')
    local('mkdir -p {}'.format(shlex.quote(generated_kustomize_dir)))
    generated_kustomization_path = os.path.join(generated_kustomize_dir, 'kustomization.yaml')
    kustomization = {
        'apiVersion': 'kustomize.config.k8s.io/v1beta1',
        'kind': 'Kustomization',
        'resources': [
            # Relative, not os.path.join(PROJECT_ROOT, ...): kustomize refuses
            # an absolute resource root ("new root ... cannot be absolute").
            # Safe to hardcode the '../../' despite k8s_dir being
            # configurable -- it expresses the fixed relationship between the
            # two paths *we* just generated (generated_kustomize_dir is
            # always PROJECT_ROOT/.workspace/final-kustomize) and
            # PROJECT_ROOT itself, not an assumption about how many path
            # segments k8s_dir has.
            deploy_root,
        ],
    }
    # Written only when it would change. k8s_yaml(kustomize(...)) below puts
    # this file under Tilt's watch, so an unconditional write makes every
    # Tiltfile load trigger the next one -- a session that reloads forever
    # and never settles long enough to run anything. `tilt ci` exits after
    # one build and never sees it; `seal up` does nothing else.
    desired = str(encode_yaml(kustomization))
    if str(read_file(generated_kustomization_path, default='')) != desired:
        local(
            'cat > {}'.format(shlex.quote(generated_kustomization_path)),
            stdin=desired,
        )
    # Absolute, not project-root-relative: this function runs from inside
    # the seal extension, a different directory than the calling project's
    # own Tiltfile, so a relative path here would be resolved against the
    # wrong base. generated_kustomize_dir (above) is already absolute and
    # PROJECT_ROOT-anchored (see PROJECT_ROOT's own comment, up top), so
    # pass it through as-is.
    k8s_yaml(kustomize(generated_kustomize_dir))
