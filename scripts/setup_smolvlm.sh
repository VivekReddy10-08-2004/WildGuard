#!/bin/sh
set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUNTIME_DIR="$REPO_ROOT/model_services/video/smolvlm"
VENV_DIR="$RUNTIME_DIR/.venv"
MODEL_DIR="$REPO_ROOT/storage/models/smolvlm2"
MODEL_ID="HuggingFaceTB/SmolVLM2-2.2B-Instruct"
MODEL_REVISION="f83c1bbead2bd476ae6cf44b73203afcd23ed83e"

uv venv "$VENV_DIR" --python 3.12
uv pip install --python "$VENV_DIR/bin/python" \
    --index-url https://download.pytorch.org/whl/cu118 \
    "torch==2.6.0" "torchvision==0.21.0"
uv pip install --python "$VENV_DIR/bin/python" \
    "transformers==5.23.0" "accelerate>=1.0" \
    "fastapi>=0.121.0" "num2words>=0.5.14" \
    "uvicorn[standard]>=0.38.0"

mkdir -p "$MODEL_DIR/huggingface/hub"
export HF_HUB_CACHE="$MODEL_DIR/huggingface/hub"
"$VENV_DIR/bin/hf" download "$MODEL_ID" --revision "$MODEL_REVISION"

PYTHONPATH="$REPO_ROOT" "$VENV_DIR/bin/python" \
    "$RUNTIME_DIR/verify.py"
