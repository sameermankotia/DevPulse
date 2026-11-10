#!/usr/bin/env bash
#
# Starts the API with secrets pulled from 1Password at launch. Nothing is
# written to disk, so no key ever lands in the repository or in shell history.
#
# Requires the 1Password CLI, signed in: https://developer.1password.com/docs/cli
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

OP_ITEM="${OP_ITEM:-op://OCR-Eval-Dashboard/dashboard-secrets}"

if ! command -v op >/dev/null 2>&1; then
  echo "The 1Password CLI (op) is not installed." >&2
  echo "Install it, or export OPENROUTER_API_KEY yourself and run uvicorn directly." >&2
  exit 1
fi

echo "Reading credentials from ${OP_ITEM}"
OPENROUTER_API_KEY="$(op read "${OP_ITEM}/OPENROUTER_API_KEY")"
export OPENROUTER_API_KEY

# GITHUB_TOKEN is optional: without it the API serves the demo dataset.
if op read "${OP_ITEM}/GITHUB_TOKEN" >/dev/null 2>&1; then
  GITHUB_TOKEN="$(op read "${OP_ITEM}/GITHUB_TOKEN")"
  export GITHUB_TOKEN
fi

cd backend
exec ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
