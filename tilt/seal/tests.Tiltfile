load('./config.Tiltfile', 'build_type', 'PROJECT_ROOT', 'seal_cli')
load('./resources.Tiltfile', 'seal_resource_name')
load('ext://__seal_syncback', 'syncback')  # After config: it registers this alias, and allow_k8s_contexts

LOCAL_TESTS_RESULTS = 'tests-results/'

# Copying results back never preserves ownership: a uid inside a container
# means nothing on the machine the artifacts land on, so the numbers are the
# whole answer and there is no name to map them to.
#
# Saying so is what keeps rsync from asking. That mapping is a glibc name
# lookup made from a statically-linked rsync -- the one Tilt installs into
# whichever container it is copying from -- and on some base images the two
# glibcs meeting inside one process kill it partway through the transfer.
# Which base image a test container is built on is the project's choice, and
# nothing a project would expect to decide whether its results come back.
SYNCBACK_RSYNC_OPTIONS = ['--numeric-ids']

# Every resource below is named through seal_resource_name() (see
# resources.Tiltfile), so a purpose is stated once here rather than a name
# being spelled out at each use.
TESTS_RESULTS_DIR_PURPOSE = 'tests_results_dir'
SYNCBACK_PURPOSE = 'tests_syncback'
SYNCBACK_TRIGGER_PURPOSE = 'tests_syncback_trigger'
RUN_PURPOSE = 'tests_run'
VERDICT_PURPOSE = 'tests_verdict'

# The one resource there is only ever one of per project, so it takes no
# service name.
TESTS_RESULTS_DIR_RESOURCE = seal_resource_name(TESTS_RESULTS_DIR_PURPOSE)


def tests_run_resource_name(service_name):
    """The resource that runs one service's own tests.

    Like a reset's name (see build.Tiltfile), this is the contract rather
    than an implementation detail: it is how anything that must not overlap
    with a service's own test run names it in its own resource_deps.
    """
    return seal_resource_name(RUN_PURPOSE, service_name)


if build_type == 'test':
    local_resource(
        TESTS_RESULTS_DIR_RESOURCE,
        cmd='mkdir -p {}'.format(shlex.quote(os.path.join(PROJECT_ROOT, LOCAL_TESTS_RESULTS))),
        labels=['tests']
    )


def local_tests_results_dir(service_name):
    """Get the local directory where test results for a given service are stored."""
    return os.path.join(PROJECT_ROOT, LOCAL_TESTS_RESULTS, service_name) + '/'


def _register_test_run(service_name, k8_resource_name, container, test_command, resource_dep):
    """Run this service's own tests inside the container that is already up,
    and never fail on what they say.

    `kubectl exec` rather than a step in the image's build: a running
    container has what a build cannot give a test -- this service's
    Kubernetes Secret, its database, its broker -- so a test that needs any
    of them is an ordinary test of this service rather than something that
    has to be promoted to an outcome to run at all.

    The exit code is deliberately discarded. What fails a run is the report
    (see the verdict resource below), and a failing suite that stopped the
    chain here would take the report of what failed with it -- the copy back
    to the project happens downstream. So the swallow lives here, in seal,
    where a project cannot leave it out by accident; a service says what to
    run and nothing about what to do when it fails.

    It waits for the service, because that is what it runs inside: `kubectl
    exec` against a Deployment that is not up yet reaches nothing. Waiting
    for *ready* rather than merely started is what a test wanting the
    service's dependencies needs, and it is also what keeps a slow suite out
    of the readiness path -- a container running its tests before its own
    process starts would be one its livenessProbe restarts partway through.

    auto_init with TRIGGER_MODE_MANUAL: a run performs it once, and a person
    who wants this service's suite run again asks for it by name, which is
    something a suite baked into an image layer cannot offer.
    """
    target = [k8_resource_name]
    if container != None:
        target += ['-c', container]

    local_resource(
        tests_run_resource_name(service_name),
        cmd='kubectl exec {} -- sh -c {} || echo {}'.format(
            ' '.join([shlex.quote(part) for part in target]),
            shlex.quote(test_command),
            shlex.quote(
                '{}: tests exited non-zero -- what that means is in the report'.format(
                    service_name,
                ),
            ),
        ),
        auto_init=True,
        trigger_mode=TRIGGER_MODE_MANUAL,
        labels=['tests'],
        resource_deps=[resource_dep],
    )


# Copy the results of the tests back to the local machine for easier access
# and debugging, and fail the Tilt run if they say the tests failed.
def register_syncback(service_name, k8_resource_name=None, container=None, test_results_dir=None,
                       resource_dep=None, test_command=None):
    """Copy test artifacts back to the local machine after running tests in CI mode,
    then check whether they passed.

    `k8_resource_name` (the kubectl object to rsync from, e.g. 'deploy/web')
    and `resource_dep` (the Tilt resource to wait on before triggering the
    sync) both default to `service_name`, which is correct when the service
    has its own Kubernetes Deployment. Override them when several services
    share the same Deployment/pod (e.g. several containers merged into a
    single 'web' resource) so the k8s object / dependency point at the shared
    resource while `service_name` keeps identifying this service's own
    results.

    `test_command` is what produces those results, run inside the running
    container (see _register_test_run() above).
    """
    if build_type == 'test':
        if k8_resource_name == None:
            k8_resource_name = 'deploy/' + service_name
        if resource_dep == None:
            resource_dep = service_name
        if test_results_dir == None:
            test_results_dir = '/app/tests-results/'

        sync_resource_name = seal_resource_name(SYNCBACK_PURPOSE, service_name)

        _register_test_run(
            service_name, k8_resource_name, container, test_command, resource_dep,
        )

        syncback(
            sync_resource_name,
            k8s_object=k8_resource_name,
            container=container,
            src_dir=test_results_dir,
            target_dir=local_tests_results_dir(service_name),
            labels=['tests'],
            rsync_options=SYNCBACK_RSYNC_OPTIONS,
        )

        # syncback is manually triggered, we force the trigger
        local_resource(
            seal_resource_name(SYNCBACK_TRIGGER_PURPOSE, service_name),
            cmd='tilt trigger {}'.format(sync_resource_name),
            labels=['tests'],
            resource_deps=[
                TESTS_RESULTS_DIR_RESOURCE, tests_run_resource_name(service_name),
            ],
        )

        # Fails this Tilt run (and so `tilt ci`) if the synced-back JUnit
        # report doesn't say every test passed -- one resource per service,
        # so a CI failure points straight at which service failed instead of
        # a single combined check.
        #
        # The report is the whole verdict, and nothing upstream of here
        # fails on a failing suite: the results have to reach the project
        # for anybody to see which test failed, and a run that stopped at
        # the failure would take them with it. What that leaves is a service
        # whose tests never ran looking exactly like one whose tests all
        # passed, so `seal _tests-verdict` treats silence -- no report, no
        # cases in it, a report that doesn't parse -- as a failure rather
        # than an absence (python/src/seal/junit.py).
        local_resource(
            seal_resource_name(VERDICT_PURPOSE, service_name),
            cmd='{} _tests-verdict {} --results-dir {}'.format(
                seal_cli(),
                shlex.quote(service_name),
                shlex.quote(local_tests_results_dir(service_name)),
            ),
            labels=['tests'],
            resource_deps=[sync_resource_name],
        )
