# One-call wrapper for a service's own Tiltfile: build its image (picking
# the right target/stage for build_type == 'test', and the
# GitHub-Actions-cached buildx path unless opted out), register the CI
# test-result syncback if this call opted the service into tests, and
# register its reset resource if it declared a reset script. Nothing here
# concerns this service's credentials -- which object carries those is the
# overlay's to say (see /rfcs/0007-credential-delivery.md).
load('./config.Tiltfile', 'build_type', 'run_outcomes')
load('./resources.Tiltfile', 'seal_resource_name')
load('./tests.Tiltfile', 'register_syncback', 'tests_run_resource_name')
# A sibling file of seal's own, not an ext:// name, so a project
# registers `seal` and nothing else to get the CI build path.
#
# It has to be a top-level load(), not a load_dynamic() inside
# seal_service(): Tilt resolves a relative path against whichever
# Tiltfile is *executing*, which up here is this directory but inside the
# function is the calling service's own -- where '../docker_build' names a
# sibling of that service and reaches nothing. Loading it unconditionally
# costs nothing: the file defines one function and does nothing at import.
load('../docker_build/Tiltfile', 'cached_docker_build')

# Tells seal_service() (use_cache=True, the default) to build via
# cached_docker_build() -- a GitHub-Actions-cached buildx build -- instead of
# Tilt's native docker_build(). Only a CI run sets this (the `ci` action at
# /actions/ci does, and so does a deploy pipeline); local `tilt up` never
# does, so it keeps Tilt's native (faster, better-supported) build and
# live_update path.
#
# Checked here, not inside cached_docker_build() itself, which always takes
# the buildx path once called -- deciding whether that path is wanted at all
# is this file's job.
_USE_BUILDX_CACHE = os.getenv('SEAL_BUILDX_CACHE', '0') == '1'


# A service's reset resource -- 'seal_reset_example_api' for 'example-api',
# see resources.Tiltfile for the convention. This name is the contract, not
# an implementation detail: it is how anything that needs a service's state
# at a known baseline before it runs -- an end-to-end test resource, most
# obviously -- names that service's reset in its own resource_deps, without
# a registry of hooks to consult or a path to guess.
RESET_PURPOSE = 'reset'

# The same script, run before this service's own tests rather than after
# them. It groups with the rest of that service's test pipeline
# (`seal_tests_*`) because that is what it belongs to -- a step of running
# this service's tests, not the baseline an outcome reads.
TESTS_RESET_PURPOSE = 'tests_reset'


def reset_resource_name(service_name):
    return seal_resource_name(RESET_PURPOSE, service_name)


def _tests_reset_resource_name(service_name):
    return seal_resource_name(TESTS_RESET_PURPOSE, service_name)



def _register_reset(resource_name, reset, resource_dep, auto_init):
    """Declare this service's reset as a Tilt resource, under the name given.

    A test run restores this service's baseline twice, so there are two of
    these: one before the service's own tests, so they start from a known
    state like anything else that reads it, and one after them, so the
    outcome suite does too whatever those tests did. Same script; a Tilt
    resource can only sit in the graph once.

    TRIGGER_MODE_MANUAL throughout: nothing about editing a file says this
    service's data should go back to its baseline, and firing a reset
    mid-keystroke is how a developer loses what they were looking at.

    `auto_init` is whether it runs once at startup, which each caller
    answers for itself -- the two resets precede different things and so
    become due at different times. In a session somebody is about to work in
    neither runs: `seal up` would throw away the state they left, and the way
    back is a trigger they ask for.

    It waits on the service whose state it puts back, which is what its
    script acts through -- `kubectl exec` against a Deployment that is not
    up yet reaches nothing.

    `reset` is read as a bare relative path, which Tilt resolves against
    whichever service's own Tiltfile called in, which is what lets a service
    name its own script without a path registry. os.path.abspath() pins that
    resolution down here, so the resource runs the script this call meant
    from the service's own directory whatever cwd Tilt happens to have."""
    local_resource(
        resource_name,
        cmd='sh {}'.format(shlex.quote(os.path.abspath(reset))),
        dir=os.path.abspath('.'),
        auto_init=auto_init,
        trigger_mode=TRIGGER_MODE_MANUAL,
        labels=['reset'],
        resource_deps=[resource_dep],
    )


def seal_service(service_name, context='.', dockerfile='Dockerfile', live_update=[],
                        use_cache=True, k8s_resource_name=None, resource_dep=None,
                        development_stage=None, runtime_stage=None, test_stage=None,
                        junit_tests_directory=None, test_command=None,
                        registry=None, reset=None, **docker_build_kwargs):
    """Build a service and wire up everything it needs, in one call:

    1. cached_docker_build() (/tilt/docker_build, when use_cache and
       SEAL_BUILDX_CACHE=1 -- see _USE_BUILDX_CACHE above) or,
       otherwise, Tilt's native docker_build() -- for
       `service_name`, targeting whichever of this service's own stages the
       run's build_type asks for.
    2. register_syncback(), only if `test_stage` was given.
    3. _register_reset(), only if `reset` was given -- the
       'seal_reset_<service_name>' Tilt resource that puts this
       service's state back to a known baseline.

    Args:
        service_name: this service's image ref and (unless overridden
            below) k8s object/container/Tilt-resource-dep name -- the one
            identifier every other argument here defaults from. Not a
            Secret name: which object carries this service's values is the
            overlay's to say (see /rfcs/0007-credential-delivery.md).
        context, dockerfile, live_update: forwarded to
            cached_docker_build()/docker_build() as-is.
        use_cache: opt into the GitHub-Actions buildx-cache path (see
            _USE_BUILDX_CACHE above) when it's active; pass False to always
            use Tilt's native docker_build() instead, even under
            SEAL_BUILDX_CACHE=1 -- see /tilt/docker_build/README.md.
            Either way, local `tilt up` is unaffected; only the reusable CI
            workflows set SEAL_BUILDX_CACHE=1.
        **docker_build_kwargs: any other docker_build() argument (e.g.
            build_args, extra_tag, ignore, only, network, ssh, secret,
            platform, cache_from, pull, entrypoint, container_args,
            dockerfile_contents, match_in_env_vars, extra_hosts), forwarded
            to cached_docker_build()/docker_build() as-is. Tilt's native
            docker_build() understands all of them; cached_docker_build()'s
            buildx command doesn't understand any of them, and fails loudly
            if given one -- see /tilt/docker_build/README.md.
        k8s_resource_name, resource_dep: forwarded to register_syncback()
            as-is (see tests.Tiltfile) -- both default to `service_name`,
            correct when this service has its own Deployment; override when
            several services share one Deployment/pod (e.g. merged into a
            single 'web' resource). register_syncback()'s `container`
            argument is always `service_name` here, not separately settable.
        development_stage, runtime_stage, test_stage: this service's own
            Dockerfile stages, one per build_type. seal names the kind of
            image a run wants; the service names what to build for it, so
            nothing here requires a project to spell its stages any
            particular way. Every one is optional, and what each absence
            claims is documented where they are resolved, below.
            `test_stage` is also the switch that turns on this service's
            test pipeline -- see `test_command`.
        junit_tests_directory: in-container directory holding this service's
            junit/coverage output, forwarded to register_syncback() as
            test_results_dir. Required whenever `test_stage` is given
            (fails loudly otherwise): unlike register_syncback()'s own
            default, there's no one convention every service's Dockerfile
            already follows, so guessing wrong here would silently sync
            back nothing instead of failing. What that directory has to
            hold is a JUnit report -- it is the whole verdict on this
            service's tests (see tests.Tiltfile and
            python/src/seal/junit.py).
        test_command: what runs this service's own tests, executed inside
            the running container (see _register_test_run() in
            tests.Tiltfile) -- e.g. 'make unit-tests'. Required whenever
            `test_stage` is given, and requires it in turn: the command
            runs in the deployed container, so the stage holding this
            service's tests has to be the stage that gets built.
        reset: this service's own reset script, as a path relative to its
            Tiltfile (e.g. 'deploy/reset.sh'). Declaring it registers the
            'seal_reset_<service_name>' resource described in
            _register_reset() below, which waits on `resource_dep` (or this
            service) before running: the script acts on the service through
            the cluster, so the service has to be up for it to reach
            anything. One script, not a reset step and a
            separate seed step: what a test needs is this service's state
            at a known, useful baseline, and an empty database is only
            half of that -- so emptying the stores and loading the fixture
            data are the same job, done in one place where their order is
            not something a caller can get wrong.
        registry: forwarded to cached_docker_build() only (Tilt's native
            docker_build() has no such argument, and never needs one --
            it's driven entirely by Tilt's own default_registry(), unlike
            cached_docker_build()'s separate, explicit SEAL_IMAGE_TAG push
            -- see /tilt/docker_build/README.md). Pass whatever the calling
            project passed to default_registry() itself; irrelevant (safe
            to leave unset) whenever SEAL_BUILDX_CACHE/SEAL_IMAGE_TAG aren't
            both set, i.e. anywhere but a pipeline actually publishing a
            build.
    """
    # A service's tests need all three or none of them: the stage that holds
    # them, the command that runs them, and where the report lands. Any one
    # alone describes half a pipeline, and the half that is missing is the
    # half that would fail somewhere further downstream -- exec'ing into an
    # image with no tests in it, or syncing back a directory nothing wrote.
    if test_command != None and test_stage == None:
        fail(
            "seal_service('{}'): test_command needs test_stage -- ".format(service_name)
            + "the command runs in the deployed container, so the stage holding this "
            + "service's tests has to be the stage that gets built. See /tilt/seal/README.md."
        )

    if test_stage != None and test_command == None:
        fail(
            "seal_service('{}'): test_command is required when test_stage is given ('{}'). ".format(
                service_name, test_stage,
            )
            + "It is what runs this service's tests, in the container seal has just "
            + "deployed. See /tilt/seal/README.md."
        )

    if test_stage != None and junit_tests_directory == None:
        fail(
            "seal_service('{}'): junit_tests_directory is required when test_stage is given ('{}'). ".format(
                service_name, test_stage,
            )
            + "See /tilt/seal/README.md."
        )

    # Which of this service's own stages the run's build type asks for. Every
    # one of them is optional, and what each absence means is a claim a
    # project would want to make:
    #
    # - no runtime stage: build with no target at all, so Docker takes the
    #   Dockerfile's last stage. That is the whole Dockerfile for a service
    #   built in one stage.
    # - no development stage: this service runs the same image in a working
    #   session as in a real environment, which is true of a worker or a
    #   small sidecar. It falls back to the runtime stage rather than
    #   independently to the last one -- in a multi-stage Dockerfile the last
    #   stage *is* the runtime one, so an independent default would hand a
    #   session the production image without saying so.
    # - no test stage: this service has no tests of its own, and a test run
    #   builds what a session would. It still has to serve, for the outcome
    #   suite and for whatever other services test against it.
    # '' rather than None for "no stage": that is Tilt's own default for
    # docker_build()'s target, and its native builder rejects None outright.
    development_target = development_stage or runtime_stage
    build_target = {
        'development': development_target,
        'runtime': runtime_stage,
        'test': test_stage or development_target,
    }[build_type] or ''

    if use_cache and _USE_BUILDX_CACHE:
        cached_docker_build(
            service_name, context=context, dockerfile=dockerfile, target=build_target,
            live_update=live_update, registry=registry, **docker_build_kwargs
        )
    else:
        # Tilt's native docker_build() has no `registry` argument (see
        # `registry`'s own docstring above) -- never forward it here, or
        # every project's local `tilt up` would fail on an unrecognized
        # kwarg the moment it passed one.
        docker_build(
            service_name, context=context, dockerfile=dockerfile, target=build_target,
            live_update=live_update, **docker_build_kwargs
        )

    # A test run has an order to it: this service's baseline, its own tests
    # against that, the baseline again, and then the promises read against
    # *that*. Both halves are the same reset, and both are worth having --
    # the first so a service's tests start from a known state like anything
    # else that reads it, the second so the outcome suite does too, whatever
    # those tests did to get their answer.
    tests_wait_for = resource_dep or service_name
    if test_stage != None:
        if reset != None and build_type == 'test':
            # Registered only in a run that executes this service's tests, and
            # it is those tests it precedes -- so it is due whenever it
            # exists at all.
            _register_reset(
                _tests_reset_resource_name(service_name), reset, tests_wait_for,
                auto_init=True,
            )
            tests_wait_for = _tests_reset_resource_name(service_name)

        register_syncback(
            service_name=service_name,
            k8_resource_name=k8s_resource_name,
            container=service_name,
            test_results_dir=junit_tests_directory,
            resource_dep=tests_wait_for,
            test_command=test_command,
        )

    if reset != None:
        reset_dep = resource_dep or service_name
        if test_stage != None and build_type == 'test':
            reset_dep = tests_run_resource_name(service_name)
        # The baseline the promises are read against, so it is due exactly
        # when they are: whenever this run is a gate. Deliberately not the
        # build type -- a gate against a production-shaped overlay builds
        # runtime images and reads the same promises, and a reset that waited
        # for `test` images would leave the suite waiting on a baseline
        # nothing was ever going to establish.
        _register_reset(
            reset_resource_name(service_name), reset, reset_dep,
            auto_init=run_outcomes,
        )
