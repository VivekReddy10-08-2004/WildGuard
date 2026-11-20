#!/bin/sh
set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VENV_DIR="$REPO_ROOT/model_services/video/smolvlm/.venv"

if [ ! -x "$VENV_DIR/bin/uvicorn" ]; then
    echo "SmolVLM2 is not installed. Run ./scripts/setup_smolvlm.sh first." >&2
    exit 1
fi

export PYTHONPATH="$REPO_ROOT"
export HF_HUB_CACHE="$REPO_ROOT/storage/models/smolvlm2/huggingface/hub"
export WILDGUARD_EVIDENCE_ROOT="$REPO_ROOT/storage/evidence"
exec "$VENV_DIR/bin/uvicorn" \
    model_services.video.smolvlm.app:app --host 127.0.0.1 --port 8011
