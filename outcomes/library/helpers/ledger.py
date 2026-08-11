"""The project two promises about a service's own state are read from.

One fixture, because one project answers both: a service that owns state,
declares how to put it back, and has a test suite of its own -- plus a
second service that declares neither, which is how "a service that declares
no reset is not made to" gets asked.

It lives beside the checks rather than inside one of them because both read
it, and a fixture written twice is two fixtures that will disagree.
"""

from helpers.projects import Project, container

# What the service's own tests must have seen to have run where they were
# promised to run: state its reset put there, and a credential its
# deployment provisioned. Neither exists while an image is being built,
# which is what makes them the evidence.
BASELINE = "baseline"
PASSWORD = "provisioned-when-it-was-deployed"
WHAT_IT_SAW = "what-it-saw.txt"

# rsync, because that is how a service's results come back from the
# container they were produced in. sleep, because what this service does is
# not what either promise is about.
IMAGE = """FROM alpine:3.20 AS runtime
RUN apk add --no-cache rsync && mkdir -p /state /app/tests-results
CMD ["sh", "-c", "sleep infinity"]

FROM runtime AS test
COPY tests/run.sh /app/tests/run.sh
"""

SERVING = {
    "exec": {"command": ["sh", "-c", "test -d /state"]},
    "periodSeconds": 2,
    "failureThreshold": 30,
}

# This service's own suite. It writes down what it found before deciding
# anything, so a check can read what the container held rather than only
# whether the suite was happy about it.
TESTS = f"""#!/bin/sh
state=$(cat /state/ledger 2>/dev/null || printf '<nothing there>')
printf 'state=%s\\npassword=%s\\n' "$state" "$LEDGER_PASSWORD" > /app/tests-results/{WHAT_IT_SAW}
if [ "$state" = "{BASELINE}" ] && [ "$LEDGER_PASSWORD" = "{PASSWORD}" ]; then
  printf '%s' '<testsuite name="ledger" tests="1" failures="0" errors="0">' \\
    '<testcase classname="ledger" name="runs against what it was deployed with"/>' \\
    '</testsuite>' > /app/tests-results/junit.xml
else
  printf '%s' '<testsuite name="ledger" tests="1" failures="1" errors="0">' \\
    '<testcase classname="ledger" name="runs against what it was deployed with">' \\
    '<failure message="not what it was deployed with"/></testcase></testsuite>' \\
    > /app/tests-results/junit.xml
fi
"""

# What putting this service's state back means here. It acts on the running
# cluster, the way a reset does: the state belongs to the container, not to
# the checkout.
RESET = f"""#!/bin/sh
set -e
kubectl exec deploy/ledger -- sh -c 'printf "{BASELINE}" > /state/ledger'
"""

# A second service, declaring no reset and no tests of its own. Nothing is
# supposed to break because it declared neither.
PLAIN = """FROM alpine:3.20
RUN mkdir -p /state
CMD ["sh", "-c", "sleep infinity"]
"""


def build(fixture: Project) -> Project:
    """A project with a service that owns state, and one that does not."""
    fixture.codeowners("* @owner\n")

    fixture.service("ledger", env=f"LEDGER_PASSWORD={PASSWORD}\n")
    fixture.write("services/ledger/tests/run.sh", TESTS)
    fixture.write("services/ledger/deploy/reset.sh", RESET)
    fixture.manifest(
        "dev",
        "ledger-values",
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "ledger-values",
                "annotations": {"seal-test.dev/fill-from": "ledger"},
            },
            "type": "Opaque",
        },
    )
    fixture.deploys(
        "ledger",
        IMAGE,
        containers=[
            container("ledger", image="ledger", probe=False)
            | {
                "readinessProbe": SERVING,
                "envFrom": [{"secretRef": {"name": "ledger-values"}}],
            }
        ],
        development_stage="runtime",
        runtime_stage="runtime",
        test_stage="test",
        test_command="sh /app/tests/run.sh",
        junit_tests_directory="/app/tests-results/",
        reset="deploy/reset.sh",
    )

    fixture.service("plain", env="")
    fixture.deploys(
        "plain",
        PLAIN,
        containers=[
            container("plain", image="plain", probe=False) | {"readinessProbe": SERVING}
        ],
    )
    return fixture
