"""Unit tests for reading what an overlay's stubs claim (stubs.py).

Every document here is one the test writes, as the dict a built overlay
would produce -- so nothing needs kubectl, Tilt, or the bundled example, and
what's asserted is what any adopting project gets.
"""

from seal.stubs import (
    FILL_FROM_ANNOTATION,
    KEYS_ANNOTATION,
    Stub,
    claims,
    stubs_in,
)


def a_stub(kind="Secret", name="api-db", service="api", keys=None, **metadata):
    annotations = {FILL_FROM_ANNOTATION: service} if service else {}
    if keys is not None:
        annotations[KEYS_ANNOTATION] = keys
    document = {
        "apiVersion": "v1",
        "kind": kind,
        "metadata": {"name": name, "annotations": annotations},
    }
    document["metadata"].update(metadata)
    return document


# -- finding stubs among an overlay's documents ----------------------------


def test_a_secret_and_a_configmap_are_both_stubs():
    found = stubs_in(
        [
            a_stub(kind="Secret", name="api-db"),
            a_stub(kind="ConfigMap", name="api-config"),
        ]
    )

    assert [(stub.kind, stub.name) for stub in found] == [
        ("Secret", "api-db"),
        ("ConfigMap", "api-config"),
    ]
    assert {stub.service for stub in found} == {"api"}


def test_an_object_with_no_fill_from_is_not_a_stub():
    """Most of an overlay is somebody else's -- a Secret a project fills its
    own way is not seal's to touch."""
    plain = {"kind": "Secret", "metadata": {"name": "postgresql"}}

    assert stubs_in([plain]) == []


def test_a_kind_seal_cannot_fill_is_not_a_stub():
    """The annotation says which service's `.env` fills an object. On a
    Deployment that is not a claim seal can act on, so it is not one
    it reads as one."""
    assert stubs_in([a_stub(kind="Deployment", name="web")]) == []


def test_no_keys_annotation_is_none_not_empty():
    """A stub naming no keys claims the rest; one naming an empty list would
    claim nothing. Only the first is a thing a project writes on purpose."""
    (stub,) = stubs_in([a_stub()])

    assert stub.keys is None


def test_a_key_list_is_split_and_stripped():
    (stub,) = stubs_in([a_stub(keys=" DEBUG , LOG_LEVEL ")])

    assert stub.keys == ("DEBUG", "LOG_LEVEL")


def test_other_metadata_does_not_stop_it_being_a_stub():
    (stub,) = stubs_in([a_stub(labels={"app": "api"})])

    assert stub.service == "api"


# -- what each stub claims -------------------------------------------------


def test_a_stub_naming_no_keys_claims_everything_claimable():
    stubs = stubs_in([a_stub(name="api-secrets")])

    claimed, problems = claims(stubs, {"api": ["DEBUG", "DJANGO_SECRET_KEY"]})

    assert problems == []
    assert claimed[stubs[0]] == ("DEBUG", "DJANGO_SECRET_KEY")


def test_a_split_gives_each_stub_its_own_keys():
    stubs = stubs_in(
        [
            a_stub(kind="ConfigMap", name="api-config", keys="DEBUG"),
            a_stub(kind="Secret", name="api-db"),
        ]
    )

    claimed, problems = claims(stubs, {"api": ["DEBUG", "DJANGO_SECRET_KEY"]})

    assert problems == []
    assert claimed[stubs[0]] == ("DEBUG",)
    # The catch-all takes what the split one left, without naming it.
    assert claimed[stubs[1]] == ("DJANGO_SECRET_KEY",)


def test_a_service_with_no_stub_at_all_claims_nothing_and_is_no_problem():
    """A project that marks no stubs has seal fill nothing -- the case
    for running an operator in a session cluster too."""
    claimed, problems = claims([], {"api": ["DEBUG"]})

    assert claimed == {}
    assert problems == []


def test_two_stubs_claiming_one_key_names_both():
    stubs = stubs_in(
        [
            a_stub(name="api-config", keys="DEBUG"),
            a_stub(name="api-other", keys="DEBUG"),
        ]
    )

    _, problems = claims(stubs, {"api": ["DEBUG"]})

    assert len(problems) == 1
    assert "DEBUG" in problems[0]
    assert "api-config" in problems[0]
    assert "api-other" in problems[0]


def test_two_catch_alls_for_one_service_is_a_problem():
    """Both would claim the remainder, and which wins is not something a
    project should have to know."""
    stubs = stubs_in([a_stub(name="api-one"), a_stub(name="api-two")])

    _, problems = claims(stubs, {"api": ["DEBUG"]})

    assert len(problems) == 1
    assert "api-one" in problems[0]
    assert "api-two" in problems[0]
    assert KEYS_ANNOTATION in problems[0]


def test_a_key_the_env_does_not_declare_is_named():
    stubs = stubs_in([a_stub(name="api-config", keys="TYPO")])

    _, problems = claims(stubs, {"api": ["DEBUG"]})

    assert len(problems) == 1
    assert "TYPO" in problems[0]
    assert "api" in problems[0]


def test_a_service_with_no_env_is_named():
    stubs = stubs_in([a_stub(name="ui-config", service="ui")])

    claimed, problems = claims(stubs, {"api": ["DEBUG"]})

    assert len(problems) == 1
    assert "ui" in problems[0]
    assert FILL_FROM_ANNOTATION in problems[0]
    assert claimed[stubs[0]] == ()


def test_every_problem_is_reported_not_the_first():
    """A project should be able to put its overlay right in one pass."""
    stubs = stubs_in(
        [
            a_stub(name="api-config", keys="TYPO"),
            a_stub(name="ui-config", service="ui"),
            a_stub(name="api-one"),
            a_stub(name="api-two"),
        ]
    )

    _, problems = claims(stubs, {"api": ["DEBUG"]})

    assert len(problems) == 3


def test_a_claim_is_keyed_by_the_stub_it_belongs_to():
    """Two stubs of different kinds can share a name across an overlay's own
    objects, so what a claim is looked up by has to tell them apart."""
    stubs = stubs_in(
        [
            a_stub(kind="ConfigMap", name="api", keys="DEBUG"),
            a_stub(kind="Secret", name="api"),
        ]
    )

    claimed, problems = claims(stubs, {"api": ["DEBUG", "DJANGO_SECRET_KEY"]})

    assert problems == []
    assert claimed[Stub("ConfigMap", "api", "api", ("DEBUG",))] == ("DEBUG",)
    assert claimed[Stub("Secret", "api", "api", None)] == ("DJANGO_SECRET_KEY",)
