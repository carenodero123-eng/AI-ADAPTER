#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    attempt=1
    while ! alembic upgrade head; do
        if [ "$attempt" -ge 10 ]; then
            echo "database migrations failed after $attempt attempts" >&2
            exit 1
        fi
        echo "database not ready; retrying migration ($attempt/10)" >&2
        attempt=$((attempt + 1))
        sleep 2
    done
fi

exec "$@"
