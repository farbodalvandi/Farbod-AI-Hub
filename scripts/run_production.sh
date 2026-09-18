#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

if [[ ! -x .venv/bin/gunicorn ]]; then
  echo "Virtual environment not found. Run ./scripts/setup_macos.sh first." >&2
  exit 1
fi

host="${FARBOD_ASSET_HOST:-0.0.0.0}"
port="${FARBOD_ASSET_PORT:-5000}"
workers="${FARBOD_WORKERS:-2}"
exec .venv/bin/gunicorn --bind "$host:$port" --workers "$workers" --threads 4 --timeout 120 wsgi:application
