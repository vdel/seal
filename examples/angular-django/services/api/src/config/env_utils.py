import os


def is_build_or_test():
    """Determine if the code is running in the build / unit-test scope (no real secrets)."""
    return os.getenv('IS_BUILD_OR_TEST', '0') == '1'


# Explicit fakes for the build / unit-test scope. These let Django import and
# `collectstatic` / the test suite run without any real secret. They live here
# (in code), never in .env, so a missing value in stag/prod fails
# loudly instead of silently falling back to a dev default.
BUILD_SCOPE_FAKES = {
    "DJANGO_SECRET_KEY": "django-insecure-placeholder-secret-key-for-unit-tests-only",
}


def load_secrets():
    """
    Make secrets available as environment variables for the current scope.

    There are three flows:

    - build / unit tests (IS_BUILD_OR_TEST=1): inject the explicit fakes above.
      No database is configured, so settings.py falls back to in-memory SQLite.
    - deployed / CI, or local development via Tilt (`seal up`/`seal ci`):
      values are already injected via the environment (the Kubernetes Secret
      `seal up`/`seal ci` generates from ../.env via pass-cli, dev and
      CI/stag/prod alike -- see /rfcs/0006-credential-resolution.md) -- nothing to
      load here.
    - local development, run directly (not through Tilt): run this process
      via `seal run -- ...` instead of invoking it directly (see
      /rfcs/0006-credential-resolution.md at the repo root) -- it resolves
      ../.env the same
      way `seal up` does, so by the time this function runs there's nothing
      left for it to do either. The only thing it still provides is a
      DATABASE_URL fallback, for commands that skip `seal run` entirely
      (e.g. an IDE's own test runner) and don't need real secrets, just a
      reachable local database.
    """
    if is_build_or_test():
        for key, value in BUILD_SCOPE_FAKES.items():
            os.environ.setdefault(key, value)
        return

    if os.environ.get('DATABASE_URL') is None:
        os.environ['DATABASE_URL'] = "postgresql://app:app-dev-password@localhost:5432/app"
