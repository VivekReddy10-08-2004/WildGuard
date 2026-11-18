"""Tests for normalized wildlife detector output."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

from model_services.image.wildlife_detector import MODEL_FILENAME, WildlifeDetector
from model_services.image.wildlife_detector import download_weights as resolve_weights


def test_download_weights_reuses_local_file(tmp_path: Path) -> None:
    weights_path = tmp_path / MODEL_FILENAME
    weights_path.touch()

    assert resolve_weights(tmp_path) == weights_path


def test_normalize_result_maps_ultralytics_box() -> None:
    box = SimpleNamespace(
        cls=torch.tensor([14.0]),
        conf=torch.tensor([0.91]),
        xyxy=torch.tensor([[10.0, 20.0, 110.0, 220.0]]),
    )
    result = SimpleNamespace(
        orig_shape=(480, 640),
        boxes=[box],
        names={14: "American Black Bear"},
        speed={"preprocess": 1.0, "inference": 5.0, "postprocess": 2.0},
        path=Path("bear.jpg"),
    )

    prediction = WildlifeDetector._normalize_result(result)

    assert prediction.source == "bear.jpg"
    assert prediction.width == 640
    assert prediction.height == 480
    assert prediction.processing_ms == 8.0
    assert len(prediction.detections) == 1
    assert prediction.detections[0].label == "American Black Bear"
    assert prediction.detections[0].confidence == pytest.approx(0.91)
    assert prediction.detections[0].bounding_box.x_max == 110.0


@pytest.mark.parametrize("field", ["confidence", "iou"])
def test_predict_rejects_invalid_threshold(field: str) -> None:
    model = SimpleNamespace(names={})
    detector = WildlifeDetector(model=model)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match=field):
        detector.predict("image.jpg", **{field: 1.1})

