"""Offline analysis of inventoried audio; no acquisition and no implicit release."""

import collections
import json

from scripts.wildlife_audio.dedup import duplicate_edges, fingerprint
from scripts.wildlife_audio.paths import safe_path
from scripts.wildlife_audio.rights import redistribution_errors
from scripts.wildlife_audio.schema import validate
from scripts.wildlife_audio.splits import group_and_split
from scripts.wildlife_audio.taxonomy import normalize


def analyze(catalog, inventory, taxonomy):
    """Catalog records carry source identities/labels, paths and official splits.

    This reports quality and conservative group membership, not an authorized
    dataset release. PNW-Cnet v5 is evaluation-only in this implementation.
    """
    records = catalog["recordings"]
    if len({r["recording_id"] for r in records}) != len(records):
        raise ValueError("duplicate catalog recording ID")
    for record in records:
        if (
            record["source_id"] == "pnw_cnet_v5"
            and record.get("source_split") != "test"
        ):
            raise ValueError(
                "PNW v5 evaluation may not be redesignated by this pipeline"
            )
    ledger = inventory.audit()
    measured = {r["path"]: r for r in ledger["assets"]}
    decoded, results, failures = {}, [], []
    for record in records:
        rid, relative = record["recording_id"], record["path"]
        try:
            row = measured.get(relative)
            if not row or row["state"] != "ready":
                raise ValueError("audio must be ready in inventory")
            path = safe_path(inventory.payload, relative)
            feature = fingerprint(path)
            if feature["sha256"] != row["sha256"]:
                raise ValueError("audio changed after inventory audit")
            decoded[rid] = feature
            rights_errors = redistribution_errors(
                record.get("rights_review", {}),
                record["source_id"],
                record["source_recording_id"],
                feature["sha256"],
            )
            results.append(
                {
                    "recording_id": rid,
                    "source_id": record["source_id"],
                    "original_labels": record["original_labels"],
                    "taxonomy": [
                        normalize(label, taxonomy)
                        for label in record["original_labels"]
                    ],
                    "audio": {k: v for k, v in feature.items() if k != "vectors"},
                    "commercial_redistribution_errors": rights_errors,
                }
            )
        except (ValueError, RuntimeError, OSError) as exc:
            failures.append({"recording_id": rid, "error": str(exc)})
    accepted_annotations = []
    record_index = {r["recording_id"]: r for r in records}
    for annotation in catalog.get("annotations", []):
        issues = validate("annotation", annotation)
        rid = annotation.get("recording_id") if isinstance(annotation, dict) else None
        if rid not in record_index:
            raise ValueError("annotation references a missing catalog recording")
        record = record_index[rid]
        if not issues and annotation["asset_id"] != record.get("asset_id", rid):
            issues.append("annotation asset does not match catalog asset")
        if not issues and annotation.get("source_split") is not None:
            if annotation["source_split"] != record.get("source_split"):
                issues.append("annotation official split differs from recording")
        if not issues and rid in decoded:
            if (
                annotation["end_seconds"] is not None
                and annotation["end_seconds"] > decoded[rid]["duration_seconds"]
            ):
                issues.append("annotation exceeds fully decoded audio duration")
            if (
                annotation.get("channel") is not None
                and annotation["channel"] >= decoded[rid]["channels"]
            ):
                issues.append("annotation channel exceeds decoded channel count")
        if issues:
            failures.append({"recording_id": rid, "error": "; ".join(issues)})
        elif rid in decoded:
            accepted_annotations.append(annotation)
    duplicate_failure = None
    try:
        edges = duplicate_edges(decoded)
    except ValueError as exc:
        edges = []
        duplicate_failure = str(exc)
        failures.append({"recording_id": "dataset", "error": duplicate_failure})
    splits = group_and_split(records, edges)
    failed_ids = {r["recording_id"] for r in failures}
    failed_groups = {s["group_id"] for s in splits if s["recording_id"] in failed_ids}
    for split in splits:
        if duplicate_failure:
            split.update(split="excluded", reason="incomplete_duplicate_audit")
        elif split["group_id"] in failed_groups:
            split.update(split="excluded", reason="validation_failure_in_group")
    return {
        "schema_version": "1.0.0",
        "release_ready": False,
        "release_note": (
            "QC only: rights, label review and release authorization "
            "remain separate gates"
        ),
        "inventory_bytes": ledger["actual_bytes"],
        "cap_bytes": ledger["cap_bytes"],
        "recordings": results,
        "annotations": accepted_annotations,
        "failures": failures,
        "duplicate_edges": edges,
        "splits": splits,
        "split_counts": dict(collections.Counter(r["split"] for r in splits)),
        "decoded_seconds": sum(r["duration_seconds"] for r in decoded.values()),
    }


def retain_report(report, inventory, relative, max_bytes=1_000_000):
    data = (
        json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()
    if len(data) > max_bytes:
        raise ValueError("QC report exceeds reserved report allowance")
    return inventory.put(
        relative, [data], len(data), {"kind": "quality_control_report"}
    )
