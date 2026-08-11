"""Unit tests for resolving a service's `.env` through what a project
declared (credentials.py + providers.py).

A `.env` value names an item; the store it lives in comes from the
project's own `seal-credentials-config.json`. These tests build every
declaration themselves and name no real password manager -- the providers
here are shell scripts the test writes, which is the whole contract a
provider has to meet.
"""

import json
import os
import pathlib
import stat
import subprocess
import tempfile

import pytest

from seal import providers
from seal.credentials import (
    Context,
    SealError,
    CredentialProblem,
    composed_values,
    declaration_problems,
    discover_service_env_files,
    parse_env_file,
    providers_needed,
    resolve,
    resolvable_values,
    undeclared_scheme_problem,
)


def a_declaration(tmp_path, *entries, default_env=None):
    document = {"provider": list(entries)}
    if default_env is not None:
        document["default_env"] = default_env
    (tmp_path / providers.CONFIG_FILENAME).write_text(
        json.dumps(document), encoding="utf-8"
    )
    declaration, problems = providers.read_config(tmp_path)
    assert problems == [], problems
    return declaration


def an_entry(**overrides):
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


def a_context(declaration, environment="dev", service="api"):
    return Context(
        declaration=declaration, environment=environment, service_name=service
    )


# A provider that really meets the `run` contract: take `--env-file`, read
# the references it holds, put a value for each in the environment, and exec
# whatever follows `--`. Resolving a reference to "resolved:<reference>" is
# what lets a test assert which store a value came out of.
RUN_PROVIDER = """#!/bin/sh
env_file=""
while [ $# -gt 0 ]; do
  case "$1" in
    --env-file) env_file="$2"; shift 2 ;;
    --) shift; break ;;
    *) shift ;;
  esac
done
while IFS='=' read -r key ref; do
  [ -n "$key" ] || continue
  export "$key=resolved:$ref"
done < "$env_file"
exec "$@"
"""

# One that exits without running anything, for the failure path.
FAILING_PROVIDER = """#!/bin/sh
echo "the store said no" >&2
exit 7
"""


def on_path(tmp_path, monkeypatch, *names, script=RUN_PROVIDER):
    """Put executables of these names where shutil.which will find them."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in names:
        path = bin_dir / name
        path.write_text(script, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


# -- `.env` parsing -------------------------------------------------------


def test_parse_env_file_takes_values_as_written(tmp_path):
    """No substitution of any kind: a value is a literal, a k8s:// marker,
    or a reference naming an item."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "DEBUG=0\n"
        "DATABASE_URL=k8s://\n"
        "DJANGO_SECRET_KEY=store://django-secret-key/password\n",
        encoding="utf-8",
    )

    assert parse_env_file(env_path) == {
        "DEBUG": "0",
        "DATABASE_URL": "k8s://",
        "DJANGO_SECRET_KEY": "store://django-secret-key/password",
    }


def test_a_dollar_brace_value_is_not_expanded(tmp_path):
    """A value's meaning does not depend on the process environment."""
    env_path = tmp_path / ".env"
    env_path.write_text("KEY=literal-${ENV}-value\n", encoding="utf-8")

    assert parse_env_file(env_path) == {"KEY": "literal-${ENV}-value"}


# -- which providers a `.env` reaches -------------------------------------


def test_a_env_of_literals_reaches_no_provider(tmp_path):
    declaration = a_declaration(tmp_path, an_entry())
    values = {"DEBUG": "0", "DATABASE_URL": "k8s://"}

    assert providers_needed(a_context(declaration), resolvable_values(values)) == []


def test_providers_are_needed_in_declaration_order(tmp_path):
    """Which provider is outermost has to be something the project can see
    and change, not a consequence of how its keys sort."""
    declaration = a_declaration(
        tmp_path,
        an_entry(),
        an_entry(scheme="other://", cli="other-cli", reference="other://{item}",
                 command=["other-cli", "run", "{command}"], environments=None),
    )
    values = {"Z": "other://z", "A": "store://a"}

    needed = providers_needed(a_context(declaration), values)

    assert [provider.cli for provider in needed] == ["store-cli", "other-cli"]


def test_a_scheme_no_provider_declares_is_a_problem(tmp_path):
    declaration = a_declaration(tmp_path, an_entry())

    problem = undeclared_scheme_problem(
        a_context(declaration), {"KEY": "elsewhere://a/b"}
    )

    assert "elsewhere://" in problem
    assert providers.CONFIG_FILENAME in problem


def test_k8s_markers_and_literals_are_not_undeclared_schemes(tmp_path):
    declaration = a_declaration(tmp_path, an_entry())

    assert (
        undeclared_scheme_problem(
            a_context(declaration), {"A": "0", "B": "store://x/y"}
        )
        is None
    )


# -- composing a reference ------------------------------------------------


def test_reference_is_composed_from_the_item_and_the_scope(tmp_path):
    """The `.env` names an item; the store comes from the declaration."""
    declaration = a_declaration(tmp_path, an_entry())

    composed = composed_values(
        a_context(declaration, environment="prod"),
        {"DJANGO_SECRET_KEY": "store://django-secret-key/password"},
    )

    assert composed == {
        "DJANGO_SECRET_KEY": "store://proj-prod/django-secret-key/password"
    }


def test_the_same_env_composes_differently_per_environment(tmp_path):
    declaration = a_declaration(tmp_path, an_entry())
    values = {"KEY": "store://item/field"}

    assert composed_values(a_context(declaration, "dev"), values) == {
        "KEY": "store://proj-dev/item/field"
    }
    assert composed_values(a_context(declaration, "prod"), values) == {
        "KEY": "store://proj-prod/item/field"
    }


def test_literals_and_markers_pass_through_composition(tmp_path):
    declaration = a_declaration(tmp_path, an_entry())

    composed = composed_values(
        a_context(declaration), {"DEBUG": "0", "KEY": "store://item/field"}
    )

    assert composed["DEBUG"] == "0"


def test_a_provider_naming_its_scope_on_the_command_line(tmp_path):
    """`reference` left at its default means the item is the whole of it."""
    declaration = a_declaration(
        tmp_path,
        an_entry(reference=None, command=["store-cli", "--project", "{project_id}",
                                          "run", "{command}"],
                 environments={"prod": {"project_id": "8f1a-uuid"}}),
    )

    composed = composed_values(
        a_context(declaration, "prod"), {"KEY": "store://SECRET_NAME"}
    )

    assert composed == {"KEY": "SECRET_NAME"}


def test_env_and_service_are_available_to_a_template(tmp_path):
    declaration = a_declaration(
        tmp_path, an_entry(reference="store://{env}/{service}/{item}", environments=None)
    )

    composed = composed_values(
        a_context(declaration, "prod", service="api"), {"KEY": "store://item"}
    )

    assert composed == {"KEY": "store://prod/api/item"}


# -- selecting an environment ---------------------------------------------


def test_environment_precedence(tmp_path, monkeypatch):
    declaration = a_declaration(tmp_path, an_entry(), default_env="dev")

    monkeypatch.setenv(providers.CREDENTIALS_ENV_VAR, "from-var")
    assert providers.select_environment(declaration, "from-flag") == "from-flag"
    assert providers.select_environment(declaration) == "from-var"

    monkeypatch.delenv(providers.CREDENTIALS_ENV_VAR)
    assert providers.select_environment(declaration) == "dev"


def test_seal_has_no_default_environment_of_its_own(tmp_path, monkeypatch):
    monkeypatch.delenv(providers.CREDENTIALS_ENV_VAR, raising=False)
    declaration = a_declaration(tmp_path, an_entry())

    assert providers.select_environment(declaration) is None


def test_a_generic_env_variable_is_not_read(tmp_path, monkeypatch):
    """`ENV` is too generic a name for a library to claim, and a collision
    would resolve silently towards the wrong store."""
    monkeypatch.delenv(providers.CREDENTIALS_ENV_VAR, raising=False)
    monkeypatch.setenv("ENV", "production")
    declaration = a_declaration(tmp_path, an_entry())

    assert providers.select_environment(declaration) is None


def test_an_undeclared_environment_lists_the_declared_ones(tmp_path):
    declaration = a_declaration(tmp_path, an_entry())

    with pytest.raises(SealError) as raised:
        composed_values(a_context(declaration, "staging"), {"K": "store://i"})

    assert "staging" in str(raised.value)
    assert "dev, prod" in str(raised.value)


def test_no_environment_named_says_how_to_name_one(tmp_path):
    declaration = a_declaration(tmp_path, an_entry())

    with pytest.raises(SealError) as raised:
        composed_values(a_context(declaration, None), {"K": "store://i"})

    message = str(raised.value)
    assert providers.CREDENTIALS_ENV_FLAG in message
    assert providers.CREDENTIALS_ENV_VAR in message
    assert providers.DEFAULT_ENV_FIELD in message


def test_a_provider_with_no_environments_needs_none_named(tmp_path):
    declaration = a_declaration(
        tmp_path, an_entry(reference="store://{item}", environments=None)
    )

    assert composed_values(a_context(declaration, None), {"K": "store://i"}) == {
        "K": "store://i"
    }


def test_an_unknown_placeholder_names_the_field(tmp_path):
    declaration = a_declaration(tmp_path, an_entry(reference="store://{nope}/{item}"))

    with pytest.raises(SealError) as raised:
        composed_values(a_context(declaration), {"K": "store://i"})

    assert "nope" in str(raised.value)
    assert providers.REFERENCE_FIELD in str(raised.value)


# -- resolving to values --------------------------------------------------


def test_a_env_of_literals_resolves_without_invoking_anything(tmp_path, monkeypatch):
    """No provider is reached, so none has to exist."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    declaration = a_declaration(tmp_path, an_entry())

    resolved = resolve(
        a_context(declaration), {"DEBUG": "0", "DATABASE_URL": "k8s://"}
    )

    # k8s:// is the manifests' to supply, so it is not a value seal returns.
    assert resolved == {"DEBUG": "0"}


def test_a_run_provider_hands_its_values_back(tmp_path, monkeypatch):
    on_path(tmp_path, monkeypatch, "store-cli")
    declaration = a_declaration(tmp_path, an_entry())

    resolved = resolve(
        a_context(declaration, "prod"),
        {"DEBUG": "0", "KEY": "store://item/field"},
    )

    assert resolved == {
        "DEBUG": "0",
        # Composed through `reference` before the provider ever saw it.
        "KEY": "resolved:store://proj-prod/item/field",
    }


def test_two_providers_resolve_without_any_ordering(tmp_path, monkeypatch):
    """Each key names one provider through its scheme, so nothing either
    returns can contend with the other. Declaration order decides nothing --
    which is why the chain it used to decide is gone."""
    on_path(tmp_path, monkeypatch, "store-cli", "other-cli")
    forward = a_declaration(
        tmp_path,
        an_entry(),
        an_entry(scheme="other://", cli="other-cli", name="Another",
                 reference="other://{item}", environments=None,
                 command=["other-cli", "run", "--env-file", "{env_file}", "--",
                          "{command}"]),
    )
    values = {"A": "store://a", "B": "other://b"}

    first = resolve(a_context(forward), values)

    reversed_declaration = a_declaration(
        tmp_path,
        an_entry(scheme="other://", cli="other-cli", name="Another",
                 reference="other://{item}", environments=None,
                 command=["other-cli", "run", "--env-file", "{env_file}", "--",
                          "{command}"]),
        an_entry(),
    )
    second = resolve(a_context(reversed_declaration), values)

    assert first == second
    assert set(first) == {"A", "B"}


def test_a_resolved_value_never_reaches_an_argv(tmp_path, monkeypatch):
    """A secret in a command line is a secret anything listing processes can
    read. Values travel by file and by environment, never as arguments."""
    on_path(tmp_path, monkeypatch, "store-cli")
    declaration = a_declaration(tmp_path, an_entry())
    seen: list[list[str]] = []
    real = subprocess.run

    def record(argv, *args, **kwargs):
        seen.append(list(argv))
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", record)
    resolved = resolve(a_context(declaration), {"KEY": "store://item/field"})

    assert resolved["KEY"].startswith("resolved:")
    for argv in seen:
        assert resolved["KEY"] not in argv


def test_temporary_files_are_removed_on_both_paths(tmp_path, monkeypatch):
    on_path(tmp_path, monkeypatch, "store-cli")
    declaration = a_declaration(tmp_path, an_entry())
    before = set(pathlib.Path(tempfile.gettempdir()).glob("seal-*"))

    resolve(a_context(declaration), {"KEY": "store://item/field"})
    assert set(pathlib.Path(tempfile.gettempdir()).glob("seal-*")) == before

    on_path(tmp_path, monkeypatch, "store-cli", script=FAILING_PROVIDER)
    with pytest.raises(SealError):
        resolve(a_context(declaration), {"KEY": "store://item/field"})
    assert set(pathlib.Path(tempfile.gettempdir()).glob("seal-*")) == before


def test_a_provider_that_fails_names_itself_and_its_keys(tmp_path, monkeypatch):
    on_path(tmp_path, monkeypatch, "store-cli", script=FAILING_PROVIDER)
    declaration = a_declaration(tmp_path, an_entry())

    with pytest.raises(SealError) as raised:
        resolve(a_context(declaration), {"KEY": "store://item/field"})

    assert "A Store" in str(raised.value)
    assert "KEY" in str(raised.value)


def test_a_missing_cli_quotes_the_declarations_own_words(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    declaration = a_declaration(tmp_path, an_entry())

    with pytest.raises(SealError) as raised:
        resolve(a_context(declaration), {"KEY": "store://item/field"})

    message = str(raised.value)
    assert "store-cli" in message
    assert "https://example.invalid/install" in message
    assert "A Store" in message


def test_command_placeholder_has_to_be_a_word_of_its_own(tmp_path, monkeypatch):
    on_path(tmp_path, monkeypatch, "store-cli")
    declaration = a_declaration(
        tmp_path, an_entry(command=["store-cli", "-c", "run {command}"])
    )

    with pytest.raises(SealError) as raised:
        resolve(a_context(declaration), {"KEY": "store://item/field"})

    assert "word of its own" in str(raised.value)


# -- the resolve and fetch forms -------------------------------------------
#
# Both hand values back on stdout rather than wrapping a command, which is
# why they share fixtures and a parsing path (_dotenv_from_stdout): the
# difference between them is what goes in and how much comes back, not how
# seal reads the result.

# `resolve`: given `--env-file <path>` of composed references, writes the
# same keys back resolved. A straight round-trip, so a value round-trips
# unquoted characters exactly -- no reinterpretation of `$`, `{` or `}`.
RESOLVE_PROVIDER = """#!/bin/sh
env_file=""
while [ $# -gt 0 ]; do
  case "$1" in
    --env-file) env_file="$2"; shift 2 ;;
    *) shift ;;
  esac
done
if [ -n "$RESOLVE_SHOULD_FAIL" ]; then
  echo "vault locked" >&2
  exit 5
fi
while IFS='=' read -r key ref; do
  [ -n "$key" ] || continue
  [ "$key" = "$RESOLVE_DROP_KEY" ] && continue
  printf '%s=resolved:%s\\n' "$key" "$ref"
done < "$env_file"
"""

# `fetch`: takes its scope from the command's own placeholders (never a
# file), and dumps a table -- recorded to $FETCH_ARGS_FILE and read from
# $FETCH_TABLE_FILE so a test controls exactly what came back, including a
# quoted multi-line value no shell round-trip would survive intact.
FETCH_PROVIDER = """#!/bin/sh
if [ -n "$FETCH_ARGS_FILE" ]; then
  printf '%s\\n' "$*" > "$FETCH_ARGS_FILE"
fi
if [ -n "$FETCH_SHOULD_FAIL" ]; then
  echo "scope not found" >&2
  exit 3
fi
cat "$FETCH_TABLE_FILE"
"""


def resolve_form_entry(**overrides):
    entry = {
        "scheme": "vault://",
        "name": "A Vault",
        "cli": "vault-cli",
        "install_hint": None,
        "form": providers.RESOLVE,
        "reference": None,  # default {item}: this provider's scope is not in the URI
        "command": ["vault-cli", "inject", "--env-file", "{env_file}"],
        "environments": None,
    }
    entry.update(overrides)
    return {key: value for key, value in entry.items() if value is not None}


def fetch_form_entry(**overrides):
    entry = {
        "scheme": "scope://",
        "name": "A Scope",
        "cli": "scope-cli",
        "install_hint": None,
        "form": providers.FETCH,
        "reference": None,
        "command": ["scope-cli", "fetch", "--project", "{project_id}", "-o", "env"],
        "environments": {
            "dev": {"project_id": "proj-dev-uuid"},
            "prod": {"project_id": "proj-prod-uuid"},
        },
    }
    entry.update(overrides)
    return {key: value for key, value in entry.items() if value is not None}


def test_resolve_form_returns_the_providers_stdout(tmp_path, monkeypatch):
    on_path(tmp_path, monkeypatch, "vault-cli", script=RESOLVE_PROVIDER)
    declaration = a_declaration(tmp_path, resolve_form_entry())

    resolved = resolve(a_context(declaration), {"KEY": "vault://item"})

    assert resolved == {"KEY": "resolved:item"}


def test_resolve_form_is_not_reinterpreted(tmp_path, monkeypatch):
    """A round-trip through this form's file-in, file-out shape is not a
    second chance for the value to be parsed as anything -- `$`, `{` and `}`
    reach the result exactly as the store gave them."""
    on_path(tmp_path, monkeypatch, "vault-cli", script=RESOLVE_PROVIDER)
    declaration = a_declaration(tmp_path, resolve_form_entry())

    resolved = resolve(a_context(declaration), {"KEY": "vault://has$dollar{brace}s"})

    assert resolved == {"KEY": "resolved:has$dollar{brace}s"}


def test_resolve_form_non_zero_exit_names_the_provider(tmp_path, monkeypatch):
    on_path(tmp_path, monkeypatch, "vault-cli", script=RESOLVE_PROVIDER)
    monkeypatch.setenv("RESOLVE_SHOULD_FAIL", "1")
    declaration = a_declaration(tmp_path, resolve_form_entry())

    with pytest.raises(SealError) as raised:
        resolve(a_context(declaration), {"KEY": "vault://item"})

    assert "A Vault" in str(raised.value)
    assert "vault locked" in str(raised.value)


def test_resolve_form_a_key_missing_from_the_response_is_an_error(tmp_path, monkeypatch):
    on_path(tmp_path, monkeypatch, "vault-cli", script=RESOLVE_PROVIDER)
    monkeypatch.setenv("RESOLVE_DROP_KEY", "KEY")
    declaration = a_declaration(tmp_path, resolve_form_entry())

    with pytest.raises(SealError) as raised:
        resolve(a_context(declaration), {"KEY": "vault://item"})

    assert "A Vault" in str(raised.value)
    assert "KEY" in str(raised.value)


def test_fetch_form_scope_placeholders_reach_the_command(tmp_path, monkeypatch):
    args_file = tmp_path / "args.txt"
    table_file = tmp_path / "table.env"
    table_file.write_text("item=fetched-value\n", encoding="utf-8")
    monkeypatch.setenv("FETCH_ARGS_FILE", str(args_file))
    monkeypatch.setenv("FETCH_TABLE_FILE", str(table_file))
    on_path(tmp_path, monkeypatch, "scope-cli", script=FETCH_PROVIDER)
    declaration = a_declaration(tmp_path, fetch_form_entry())

    resolve(a_context(declaration, "prod"), {"KEY": "scope://item"})

    assert "proj-prod-uuid" in args_file.read_text(encoding="utf-8")


def test_fetch_form_selects_only_the_declared_keys(tmp_path, monkeypatch):
    """A scope can hold far more than one service needs -- only what the
    `.env` actually referenced reaches the result."""
    table_file = tmp_path / "table.env"
    table_file.write_text(
        "wanted=keep-me\nother_secret=never-declared\nthird=also-not-mine\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FETCH_TABLE_FILE", str(table_file))
    on_path(tmp_path, monkeypatch, "scope-cli", script=FETCH_PROVIDER)
    declaration = a_declaration(tmp_path, fetch_form_entry())

    resolved = resolve(a_context(declaration, "dev"), {"KEY": "scope://wanted"})

    assert resolved == {"KEY": "keep-me"}


def test_fetch_form_a_quoted_multiline_value_survives_intact(tmp_path, monkeypatch):
    table_file = tmp_path / "table.env"
    table_file.write_text('item="line one\\nline two"\n', encoding="utf-8")
    monkeypatch.setenv("FETCH_TABLE_FILE", str(table_file))
    on_path(tmp_path, monkeypatch, "scope-cli", script=FETCH_PROVIDER)
    declaration = a_declaration(tmp_path, fetch_form_entry())

    resolved = resolve(a_context(declaration, "dev"), {"KEY": "scope://item"})

    assert resolved == {"KEY": "line one\nline two"}


def test_fetch_form_omitting_a_declared_key_names_it(tmp_path, monkeypatch):
    table_file = tmp_path / "table.env"
    table_file.write_text("something-else=x\n", encoding="utf-8")
    monkeypatch.setenv("FETCH_TABLE_FILE", str(table_file))
    on_path(tmp_path, monkeypatch, "scope-cli", script=FETCH_PROVIDER)
    declaration = a_declaration(tmp_path, fetch_form_entry())

    with pytest.raises(SealError) as raised:
        resolve(a_context(declaration, "dev"), {"KEY": "scope://item"})

    message = str(raised.value)
    assert "A Scope" in message
    assert "KEY" in message
    assert "item" in message


def test_fetch_form_non_zero_exit_names_the_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCH_SHOULD_FAIL", "1")
    on_path(tmp_path, monkeypatch, "scope-cli", script=FETCH_PROVIDER)
    declaration = a_declaration(tmp_path, fetch_form_entry())

    with pytest.raises(SealError) as raised:
        resolve(a_context(declaration, "dev"), {"KEY": "scope://item"})

    assert "A Scope" in str(raised.value)
    assert "scope not found" in str(raised.value)


def test_a_env_mixing_run_and_fetch_resolves_both(tmp_path, monkeypatch):
    table_file = tmp_path / "table.env"
    table_file.write_text("item=fetched-value\n", encoding="utf-8")
    monkeypatch.setenv("FETCH_TABLE_FILE", str(table_file))
    on_path(tmp_path, monkeypatch, "store-cli", script=RUN_PROVIDER)
    on_path(tmp_path, monkeypatch, "scope-cli", script=FETCH_PROVIDER)
    declaration = a_declaration(tmp_path, an_entry(), fetch_form_entry())

    resolved = resolve(
        a_context(declaration, "dev"),
        {"A": "store://a", "B": "scope://item"},
    )

    assert resolved["A"] == "resolved:store://proj-dev/a"
    assert resolved["B"] == "fetched-value"


# -- the get form -----------------------------------------------------------
#
# One item in, one value on stdout, invoked once per reference -- the shape
# every surveyed product with no run/resolve/fetch form supports. The
# fixture records what it was called with and serves a value from a file the
# test controls, so byte-exact preservation (leading whitespace, internal
# and trailing newlines) needs no shell-quoting gymnastics.

GET_PROVIDER = """#!/bin/sh
item="$1"
if [ -n "$GET_CALLS_FILE" ]; then
  printf '%s\\n' "$item" >> "$GET_CALLS_FILE"
fi
if [ "$item" = "$GET_FAIL_ITEM" ]; then
  echo "not found" >&2
  exit 4
fi
if [ -f "$GET_VALUES_DIR/$item" ]; then
  cat "$GET_VALUES_DIR/$item"
fi
"""


def get_form_entry(**overrides):
    entry = {
        "scheme": "vault2://",
        "name": "A Vault2",
        "cli": "get-cli",
        "install_hint": None,
        "form": providers.GET,
        "reference": None,  # default {item}: get() addresses items directly
        "command": ["get-cli", "{item}"],
        "environments": None,
    }
    entry.update(overrides)
    return {key: value for key, value in entry.items() if value is not None}


def test_get_form_is_invoked_once_per_reference(tmp_path, monkeypatch):
    calls_file = tmp_path / "calls.txt"
    values_dir = tmp_path / "values"
    values_dir.mkdir()
    (values_dir / "one").write_text("value-one", encoding="utf-8")
    (values_dir / "two").write_text("value-two", encoding="utf-8")
    monkeypatch.setenv("GET_CALLS_FILE", str(calls_file))
    monkeypatch.setenv("GET_VALUES_DIR", str(values_dir))
    on_path(tmp_path, monkeypatch, "get-cli", script=GET_PROVIDER)
    declaration = a_declaration(tmp_path, get_form_entry())

    resolved = resolve(
        a_context(declaration), {"A": "vault2://one", "B": "vault2://two"}
    )

    assert resolved == {"A": "value-one", "B": "value-two"}
    calls = calls_file.read_text(encoding="utf-8").splitlines()
    # The form's defining cost: one invocation per reference, not one for
    # the lot -- asserted, not assumed.
    assert sorted(calls) == ["one", "two"]
    assert len(calls) == 2


def test_get_form_strips_exactly_one_trailing_newline(tmp_path, monkeypatch):
    values_dir = tmp_path / "values"
    values_dir.mkdir()
    (values_dir / "single-nl").write_bytes(b"secret\n")
    (values_dir / "double-nl").write_bytes(b"secret\n\n")
    (values_dir / "leading-space").write_bytes(b"  leading\n")
    (values_dir / "internal-nl").write_bytes(b"line one\nline two\n")
    monkeypatch.setenv("GET_VALUES_DIR", str(values_dir))
    on_path(tmp_path, monkeypatch, "get-cli", script=GET_PROVIDER)
    declaration = a_declaration(tmp_path, get_form_entry())

    resolved = resolve(
        a_context(declaration),
        {
            "A": "vault2://single-nl",
            "B": "vault2://double-nl",
            "C": "vault2://leading-space",
            "D": "vault2://internal-nl",
        },
    )

    assert resolved["A"] == "secret"
    assert resolved["B"] == "secret\n"
    assert resolved["C"] == "  leading"
    assert resolved["D"] == "line one\nline two"


def test_get_form_non_zero_exit_names_the_item_and_the_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("GET_FAIL_ITEM", "gone")
    on_path(tmp_path, monkeypatch, "get-cli", script=GET_PROVIDER)
    declaration = a_declaration(tmp_path, get_form_entry())

    with pytest.raises(SealError) as raised:
        resolve(a_context(declaration), {"KEY": "vault2://gone"})

    message = str(raised.value)
    assert "A Vault2" in message
    assert "gone" in message
    assert "not found" in message


def test_get_form_empty_stdout_is_an_error_not_an_empty_value(tmp_path, monkeypatch):
    """A store that returns nothing for an item it was asked about is a
    store that did not have it -- not a service starting with a blank where
    a secret should be."""
    monkeypatch.setenv("GET_VALUES_DIR", str(tmp_path / "empty-values"))
    (tmp_path / "empty-values").mkdir()
    on_path(tmp_path, monkeypatch, "get-cli", script=GET_PROVIDER)
    declaration = a_declaration(tmp_path, get_form_entry())

    with pytest.raises(SealError) as raised:
        resolve(a_context(declaration), {"KEY": "vault2://missing"})

    message = str(raised.value)
    assert "A Vault2" in message
    assert "missing" in message


def test_a_env_mixing_get_with_run_resolves_both(tmp_path, monkeypatch):
    values_dir = tmp_path / "values"
    values_dir.mkdir()
    (values_dir / "item").write_text("get-value", encoding="utf-8")
    monkeypatch.setenv("GET_VALUES_DIR", str(values_dir))
    on_path(tmp_path, monkeypatch, "store-cli", script=RUN_PROVIDER)
    on_path(tmp_path, monkeypatch, "get-cli", script=GET_PROVIDER)
    declaration = a_declaration(tmp_path, an_entry(), get_form_entry())

    resolved = resolve(
        a_context(declaration, "dev"),
        {"A": "store://a", "B": "vault2://item"},
    )

    assert resolved["A"] == "resolved:store://proj-dev/a"
    assert resolved["B"] == "get-value"


# -- taking the flag off an argument list ---------------------------------


@pytest.mark.parametrize(
    "args, expected_value, expected_rest",
    [
        (["--credentials_env", "prod", "--", "make"], "prod", ["--", "make"]),
        (["--credentials_env=prod", "--", "make"], "prod", ["--", "make"]),
        (["--", "make"], None, ["--", "make"]),
        ([], None, []),
        (["--build_type", "test"], None, ["--build_type", "test"]),
    ],
)
def test_take_credentials_env(args, expected_value, expected_rest):
    assert providers.take_credentials_env(args) == (expected_value, expected_rest)


def test_the_flag_is_not_taken_from_a_wrapped_command():
    """After `--` is somebody else's argument list, and a flag seal
    recognises there is a flag seal would be stealing."""
    args = ["--", "make", "--credentials_env", "prod"]

    assert providers.take_credentials_env(args) == (None, args)


def test_a_trailing_flag_is_left_for_whoever_parses_the_rest():
    assert providers.take_credentials_env(["--credentials_env"]) == (
        None,
        ["--credentials_env"],
    )


# -- static checks against a project's declaration -------------------------
#
# declaration_problems() is what `seal check` runs instead of resolve():
# named rather than resolved, and over every service's `.env` at once rather
# than the one a single run would read.


def write_service_env(seal_root, service_name, content):
    service_dir = seal_root / "services" / service_name
    service_dir.mkdir(parents=True, exist_ok=True)
    (service_dir / ".env").write_text(content, encoding="utf-8")
    return service_dir


def test_discover_service_env_files_finds_every_one(tmp_path):
    write_service_env(tmp_path, "api", "DEBUG=0\n")
    write_service_env(tmp_path, "worker", "DEBUG=0\n")
    (tmp_path / "services" / "ui").mkdir(parents=True)  # no .env of its own

    found = discover_service_env_files(tmp_path)

    assert [name for name, _ in found] == ["api", "worker"]  # sorted, ui skipped


def test_discover_service_env_files_with_no_services_dir(tmp_path):
    assert discover_service_env_files(tmp_path) == []


def test_credential_problem_describe_names_the_service():
    problem = CredentialProblem("api", "something is wrong")

    assert problem.describe() == "api/.env: something is wrong"


def test_credential_problem_describe_with_no_service_is_the_problem_alone():
    """A problem naming a provider rather than one `.env` -- see
    declaration_problems()'s note on why a missing environment mapping is
    reported once, not once per referencing service."""
    problem = CredentialProblem(None, "A Store reads a different store per environment")

    assert problem.describe() == "A Store reads a different store per environment"


def test_declaration_problems_is_empty_for_literals_and_markers(tmp_path):
    """Nothing to say about a provider nothing references -- and nothing
    invoked to say it, since no provider CLI is on PATH here at all."""
    write_service_env(tmp_path, "api", "DEBUG=0\nDATABASE_URL=k8s://\n")
    declaration = a_declaration(tmp_path)

    assert declaration_problems(tmp_path, declaration, None) == []


def test_declaration_problems_reports_an_undeclared_scheme(tmp_path):
    write_service_env(tmp_path, "api", "SECRET=other://item\n")
    declaration = a_declaration(tmp_path, an_entry())

    problems = declaration_problems(tmp_path, declaration, "dev")

    assert len(problems) == 1
    assert problems[0].service_name == "api"
    assert "SECRET" in problems[0].problem
    assert "other://" in problems[0].problem
    assert "no provider declares" in problems[0].problem


def test_declaration_problems_reports_a_dollar_brace_value(tmp_path):
    """A literal is allowed to contain anything except this. `${` is what a
    project reaches for when it means a value to expand per environment, and
    a value whose meaning depends on where it is read is exactly what this
    rule exists to catch."""
    write_service_env(tmp_path, "api", "SECRET=literal-${ENV}-value\n")
    declaration = a_declaration(tmp_path)

    problems = declaration_problems(tmp_path, declaration, None)

    assert len(problems) == 1
    assert problems[0].service_name == "api"
    assert "SECRET" in problems[0].problem
    assert "${" in problems[0].problem


def test_declaration_problems_reports_a_dollar_brace_value_in_a_reference_too(tmp_path):
    write_service_env(tmp_path, "api", "SECRET=store://has-${ENV}-in-it\n")
    declaration = a_declaration(tmp_path, an_entry())

    problems = declaration_problems(tmp_path, declaration, "dev")

    assert any("${" in problem.problem for problem in problems)


def test_declaration_problems_reports_a_provider_two_services_reach_once(tmp_path):
    """Whether a provider has a mapping for the selected environment doesn't
    depend on which `.env` referenced it -- so two services reaching the
    same one with no environment selected is one problem, not two."""
    write_service_env(tmp_path, "api", "SECRET=store://item\n")
    write_service_env(tmp_path, "worker", "SECRET=store://item\n")
    declaration = a_declaration(tmp_path, an_entry())

    problems = declaration_problems(tmp_path, declaration, None)

    assert len(problems) == 1
    assert problems[0].service_name is None
    assert "named none" in problems[0].problem


def test_declaration_problems_names_the_selected_environment_when_undeclared(tmp_path):
    write_service_env(tmp_path, "api", "SECRET=store://item\n")
    declaration = a_declaration(tmp_path, an_entry())

    problems = declaration_problems(tmp_path, declaration, "staging")

    assert len(problems) == 1
    assert problems[0].service_name is None
    assert "declares no store for 'staging'" in problems[0].problem


def test_declaration_problems_a_provider_needing_no_environment_is_never_reported(tmp_path):
    write_service_env(tmp_path, "api", "SECRET=store://item\n")
    declaration = a_declaration(tmp_path, an_entry(environments=None))

    assert declaration_problems(tmp_path, declaration, None) == []


def test_declaration_problems_touches_no_provider_cli(tmp_path, monkeypatch):
    """`seal check` runs before credentials are established -- these
    rules check that a name is accounted for, never that a store holds a
    value for it, so nothing here shells out to a provider's CLI at all."""
    monkeypatch.setenv("PATH", str(tmp_path))  # empty: no provider CLI reachable
    write_service_env(tmp_path, "api", "SECRET=store://item\n")
    declaration = a_declaration(tmp_path, an_entry())

    # Would raise (CLI not found) if this resolved anything -- see
    # _require_cli() in resolve()'s own path.
    assert declaration_problems(tmp_path, declaration, "dev") == []
