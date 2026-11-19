"""Compatibility projection without synthesizing event boundaries or labels."""

from scripts.wildlife_audio.schema import validate_bundle


def legacy_records(tables, source_ids):
    """Project one original audio asset per recording into the legacy JSONL shape.

    Full v1 tables remain authoritative. Window annotations remain only in the
    original_annotation_records extension, never masquerading as timed events.
    """
    errors = validate_bundle(tables, source_ids)
    if errors:
        raise ValueError("; ".join(errors))
    provenance = {p["provenance_id"]: p for p in tables.get("provenance", [])}
    reviews = {r["review_id"]: r for r in tables.get("rights", [])}
    splits = {s["recording_id"]: s["split"] for s in tables.get("split", [])}
    output = []
    for recording in tables.get("recording", []):
        rid = recording["recording_id"]
        assets = [
            a
            for a in tables.get("asset", [])
            if a["recording_id"] == rid and a["kind"] == "original"
        ]
        if len(assets) != 1:
            raise ValueError(
                "legacy export requires one selected original per recording"
            )
        asset = assets[0]
        annotations = [
            a
            for a in tables.get("annotation", [])
            if a["asset_id"] == asset["asset_id"]
        ]
        events = [
            {
                "start_seconds": a["start_seconds"],
                "end_seconds": a["end_seconds"],
                "label": a["label"],
            }
            for a in annotations
            if a["annotation_type"] == "event"
        ]
        review = reviews.get(recording["rights_review_id"], {})
        split = splits.get(rid, "unassigned")
        if split == "excluded":
            split = "unassigned"
        output.append(
            {
                "recording_id": rid,
                "source": recording["source_id"],
                "source_url": provenance[recording["provenance_id"]]["source_url"],
                "audio_path": asset["path"],
                "license_id": review.get("license_id"),
                "license_verified": review.get("status") == "approved",
                "taxon": recording["taxon"],
                "scientific_name": recording["scientific_name"],
                "region": recording["geography"]["region"],
                "annotation_type": "event"
                if events
                else ("clip" if recording["original_labels"] else "unlabeled"),
                "annotation_method": "preserved_source_annotations",
                "split": split,
                "events": events,
                "original_annotation_records": annotations,
                "original_labels": recording["original_labels"],
                "duration_seconds": asset["duration_seconds"],
            }
        )
    return output
