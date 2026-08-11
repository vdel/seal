FROM python:3.12-slim as development

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml /app
COPY uv.lock /app
RUN uv sync --frozen --group dev

# The application code lives in the `config`/`core` packages under src/, so make
# it importable regardless of the working directory (manage.py, gunicorn, celery).
ENV PYTHONPATH=/app/src

COPY ./src /app/src

# Entrypoint runs database migrations (when DATABASE_URL is set) before starting
# the server, and marks IS_BUILD_OR_TEST=0 so secrets are read from the environment.
COPY deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# IS_BUILD_OR_TEST=1 marks the build / unit-test scope: load_secrets() injects the
# explicit fakes (no real secrets, e.g. no pass-cli) so collectstatic can run while
# building the image without requiring any deployment environment variables.
RUN IS_BUILD_OR_TEST=1 uv run python src/manage.py collectstatic --noinput

EXPOSE 8888

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uv", "run", "python", "src/manage.py", "runserver", "0.0.0.0:8888"]


# ---
FROM development as test

# rsync is needed to copy the test results from the container to the host machine
RUN apt update && apt install -y --no-install-recommends \
    make rsync\
    && rm -rf /var/lib/apt/lists/*

COPY ./tests /app/tests
COPY ./Makefile /app

# This stage only carries the suite; nothing here runs it. `seal ci` runs
# `make unit-tests` inside the container once it is up (services/api/Tiltfile
# declares it as this service's test_command), which is what lets these
# tests use the real Postgres this service is configured against instead of
# the fakes a build has to settle for.


# ---
FROM development as runtime

CMD ["uv", "run", "python", "-m", "gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8888", "--workers", "3"]
