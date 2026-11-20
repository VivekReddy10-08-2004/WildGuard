"""Local SmolVLM2 runtime for multi-frame event descriptions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

from model_services.video.smolvlm.prompt import build_prompt, parse_description
from shared.contracts import SceneDescription, TrackEvidence

MODEL_ID = "HuggingFaceTB/SmolVLM2-2.2B-Instruct"
MODEL_REVISION = "f83c1bbead2bd476ae6cf44b73203afcd23ed83e"


class SmolVLMRuntime:
    def __init__(self) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = AutoProcessor.from_pretrained(
            MODEL_ID,
            revision=MODEL_REVISION,
        )
        self.model = AutoModelForImageTextToText.from_pretrained(
            MODEL_ID,
            revision=MODEL_REVISION,
            dtype=torch.bfloat16 if self.device.type == "cuda" else torch.float32,
            attn_implementation="eager",
        ).to(self.device)
        self.model.eval()

    def describe(
        self, frame_paths: list[Path], detections: list[TrackEvidence]
    ) -> SceneDescription:
        images = [Image.open(path).convert("RGB") for path in frame_paths]
        content: list[dict[str, Any]] = [
            {"type": "image"} for _ in frame_paths
        ]
        content.append({"type": "text", "text": build_prompt(detections)})
        messages = [{"role": "user", "content": content}]
        prompt = self.processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
        )
        inputs = self.processor(
            text=prompt,
            images=images,
            return_tensors="pt",
        ).to(self.device)
        with torch.inference_mode():
            generated = self.model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=256,
            )
        generated = generated[:, inputs["input_ids"].shape[1] :]
        output = self.processor.batch_decode(generated, skip_special_tokens=True)[0]
        return parse_description(output)
