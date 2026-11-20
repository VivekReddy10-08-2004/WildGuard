#!/bin/sh
set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WILDGUARD_API_PORT=${WILDGUARD_API_PORT:-8010}

cd "$REPO_ROOT"
exec uv run uvicorn backend.api.app:app \
    --host 127.0.0.1 --port "$WILDGUARD_API_PORT"
