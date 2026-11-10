#!/usr/bin/env bash
#
# Runs the API locally. Secrets come from 1Password at launch, so nothing is
# written to disk and no key lands in the repository or in shell history.
#
# Needs the 1Password CLI, signed in: https://developer.1password.com/docs/cli
# Without it, export OPENROUTER_API_KEY yourself; everything except the
# recommendations still works.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

OP_ITEM="${OP_ITEM:-op://OCR-Eval-Dashboard/dashboard-secrets}"

# Local runs need no database server. Point DATABASE_URL_OVERRIDE at Postgres,
# or unset it and fill in POSTGRES_*, to use one.
export DATABASE_URL_OVERRIDE="${DATABASE_URL_OVERRIDE:-sqlite+aiosqlite:///./devpulse-local.db}"
export DEMO_MODE="${DEMO_MODE:-true}"
export ENVIRONMENT="${ENVIRONMENT:-local}"

if command -v op >/dev/null 2>&1; then
  if op read "${OP_ITEM}/OPENROUTER_API_KEY" >/dev/null 2>&1; then
    OPENROUTER_API_KEY="$(op read "${OP_ITEM}/OPENROUTER_API_KEY")"
    export OPENROUTER_API_KEY
    echo "Loaded OPENROUTER_API_KEY from ${OP_ITEM}"
  else
    echo "No OPENROUTER_API_KEY in ${OP_ITEM}; recommendations will be disabled."
  fi

  # Optional. Without it the API serves the demo dataset only.
  if op read "${OP_ITEM}/GITHUB_TOKEN" >/dev/null 2>&1; then
    GITHUB_TOKEN="$(op read "${OP_ITEM}/GITHUB_TOKEN")"
    export GITHUB_TOKEN
  fi
elif [ -z "${OPENROUTER_API_KEY:-}" ]; then
  echo "The 1Password CLI (op) is not installed and OPENROUTER_API_KEY is unset."
  echo "Starting anyway: the dashboard works, recommendations are disabled."
fi

cd backend

if [ ! -x .venv/bin/uvicorn ]; then
  echo "No virtualenv found. Run 'make install' first." >&2
  exit 1
fi

echo "API on http://localhost:8000  (docs at /docs)"
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
