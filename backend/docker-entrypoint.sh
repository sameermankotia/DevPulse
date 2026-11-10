#!/bin/sh
# Applies migrations where they apply, then starts the API on the host's port.
set -e

DB="${DATABASE_URL_OVERRIDE:-postgres}"

case "$DB" in
  sqlite*)
    # SQLite builds its schema at startup; see the note in app/main.py.
    echo "SQLite backend: skipping migrations, schema is created at startup."
    ;;
  *)
    echo "Applying database migrations..."
    alembic upgrade head
    ;;
esac

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
