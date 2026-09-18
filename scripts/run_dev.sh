#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

if [[ ! -x .venv/bin/python ]]; then
  echo "Virtual environment not found. Run ./scripts/setup_macos.sh first." >&2
  exit 1
fi

export FLASK_DEBUG="${FLASK_DEBUG:-1}"
export FARBOD_ASSET_HOST="${FARBOD_ASSET_HOST:-127.0.0.1}"
export FARBOD_ASSET_PORT="${FARBOD_ASSET_PORT:-5000}"
exec .venv/bin/python app.py
