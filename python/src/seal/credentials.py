"""Shared logic behind `seal run`, `seal up`, `seal ci` and `seal check`:
locate a seal project/service, and resolve a service's `.env` (see
/rfcs/0006-credential-resolution.md at the repo root) into plain values --
through whatever providers a project declared for any `scheme://` reference
it contains, and direct injection for everything else. `resolve()` is the
one place credential resolution happens; `seal run` (an arbitrary command),
`seal up` (building each service's dev Kubernetes Secret) and `seal ci` (the
same, for CI/stag/prod -- see seal.py) all go through it.
`declaration_problems()` checks a project's `.env` files against the same
declarations without resolving anything, for `seal check`.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from dotenv import dotenv_values

from seal import providers

ROOT_TILTFILE_NAME = "Tiltfile"
SERVICES_DIR_NAME = "services"
ENV_FILE_NAME = ".env"

# The one placeholder in a provider's `command` that stands for a list
# rather than a string: the whole command being wrapped.
COMMAND_PLACEHOLDER = "{command}"

# How seal gets values back out of a `run`-form provider: the command it
# wraps is seal itself, writing the keys it was asked for out of the
# environment that provider put them in.
EMIT_ENV_SUBCOMMAND = "_emit-env"

# Not a password manager: marks a key as supplied directly by the Kubernetes
# deployment manifests (a literal `env:` entry pointing at an in-cluster
# service, e.g. a bundled dev Postgres) in every scope -- dev and CI/stag/
# prod alike. Never resolved or injected by seal; see
# rfcs/0006-credential-resolution.md.
K8S_PROVIDED_PREFIX = "k8s://"

class SealError(Exception):
    """A user-facing error: `main()` prints it (no traceback) and exits 1."""


def find_seal_root(start: Path, outcomes_dir_name: str | None = None) -> Path:
    """Walk up from `start` looking for a seal project's root.

    A project with services is a directory with its own `Tiltfile` *and* a
    `services/` subdirectory -- both together, since a service's own
    directory (e.g. services/api/) has a Tiltfile too, but never its own
    nested `services/`.

    `outcomes_dir_name` also accepts **a directory holding that tree**, and
    is passed by the commands that read a project's promises rather than
    bring one up. A project whose groups all run on the machine needs no
    Tiltfile and no cluster to state what it promises or to check it (see
    /rfcs/0014-seal-on-seal.md), and there is nothing for the
    commands that do need one to do about that but keep asking for it.

    The name is passed in rather than assumed, because where a project keeps
    its tree is the project's to say (SEAL_OUTCOMES_DIR, or
    `--outcomes-dir` for one invocation) -- and a walk looking for a
    hardcoded `outcomes/` would miss the tree it was about to read.

    Nearest wins, and the two rules are tried at each level before moving
    up. So a project that has both is found at the level that has both,
    rather than at whichever rule happens to be checked first.
    """
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ROOT_TILTFILE_NAME).exists() and (candidate / SERVICES_DIR_NAME).is_dir():
            return candidate
        if outcomes_dir_name and (candidate / outcomes_dir_name).is_dir():
            return candidate
    looked_for = (
        f"no directory with both a '{ROOT_TILTFILE_NAME}' and a "
        f"'{SERVICES_DIR_NAME}/' subdirectory"
    )
    if outcomes_dir_name is not None:
        # Both ways of being a project, named. A reader who has one of the
        # two shapes should not have to find out from somewhere else that
        # the other would have done.
        article = "an" if outcomes_dir_name[:1].lower() in "aeiou" else "a"
        looked_for += f", and none holding {article} '{outcomes_dir_name}/' tree"
    raise SealError(
        f"Error: not inside a seal project -- {looked_for} found in "
        f"{start} or any parent directory."
    )


def find_service(seal_root: Path, cwd: Path) -> tuple[str, Path]:
    """Deduce which services/<name>/ the given directory is inside of."""
    services_dir = seal_root / SERVICES_DIR_NAME
    resolved_cwd = cwd.resolve()
    try:
        relative = resolved_cwd.relative_to(services_dir.resolve())
    except ValueError:
        relative = None
    if relative is None or not relative.parts:
        raise SealError(
            f"Error: not inside a service directory -- {resolved_cwd} is not under "
            f"{services_dir}. Run `seal run` from inside services/<name>/ (or a "
            "subdirectory of it)."
        )
    service_name = relative.parts[0]
    service_dir = services_dir / service_name
    if not service_dir.is_dir():
        raise SealError(f"Error: service directory not found: {service_dir}")
    return service_name, service_dir


def discover_service_env_files(seal_root: Path) -> list[tuple[str, Path]]:
    """Every services/<name>/.env `seal check` can read straight off disk,
    sorted by name for a deterministic report.

    Walked directly rather than through `tilt_discovery.discover_services()`:
    a static check runs before anything establishes a session, and the
    image ref Tilt would report only matters for where a generated Secret
    lands, not for which file to read. A service directory with no `.env`
    has nothing to check, so it is skipped rather than reported.
    """
    services_dir = seal_root / SERVICES_DIR_NAME
    if not services_dir.is_dir():
        return []
    found = []
    for child in sorted(services_dir.iterdir()):
        if child.is_dir() and env_file_path(child).exists():
            found.append((child.name, child))
    return found


def env_file_path(service_dir: Path) -> Path:
    return service_dir / ENV_FILE_NAME


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise SealError(f"Error: no {ENV_FILE_NAME} found (expected at {path}).")
    # interpolate=False: a value is a literal, a `k8s://` marker, or a
    # reference naming an item -- never a template. Left on, dotenv expands
    # `${NAME}` from the process environment, which would make what a
    # service receives depend on whatever the shell happened to hold, and
    # would resolve to the empty string where it held nothing.
    values = dotenv_values(path, interpolate=False)
    return {key: value for key, value in values.items() if value is not None}


def resolvable_keys(values: dict[str, str]) -> list[str]:
    """Keys seal actually resolves/injects -- everything except k8s://-marked
    ones (see K8S_PROVIDED_PREFIX)."""
    return [key for key, value in values.items() if not value.startswith(K8S_PROVIDED_PREFIX)]


def resolvable_values(values: dict[str, str]) -> dict[str, str]:
    return {key: values[key] for key in resolvable_keys(values)}


@dataclass(frozen=True)
class Context:
    """What a run needs to turn a `.env` reference into a value: what the
    project declared, which of its environments this run reads, and which
    service is asking.

    Carried as one object rather than three arguments because every step of
    resolution needs all three, and a signature that grows a parameter per
    fact is one nobody can call from memory.
    """

    declaration: providers.Declaration
    # None where nothing named one. Only a problem if a `.env` actually
    # reaches a provider that scopes by environment -- see scope_for().
    environment: str | None
    service_name: str


def looks_like_reference(value: str) -> bool:
    """Whether this `.env` value names a store rather than being one.

    A scheme and a value are told apart by `://`, the same way a provider's
    own `scheme` is. A literal that happens to be a URL is indistinguishable
    from a reference by shape alone, so this is deliberately only used to
    ask "did the project mean a provider it has not declared?" -- never to
    decide that something is a reference.
    """
    return providers.SCHEME_SUFFIX in value


def providers_needed(context: Context, resolvable: dict[str, str]) -> list[providers.Provider]:
    """Which declared providers this `.env` actually reaches, in the order
    the project declared them.

    Declaration order, not discovery order: chaining wraps them one inside
    another, and which is outermost has to be something the project can see
    and change rather than a consequence of how its keys happen to sort.
    """
    needed: list[providers.Provider] = []
    for provider in context.declaration.providers:
        if any(value.startswith(provider.scheme) for value in resolvable.values()):
            needed.append(provider)
    return needed


def undeclared_scheme_problem(context: Context, resolvable: dict[str, str]) -> str | None:
    """The first value naming a store nothing declares, as a message.

    A `.env` that reaches a provider the project never declared is the one
    mistake that would otherwise reach a CLI as a literal, nonsense string:
    nothing resolves it, and the service starts with a URL where a secret
    should be.
    """
    for key, value in sorted(resolvable.items()):
        if not looks_like_reference(value):
            continue
        if context.declaration.for_scheme(value) is not None:
            continue
        scheme = value.split(providers.SCHEME_SUFFIX, 1)[0] + providers.SCHEME_SUFFIX
        return (
            f"Error: {key} names '{scheme}', which no provider declares. Add one to "
            f"{providers.CONFIG_FILENAME} at the project root, or make this value a "
            f"literal or a '{K8S_PROVIDED_PREFIX}' marker."
        )
    return None


def scope_for(context: Context, provider: providers.Provider) -> dict[str, str]:
    """What this provider calls the environment this run reads.

    A provider declaring no `environments` at all scopes some other way --
    by whatever session its CLI is authenticated for -- and needs no
    environment selected. One that does declare them needs this run to have
    named one of them.
    """
    scope = provider.scope(context.environment)
    if scope is not None:
        return scope

    declared = ", ".join(sorted(provider.environments))
    if context.environment is None:
        raise SealError(
            f"Error: {provider.name} reads a different store per environment, and "
            "this run named none. Pass "
            f"{providers.CREDENTIALS_ENV_FLAG}, set {providers.CREDENTIALS_ENV_VAR}, "
            f"or give {providers.CONFIG_FILENAME} a "
            f"'{providers.DEFAULT_ENV_FIELD}'. It declares: {declared}."
        )
    raise SealError(
        f"Error: {provider.name} declares no store for '{context.environment}'. It "
        f"declares: {declared}. Add it to '{providers.ENVIRONMENTS_FIELD}' in "
        f"{providers.CONFIG_FILENAME}, or name one of those."
    )


@dataclass(frozen=True)
class CredentialProblem:
    """One mismatch between a project's `.env` files and what it declared in
    seal-credentials-config.json, from declaration_problems(). `service_name`
    is None for a problem that names a provider rather than one `.env` --
    see declaration_problems()'s own note on why those are reported once."""

    service_name: str | None
    problem: str

    def describe(self) -> str:
        if self.service_name is None:
            return self.problem
        return f"{self.service_name}/{ENV_FILE_NAME}: {self.problem}"


def claimable_keys(seal_root: Path) -> dict[str, list[str]]:
    """Per service, the keys of its `.env` that something has to supply.

    Everything except `k8s://` markers: those name a value the manifests
    declare individually, from whatever they point at, and no object
    seal fills is entitled to them. So this is exactly the set an
    overlay's objects between them have to account for.
    """
    return {
        service_name: resolvable_keys(parse_env_file(env_file_path(service_dir)))
        for service_name, service_dir in discover_service_env_files(seal_root)
    }


def declaration_problems(
    seal_root: Path, declaration: providers.Declaration, environment: str | None
) -> list[CredentialProblem]:
    """Every mismatch between a project's `.env` files and its declared
    providers, named rather than resolved -- `seal check` runs before
    credentials are established, and checking a store actually holds a
    value would need whatever environment production reads to check
    production, which is a worse trade than the failure it prevents. See
    /rfcs/0006-credential-resolution.md.

    Three checks, over every services/<name>/.env on disk (see
    discover_service_env_files()): a value naming a scheme no provider
    declares; a value carrying a `${`, which a project writing one means to
    expand and this format never does; and a declared provider that some `.env`
    actually reaches with no mapping for `environment` -- checked once per
    provider rather than once per referencing `.env`, since whether one
    exists doesn't depend on which service asked.
    """
    problems: list[CredentialProblem] = []
    referenced: dict[str, providers.Provider] = {}
    for service_name, service_dir in discover_service_env_files(seal_root):
        values = parse_env_file(env_file_path(service_dir))
        for key, value in values.items():
            if "${" in value:
                problems.append(
                    CredentialProblem(
                        service_name,
                        f"{key} names {value!r}, which contains '${{' -- a `.env` "
                        f"value is a literal, a '{K8S_PROVIDED_PREFIX}' marker, or a "
                        "reference naming an item, never a template.",
                    )
                )
        resolvable = resolvable_values(values)
        context = Context(declaration=declaration, environment=environment, service_name=service_name)
        scheme_problem = undeclared_scheme_problem(context, resolvable)
        if scheme_problem is not None:
            problems.append(
                CredentialProblem(service_name, scheme_problem.removeprefix("Error: "))
            )
        for provider in providers_needed(context, resolvable):
            referenced.setdefault(provider.scheme, provider)

    # Not tied to any one service's context: which provider needs which
    # environment, and whether this run selected one, is the same question
    # regardless of which `.env` happened to reference it.
    run_context = Context(declaration=declaration, environment=environment, service_name="")
    for provider in referenced.values():
        try:
            scope_for(run_context, provider)
        except SealError as error:
            problems.append(CredentialProblem(None, str(error).removeprefix("Error: ")))
    return problems


def _template_values(context: Context, provider: providers.Provider) -> dict[str, str]:
    """What a `reference` or `command` template can hold, beyond the two
    each has of its own. The scope's own names come last, so a project's
    vocabulary is what it says it is."""
    values = {
        "env": context.environment or "",
        "service": context.service_name,
    }
    values.update(scope_for(context, provider))
    return values


def _filled(template: str, values: dict[str, str], provider: providers.Provider, field: str) -> str:
    try:
        return providers.fill(template, values)
    except providers.UnknownPlaceholder as unknown:
        raise SealError(
            f"Error: {provider.name}'s '{field}' names {unknown}"
        ) from unknown


def composed_values(context: Context, resolvable: dict[str, str]) -> dict[str, str]:
    """Every resolvable value, with each reference composed into the one its
    own provider understands.

    A reference in a `.env` names an item; the store it lives in comes from
    the provider's `reference` template and the selected environment's
    scope. This is what lets a provider whose scope lives inside the URI be
    declared without the `.env` carrying it.

    Literals pass through untouched, and so does a value belonging to
    another provider: each entry is composed by the one provider whose
    scheme it starts with, and chaining lets the rest through unchanged.
    """
    problem = undeclared_scheme_problem(context, resolvable)
    if problem is not None:
        raise SealError(problem)

    composed: dict[str, str] = {}
    for key, value in resolvable.items():
        provider = context.declaration.for_scheme(value)
        if provider is None:
            composed[key] = value
            continue
        values = _template_values(context, provider)
        values["item"] = value[len(provider.scheme) :]
        composed[key] = _filled(
            provider.reference, values, provider, providers.REFERENCE_FIELD
        )
    return composed


def _references_file(owned: dict[str, str]) -> Path:
    """A temp dotenv file of one provider's composed references, for the
    forms whose CLI reads references from a file.

    One provider's keys, not every resolvable one: a provider handed
    another's references would pass them through as literal, nonsense
    strings, and seal's own `k8s://` markers are not any provider's to see
    at all.

    mkstemp, so the file is created 0600 rather than made so afterwards.
    """
    fd, tmp_path = tempfile.mkstemp(prefix="seal-refs-", suffix=".env")
    with os.fdopen(fd, "w") as f:
        for key, value in owned.items():
            f.write(f"{key}={value}\n")
    return Path(tmp_path)


def _require_cli(context: Context, provider: providers.Provider) -> None:
    if shutil.which(provider.cli) is not None:
        return
    hint = f" -- install it: {provider.install_hint}" if provider.install_hint else ""
    raise SealError(
        f"Error: '{provider.cli}' not found on PATH{hint}\n(a `.env` references "
        f"a {provider.scheme} value, which {provider.name} resolves.)"
    )


def _command_argv(
    context: Context,
    provider: providers.Provider,
    extra: dict[str, str],
    terminal_argv: list[str] | None = None,
) -> list[str]:
    """One provider's `command`, filled.

    `{command}` is the one placeholder standing for a list rather than a
    string, so it has to be a word of its own; a form that wraps nothing
    passes `terminal_argv=None` and rejects it outright.
    """
    values = _template_values(context, provider)
    values.update(extra)
    argv: list[str] = []
    for word in provider.command:
        if word == COMMAND_PLACEHOLDER:
            if terminal_argv is None:
                raise SealError(
                    f"Error: {provider.name}'s '{providers.COMMAND_FIELD}' has "
                    f"{COMMAND_PLACEHOLDER}, which only the "
                    f"'{providers.RUN}' form wraps anything for."
                )
            argv.extend(terminal_argv)
        elif COMMAND_PLACEHOLDER in word:
            raise SealError(
                f"Error: {provider.name}'s '{providers.COMMAND_FIELD}' has "
                f"{COMMAND_PLACEHOLDER} inside {word!r}. It stands for the whole "
                "command being wrapped, so it has to be a word of its own."
            )
        else:
            argv.append(_filled(word, values, provider, providers.COMMAND_FIELD))
    return argv


def _resolve_run(
    context: Context, provider: providers.Provider, owned: dict[str, str]
) -> dict[str, str]:
    """A provider whose CLI wraps a command, putting values in its
    environment.

    The only form that cannot hand values back directly, so seal supplies
    the command being wrapped: `seal _emit-env`, which writes the keys it
    was asked for out of its own environment. That is the whole reason an
    internal subcommand exists.
    """
    references = _references_file(owned)
    fd, out_path = tempfile.mkstemp(prefix="seal-values-", suffix=".json")
    os.close(fd)
    try:
        argv = _command_argv(
            context,
            provider,
            {"env_file": str(references)},
            [
                sys.executable, "-m", "seal.seal", EMIT_ENV_SUBCOMMAND,
                "--keys", ",".join(owned),
                "--out", out_path,
            ],
        )
        result = subprocess.run(argv, env=os.environ.copy())
        if result.returncode != 0:
            raise SealError(
                f"Error: {provider.name} exited {result.returncode} resolving "
                f"{', '.join(sorted(owned))}."
            )
        return json.loads(Path(out_path).read_text(encoding="utf-8"))
    finally:
        references.unlink(missing_ok=True)
        Path(out_path).unlink(missing_ok=True)


def _dotenv_from_stdout(text: str) -> dict[str, str]:
    """A provider's stdout, read the same way a `.env` file is: no
    interpolation, since a resolved value is a value, never a template."""
    values = dotenv_values(stream=StringIO(text), interpolate=False)
    return {key: value for key, value in values.items() if value is not None}


def _run_provider(
    context: Context,
    provider: providers.Provider,
    extra: dict[str, str],
    doing: str,
    owned: dict[str, str],
) -> str:
    """One non-interactive invocation of a provider's `command`, with no
    terminal command of its own -- the forms that hand values back directly
    rather than wrapping one. Returns stdout; raises naming the provider,
    what it was doing, and its stderr, on a non-zero exit."""
    argv = _command_argv(context, provider, extra)
    result = subprocess.run(argv, capture_output=True, text=True)
    if result.returncode != 0:
        raise SealError(
            f"Error: {provider.name} exited {result.returncode} {doing} "
            f"{', '.join(sorted(owned))}: {result.stderr.strip()}"
        )
    return result.stdout


def _resolve_resolve(
    context: Context, provider: providers.Provider, owned: dict[str, str]
) -> dict[str, str]:
    """A provider whose CLI reads a dotenv file of references and writes the
    same file, resolved, to stdout -- a straight round-trip, so the table it
    returns is keyed by the `.env`'s own key names."""
    references = _references_file(owned)
    try:
        stdout = _run_provider(
            context, provider, {"env_file": str(references)}, "resolving", owned
        )
    finally:
        references.unlink(missing_ok=True)

    table = _dotenv_from_stdout(stdout)
    missing = [key for key in owned if key not in table]
    if missing:
        raise SealError(
            f"Error: {provider.name} did not resolve {', '.join(sorted(missing))}."
        )
    return {key: table[key] for key in owned}


def _resolve_fetch(
    context: Context, provider: providers.Provider, owned: dict[str, str]
) -> dict[str, str]:
    """A provider whose CLI dumps a whole scope; seal keeps only what the
    `.env` actually named and ignores the rest.

    `owned` maps each `.env` key to its composed item -- the name inside
    this provider's own scope, which is what the returned table is keyed
    by, not what a project chose to call the environment variable. A scope
    holding fifty secrets does not put fifty variables in a container.
    """
    stdout = _run_provider(context, provider, {}, "fetching", owned)
    table = _dotenv_from_stdout(stdout)

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for key, item in owned.items():
        if item in table:
            resolved[key] = table[item]
        else:
            missing.append(key)
    if missing:
        named = ", ".join(f"{key} ({owned[key]!r})" for key in sorted(missing))
        raise SealError(f"Error: {provider.name}'s scope has no value for {named}.")
    return resolved


def _resolve_get(
    context: Context, provider: providers.Provider, owned: dict[str, str]
) -> dict[str, str]:
    """A provider with no wrapping form at all: one item in, one value on
    stdout, invoked once per reference. The slow shape, and the one every
    surveyed product with no `run`/`resolve`/`fetch` form supports.

    Stdout *is* the value, with exactly one trailing newline stripped and
    nothing else -- a store is free to keep a value with leading spaces,
    internal newlines, or a trailing one that matters.
    """
    resolved: dict[str, str] = {}
    for key, item in owned.items():
        argv = _command_argv(context, provider, {"item": item})
        result = subprocess.run(argv, capture_output=True, text=True)
        if result.returncode != 0:
            raise SealError(
                f"Error: {provider.name} exited {result.returncode} resolving "
                f"{key} ({item!r}): {result.stderr.strip()}"
            )
        value = result.stdout[:-1] if result.stdout.endswith("\n") else result.stdout
        if not value:
            # A store that returns nothing for an item it was asked about is
            # a store that did not have it -- not a service that starts with
            # a blank where a secret should be.
            raise SealError(
                f"Error: {provider.name} returned nothing for {key} ({item!r})."
            )
        resolved[key] = value
    return resolved


def resolve(context: Context, values: dict[str, str]) -> dict[str, str]:
    """Every value a service's `.env` declares, resolved.

    One function and one return, rather than a process each caller has to
    wrap: `seal run` merges the result into an environment, `seal up` and
    `seal ci` render a Kubernetes Secret from it, and neither has to run
    inside whatever a provider's CLI started.

    Providers are queried independently and their results merged. There is
    no ordering: each key names exactly one provider through its scheme, so
    nothing a provider returns can contend with anything another did.
    """
    resolvable = resolvable_values(values)

    problem = undeclared_scheme_problem(context, resolvable)
    if problem is not None:
        raise SealError(problem)

    composed = composed_values(context, resolvable)

    resolved: dict[str, str] = {}
    owned_by: dict[str, dict[str, str]] = {}
    for key, value in resolvable.items():
        provider = context.declaration.for_scheme(value)
        if provider is None:
            resolved[key] = value  # a literal is already its own value
        else:
            owned_by.setdefault(provider.scheme, {})[key] = composed[key]

    for provider in providers_needed(context, resolvable):
        _require_cli(context, provider)
        owned = owned_by[provider.scheme]
        if provider.form == providers.RUN:
            resolved.update(_resolve_run(context, provider, owned))
        elif provider.form == providers.RESOLVE:
            resolved.update(_resolve_resolve(context, provider, owned))
        elif provider.form == providers.FETCH:
            resolved.update(_resolve_fetch(context, provider, owned))
        elif provider.form == providers.GET:
            resolved.update(_resolve_get(context, provider, owned))
        else:  # pragma: no cover -- unreachable: FORMS == IMPLEMENTED_FORMS
            raise SealError(
                f"Error: {provider.name} declares the '{provider.form}' form, "
                f"which seal does not implement."
            )
    return resolved


def exec_resolved(resolved: dict[str, str], terminal_argv: list[str]) -> None:
    """Replace the current process with `terminal_argv`, its environment the
    resolved values under whatever is already set.

    An already-set variable wins, so a developer can override one key for a
    single command without editing `.env`.
    """
    env = dict(resolved)
    env.update(os.environ)
    os.execvpe(terminal_argv[0], terminal_argv, env)
