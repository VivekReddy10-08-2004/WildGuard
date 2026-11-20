"""Ultralytics adapter for the North American wildlife detector."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import torch
from huggingface_hub import hf_hub_download
from PIL import Image
from ultralytics import YOLO  # type: ignore[attr-defined]

from shared.contracts import BoundingBox, Detection, ImagePrediction

MODEL_REPOSITORY = "UWyo/wildlife-north-american-wildlife"
MODEL_FILENAME = (
    "yolo26s_finetuned_26-wildlife-class_by_J.Gong_uwyo_2026-05-28.pt"
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_DIR = PROJECT_ROOT / "storage" / "models" / "north_american_wildlife"
ImageSource = str | Path | Image.Image


def download_weights(model_dir: Path = DEFAULT_MODEL_DIR) -> Path:
    """Download the model weight into project-local storage and return its path."""

    weights_path = model_dir / MODEL_FILENAME
    if weights_path.is_file():
        return weights_path

    model_dir.mkdir(parents=True, exist_ok=True)
    return Path(
        hf_hub_download(
            repo_id=MODEL_REPOSITORY,
            filename=MODEL_FILENAME,
            local_dir=model_dir,
        )
    )


class WildlifeDetector:
    """Load the wildlife model once and expose normalized prediction results."""

    def __init__(
        self,
        weights_path: str | Path | None = None,
        *,
        device: str | int | None = None,
        model: YOLO | None = None,
    ) -> None:
        if model is None:
            resolved_weights = (
                Path(weights_path) if weights_path else download_weights()
            )
            model = YOLO(resolved_weights)

        self._model = model
        default_device = 0 if torch.cuda.is_available() else "cpu"
        self.device = device if device is not None else default_device

    @property
    def class_names(self) -> Mapping[int, str]:
        """Return the model's class-id to class-name mapping."""

        return self._model.names

    def predict(
        self,
        source: ImageSource | Sequence[ImageSource],
        *,
        confidence: float = 0.25,
        iou: float = 0.7,
        image_size: int = 640,
        save: bool = False,
        output_dir: str | Path | None = None,
    ) -> list[ImagePrediction]:
        """Run inference and normalize Ultralytics results for the backend."""

        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not 0 <= iou <= 1:
            raise ValueError("iou must be between 0 and 1")

        normalized_source: str | Image.Image | list[str | Image.Image]
        if isinstance(source, (str, Path)):
            normalized_source = str(source)
        elif isinstance(source, Image.Image):
            normalized_source = source
        else:
            normalized_source = [
                str(item) if isinstance(item, (str, Path)) else item
                for item in source
            ]

        predict_options: dict[str, Any] = {
            "source": normalized_source,
            "conf": confidence,
            "iou": iou,
            "imgsz": image_size,
            "device": self.device,
            "save": save,
            "verbose": False,
        }
        if output_dir is not None:
            destination = Path(output_dir)
            predict_options.update(
                project=str(destination.parent),
                name=destination.name,
                exist_ok=True,
            )

        results = self._model.predict(**predict_options)
        return [self._normalize_result(result) for result in results]

    @staticmethod
    def _normalize_result(result: Any) -> ImagePrediction:
        height, width = result.orig_shape
        detections: list[Detection] = []

        if result.boxes is not None:
            for box in result.boxes:
                class_id = int(box.cls.item())
                x_min, y_min, x_max, y_max = box.xyxy[0].tolist()
                detections.append(
                    Detection(
                        class_id=class_id,
                        label=result.names[class_id],
                        confidence=float(box.conf.item()),
                        bounding_box=BoundingBox(
                            x_min=x_min,
                            y_min=y_min,
                            x_max=x_max,
                            y_max=y_max,
                        ),
                    )
                )

        speed: Mapping[str, float] = result.speed or {}
        processing_ms = sum(speed.get(stage, 0.0) for stage in _TIMING_STAGES)
        return ImagePrediction(
            source=str(result.path),
            width=width,
            height=height,
            detections=detections,
            processing_ms=processing_ms,
        )


_TIMING_STAGES: Sequence[str] = ("preprocess", "inference", "postprocess")

