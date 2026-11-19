"""Source-specific annotation import: predictions never become ground truth."""

import csv
import hashlib
import math
import re
from pathlib import PurePosixPath

from scripts.wildlife_audio.paths import safe_path


def nps_clip(source_label, source_page, transcript=None):
    """Page/transcript labels are weak clip labels, with no invented timestamps."""
    return {
        "original_label": source_label,
        "label": source_label,
        "annotation_type": "clip",
        "start_seconds": None,
        "end_seconds": None,
        "annotation_method": "unknown",
        "verification": "unverified",
        "confidence": None,
        "original_annotation": {
            "source_page": source_page,
            "source_label": source_label,
            "transcript": transcript,
        },
    }


def pnw_test2(csv_path):
    """Parse focal-class verification, not exhaustive species presence/absence.

    OFFSET/DURATION refer to the reviewed 12s candidate window, potentially inside
    a longer clip. They are retained as source offsets, not vocalization onsets.
    MANUAL_ID=No means focal class rejected, not an animal-free recording.
    """
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    output = []
    with csv_path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {
            "FOLDER",
            "IN_FILE",
            "CHANNEL",
            "OFFSET",
            "DURATION",
            "TOP1MATCH",
            "TOP1DIST",
            "MANUAL_ID",
        }
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise ValueError("unexpected PNW Test Set 2 columns")
        for number, row in enumerate(reader, 2):
            offset, duration = float(row["OFFSET"]), float(row["DURATION"])
            score = float(row["TOP1DIST"])
            if (
                not all(math.isfinite(v) for v in (offset, duration, score))
                or offset < 0
                or duration <= 0
                or not 0 <= score <= 1
            ):
                raise ValueError(f"invalid PNW numeric annotation at line {number}")
            channel = int(row["CHANNEL"])
            if channel < 0:
                raise ValueError("negative channel")
            folder = PurePosixPath(row["FOLDER"])
            filename = PurePosixPath(row["IN_FILE"])
            if (
                folder.is_absolute()
                or ".." in folder.parts
                or filename.name != row["IN_FILE"]
            ):
                raise ValueError("unsafe PNW source filename")
            safe_path(csv_path.parent, f"{row['FOLDER']}/{row['IN_FILE']}")
            focal, manual = row["TOP1MATCH"], row["MANUAL_ID"]
            if not focal or manual not in {focal, "No"}:
                raise ValueError("unrecognized manual-ID semantics; requires review")
            output.append(
                {
                    "original_label": focal,
                    "label": focal,
                    "focal_class": focal,
                    "focal_present": manual == focal,
                    "annotation_type": "window",
                    "annotation_method": "human",
                    "verification": "verified",
                    "start_seconds": offset,
                    "end_seconds": offset + duration,
                    "channel": channel,
                    "confidence": None,
                    "prediction_score": score,
                    "source_path": str(folder / filename),
                    "source_split": "test",
                    "source_manifest_sha256": digest,
                    "source_row": number,
                    "original_annotation": dict(row),
                }
            )
    return output


def canonical_annotation(
    imported, recording_id, asset_id, provenance_id, taxonomy_result
):
    """Convert a source row to the additive v1.1 contract without losing its payload."""
    identity = f"{provenance_id}:{imported.get('source_row', 0)}:{asset_id}"
    result = {
        "schema_version": "1.1.0",
        "annotation_id": hashlib.sha256(identity.encode()).hexdigest(),
        "recording_id": recording_id,
        "asset_id": asset_id,
        "annotation_type": imported["annotation_type"],
        "label": imported["label"],
        "taxon_id": taxonomy_result["taxon_id"]
        if imported.get("focal_present") is not False
        else None,
        "start_seconds": imported["start_seconds"],
        "end_seconds": imported["end_seconds"],
        "annotation_method": imported["annotation_method"],
        "verification": imported["verification"],
        "annotator_id": None,
        "confidence": imported["confidence"],
        "original_annotation": imported["original_annotation"],
        "provenance_id": provenance_id,
        "focal_present": imported.get("focal_present"),
        "prediction_score": imported.get("prediction_score"),
        "source_split": imported.get("source_split"),
        "channel": imported.get("channel"),
        "source_manifest_sha256": imported.get("source_manifest_sha256"),
        "source_row": imported.get("source_row"),
        "source_path": imported.get("source_path"),
    }
    return result


def pnw_record_identity(imported):
    """Derive only literal, obfuscated source identity; never infer coordinates."""
    filename = PurePosixPath(imported["source_path"]).name
    match = re.fullmatch(r"(Loc_\d+)_(\d{8})_(\d{6})_part_\d+\.wav", filename)
    if not match:
        raise ValueError("unknown PNW filename identity; requires review")
    site, date, time = match.groups()
    return {
        "recording_id": hashlib.sha256(imported["source_path"].encode()).hexdigest(),
        "source_id": "pnw_cnet_v5",
        "source_recording_id": filename,
        "identity_namespace": "pnw-nwfp-obfuscated-2023-v5",
        "site_id": site,
        "session_id": f"{site}:{date}:{time}",
        "recordist_id": None,
        "source_split": "test",
    }
