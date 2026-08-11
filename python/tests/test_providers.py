"""Unit tests for reading `seal-credentials-config.json` (providers.py).

Every fixture here is built by the test itself. Nothing asserts on the
worked example's own config, and no real password manager is named except
where a test is checking that seal carries a project's chosen words through
untouched.
"""

import json

import pytest

from seal import providers


def write_config(root, document):
    path = root / providers.CONFIG_FILENAME
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def a_provider(**overrides):
    """A well-formed entry, so each test can break one thing at a time."""
    entry = {
        "scheme": "store://",
        "name": "A Store",
        "cli": "store-cli",
        "install_hint": "https://example.invalid/install",
        "form": "run",
        "reference": "store://{vault}/{item}",
        "command": ["store-cli", "run", "--env-file", "{env_file}", "--", "{command}"],
        "environments": {"dev": {"vault": "proj-dev"}, "prod": {"vault": "proj-prod"}},
    }
    entry.update(overrides)
    return {key: value for key, value in entry.items() if value is not None}


def test_well_formed_config_parses(tmp_path):
    write_config(tmp_path, {"default_env": "dev", "provider": [a_provider()]})

    declaration, problems = providers.read_config(tmp_path)

    assert problems == []
    assert declaration.default_env == "dev"
    assert len(declaration.providers) == 1
    provider = declaration.providers[0]
    assert provider.scheme == "store://"
    assert provider.name == "A Store"
    assert provider.cli == "store-cli"
    assert provider.install_hint == "https://example.invalid/install"
    assert provider.form == providers.RUN
    assert provider.reference == "store://{vault}/{item}"
    assert provider.command == (
        "store-cli", "run", "--env-file", "{env_file}", "--", "{command}",
    )
    assert provider.environments == {
        "dev": {"vault": "proj-dev"},
        "prod": {"vault": "proj-prod"},
    }


def test_no_config_file_is_not_a_problem(tmp_path):
    """A project of literals and k8s:// markers reaches no provider, so it
    has nothing to declare and is not asked to."""
    declaration, problems = providers.read_config(tmp_path)

    assert problems == []
    assert declaration == providers.EMPTY


def test_optional_fields_default(tmp_path):
    write_config(
        tmp_path,
        {
            "provider": [
                {
                    "scheme": "store://",
                    "cli": "store-cli",
                    "form": "run",
                    "command": ["store-cli", "get", "{item}"],
                }
            ]
        },
    )

    declaration, problems = providers.read_config(tmp_path)

    assert problems == []
    provider = declaration.providers[0]
    # A provider naming its scope on the command line composes the item alone.
    assert provider.reference == providers.DEFAULT_REFERENCE
    # Nothing to call it by but the binary, which is what an error will say.
    assert provider.name == "store-cli"
    assert provider.install_hint is None
    assert provider.environments == {}
    assert declaration.default_env is None


def test_malformed_json_names_the_problem(tmp_path):
    (tmp_path / providers.CONFIG_FILENAME).write_text("{not json", encoding="utf-8")

    declaration, problems = providers.read_config(tmp_path)

    assert declaration == providers.EMPTY
    assert len(problems) == 1
    assert "cannot be read as JSON" in problems[0]


def test_document_that_is_not_an_object(tmp_path):
    write_config(tmp_path, ["store://"])

    _, problems = providers.read_config(tmp_path)

    assert len(problems) == 1
    assert "is not a JSON object" in problems[0]


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"scheme": None}, "has no 'scheme'"),
        ({"scheme": "store"}, "does not end in '://'"),
        ({"cli": None}, "has no 'cli'"),
        ({"form": None}, "has no 'form'"),
        ({"command": None}, "has no 'command'"),
    ],
)
def test_missing_required_field(tmp_path, overrides, expected):
    write_config(tmp_path, {"provider": [a_provider(**overrides)]})

    declaration, problems = providers.read_config(tmp_path)

    assert declaration.providers == ()
    assert any(expected in problem for problem in problems), problems
    assert all(problem.startswith("provider[0]") for problem in problems), problems


def test_unknown_form_lists_the_forms(tmp_path):
    write_config(tmp_path, {"provider": [a_provider(form="telepathy")]})

    _, problems = providers.read_config(tmp_path)

    assert len(problems) == 1
    assert "'telepathy'" in problems[0]
    for form in providers.FORMS:
        assert form in problems[0]


def test_every_declarable_form_is_implemented():
    """A form a project can declare and seal parses without complaint is one
    seal can actually run -- there is no state where a `.env` resolves fine
    up to the point of asking a store for a value, and only then finds out
    the form was never wired up."""
    assert providers.IMPLEMENTED_FORMS == providers.FORMS


@pytest.mark.parametrize("form", providers.FORMS)
def test_every_form_parses_without_complaint(tmp_path, form):
    write_config(tmp_path, {"provider": [a_provider(form=form)]})

    _, problems = providers.read_config(tmp_path)

    assert problems == []


def test_command_has_to_be_a_list_of_strings(tmp_path):
    write_config(tmp_path, {"provider": [a_provider(command="store-cli run")]})

    _, problems = providers.read_config(tmp_path)

    assert len(problems) == 1
    assert "list of strings" in problems[0]


def test_empty_command_is_refused(tmp_path):
    write_config(tmp_path, {"provider": [a_provider(command=[])]})

    _, problems = providers.read_config(tmp_path)

    assert len(problems) == 1
    assert "non-empty list" in problems[0]


@pytest.mark.parametrize(
    "environments",
    [
        "dev",
        {"dev": "proj-dev"},
        {"dev": {"vault": 3}},
    ],
)
def test_environments_has_to_be_objects_of_strings(tmp_path, environments):
    write_config(tmp_path, {"provider": [a_provider(environments=environments)]})

    _, problems = providers.read_config(tmp_path)

    assert len(problems) == 1
    assert providers.ENVIRONMENTS_FIELD in problems[0]


def test_unknown_provider_field_is_refused(tmp_path):
    write_config(tmp_path, {"provider": [a_provider(vaultt="typo")]})

    _, problems = providers.read_config(tmp_path)

    assert len(problems) == 1
    assert "'vaultt'" in problems[0]


def test_unknown_top_level_field_is_refused(tmp_path):
    write_config(tmp_path, {"provider": [a_provider()], "defualt_env": "dev"})

    _, problems = providers.read_config(tmp_path)

    assert len(problems) == 1
    assert "'defualt_env'" in problems[0]


def test_two_providers_cannot_share_a_scheme(tmp_path):
    write_config(tmp_path, {"provider": [a_provider(), a_provider(cli="other-cli")]})

    _, problems = providers.read_config(tmp_path)

    assert len(problems) == 1
    assert "already does" in problems[0]


def test_every_problem_is_reported_not_the_first(tmp_path):
    """A project should be able to put its config right in one pass."""
    write_config(
        tmp_path,
        {"provider": [{"form": "telepathy", "command": []}]},
    )

    _, problems = providers.read_config(tmp_path)

    assert len(problems) >= 3


def test_for_scheme_picks_the_matching_provider(tmp_path):
    write_config(
        tmp_path,
        {
            "provider": [
                a_provider(),
                a_provider(scheme="other://", cli="other-cli", reference="other://{item}"),
            ]
        },
    )

    declaration, problems = providers.read_config(tmp_path)

    assert problems == []
    assert declaration.for_scheme("store://a/b").cli == "store-cli"
    assert declaration.for_scheme("other://a/b").cli == "other-cli"
    assert declaration.for_scheme("k8s://") is None
    assert declaration.for_scheme("a-plain-literal") is None


def test_scope_for_a_declared_environment(tmp_path):
    write_config(tmp_path, {"provider": [a_provider()]})

    declaration, _ = providers.read_config(tmp_path)
    provider = declaration.providers[0]

    assert provider.scope("prod") == {"vault": "proj-prod"}
    assert provider.scope("staging") is None
    assert provider.scope(None) is None


def test_a_provider_declaring_no_environments_scopes_some_other_way(tmp_path):
    """Not every store has a scope to name -- one may scope by whatever
    session the CLI is already authenticated for. That is an empty scope,
    not a missing one, so no environment has to be selected for it."""
    write_config(tmp_path, {"provider": [a_provider(environments=None)]})

    declaration, _ = providers.read_config(tmp_path)

    assert declaration.providers[0].scope(None) == {}
    assert declaration.providers[0].scope("anything") == {}


def test_fill_substitutes_every_placeholder():
    assert providers.fill("s://{vault}/{item}", {"vault": "v", "item": "i/f"}) == "s://v/i/f"


def test_fill_leaves_text_without_placeholders_alone():
    assert providers.fill("no braces here", {}) == "no braces here"


def test_fill_does_not_rescan_what_it_substituted():
    """A store is free to keep a value with braces in it."""
    filled = providers.fill("{item}", {"item": "{vault}", "vault": "never used"})

    assert filled == "{vault}"


def test_fill_raises_on_a_name_it_cannot_supply():
    with pytest.raises(providers.UnknownPlaceholder) as raised:
        providers.fill("s://{vault}/{item}", {"item": "i"})

    assert raised.value.name == "vault"
    assert raised.value.available == ("item",)
    assert "vault" in str(raised.value)


def test_fill_argv_fills_word_by_word():
    argv = providers.fill_argv(
        ["cli", "--vault", "{vault}", "--", "{command}"],
        {"vault": "a vault with spaces", "command": "run"},
    )

    # One filled value is one argument, however much whitespace it holds.
    assert argv == ["cli", "--vault", "a vault with spaces", "--", "run"]
