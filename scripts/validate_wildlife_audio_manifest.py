"""Validate a JSONL wildlife-audio manifest without altering source recordings."""

import argparse
import json
import math
from pathlib import Path

REQUIRED = {
    "recording_id", "source", "source_url", "audio_path", "license_id",
    "license_verified", "taxon", "scientific_name", "region",
    "annotation_type", "annotation_method", "split",
}
ALLOWED_SPLITS = {"train", "val", "test", "unassigned"}
ALLOWED_ANNOTATIONS = {"clip", "event", "unlabeled"}
ALLOWED_SUFFIXES = {".wav", ".flac", ".mp3", ".ogg", ".m4a"}


def validate_record(record: object, audio_root: Path | None = None) -> list[str]:
    """Return validation errors; never infer missing species or event times."""
    if not isinstance(record, dict):
        return ["record must be a JSON object"]
    errors = []
    missing = REQUIRED - record.keys()
    if missing:
        errors.append("missing fields: " + ", ".join(sorted(missing)))
    if record.get("split") not in ALLOWED_SPLITS:
        errors.append("invalid split")
    if record.get("annotation_type") not in ALLOWED_ANNOTATIONS:
        errors.append("invalid annotation_type")
    if not isinstance(record.get("license_verified"), bool):
        errors.append("license_verified must be boolean")
    if record.get("license_verified") is True and not record.get("license_id"):
        errors.append("verified license requires license_id")
    if not isinstance(record.get("recording_id"), str) or not record.get("recording_id"):
        errors.append("recording_id must be nonempty")
    url = record.get("source_url")
    if not isinstance(url, str) or not url.startswith("https://"):
        errors.append("source_url must be HTTPS")
    rel = record.get("audio_path")
    if not isinstance(rel, str) or not rel:
        errors.append("audio_path must be nonempty")
    else:
        path = Path(rel)
        if path.is_absolute() or ".." in path.parts:
            errors.append("audio_path must be relative and must not escape root")
        elif path.suffix.lower() not in ALLOWED_SUFFIXES:
            errors.append("unsupported audio extension")
        elif audio_root is not None and not (audio_root / path).is_file():
            errors.append("audio file missing")
    events = record.get("events", [])
    if not isinstance(events, list):
        errors.append("events must be an array")
    else:
        if record.get("annotation_type") == "event" and not events:
            errors.append("event annotations require nonempty events")
        duration = record.get("duration_seconds")
        for i, event in enumerate(events):
            if not isinstance(event, dict):
                errors.append(f"event {i} must be object")
                continue
            start, end = event.get("start_seconds"), event.get("end_seconds")
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, end)):
                errors.append(f"event {i} invalid timestamps")
            elif start < 0 or end <= start or (isinstance(duration, (int, float)) and end > duration):
                errors.append(f"event {i} invalid time bounds")
            if not isinstance(event.get("label"), str) or not event["label"]:
                errors.append(f"event {i} missing label")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--audio-root", type=Path, default=None)
    args = parser.parse_args()
    errors = []
    ids = set()
    with args.manifest.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {number}: invalid JSON: {exc}")
                continue
            for error in validate_record(record, args.audio_root):
                errors.append(f"line {number}: {error}")
            if isinstance(record, dict):
                rid = record.get("recording_id")
                if rid in ids:
                    errors.append(f"line {number}: duplicate recording_id")
                ids.add(rid)
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1
    print("Manifest schema validation passed (not a license or label-accuracy audit).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
