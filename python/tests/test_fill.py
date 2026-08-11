"""Unit tests for filling the objects an overlay names (fill.py).

Pure: what's asserted is the patch text and the kustomization written beside
it, both read straight back off disk. Whether kustomize and Tilt then do
what these files ask is settled by the example's own CI and by the
tilt-gated test, not guessed at here.
"""

import base64

import yaml

from seal.fill import (
    KUSTOMIZATION_FILENAME,
    filled_dir,
    patch_for,
    write_filled,
)
from seal.stubs import Stub


def a_stub(kind="Secret", name="api-db", service="api", keys=None):
    return Stub(kind=kind, name=name, service=service, keys=keys)


# -- one stub, as a patch --------------------------------------------------


def test_a_secret_patch_carries_base64_values():
    document = yaml.safe_load(patch_for(a_stub(), {"DEBUG": "0"}))

    assert document["kind"] == "Secret"
    assert document["metadata"]["name"] == "api-db"
    assert base64.b64decode(document["data"]["DEBUG"]).decode("utf-8") == "0"


def test_a_configmap_patch_carries_plain_values():
    """Which kind an object is decides RBAC and what `kubectl describe`
    prints, which is why the project picks it -- and a ConfigMap holding
    base64 would be a Secret wearing the wrong name."""
    document = yaml.safe_load(patch_for(a_stub(kind="ConfigMap"), {"DEBUG": "0"}))

    assert document["kind"] == "ConfigMap"
    assert document["data"]["DEBUG"] == "0"


def test_a_patch_names_only_what_kustomize_matches_on():
    """Everything else the project wrote about this object is already in the
    overlay; a patch restating it would be a second place to keep it right."""
    document = yaml.safe_load(patch_for(a_stub(), {"DEBUG": "0"}))

    assert set(document) == {"apiVersion", "kind", "metadata", "data"}
    assert set(document["metadata"]) == {"name"}


def test_a_value_that_looks_like_yaml_survives_a_configmap_patch():
    """A resolved value is arbitrary text. Quoting it correctly by hand is
    what works until a value contains a colon."""
    tricky = "- not\n  a: list"
    document = yaml.safe_load(patch_for(a_stub(kind="ConfigMap"), {"K": tricky}))

    assert document["data"]["K"] == tricky


def test_an_empty_value_stays_an_empty_string():
    plain = yaml.safe_load(patch_for(a_stub(kind="ConfigMap"), {"K": ""}))
    secret = yaml.safe_load(patch_for(a_stub(), {"K": ""}))

    assert plain["data"]["K"] == ""
    assert secret["data"]["K"] == ""


# -- a whole overlay's worth -----------------------------------------------


def test_writes_a_patch_per_stub_and_a_kustomization(tmp_path):
    overlay = tmp_path / "k8s" / "dev"
    overlay.mkdir(parents=True)
    config = a_stub(kind="ConfigMap", name="api-config", keys=("DEBUG",))
    secret = a_stub(kind="Secret", name="api-db", keys=None)

    directory = write_filled(
        tmp_path,
        "dev",
        overlay,
        {config: ("DEBUG",), secret: ("DJANGO_SECRET_KEY",)},
        {"api": {"DEBUG": "0", "DJANGO_SECRET_KEY": "s3cret"}},
    )

    assert directory == filled_dir(tmp_path, "dev")
    kustomization = yaml.safe_load(
        (directory / KUSTOMIZATION_FILENAME).read_text(encoding="utf-8")
    )
    # The real overlay, named relatively: kustomize refuses an absolute root.
    assert kustomization["resources"] == ["../../../k8s/dev"]
    assert kustomization["patches"] == [
        {"path": "configmap-api-config.yaml"},
        {"path": "secret-api-db.yaml"},
    ]
    # Every patch path is local to this kustomization's own root, so nothing
    # depends on how permissive kustomize's load restrictor happens to be.
    for patch in kustomization["patches"]:
        assert (directory / patch["path"]).is_file()


def test_each_key_lands_in_exactly_one_object(tmp_path):
    overlay = tmp_path / "k8s" / "dev"
    overlay.mkdir(parents=True)
    config = a_stub(kind="ConfigMap", name="api-config", keys=("DEBUG",))
    secret = a_stub(kind="Secret", name="api-db")

    directory = write_filled(
        tmp_path,
        "dev",
        overlay,
        {config: ("DEBUG",), secret: ("DJANGO_SECRET_KEY",)},
        {"api": {"DEBUG": "0", "DJANGO_SECRET_KEY": "s3cret"}},
    )

    in_config = yaml.safe_load(
        (directory / "configmap-api-config.yaml").read_text(encoding="utf-8")
    )["data"]
    in_secret = yaml.safe_load(
        (directory / "secret-api-db.yaml").read_text(encoding="utf-8")
    )["data"]

    assert set(in_config) == {"DEBUG"}
    assert set(in_secret) == {"DJANGO_SECRET_KEY"}


def test_an_overlay_declaring_no_stub_writes_nothing(tmp_path):
    """A project running an operator in its session cluster too marks
    nothing, and what deploys is its own overlay, untouched."""
    overlay = tmp_path / "k8s" / "prod"
    overlay.mkdir(parents=True)

    assert write_filled(tmp_path, "prod", overlay, {}, {}) is None
    assert not filled_dir(tmp_path, "prod").exists()


def test_a_stale_patch_from_a_previous_run_is_removed(tmp_path):
    """An overlay that stopped declaring a stub would otherwise keep being
    handed the values it used to claim."""
    overlay = tmp_path / "k8s" / "dev"
    overlay.mkdir(parents=True)
    directory = filled_dir(tmp_path, "dev")
    directory.mkdir(parents=True)
    (directory / "secret-gone.yaml").write_text("stale\n", encoding="utf-8")

    write_filled(
        tmp_path, "dev", overlay, {a_stub(): ("DEBUG",)}, {"api": {"DEBUG": "0"}}
    )

    assert not (directory / "secret-gone.yaml").exists()
    assert (directory / "secret-api-db.yaml").is_file()


def test_a_key_no_value_was_resolved_for_is_simply_absent(tmp_path):
    """A `k8s://`-marked key never reaches resolution, so no stub can be
    handed one -- and a patch inventing an empty value for it would
    overwrite whatever the manifests point it at."""
    overlay = tmp_path / "k8s" / "dev"
    overlay.mkdir(parents=True)

    directory = write_filled(
        tmp_path,
        "dev",
        overlay,
        {a_stub(): ("DEBUG", "DATABASE_URL")},
        {"api": {"DEBUG": "0"}},
    )

    data = yaml.safe_load(
        (directory / "secret-api-db.yaml").read_text(encoding="utf-8")
    )["data"]
    assert set(data) == {"DEBUG"}


def test_two_kinds_sharing_a_name_do_not_collide(tmp_path):
    """A ConfigMap and a Secret may both be called `api` -- legal in
    Kubernetes, and it has to stay legal here."""
    overlay = tmp_path / "k8s" / "dev"
    overlay.mkdir(parents=True)
    config = a_stub(kind="ConfigMap", name="api", keys=("DEBUG",))
    secret = a_stub(kind="Secret", name="api")

    directory = write_filled(
        tmp_path,
        "dev",
        overlay,
        {config: ("DEBUG",), secret: ("DJANGO_SECRET_KEY",)},
        {"api": {"DEBUG": "0", "DJANGO_SECRET_KEY": "s3cret"}},
    )

    assert (directory / "configmap-api.yaml").is_file()
    assert (directory / "secret-api.yaml").is_file()
