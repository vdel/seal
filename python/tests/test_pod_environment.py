"""Unit tests for whether every key a service declares reaches the process.

Almost all of this is pure: `accounted_in()` judges one overlay from the
documents it is handed, so what's asserted below needs no kustomize and no
cluster. The one kubectl-gated test at the bottom covers the walk itself --
that `unaccounted_keys()` reaches every overlay and aggregates across them.
"""

import shutil
from pathlib import Path

import pytest
import yaml

from seal.pod_environment import (
    UnconsumedKey,
    UnsourcedKey,
    _split,
    accounted_in,
    unaccounted_keys,
)
from seal.stubs import FILL_FROM_ANNOTATION, KEYS_ANNOTATION


def stub(name, service="api", kind="Secret", keys=None):
    annotations = {FILL_FROM_ANNOTATION: service}
    if keys is not None:
        annotations[KEYS_ANNOTATION] = keys
    return {
        "apiVersion": "v1",
        "kind": kind,
        "metadata": {"name": name, "annotations": annotations},
    }


def carrying(name, keys, kind="Secret"):
    """An object a project fills its own way -- an operator's target, or a
    committed dev fixture. Not a stub: it says what it holds."""
    return {
        "apiVersion": "v1",
        "kind": kind,
        "metadata": {"name": name},
        "data": {key: "" for key in keys},
    }


def deployment(name="web", container="api", env_from=(), env=()):
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": container,
                            "envFrom": [
                                {"secretRef": {"name": ref}}
                                if kind == "Secret"
                                else {"configMapRef": {"name": ref}}
                                for kind, ref in env_from
                            ],
                            "env": list(env),
                        }
                    ]
                }
            }
        },
    }


API = {"api": ["DEBUG", "DJANGO_SECRET_KEY"]}


# -- one overlay's own answer ----------------------------------------------


def test_a_stub_supplying_every_key_accounts_for_all_of_them():
    documents = [
        stub("api-secrets"),
        deployment(env_from=[("Secret", "api-secrets")]),
    ]

    unsourced, consumed = accounted_in("dev", documents, API)

    assert unsourced == []
    assert consumed["api"] == {"DEBUG", "DJANGO_SECRET_KEY"}


def test_a_container_short_a_key_is_named():
    """The failure that ships: the object is there, and supplies less than
    the service needs."""
    documents = [
        stub("api-config", kind="ConfigMap", keys="DEBUG"),
        deployment(env_from=[("ConfigMap", "api-config")]),
    ]

    unsourced, consumed = accounted_in("prod", documents, API)

    assert [problem.key for problem in unsourced] == ["DJANGO_SECRET_KEY"]
    problem = unsourced[0]
    assert problem.overlay == "prod"
    assert problem.deployment == "web"
    assert problem.container == "api"
    assert problem.service == "api"
    assert "no source for 'DJANGO_SECRET_KEY'" in problem.describe()
    assert consumed["api"] == {"DEBUG"}


def test_an_explicit_env_entry_accounts_for_its_name():
    """A literal value and a valueFrom are both a source. What is checked is
    that the name is accounted for, never where the value comes from."""
    documents = [
        stub("api-config", kind="ConfigMap", keys="DEBUG"),
        deployment(
            env_from=[("ConfigMap", "api-config")],
            env=[
                {
                    "name": "DJANGO_SECRET_KEY",
                    "valueFrom": {"secretKeyRef": {"name": "elsewhere", "key": "k"}},
                }
            ],
        ),
    ]

    unsourced, _ = accounted_in("prod", documents, API)

    assert unsourced == []


def test_an_object_a_project_fills_itself_supplies_what_it_carries():
    """A real environment's overlay carries an operator's target rather than
    a stub. Its own keys are what it supplies."""
    documents = [
        stub("api-config", kind="ConfigMap", keys="DEBUG"),
        carrying("api-db", ["DJANGO_SECRET_KEY"]),
        deployment(env_from=[("ConfigMap", "api-config"), ("Secret", "api-db")]),
    ]

    unsourced, _ = accounted_in("prod", documents, API)

    assert unsourced == []


def test_a_container_no_stub_reaches_is_not_any_services():
    """Which container is which service's comes from the annotation, not a
    name -- so a container reading nothing seal fills is simply not
    one these rules have anything to say about."""
    documents = [
        stub("api-secrets"),
        deployment(name="valkey", container="valkey"),
    ]

    unsourced, consumed = accounted_in("dev", documents, API)

    assert unsourced == []
    assert consumed["api"] == set()


def test_a_k8s_marked_key_is_never_expected():
    """`claimable` is what seal fills; a k8s:// key is the manifests'
    to declare individually and is not in it, so nothing asks for it."""
    documents = [
        stub("api-secrets"),
        deployment(env_from=[("Secret", "api-secrets")]),
    ]

    unsourced, _ = accounted_in("dev", documents, {"api": ["DEBUG"]})

    assert unsourced == []


def test_every_short_container_is_reported_not_the_first():
    documents = [
        stub("api-config", kind="ConfigMap", keys="DEBUG"),
        deployment(name="web", container="api", env_from=[("ConfigMap", "api-config")]),
        deployment(
            name="worker", container="celery", env_from=[("ConfigMap", "api-config")]
        ),
    ]

    unsourced, _ = accounted_in("prod", documents, API)

    assert {problem.deployment for problem in unsourced} == {"web", "worker"}


def test_a_project_with_no_env_at_all_has_nothing_to_say():
    unsourced, consumed = accounted_in("dev", [deployment()], {})

    assert unsourced == []
    assert consumed == {}


# -- across every overlay --------------------------------------------------


def _overlay(directory: Path, **documents):
    directory.mkdir(parents=True, exist_ok=True)
    for name, document in documents.items():
        (directory / f"{name}.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
    (directory / "kustomization.yaml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "kustomize.config.k8s.io/v1beta1",
                "kind": "Kustomization",
                "resources": [f"{name}.yaml" for name in documents],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.skipif(
    shutil.which("kubectl") is None,
    reason="needs kubectl, which builds a project's overlays",
)
def test_a_key_one_overlay_supplies_is_not_dead(tmp_path):
    """Aggregation across overlays: consumed anywhere means not dead, and
    only then is the overlay that lacks it worth naming."""
    k8s = tmp_path / "k8s"
    _overlay(
        k8s / "dev",
        secret=stub("api-secrets"),
        web=deployment(env_from=[("Secret", "api-secrets")]),
    )
    _overlay(
        k8s / "prod",
        config=stub("api-config", kind="ConfigMap", keys="DEBUG"),
        web=deployment(env_from=[("ConfigMap", "api-config")]),
    )

    unconsumed, unsourced = unaccounted_keys(k8s, API)

    assert unconsumed == []
    assert unsourced == [
        UnsourcedKey("prod", "web", "api", "api", "DJANGO_SECRET_KEY")
    ]


@pytest.mark.skipif(
    shutil.which("kubectl") is None,
    reason="needs kubectl, which builds a project's overlays",
)
def test_a_key_nothing_anywhere_consumes_is_reported_once(tmp_path):
    """One mistake, named once -- not again in every overlay that also
    lacks it."""
    k8s = tmp_path / "k8s"
    for overlay in ("dev", "prod"):
        _overlay(
            k8s / overlay,
            config=stub("api-config", kind="ConfigMap", keys="DEBUG"),
            web=deployment(env_from=[("ConfigMap", "api-config")]),
        )

    unconsumed, unsourced = unaccounted_keys(k8s, API)

    assert unconsumed == [UnconsumedKey("api", "DJANGO_SECRET_KEY")]
    assert unsourced == []
    assert "no container in any overlay" in unconsumed[0].describe()


def test_no_manifests_at_all_is_not_a_failure(tmp_path):
    assert unaccounted_keys(tmp_path / "nowhere", API) == ([], [])


def test_a_project_whose_overlays_declare_no_stub_says_nothing():
    """The convention-not-adopted case, and the one the worked example is in
    until its overlay grows a stub: no object in any overlay says seal
    fills it, so seal has not been asked to place these keys anywhere
    and has nothing to report. The same silence the outcome checks keep for
    a project with no outcome tree."""
    documents = [deployment(env_from=[("Secret", "some-secret")])]

    unsourced, consumed = accounted_in("dev", documents, API)

    assert unsourced == []
    # No entry at all, rather than an empty one: an empty entry would mean
    # "placed here and supplied nothing", which is the dead-key finding.
    assert consumed == {}


def test_an_unplaced_service_has_no_key_called_dead():
    """The regression this check shipped with: a project whose objects
    seal does not fill had every key of every `.env` reported dead,
    because nothing consumed them *through seal*. Nothing had asked
    it to place them in the first place."""
    unconsumed, unsourced = _split(unsourced=[], consumed={}, claimable=API)

    assert unconsumed == []
    assert unsourced == []


def test_a_placed_service_supplying_nothing_does_have_dead_keys():
    """The other side of the same line: once an overlay says seal
    fills something for this service, a key nothing supplies is a finding."""
    unconsumed, _ = _split(unsourced=[], consumed={"api": set()}, claimable=API)

    assert [problem.key for problem in unconsumed] == ["DEBUG", "DJANGO_SECRET_KEY"]
