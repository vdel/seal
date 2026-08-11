"""The bundled example's own credential declaration is well-formed.

Every other test here builds its fixtures itself, on purpose: what an
adopting project gets has to be true regardless of how the example happens
to be laid out. This file is the deliberate exception, and it asserts the
opposite thing -- not that the library behaves a certain way, but that the
*example* does, because a worked example nobody checks is a snippet.

`examples/angular-django/` declares a provider its own `.env` never
references (its `DJANGO_SECRET_KEY` is a literal, so its CI depends on no
store being reachable). That makes the declaration documentation, and
documentation rots. Parsing it here is what keeps it from rotting silently:
a project copying this file gets something that works.
"""

from pathlib import Path

from seal import providers

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "angular-django"


def test_the_example_declares_a_provider_with_no_problems():
    declaration, problems = providers.read_config(EXAMPLE)

    assert problems == [], problems
    assert declaration.providers, "the example is supposed to declare one"


def test_the_example_names_a_store_per_environment():
    """The `environments` mapping is the thing the design turns on -- a
    store is named per environment rather than substituted into a reference
    -- so an example that declared a provider with no mapping would
    demonstrate the wrong half of it."""
    declaration, _ = providers.read_config(EXAMPLE)
    provider = declaration.providers[0]

    assert len(provider.environments) >= 2, provider.environments
    for environment in provider.environments:
        assert provider.scope(environment), environment


def test_the_example_names_the_environment_a_bare_run_reads():
    """seal owns no default. A bare `seal up` works here only
    because the project said what a bare run means."""
    declaration, _ = providers.read_config(EXAMPLE)

    assert declaration.default_env in declaration.providers[0].environments


def test_the_examples_env_teaches_nothing_seal_would_refuse():
    """The `.env` an adopting project copies from is documentation too. A
    `${` in it -- even commented -- would be teaching the substitution
    `seal check` now rejects outright."""
    env = (EXAMPLE / "services" / "api" / ".env").read_text(encoding="utf-8")

    assert "${" not in env
