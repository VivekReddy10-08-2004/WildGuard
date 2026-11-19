"""Offline JSON Schema validation and cross-table checks."""

import json
import math
import re
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from scripts.wildlife_audio.paths import safe_path

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "data/datasets/audio/schema"
IDENTIFIERS = {
    "recording": "recording_id",
    "asset": "asset_id",
    "annotation": "annotation_id",
    "split": "recording_id",
    "rights": "review_id",
    "provenance": "provenance_id",
}
FORMATS = FormatChecker()


@FORMATS.checks("date-time", raises=(ValueError, TypeError))
def is_datetime(value):
    """Require RFC3339 timestamps even without jsonschema's optional extras."""
    if not isinstance(value, str):
        return True
    if not re.fullmatch(
        r"\d{4}-\d\d-\d\d[Tt]\d\d:\d\d:\d\d(?:\.\d+)?(?:[Zz]|[+-]\d\d:\d\d)", value
    ):
        return False
    return datetime.fromisoformat(value.upper()).tzinfo is not None


def validate(kind, record):
    """Return errors without coercing source metadata or fetching remote schemas."""
    if kind not in IDENTIFIERS:
        raise ValueError("unknown schema kind")
    schema = json.loads((SCHEMA_ROOT / f"{kind}.schema.json").read_text("utf-8"))
    validator = Draft202012Validator(schema, format_checker=FORMATS)
    errors = [
        f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
        for e in validator.iter_errors(record)
    ]

    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            errors.append("nonfinite JSON number")
        elif isinstance(value, dict):
            for child in value.values():
                finite(child)
        elif isinstance(value, list):
            for child in value:
                finite(child)

    finite(record)
    if errors:
        return errors
    if kind == "asset":
        try:
            safe_path(Path.cwd(), record["path"])
        except ValueError as exc:
            errors.append(str(exc))
        if record["kind"] == "processed" and (
            not record["parent_asset_id"] or not record["transformation"]
        ):
            errors.append("processed asset requires parent and transformation")
        if record["kind"] == "original" and (
            record["parent_asset_id"] is not None
            or record["transformation"] is not None
        ):
            errors.append("original asset cannot claim a parent or transformation")
    if kind == "annotation" and record["annotation_type"] in {"event", "window"}:
        if record["end_seconds"] <= record["start_seconds"]:
            errors.append("annotation end must follow start")
    if (
        kind == "annotation"
        and record.get("focal_present") is False
        and record["taxon_id"] is not None
    ):
        errors.append("focal rejection must not assign a positive taxon ID")
    return errors


def validate_inventory(tables, inventory):
    """Match declared assets to measured, ready inventory entries after full audit."""
    measured = {row["path"]: row for row in inventory.audit()["assets"]}
    errors = []
    for asset in tables.get("asset", []):
        row = measured.get(asset["path"])
        if not row or row["state"] != "ready":
            errors.append(f"{asset['asset_id']}: asset is not ready in inventory")
        elif (row["size"], row["sha256"]) != (asset["size_bytes"], asset["sha256"]):
            errors.append(
                f"{asset['asset_id']}: manifest differs from measured inventory"
            )
    return errors


def validate_bundle(tables, source_ids):
    """Check IDs/references, true asset durations, group splits and lineage cycles."""
    errors = []
    if not isinstance(tables, dict):
        return ["bundle must be an object"]
    if set(tables) - IDENTIFIERS.keys():
        errors.append("unknown table name")
    for kind in IDENTIFIERS:
        if not isinstance(tables.get(kind, []), list):
            errors.append(f"{kind} table must be an array")
    if errors:
        return errors
    index = {}
    for kind, key in IDENTIFIERS.items():
        index[kind] = {}
        for n, record in enumerate(tables.get(kind, [])):
            issues = validate(kind, record)
            errors.extend(f"{kind}[{n}]: {e}" for e in issues)
            if issues:
                continue
            rid = record[key]
            if rid in index[kind]:
                errors.append(f"duplicate {kind} ID: {rid}")
            index[kind][rid] = record
    if errors:
        return errors
    for kind in ("recording", "rights", "provenance"):
        for r in index[kind].values():
            if r["source_id"] not in source_ids:
                errors.append(f"unknown registry source: {r['source_id']}")
    for r in index["recording"].values():
        p = index["provenance"].get(r["provenance_id"])
        if not p or (p["source_id"], p["source_recording_id"]) != (
            r["source_id"],
            r["source_recording_id"],
        ):
            errors.append("recording provenance missing or inconsistent")
        review_id = r["rights_review_id"]
        if review_id is not None:
            review = index["rights"].get(review_id)
            if not review or (review["source_id"], review["source_recording_id"]) != (
                r["source_id"],
                r["source_recording_id"],
            ):
                errors.append("recording rights review missing or inconsistent")
    paths = set()
    for a in index["asset"].values():
        if a["path"].casefold() in paths:
            errors.append("duplicate asset path")
        paths.add(a["path"].casefold())
        if a["recording_id"] not in index["recording"]:
            errors.append("asset recording missing")
        visited = {a["asset_id"]}
        parent = a["parent_asset_id"]
        root_asset = a
        while parent:
            if parent in visited:
                errors.append("asset lineage cycle")
                break
            visited.add(parent)
            ancestor = index["asset"].get(parent)
            if not ancestor or ancestor["recording_id"] != a["recording_id"]:
                errors.append("parent asset missing or belongs to another recording")
                break
            root_asset = ancestor
            parent = ancestor["parent_asset_id"]
        if a["kind"] == "processed" and root_asset["kind"] != "original":
            errors.append("processed asset lineage must terminate at an original")
    for a in index["annotation"].values():
        asset = index["asset"].get(a["asset_id"])
        if not asset or asset["recording_id"] != a["recording_id"]:
            errors.append("annotation asset/recording mismatch")
        elif a["annotation_type"] in {"event", "window"}:
            if (
                asset["duration_seconds"] is None
                or a["end_seconds"] > asset["duration_seconds"]
            ):
                errors.append("annotation exceeds known asset duration")
        if a["provenance_id"] not in index["provenance"]:
            errors.append("annotation provenance missing")
    groups = {}
    for s in index["split"].values():
        if s["recording_id"] not in index["recording"]:
            errors.append("split recording missing")
        if s["split"] in {"train", "val", "test"}:
            previous = groups.setdefault(s["group_id"], s["split"])
            if previous != s["split"]:
                errors.append("group leaks across splits")
    return errors
