#!/bin/sh
set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UPSTREAM_DIR="$REPO_ROOT/model_services/audio/animalclap/upstream"
VENV_DIR="$REPO_ROOT/model_services/audio/animalclap/.venv"
MODEL_DIR="$REPO_ROOT/storage/models/animalclap"
PATCH_FILE="$REPO_ROOT/model_services/audio/animalclap/use_pytorch_checkpoint.patch"
UPSTREAM_REV="3cd5be491b6c0cb3dfbabdd5dc7b84cecb3ca09d"

uv venv "$VENV_DIR" --python 3.12
uv pip install --python "$VENV_DIR/bin/python" \
    --index-url https://download.pytorch.org/whl/cu121 \
    "torch==2.5.1" "torchaudio==2.5.1"
uv pip install --python "$VENV_DIR/bin/python" \
    "transformers[sentencepiece]==4.44.2" \
    "librosa==0.11.0" "fastapi>=0.121.0" "uvicorn[standard]>=0.38.0" \
    pandas tqdm

if [ ! -d "$UPSTREAM_DIR/.git" ]; then
    git clone --quiet https://github.com/dahlian00/AnimalCLAP.git "$UPSTREAM_DIR"
fi
git -C "$UPSTREAM_DIR" fetch --quiet origin "$UPSTREAM_REV"
git -C "$UPSTREAM_DIR" checkout --quiet --force "$UPSTREAM_REV"
git -C "$UPSTREAM_DIR" apply "$PATCH_FILE"

mkdir -p "$MODEL_DIR/huggingface/hub"
export HF_HUB_CACHE="$MODEL_DIR/huggingface/hub"

"$VENV_DIR/bin/hf" download \
    risashinoda/animalclap animalclap_epoch020.pth
"$VENV_DIR/bin/hf" download laion/clap-htsat-unfused
"$VENV_DIR/bin/python" "$REPO_ROOT/model_services/audio/animalclap/verify.py"
