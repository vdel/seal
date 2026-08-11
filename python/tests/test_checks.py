"""`seal check`, exercised against overlays written by the test rather than
the ones this repo happens to ship.

The point of the check is that any project adopting seal gets it, so the
fixtures here are synthetic projects in tmp_path: nothing asserted below is
true because of how the bundled example is laid out, and none of it stops
being checked if that example changes. The example gets its own coverage by
being run through `seal ci` in the Tilt workflow.

The fixtures are real kustomize overlays because the check builds them. What
a project deploys is the rendered result, not the files as written, and a
test writing loose manifests would be asserting about something no cluster
ever sees -- which is exactly the gap that let a patch amending a container
be read as one declaring it.

Needs `kubectl`, which builds them. Skips without it rather than failing,
the same way the Tiltfile-evaluation tests gate on tilt.
"""

import shutil
from pathlib import Path

import pytest
import yaml

from seal.checks import K8S_DIR_ENV_VAR, missing_readiness_probes
from seal.credentials import SealError
from seal.seal import main

PROBE = {"httpGet": {"path": "/healthz", "port": 8000}}

# Captured before any test can replace it. `seal.seal` and `seal.checks` both
# reach the one shutil module, so patching the lookup for one patches it for
# both -- and a stub calling shutil.which would be calling itself.
_REAL_WHICH = shutil.which

pytestmark = pytest.mark.skipif(
    shutil.which("kubectl") is None,
    reason="needs kubectl, which builds a project's overlays",
)


def _deployment(name: str, containers: list[dict]) -> dict:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {"containers": containers},
            },
        },
    }


def _write(path: Path, *documents: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump_all(documents), encoding="utf-8")
    return path


def _overlay(directory: Path, *documents: dict, **files: list[dict]) -> Path:
    """An overlay deploying `documents`, plus any extra `name=documents` file
    it needs for a patch to point at. Everything written is listed in the
    kustomization, since a file no kustomization names is a file no cluster
    sees."""
    resources = []
    for index, document in enumerate(documents):
        name = f"resource-{index}.yaml"
        _write(directory / name, document)
        resources.append(name)
    for name, extra in files.items():
        _write(directory / f"{name}.yaml", *extra)
    _write(
        directory / "kustomization.yaml",
        {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "resources": resources,
        },
    )
    return directory


def _patching(directory: Path, base: str, patch: dict, target: str) -> Path:
    """An overlay layered on `base`, applying `patch` to the Deployment
    named `target`."""
    _write(directory / "patch.yaml", patch)
    _write(
        directory / "kustomization.yaml",
        {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "resources": [base],
            "patches": [
                {
                    "path": "patch.yaml",
                    "target": {
                        "group": "apps",
                        "version": "v1",
                        "kind": "Deployment",
                        "name": target,
                    },
                }
            ],
        },
    )
    return directory


def _unreachable(*args, **kwargs):  # pragma: no cover - reaching this is the failure
    raise AssertionError("seal ci got past the readiness check")


def _finds_everything_but_tilt(name: str) -> str | None:
    """Looking for tilt is the first thing `seal ci` does that the readiness
    check is supposed to come before, so that lookup is the tripwire.

    Everything else resolves normally -- kubectl above all, which the check
    itself needs to build an overlay. A blanket stub would block the check
    rather than the run it is guarding, and pass for the wrong reason."""
    if name == "tilt":  # pragma: no cover - reaching this is the failure
        raise AssertionError("seal ci got past the readiness check")
    return _REAL_WHICH(name)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A minimal seal project root -- what find_seal_root() looks for --
    with an empty k8s/ for each test to fill in as it needs."""
    (tmp_path / "Tiltfile").write_text("# root Tiltfile\n", encoding="utf-8")
    (tmp_path / "services").mkdir()
    (tmp_path / "k8s").mkdir()
    monkeypatch.delenv(K8S_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# --- the rule ---------------------------------------------------------------


def test_a_probe_on_every_container_passes(project):
    _overlay(
        project / "k8s" / "dev",
        _deployment("web", [{"name": "api", "image": "api", "readinessProbe": PROBE}]),
    )

    assert missing_readiness_probes(project / "k8s") == []


def test_a_container_without_a_probe_is_reported(project):
    _overlay(project / "k8s" / "dev", _deployment("web", [{"name": "api", "image": "api"}]))

    (problem,) = missing_readiness_probes(project / "k8s")

    assert problem.deployment == "web"
    assert problem.container == "api"
    assert problem.overlay == "dev"


def test_every_container_of_a_multi_container_pod_is_checked(project):
    """A Deployment is only as ready as its least ready container, so one
    probe among several says nothing about the rest."""
    _overlay(
        project / "k8s" / "dev",
        _deployment(
            "web",
            [
                {"name": "api", "image": "api", "readinessProbe": PROBE},
                {"name": "ui", "image": "ui"},
                {"name": "nginx", "image": "nginx"},
            ],
        ),
    )

    assert [p.container for p in missing_readiness_probes(project / "k8s")] == ["ui", "nginx"]


def test_every_document_an_overlay_deploys_is_checked(project):
    """An overlay routinely brings up several workloads; stopping at the
    first would silently exempt everything after it."""
    _overlay(
        project / "k8s" / "dev",
        _deployment("web", [{"name": "api", "image": "api", "readinessProbe": PROBE}]),
        _deployment("worker", [{"name": "celery", "image": "celery"}]),
    )

    assert [p.deployment for p in missing_readiness_probes(project / "k8s")] == ["worker"]


def test_kinds_other_than_deployment_are_left_alone(project):
    """Only a Deployment's pods gate `tilt ci` on their containers' readiness
    in the way this check is about."""
    _overlay(
        project / "k8s" / "dev",
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "web"}},
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "env"}},
    )

    assert missing_readiness_probes(project / "k8s") == []


# --- what a patch does, and does not, declare -------------------------------


def test_a_container_a_patch_introduces_is_checked(project):
    """A container an overlay adds reaches the cluster like any other, and
    the base it was added to says nothing about its readiness."""
    _overlay(
        project / "k8s" / "base",
        _deployment("web", [{"name": "api", "image": "api", "readinessProbe": PROBE}]),
    )
    _patching(
        project / "k8s" / "dev",
        base="../base",
        patch=_deployment("web", [{"name": "ui", "image": "ui"}]),
        target="web",
    )

    problems = missing_readiness_probes(project / "k8s")

    assert [(p.overlay, p.container) for p in problems] == [("dev", "ui")]


def test_a_patch_that_only_amends_a_container_is_not_an_offender(project):
    """The probe lives in the base, and a patch adding a volumeMount has no
    business restating it. Requiring one would mean copying a probe into
    every patch that touches a container, and a copied probe is one that
    goes stale against the container it claims to describe."""
    _overlay(
        project / "k8s" / "base",
        _deployment("web", [{"name": "api", "image": "api", "readinessProbe": PROBE}]),
    )
    _patching(
        project / "k8s" / "dev",
        base="../base",
        patch={
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "web"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "api",
                                "volumeMounts": [{"name": "cache", "mountPath": "/cache"}],
                            }
                        ],
                        "volumes": [{"name": "cache", "emptyDir": {}}],
                    }
                }
            },
        },
        target="web",
    )

    assert missing_readiness_probes(project / "k8s") == []


def test_a_container_a_patch_deletes_is_not_an_offender(project):
    """There is no container left to report. A shape that drops one -- a dev
    server a production-shaped overlay has no use for -- would otherwise be
    asked for a probe on something it just removed."""
    _overlay(
        project / "k8s" / "base",
        _deployment(
            "web",
            [
                {"name": "api", "image": "api", "readinessProbe": PROBE},
                {"name": "ui", "image": "ui", "readinessProbe": PROBE},
            ],
        ),
    )
    _patching(
        project / "k8s" / "dev",
        base="../base",
        patch={
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "web"},
            "spec": {
                "template": {"spec": {"containers": [{"name": "ui", "$patch": "delete"}]}}
            },
        },
        target="web",
    )

    assert missing_readiness_probes(project / "k8s") == []


def test_an_init_container_needs_no_probe(project):
    """It runs to completion before the pod's containers start, so readiness
    is not a question it can answer -- and the ordering a project wants from
    it is what Kubernetes already guarantees."""
    deployment = _deployment(
        "web", [{"name": "api", "image": "api", "readinessProbe": PROBE}]
    )
    deployment["spec"]["template"]["spec"]["initContainers"] = [
        {"name": "assets", "image": "assets", "command": ["cp", "-R", "/in", "/out"]}
    ]
    _overlay(project / "k8s" / "dev", deployment)

    assert missing_readiness_probes(project / "k8s") == []


def test_a_patch_that_declares_no_containers_is_not_an_offender(project):
    """Patches that only change `replicas` or labels have nothing to say
    about readiness, and flagging them would be noise a project learns to
    ignore."""
    _overlay(
        project / "k8s" / "base",
        _deployment("web", [{"name": "api", "image": "api", "readinessProbe": PROBE}]),
    )
    _patching(
        project / "k8s" / "dev",
        base="../base",
        patch={
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "web"},
            "spec": {"replicas": 2},
        },
        target="web",
    )

    assert missing_readiness_probes(project / "k8s") == []


# --- several shapes ---------------------------------------------------------


def test_each_overlay_is_reported_under_its_own_name(project):
    """Which shape is broken is the first thing a reader needs: the same
    container can be fine in the shape they work in and missing a probe in
    the shape that ships."""
    _overlay(
        project / "k8s" / "dev",
        _deployment("web", [{"name": "api", "image": "api", "readinessProbe": PROBE}]),
    )
    _overlay(project / "k8s" / "non-dev", _deployment("web", [{"name": "api", "image": "api"}]))

    problems = missing_readiness_probes(project / "k8s")

    assert [(p.overlay, p.container) for p in problems] == [("non-dev", "api")]


def test_a_base_both_shapes_deploy_is_reported_for_each(project):
    """Fixing one shape has not fixed the other, and a project told about
    only one of them would think it had."""
    _overlay(project / "k8s" / "base", _deployment("web", [{"name": "api", "image": "api"}]))
    for shape in ("dev", "non-dev"):
        _patching(
            project / "k8s" / shape,
            base="../base",
            patch={
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "web"},
                "spec": {"replicas": 1},
            },
            target="web",
        )

    assert sorted(p.overlay for p in missing_readiness_probes(project / "k8s")) == [
        "base",
        "dev",
        "non-dev",
    ]


def test_a_directory_below_an_overlay_is_part_of_it(project):
    """Overlays are the directories a run can name, so a component folder
    inside one is checked through the overlay that builds it rather than as
    a shape of its own."""
    _write(
        project / "k8s" / "dev" / "celery" / "worker.yaml",
        _deployment("celery-worker", [{"name": "celery", "image": "celery"}]),
    )
    _write(
        project / "k8s" / "dev" / "kustomization.yaml",
        {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "resources": ["celery/worker.yaml"],
        },
    )

    problems = missing_readiness_probes(project / "k8s")

    assert [(p.overlay, p.deployment) for p in problems] == [("dev", "celery-worker")]


# --- what the check refuses to guess at -------------------------------------


def test_an_overlay_that_will_not_build_says_so(project):
    """A shape kustomize refuses is a shape nothing can deploy, so finding
    out here beats finding out from Tilt several minutes into a run."""
    _write(
        project / "k8s" / "dev" / "kustomization.yaml",
        {
            "apiVersion": "kustomize.config.k8s.io/v1beta1",
            "kind": "Kustomization",
            "resources": ["nothing-is-here.yaml"],
        },
    )

    with pytest.raises(SealError) as error:
        missing_readiness_probes(project / "k8s")

    assert "dev" in str(error.value)


def test_a_directory_with_no_overlays_is_an_error(project):
    """Manifests no kustomization names are manifests nothing deploys.
    Passing a project whose overlays the check never found would be the
    false green this whole rule exists to prevent."""
    _write(project / "k8s" / "web.yaml", _deployment("web", [{"name": "api", "image": "api"}]))

    with pytest.raises(SealError) as error:
        missing_readiness_probes(project / "k8s")

    assert "overlay" in str(error.value)


def test_a_missing_k8s_directory_is_an_error(project):
    with pytest.raises(SealError) as error:
        missing_readiness_probes(project / "nowhere")

    assert "--k8s-dir" in str(error.value)


def test_a_missing_kubectl_is_an_error_naming_it(project, monkeypatch):
    """A check that quietly passed because it could not run would be worth
    less than no check."""
    _overlay(project / "k8s" / "dev", _deployment("web", [{"name": "api", "image": "api"}]))
    monkeypatch.setattr("seal.checks.shutil.which", lambda _: None)

    with pytest.raises(SealError) as error:
        missing_readiness_probes(project / "k8s")

    assert "kubectl" in str(error.value)


# --- through the CLI --------------------------------------------------------


def test_seal_check_succeeds_on_a_project_that_passes(project, capsys):
    _overlay(
        project / "k8s" / "dev",
        _deployment("web", [{"name": "api", "image": "api", "readinessProbe": PROBE}]),
    )

    assert main(["check"]) == 0
    assert "readinessProbe" in capsys.readouterr().out


def test_seal_check_reports_every_offender_at_once(project, capsys):
    """One failed run should be enough to fix a project, rather than
    surfacing the next container only once the last one is done."""
    _overlay(
        project / "k8s" / "dev",
        _deployment("web", [{"name": "api", "image": "api"}, {"name": "ui", "image": "ui"}]),
        _deployment("worker", [{"name": "celery", "image": "celery"}]),
    )

    assert main(["check"]) == 1

    errors = capsys.readouterr().err
    assert "overlay 'dev': Deployment 'web', container 'api'" in errors
    assert "overlay 'dev': Deployment 'web', container 'ui'" in errors
    assert "overlay 'dev': Deployment 'worker', container 'celery'" in errors


def test_seal_check_looks_where_k8s_dir_says(project, capsys):
    """A project is free to lay its manifests out somewhere other than
    k8s/, and the check has to be able to follow."""
    _overlay(project / "deploy" / "dev", _deployment("web", [{"name": "api", "image": "api"}]))

    assert main(["check", "--k8s-dir", "deploy"]) == 1
    assert "overlay 'dev'" in capsys.readouterr().err


def test_seal_ci_refuses_to_start_when_a_probe_is_missing(project, monkeypatch, capsys):
    """`seal ci`'s whole value is that a green run means the environment came
    up. Starting Tilt against manifests that can't report that honestly would
    produce exactly the false green this check exists to prevent -- so the
    check runs before anything that costs time or touches credentials."""
    _overlay(project / "k8s" / "dev", _deployment("web", [{"name": "api", "image": "api"}]))

    monkeypatch.setattr("seal.seal._fill_declared_objects", _unreachable)
    monkeypatch.setattr("seal.seal.shutil.which", _finds_everything_but_tilt)

    assert main(["ci"]) == 1
    assert "no readinessProbe" in capsys.readouterr().err


def test_the_k8s_dir_env_var_is_what_seal_ci_can_be_told(project, monkeypatch, capsys):
    """`seal ci` forwards its arguments to `tilt ci` untouched, so a project
    whose manifests aren't in k8s/ has no flag to reach for -- this is how it
    says where they are, and both commands read the same answer."""
    _overlay(project / "deploy" / "dev", _deployment("web", [{"name": "api", "image": "api"}]))
    monkeypatch.setenv(K8S_DIR_ENV_VAR, "deploy")

    monkeypatch.setattr("seal.seal._fill_declared_objects", _unreachable)
    monkeypatch.setattr("seal.seal.shutil.which", _finds_everything_but_tilt)

    assert main(["check"]) == 1
    assert main(["ci"]) == 1
    assert "overlay 'dev'" in capsys.readouterr().err


def test_an_explicit_k8s_dir_wins_over_the_env_var(project, monkeypatch):
    _overlay(
        project / "deploy" / "dev",
        _deployment("web", [{"name": "api", "image": "api", "readinessProbe": PROBE}]),
    )
    _overlay(project / "other" / "dev", _deployment("web", [{"name": "api", "image": "api"}]))
    monkeypatch.setenv(K8S_DIR_ENV_VAR, "deploy")

    assert main(["check"]) == 0
    assert main(["check", "--k8s-dir", "other"]) == 1
