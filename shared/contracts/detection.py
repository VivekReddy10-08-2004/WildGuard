"""Normalized image-detection contracts independent of any model vendor."""

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Pixel coordinates for one detected object's bounding box."""

    x_min: float = Field(ge=0)
    y_min: float = Field(ge=0)
    x_max: float = Field(ge=0)
    y_max: float = Field(ge=0)


class Detection(BaseModel):
    """One normalized wildlife detection."""

    class_id: int = Field(ge=0)
    label: str
    confidence: float = Field(ge=0, le=1)
    bounding_box: BoundingBox


class ImagePrediction(BaseModel):
    """All detections and timing data produced for one image."""

    source: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    detections: list[Detection]
    processing_ms: float = Field(ge=0)

