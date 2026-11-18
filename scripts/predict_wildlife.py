"""Run North American wildlife detection against an image or supported source."""

import argparse
import json
from pathlib import Path

from model_services.image import WildlifeDetector


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Local image path or Ultralytics source URL")
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.7)
    parser.add_argument("--device", help="Ultralytics device, such as 0 or cpu")
    parser.add_argument("--save", action="store_true", help="Save annotated images")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("storage/evidence/predictions"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    detector = WildlifeDetector(device=args.device)
    predictions = detector.predict(
        args.source,
        confidence=args.confidence,
        iou=args.iou,
        save=args.save,
        output_dir=args.output_dir if args.save else None,
    )
    print(json.dumps([result.model_dump() for result in predictions], indent=2))


if __name__ == "__main__":
    main()

