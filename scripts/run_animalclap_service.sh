#!/bin/sh
set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VENV_DIR="$REPO_ROOT/model_services/audio/animalclap/.venv"

if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "AnimalCLAP environment is missing. Run ./scripts/setup_animalclap_audio.sh" >&2
    exit 1
fi

cd "$REPO_ROOT"
export HF_HUB_CACHE="$REPO_ROOT/storage/models/animalclap/huggingface/hub"
export WILDGUARD_EVIDENCE_ROOT="$REPO_ROOT/storage/evidence"
exec "$VENV_DIR/bin/python" -m uvicorn \
    model_services.audio.animalclap.app:app --host 127.0.0.1 --port 8012
