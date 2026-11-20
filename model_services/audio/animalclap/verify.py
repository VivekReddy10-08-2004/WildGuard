"""Verify the pinned AnimalCLAP checkpoint and backbone load successfully."""

from __future__ import annotations

import sys
from pathlib import Path

import torch
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[3]
UPSTREAM = Path(__file__).resolve().parent / "upstream"
sys.path.insert(0, str(UPSTREAM))

from inference import HFCLAPContrastive  # noqa: E402


def load_model() -> tuple[torch.nn.Module, torch.device]:
    checkpoint = hf_hub_download("risashinoda/animalclap", "animalclap_epoch020.pth")
    model = HFCLAPContrastive("laion/clap-htsat-unfused")
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if isinstance(state, dict) and "state_dict" in state:
        state = state["state_dict"]
    state = {key.removeprefix("module."): value for key, value in state.items()}
    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing or unexpected:
        raise RuntimeError(
            f"Checkpoint mismatch: missing={missing}, unexpected={unexpected}"
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    return model, device


def main() -> None:
    model, device = load_model()
    parameters = sum(parameter.numel() for parameter in model.parameters())
    print(f"AnimalCLAP ready on {device}; parameters={parameters:,}")


if __name__ == "__main__":
    main()
