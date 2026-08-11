#!/bin/sh
# This service's reset, run by the '__example_api_reset' Tilt resource that
# services/api/Tiltfile's seal_service(reset=...) declares (see
# /tilt/seal/build.Tiltfile for the contract,
# /rfcs/0004-deterministic-state.md for
# the convention this is the worked example of).
#
# One script, not a clean step and a separate seed step: what a test needs
# is this service's state at a known, useful baseline, and an empty database
# is only half of that. Emptying the stores and loading the fixture belong
# together, in that order, where nothing can run one without the other.
#
# Acts on the running cluster through kubectl rather than connecting to
# Postgres itself: the pod already holds the credentials `seal up` generated
# from services/api/.env, so nothing here needs them resolved locally.
set -e

echo "reset(api): applying migrations..."
kubectl exec deploy/web -c example-api -- uv run python src/manage.py migrate --noinput

# `flush`, not a DROP/CREATE of the database: it empties every table and
# resets sequences while leaving the schema exactly as the migrations just
# built it, which is the baseline this hook promises. Dropping the database
# would also mean evicting every open connection (the api and both celery
# containers hold one) before it could succeed.
echo "reset(api): emptying every table..."
kubectl exec deploy/web -c example-api -- uv run python src/manage.py flush --noinput

# Valkey is this service's Celery broker and result backend (see
# CELERY_BROKER_URL / CELERY_RESULT_BACKEND in k8s/dev/web/api and
# k8s/dev/celery): task results and django-celery-beat's schedule survive
# there across runs, which is the same leftover-state problem the database
# flush above solves. It lives here, in the reset of the service whose code
# puts that data there, rather than in `seal` -- which deliberately knows
# nothing about datastores.
echo "reset(api): flushing valkey..."
kubectl exec deploy/valkey -- valkey-cli flushall

# `loaddata` against a checked-in fixture, rather than a script that creates
# rows: the fixture is data, so it diffs as data, and every row's primary key
# and created_at are pinned in it -- a test can name `todo 3` and mean it.
# It runs on tables the flush above just emptied; loading it over existing
# rows would overwrite by pk rather than produce the baseline.
echo "reset(api): loading the baseline fixture..."
kubectl exec deploy/web -c example-api -- uv run python src/manage.py loaddata baseline
