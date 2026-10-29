#!/usr/bin/env bash
# Run from any working directory; paths containing spaces are supported.
set -Eeuo pipefail

trap 'status=$?; printf "Culture-Fit could not start (exit %s). See the error above.\n" "$status" >&2; exit "$status"' ERR

project_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$project_dir"

if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' \
    'uv is required. Install it using the official instructions, then reopen your terminal:' \
    'https://docs.astral.sh/uv/getting-started/installation/' >&2
  exit 127
fi

if [[ ! -f pyproject.toml || ! -f uv.lock ]]; then
  printf '%s\n' 'Extract the complete source ZIP before running this script. pyproject.toml or uv.lock is missing.' >&2
  exit 1
fi

port="${ARBITER_PORT:-8787}"
if [[ ! "$port" =~ ^[0-9]{1,5}$ ]] || (( 10#$port < 1 || 10#$port > 65535 )); then
  printf '%s\n' 'ARBITER_PORT must be an integer from 1 to 65535.' >&2
  exit 2
fi
port="$((10#$port))"

printf '%s\n' 'Preparing the locked Python environment (uv sync --frozen)...'
uv sync --frozen
printf '%s\n' 'Preparing local source and Skill downloads...'
uv run --frozen python scripts/package_downloads.py
printf '\nOpen http://127.0.0.1:%s/workspace in your browser.\n' "$port"
printf '%s\n' 'Keep this terminal open. Press Ctrl+C to stop Culture-Fit.'
exec uv run --frozen uvicorn arbiter.app:app --host 127.0.0.1 --port "$port"
