"""Where a service's credentials come from, and how a project says so.

A `.env` value names what a service needs -- an item in some store, and
optionally a field within it:

    DJANGO_SECRET_KEY=store://django-secret-key/password

It does not name the store. Which vault, project or folder that item lives
in is a fact about deployment, and it differs per environment while the
item does not. So the store is declared once, per project, in
`seal-credentials-config.json` at the project root:

    {
      "default_env": "dev",
      "provider": [
        {
          "scheme": "store://",
          "name": "A Password Manager",
          "cli": "store-cli",
          "install_hint": "https://example.invalid/download",
          "form": "run",
          "reference": "store://{vault}/{item}",
          "command": ["store-cli", "run", "--env-file", "{env_file}",
                      "--", "{command}"],
          "environments": {
            "dev":  {"vault": "project-seal-dev"},
            "prod": {"vault": "project-seal-prod"}
          }
        }
      ]
    }

Three parts carry the whole difference between one password manager and the
next:

- **`environments`** maps the credentials environment a run selects to
  whatever this provider calls a scope. A mapping rather than a template,
  because a scope is not always derivable from an environment's name -- one
  manager scopes by a vault called after the environment, another by a UUID
  no string built from the word `prod` will ever produce.
- **`reference`** rebuilds the provider-native reference from the item the
  `.env` declared plus that scope, which is what lets a manager whose scope
  lives inside the URI work without the `.env` carrying it. A manager that
  names its scope on the command line leaves this as `{item}` and puts the
  mapping's values in `command` instead.
- **`command`** is the invocation, in the form the manager supports.

Placeholders are a closed set, filled by the caller and interpreted by
nothing here: seal substitutes names and never reads what it substituted.

Nothing in this module names a product -- the scheme, the binary and the
words in the templates above are all a project's own, and the example here
is written with invented ones for that reason. A project that references no
provider from any `.env` -- one of literals and `k8s://` markers -- needs no
config file at all, and gets an empty declaration rather than an error.

Problems are returned rather than raised, the same way runners.py reports a
malformed `seal-test-config.json`: every problem with a file, not the first,
so a project can put it right in one pass. Whether a problem stops a run is
the caller's question, and `seal check` wants the list rather than an
exception.
"""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

# Where a project declares which stores its `.env` files reference. At the
# project root beside the root Tiltfile: every service's `.env` resolves
# through the same declarations, so what they are belongs in one place
# rather than once per service.
CONFIG_FILENAME = "seal-credentials-config.json"

# What the config carries. `provider` is singular and holds a list, matching
# `seal-test-config.json`'s `runner`, so the two config files read the same
# way. `default_env` is a single value: a run selects one environment.
PROVIDER_FIELD = "provider"
DEFAULT_ENV_FIELD = "default_env"

SCHEME_FIELD = "scheme"
NAME_FIELD = "name"
CLI_FIELD = "cli"
INSTALL_HINT_FIELD = "install_hint"
FORM_FIELD = "form"
REFERENCE_FIELD = "reference"
COMMAND_FIELD = "command"
ENVIRONMENTS_FIELD = "environments"

# How a manager's CLI hands a value over. `run` wraps a command and puts
# the values in its environment. `resolve` reads a file of references and
# writes the same file, resolved. `fetch` dumps a whole scope and seal keeps
# only what was asked for. `get` -- one item in, one value out, invoked once
# per reference -- is what a manager with no wrapping form at all needs, and
# is the only one of the four every surveyed product supports.
RUN = "run"
RESOLVE = "resolve"
FETCH = "fetch"
GET = "get"

FORMS = (RUN, RESOLVE, FETCH, GET)
# Every declarable form is implemented. Kept as its own name, equal to
# FORMS by definition rather than by coincidence, so a form added to one and
# not the other is a mismatch a reader -- or a future `assert
# IMPLEMENTED_FORMS == FORMS` -- can actually catch.
IMPLEMENTED_FORMS = FORMS

# What a reference is composed into when a provider names its scope on the
# command line rather than inside the URI: the item, and nothing around it.
DEFAULT_REFERENCE = "{item}"

# What separates a scheme from the item path in a `.env` value. A scheme has
# to end in it, so matching a value to a provider is a prefix test with no
# ambiguity about where one stops.
SCHEME_SUFFIX = "://"

# Which credentials environment a run reads, where a project's own default
# is not what is wanted. Named for seal rather than called `ENV`: a
# one-word name claimed out of a developer's shell collides with whatever
# else set it, and a collision here resolves silently towards the wrong
# store.
#
# The flag is taken from the arguments before any `--`, so it never reaches
# `tilt` or a wrapped command -- `--` separates seal's own arguments from
# somebody else's in every command that has one.
CREDENTIALS_ENV_FLAG = "--credentials_env"
CREDENTIALS_ENV_VAR = "SEAL_CREDENTIALS_ENV"

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class UnknownPlaceholder(Exception):
    """A template names something the caller did not supply.

    Carries the name and what was available, so a caller can say which
    template held it -- this module fills templates without knowing whether
    one came from a `reference`, a `command`, or somewhere later.
    """

    def __init__(self, name: str, available: tuple[str, ...]):
        self.name = name
        self.available = available
        super().__init__(
            f"'{{{name}}}' is not something seal can fill here. Available: "
            f"{', '.join(available) if available else '(nothing)'}."
        )


def fill(template: str, values: dict[str, str]) -> str:
    """One template, with every `{name}` replaced by `values[name]`.

    A substituted value is never rescanned, so a secret's own braces are
    just characters. An unfillable name raises rather than being left in
    place: a template reaching a CLI with `{vault}` still in it would ask a
    store for an item nobody named.
    """
    available = tuple(sorted(values))
    out: list[str] = []
    at = 0
    for match in _PLACEHOLDER.finditer(template):
        name = match.group(1)
        if name not in values:
            raise UnknownPlaceholder(name, available)
        out.append(template[at : match.start()])
        out.append(values[name])
        at = match.end()
    out.append(template[at:])
    return "".join(out)


def fill_argv(template: list[str] | tuple[str, ...], values: dict[str, str]) -> list[str]:
    """`fill()` over each word of a command template.

    Word by word, so a filled value is one argument however much whitespace
    it holds -- a store is free to keep a value with spaces in it, and a
    template is not a shell string.
    """
    return [fill(word, values) for word in template]


@dataclass(frozen=True)
class Provider:
    """One store a project's `.env` files reference, and how to read it."""

    # The `.env` value prefix that picks this provider, ending in '://'.
    scheme: str
    # What to call it in an error a person reads. Defaults to `cli`.
    name: str
    # The binary expected on PATH.
    cli: str
    # Where to get that binary, quoted when it is missing. None where the
    # project said nothing -- not every provider is something you install.
    install_hint: str | None
    form: str
    # How to compose the provider-native reference from `{item}` plus the
    # selected environment's mapping.
    reference: str
    command: tuple[str, ...]
    # Credentials environment -> this provider's own idea of a scope.
    # Empty where a provider has no scope to name.
    environments: dict[str, dict[str, str]]

    def scope(self, environment: str | None) -> dict[str, str] | None:
        """What this provider calls the given environment's scope, or None
        where it declares none for it. A provider with no `environments` at
        all has an empty scope for every environment rather than no scope:
        it is a provider that scopes some other way, not one that is
        missing a mapping.
        """
        if not self.environments:
            return {}
        if environment is None:
            return None
        return self.environments.get(environment)


@dataclass(frozen=True)
class Declaration:
    """Everything a project declares about where its credentials come from."""

    providers: tuple[Provider, ...]
    # The credentials environment a run uses when nothing else names one.
    # None where the project declared none, which is not a problem until
    # something actually needs an environment.
    default_env: str | None

    def for_scheme(self, value: str) -> Provider | None:
        """The provider whose scheme this `.env` value starts with."""
        for provider in self.providers:
            if value.startswith(provider.scheme):
                return provider
        return None


EMPTY = Declaration(providers=(), default_env=None)


def config_path(seal_root: Path) -> Path:
    """Where a project declares its providers, whether or not it has yet."""
    return seal_root / CONFIG_FILENAME


def take_credentials_env(args: list[str]) -> tuple[str | None, list[str]]:
    """`--credentials_env`'s value, and everything else, in order.

    Only the arguments before the first `--` are searched. After it is
    somebody else's argument list -- a wrapped command for `seal run`, a
    Tiltfile's own arguments for `seal up` -- and a flag seal recognises
    there is a flag seal would be stealing.

    The `--` itself, and everything after it, is returned untouched, since
    what it separates differs per command and this is not the place that
    knows.
    """
    value: str | None = None
    rest: list[str] = []
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == "--":
            rest.extend(args[index:])
            break
        if argument == CREDENTIALS_ENV_FLAG:
            if index + 1 < len(args) and args[index + 1] != "--":
                value = args[index + 1]
                index += 2
                continue
            # A trailing flag with nothing after it: left in place, so
            # whoever parses the rest reports it rather than this silently
            # swallowing it.
            rest.append(argument)
            index += 1
            continue
        if argument.startswith(f"{CREDENTIALS_ENV_FLAG}="):
            value = argument.split("=", 1)[1]
            index += 1
            continue
        rest.append(argument)
        index += 1
    return value, rest


def select_environment(
    declaration: Declaration,
    flag: str | None = None,
    environ: dict[str, str] | None = None,
) -> str | None:
    """Which credentials environment this run reads: the flag, then
    `SEAL_CREDENTIALS_ENV`, then the project's own `default_env`.

    None where nothing named one. seal has no default of its own -- a name
    it picked would be a name it invented for one of a project's
    environments, which is the whole thing this file exists to stop. Whether
    None is a problem depends on whether any `.env` actually references a
    provider, which the caller knows.
    """
    if flag:
        return flag
    from_environment = (environ if environ is not None else os.environ).get(
        CREDENTIALS_ENV_VAR
    )
    if from_environment:
        return from_environment
    return declaration.default_env


def _document(seal_root: Path) -> tuple[object | None, str | None]:
    """What the config file holds, whatever shape that turns out to be --
    None where the project has no config file, and a problem where there is
    one and it cannot be read.

    No config file is not a problem here. Whether it is one depends on what
    the project's `.env` files reference, which the caller knows and this
    does not.
    """
    path = config_path(seal_root)
    if not path.is_file():
        return None, None
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        return None, f"cannot be read as JSON: {error}"


def _string_field(entry: dict, field: str, where: str, problems: list[str]) -> str | None:
    value = entry.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        problems.append(f"{where}: '{field}' has to be a non-empty string.")
        return None
    return value


def _parse_environments(value: object, where: str, problems: list[str]) -> dict[str, dict[str, str]]:
    """The environment -> scope mapping, and everything wrong with it.

    Two levels of object: an environment's name, then the named values that
    provider's own `reference` and `command` templates draw on. Both are the
    project's vocabulary, not seal's -- nothing here knows what a `vault` or
    a `project_id` is, only that it is a string a template can hold.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        problems.append(
            f"{where}: '{ENVIRONMENTS_FIELD}' has to be an object keyed by "
            "credentials environment, each holding the named values this "
            "provider's templates draw on."
        )
        return {}

    environments: dict[str, dict[str, str]] = {}
    for environment, scope in value.items():
        if not isinstance(scope, dict) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in scope.items()
        ):
            problems.append(
                f"{where}: '{ENVIRONMENTS_FIELD}.{environment}' has to be an object "
                "of strings -- each one a name this provider's 'reference' or "
                "'command' can hold in braces."
            )
            continue
        environments[environment] = dict(scope)
    return environments


def _parse_provider(entry: object, index: int) -> tuple[Provider | None, list[str]]:
    """One `provider` entry, and everything wrong with it.

    Every problem with an entry is returned, not the first: a project should
    be able to put its config right in one pass.
    """
    where = f"{PROVIDER_FIELD}[{index}]"
    if not isinstance(entry, dict):
        return None, [f"{where} is not an object."]

    problems: list[str] = []

    scheme = _string_field(entry, SCHEME_FIELD, where, problems)
    if scheme is None and SCHEME_FIELD not in entry:
        problems.append(
            f"{where} has no '{SCHEME_FIELD}' -- the prefix a `.env` value starts "
            f"with to reach this provider, ending in '{SCHEME_SUFFIX}'."
        )
    elif scheme is not None and not scheme.endswith(SCHEME_SUFFIX):
        problems.append(
            f"{where}: '{SCHEME_FIELD}' is {scheme!r}, which does not end in "
            f"'{SCHEME_SUFFIX}'. A `.env` value is matched to a provider by this "
            "prefix, and one without it would also match a value that merely "
            "starts with the same letters."
        )
        scheme = None

    cli = _string_field(entry, CLI_FIELD, where, problems)
    if cli is None and CLI_FIELD not in entry:
        problems.append(
            f"{where} has no '{CLI_FIELD}' -- the binary expected on PATH, quoted "
            "when it is missing."
        )

    form = _string_field(entry, FORM_FIELD, where, problems)
    if form is None and FORM_FIELD not in entry:
        problems.append(
            f"{where} has no '{FORM_FIELD}' -- how this provider's CLI hands a "
            f"value over. One of {', '.join(FORMS)}."
        )
    elif form is not None and form not in FORMS:
        problems.append(
            f"{where}: '{FORM_FIELD}' is {form!r}, which is not a shape a provider "
            f"CLI takes. One of {', '.join(FORMS)}."
        )
        form = None

    command = entry.get(COMMAND_FIELD)
    if command is None:
        problems.append(
            f"{where} has no '{COMMAND_FIELD}' -- the invocation, as a list of "
            "words with the placeholders this provider needs."
        )
        command = []
    elif (
        not isinstance(command, list)
        or not command
        or not all(isinstance(word, str) for word in command)
    ):
        problems.append(
            f"{where}: '{COMMAND_FIELD}' has to be a non-empty list of strings. It "
            "is argv, not a shell line, so a value filled into it is one argument "
            "however much whitespace it holds."
        )
        command = []

    reference = entry.get(REFERENCE_FIELD)
    if reference is None:
        reference = DEFAULT_REFERENCE
    elif not isinstance(reference, str) or not reference:
        problems.append(
            f"{where}: '{REFERENCE_FIELD}' has to be a non-empty string -- how this "
            "provider's own reference is composed from '{item}' and the selected "
            "environment's values. Leave it out where the item is the whole of it."
        )
        reference = DEFAULT_REFERENCE

    environments = _parse_environments(entry.get(ENVIRONMENTS_FIELD), where, problems)

    name = _string_field(entry, NAME_FIELD, where, problems)
    install_hint = _string_field(entry, INSTALL_HINT_FIELD, where, problems)

    unknown = sorted(
        key
        for key in entry
        if key
        not in (
            SCHEME_FIELD,
            NAME_FIELD,
            CLI_FIELD,
            INSTALL_HINT_FIELD,
            FORM_FIELD,
            REFERENCE_FIELD,
            COMMAND_FIELD,
            ENVIRONMENTS_FIELD,
        )
    )
    if unknown:
        problems.append(
            f"{where}: {', '.join(repr(key) for key in unknown)} is not something a "
            "provider declares. A misspelled field reads as a default nobody asked "
            "for, which is the one config mistake a run cannot report."
        )

    if problems:
        return None, problems

    return (
        Provider(
            scheme=scheme,
            name=name or cli,
            cli=cli,
            install_hint=install_hint,
            form=form,
            reference=reference,
            command=tuple(command),
            environments=environments,
        ),
        [],
    )


def read_config(seal_root: Path) -> tuple[Declaration, list[str]]:
    """Every provider this project declares, and everything wrong with the
    declaration -- along with whatever is wrong with the file itself, which
    is reported here rather than by every reader of it.

    A project with no config file at all comes back empty rather than as a
    problem: a `.env` of literals and `k8s://` markers reaches no provider,
    and asking such a project to declare one would be asking it to write
    down something it does not use.
    """
    document, problem = _document(seal_root)
    if problem is not None:
        return EMPTY, [problem]
    if document is None:
        return EMPTY, []

    if not isinstance(document, dict):
        return EMPTY, [
            f"is not a JSON object. It holds '{PROVIDER_FIELD}', a list with one "
            f"entry per store the project's `.env` files reference, and "
            f"'{DEFAULT_ENV_FIELD}', the credentials environment a run uses when "
            "nothing else names one."
        ]

    problems: list[str] = []

    default_env = document.get(DEFAULT_ENV_FIELD)
    if default_env is not None and (not isinstance(default_env, str) or not default_env):
        problems.append(
            f"'{DEFAULT_ENV_FIELD}' has to be a non-empty string -- one of the "
            "environments the providers below declare."
        )
        default_env = None

    unknown = sorted(
        key for key in document if key not in (PROVIDER_FIELD, DEFAULT_ENV_FIELD)
    )
    if unknown:
        problems.append(
            f"{', '.join(repr(key) for key in unknown)} is not something this file "
            f"declares. It holds '{PROVIDER_FIELD}' and '{DEFAULT_ENV_FIELD}', and "
            "nothing else."
        )

    entries = document.get(PROVIDER_FIELD)
    if entries is None:
        entries = []
    elif not isinstance(entries, list):
        problems.append(
            f"'{PROVIDER_FIELD}' has to be a list, one entry per store the "
            "project's `.env` files reference."
        )
        entries = []

    providers: list[Provider] = []
    for index, entry in enumerate(entries):
        provider, entry_problems = _parse_provider(entry, index)
        problems.extend(entry_problems)
        if provider is not None:
            providers.append(provider)

    seen: dict[str, int] = {}
    for index, provider in enumerate(providers):
        if provider.scheme in seen:
            problems.append(
                f"{PROVIDER_FIELD}[{index}] declares '{provider.scheme}', which "
                f"{PROVIDER_FIELD}[{seen[provider.scheme]}] already does. A `.env` "
                "value matches one provider, so which of the two resolved it would "
                "be whichever was read last."
            )
        else:
            seen[provider.scheme] = index

    return Declaration(providers=tuple(providers), default_env=default_env), problems
