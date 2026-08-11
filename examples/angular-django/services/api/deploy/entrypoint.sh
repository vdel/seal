#!/bin/sh
set -e

# TODO: the migration step below should be moved out of the container entrypoint
# into a dedicated Kubernetes Job (run once per deploy) rather than running on
# every container start.
#
# Run from the app root so that `src/manage.py` and the uv project resolve.
cd /app

# When DATABASE_URL is set we run database migrations (waiting for the database
# to become reachable). Only the API container goes through this entrypoint;
# Celery containers override the command and rely on the API having migrated.
if [ -n "$DATABASE_URL" ]; then
    echo "Applying database migrations..."
    i=0
    until uv run python src/manage.py migrate --noinput; do
        i=$((i + 1))
        if [ "$i" -ge 30 ]; then
            echo "Database still not ready after $i attempts, giving up." >&2
            exit 1
        fi
        echo "Database not ready yet, retrying in 3s ($i/30)..."
        sleep 3
    done
    echo "Migrations applied."
fi

# Signal the application that secrets are already provided via the environment.
export IS_BUILD_OR_TEST=0

exec "$@"
