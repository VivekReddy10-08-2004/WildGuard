"""Synthetic-only tests: no wildlife labels, audio downloads or network access."""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.validate_wildlife_audio_manifest import validate_record
from scripts.wildlife_audio.manifest import legacy_records
from scripts.wildlife_audio.paths import safe_path
from scripts.wildlife_audio.rights import (
    bundle_redistribution_errors,
    redistribution_errors,
)
from scripts.wildlife_audio.schema import (
    SCHEMA_ROOT,
    validate,
    validate_bundle,
    validate_inventory,
)
from scripts.wildlife_audio.storage import (
    CAP_BYTES,
    BudgetExceeded,
    Inventory,
    InventoryError,
    exclusive_lock,
)

PROVENANCE = {"source_id": "synthetic-test", "source_recording_id": "1"}
HASH = hashlib.sha256(b"abc").hexdigest()


@pytest.mark.parametrize(
    "relative",
    [
        "../x.wav",
        "/x.wav",
        "C:/x.wav",
        "C:x.wav",
        "\\\\host\\x",
        "a\\b.wav",
        "a/../x",
        "a//b",
        "./a",
        "a/",
        "a:b",
        "a\x00b",
        "CON.wav",
        "con",
        "LPT1.flac",
        "a.",
        "a ",
        "a/..",
        "a/?",
    ],
)
def test_reject_unsafe_portable_paths(tmp_path, relative):
    with pytest.raises(ValueError):
        safe_path(tmp_path, relative)


def test_safe_nested_path(tmp_path):
    assert safe_path(tmp_path, "originals/a.flac") == tmp_path / "originals/a.flac"


def test_hard_link_rejected(tmp_path):
    (tmp_path / "a").write_bytes(b"a")
    os.link(tmp_path / "a", tmp_path / "b")
    with pytest.raises(ValueError, match="hard-linked"):
        safe_path(tmp_path, "b")


def test_symlink_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("OS user cannot create symlinks")
    with pytest.raises(ValueError, match="linked"):
        safe_path(tmp_path, "link/a")


def test_junction_rejected(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows junction test")
    outside = tmp_path / "outside"
    outside.mkdir()
    junction = tmp_path / "junction"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    try:
        with pytest.raises(ValueError, match="linked"):
            safe_path(tmp_path, "junction/a")
    finally:
        junction.rmdir()  # Remove only the verified test junction, never its target.


@pytest.mark.parametrize("cap", [0, -1, True, 1.5, CAP_BYTES + 1])
def test_invalid_caps(tmp_path, cap):
    with pytest.raises(ValueError):
        Inventory(tmp_path, cap)


def test_hard_cap_and_all_copies_count(tmp_path):
    inv = Inventory(tmp_path, 6)
    assert inv.put("original/a", [b"abc"], 3, PROVENANCE)["sha256"] == HASH
    inv.put("processed/a", [b"abc"], 3, PROVENANCE)
    assert inv.audit()["actual_bytes"] == 6
    with pytest.raises(BudgetExceeded):
        inv.put("more", [b"x"], 1, PROVENANCE)
    assert not (inv.payload / "more").exists()


def test_unused_reservation_released(tmp_path):
    inv = Inventory(tmp_path, 10)
    inv.put("a", [b"abc"], 10, PROVENANCE)
    assert inv.audit()["available_bytes"] == 7
    with pytest.raises(InventoryError, match="cap differs"):
        Inventory(tmp_path, 11)


def test_stream_cannot_overrun_and_quarantine_is_counted(tmp_path):
    inv = Inventory(tmp_path, 5)
    with pytest.raises(BudgetExceeded):
        inv.put("a", [b"abc", b"def"], 5, PROVENANCE)
    report = inv.audit()
    assert report["actual_bytes"] == 3
    assert report["assets"][0]["state"] == "quarantined"
    assert (inv.payload / "a").read_bytes() == b"abc"


def test_source_checksum_and_no_overwrite(tmp_path):
    inv = Inventory(tmp_path, 10)
    with pytest.raises(InventoryError, match="checksum"):
        inv.put("a", [b"abc"], 3, PROVENANCE, "0" * 64)
    assert inv.audit()["actual_bytes"] == 3
    with pytest.raises(InventoryError, match="already"):
        inv.put("a", [], 0, PROVENANCE)
    with pytest.raises(InventoryError, match="already"):
        inv.put("A", [], 0, PROVENANCE)


def test_generator_failure_retains_partial(tmp_path):
    def broken():
        yield b"ab"
        raise RuntimeError("connection lost")

    inv = Inventory(tmp_path, 10)
    with pytest.raises(RuntimeError, match="connection lost"):
        inv.put("archive.zip", broken(), 10, PROVENANCE)
    assert inv.audit()["actual_bytes"] == 2


@pytest.mark.parametrize(
    "change", ["untracked", "resize", "checksum", "missing", "control"]
)
def test_audit_fails_closed(tmp_path, change):
    inv = Inventory(tmp_path, 10)
    inv.put("a", [b"abc"], 3, PROVENANCE)
    if change == "untracked":
        (inv.payload / "unknown").write_bytes(b"x")
    elif change == "resize":
        (inv.payload / "a").write_bytes(b"longer")
    elif change == "checksum":
        (inv.payload / "a").write_bytes(b"xyz")
    elif change == "missing":
        (inv.payload / "a").unlink()
    else:
        (inv.state / "hidden.wav").write_bytes(b"x")
    with pytest.raises(InventoryError):
        inv.put("b", [], 0, PROVENANCE)


def test_single_writer_lock(tmp_path):
    inv = Inventory(tmp_path, 10)
    with exclusive_lock(inv.state / "inventory.lock"), pytest.raises(OSError):
        inv.put("a", [], 0, PROVENANCE)


def test_real_process_crash_and_recovery(tmp_path):
    inv = Inventory(tmp_path, 200_000)
    code = """
import os, sys
from pathlib import Path
from scripts.wildlife_audio.storage import Inventory
def chunks():
    yield b'x' * 100000
    os._exit(17)
Inventory(Path(sys.argv[1]), 200000).put('partial', chunks(), 150000, {'source':'test'})
"""
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], check=False)
    assert result.returncode == 17
    with pytest.raises(InventoryError, match="recover"):
        inv.audit()
    assert inv.recover() == ["partial"]
    report = inv.audit()
    assert report["assets"][0]["state"] == "quarantined"
    assert report["actual_bytes"] == 100_000
    assert report["available_bytes"] == 100_000
    assert inv.recover() == []


def test_recover_missing_pending_file(tmp_path):
    inv = Inventory(tmp_path, 10)
    with sqlite3.connect(inv.state / "inventory.sqlite3") as db:
        db.execute(
            "INSERT INTO assets VALUES ('missing','pending',10,0,NULL,NULL,'{}')"
        )
    assert inv.recover() == ["missing"]
    assert inv.audit()["actual_bytes"] == 0
    assert (inv.payload / "missing").exists()


def test_oversized_pending_is_not_silently_accepted(tmp_path):
    inv = Inventory(tmp_path, 10)
    with sqlite3.connect(inv.state / "inventory.sqlite3") as db:
        db.execute("INSERT INTO assets VALUES ('partial','pending',1,0,NULL,NULL,'{}')")
    (inv.payload / "partial").write_bytes(b"xx")
    with pytest.raises(InventoryError, match="reservation"):
        inv.recover()


def rights_example():
    return {
        "schema_version": "1.0.0",
        "review_id": "review-1",
        "source_id": "source",
        "source_recording_id": "1",
        "asset_sha256": HASH,
        "status": "approved",
        "license_id": "CC-BY-4.0",
        "license_url": "https://example.org/license",
        "commercial_use": True,
        "training": True,
        "redistribution": True,
        "derivatives": True,
        "attribution": "Example recordist",
        "conditions": [],
        "reviewed_by": "reviewer",
        "reviewed_at": "2026-11-19T00:00:00Z",
        "evidence": [
            {
                "url": "https://example.org/1",
                "sha256": HASH,
                "retrieved_at": "2026-11-19T00:00:00Z",
            }
        ],
    }


def test_review_must_match_asset():
    review = rights_example()
    assert redistribution_errors(review, "source", "1", HASH) == []
    assert redistribution_errors(review, "source", "2", HASH)
    assert redistribution_errors(review, "source", "1", "0" * 64)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "pending"),
        ("license_id", "CC-BY-NC-4.0"),
        ("license_id", "CC-BY-ND-4.0"),
        ("evidence", []),
        ("reviewed_by", None),
        ("commercial_use", False),
        ("training", None),
        ("redistribution", False),
        ("derivatives", False),
        ("license_id", None),
    ],
)
def test_unclear_or_restrictive_rights_blocked(field, value):
    review = rights_example()
    review[field] = value
    assert redistribution_errors(review, "source", "1", HASH)


def test_registry_claim_is_not_recording_review():
    registry = json.loads(Path("data/datasets/audio/sources.json").read_text("utf-8"))
    assert registry["audio_storage_cap_bytes"] == CAP_BYTES
    for source in registry["sources"]:
        assert redistribution_errors(source, source["id"], "1", HASH)


def bundle_example():
    return {
        "provenance": [
            {
                "schema_version": "1.0.0",
                "provenance_id": "p",
                "source_id": "source",
                "source_recording_id": "1",
                "source_release": None,
                "source_url": "https://example.org/1",
                "retrieved_at": "2026-11-19T00:00:00Z",
                "metadata_sha256": HASH,
                "original_metadata": {"source_label": "unchanged"},
                "code_commit": None,
            }
        ],
        "recording": [
            {
                "schema_version": "1.0.0",
                "recording_id": "r",
                "source_id": "source",
                "source_recording_id": "1",
                "provenance_id": "p",
                "rights_review_id": "review-1",
                "original_labels": ["unchanged"],
                "original_annotations": None,
                "taxon": "unknown",
                "scientific_name": None,
                "taxon_id": None,
                "taxonomy_version": None,
                "geography": {
                    "country_code": None,
                    "region": None,
                    "north_america_verified": False,
                    "evidence_url": None,
                },
                "context": "unknown",
                "site_id": None,
                "session_id": None,
                "recordist_id": None,
                "recorded_at": None,
            }
        ],
        "asset": [
            {
                "schema_version": "1.0.0",
                "asset_id": "a",
                "recording_id": "r",
                "parent_asset_id": None,
                "path": "originals/test.wav",
                "kind": "original",
                "size_bytes": 3,
                "sha256": HASH,
                "duration_seconds": 2.0,
                "sample_rate_hz": 48000,
                "channels": 1,
                "codec": "PCM_16",
                "transformation": None,
                "source_checksum": None,
            }
        ],
        "annotation": [
            {
                "schema_version": "1.0.0",
                "annotation_id": "n",
                "recording_id": "r",
                "asset_id": "a",
                "annotation_type": "window",
                "label": "unchanged",
                "taxon_id": None,
                "start_seconds": 0,
                "end_seconds": 2,
                "annotation_method": "unknown",
                "verification": "unverified",
                "annotator_id": None,
                "confidence": None,
                "original_annotation": {"tag": "unchanged"},
                "provenance_id": "p",
            }
        ],
        "rights": [rights_example()],
        "split": [
            {
                "schema_version": "1.0.0",
                "recording_id": "r",
                "group_id": "g",
                "split": "unassigned",
                "reason": None,
                "seed": 42,
                "algorithm_version": "pending",
                "config_sha256": HASH,
            }
        ],
    }


def test_schema_definitions_are_valid():
    for file in SCHEMA_ROOT.glob("*.json"):
        Draft202012Validator.check_schema(json.loads(file.read_text("utf-8")))


def test_valid_bundle_preserves_raw_annotations():
    bundle = bundle_example()
    before = json.dumps(bundle, sort_keys=True)
    assert validate_bundle(bundle, {"source"}) == []
    assert json.dumps(bundle, sort_keys=True) == before


@pytest.mark.parametrize(
    "kind,field,value",
    [
        ("recording", "schema_version", "2.0.0"),
        ("asset", "size_bytes", True),
        ("asset", "path", "C:/escape.wav"),
        ("asset", "sha256", "bad"),
        ("asset", "duration_seconds", float("nan")),
        ("asset", "kind", "processed"),
        ("annotation", "end_seconds", 0),
        ("annotation", "confidence", 2),
        ("annotation", "annotation_type", "clip"),
        ("annotation", "annotation_method", "invented"),
        ("split", "split", "validation"),
        ("provenance", "retrieved_at", "yesterday"),
    ],
)
def test_bad_schema_records(kind, field, value):
    record = bundle_example()[kind][0]
    record[field] = value
    assert validate(kind, record)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_ref",
        "duration",
        "duplicate",
        "source",
        "lineage",
        "provenance",
        "rights",
        "leakage",
    ],
)
def test_bundle_references_and_leakage(mutation):
    bundle = bundle_example()
    if mutation == "missing_ref":
        bundle["annotation"][0]["asset_id"] = "absent"
    elif mutation == "duration":
        bundle["annotation"][0]["end_seconds"] = 3
    elif mutation == "duplicate":
        bundle["asset"].append(bundle["asset"][0].copy())
    elif mutation == "source":
        bundle["provenance"][0]["source_id"] = "absent"
    elif mutation == "lineage":
        bundle["asset"][0]["parent_asset_id"] = "a"
    elif mutation == "provenance":
        bundle["recording"][0]["provenance_id"] = "absent"
    elif mutation == "rights":
        bundle["rights"][0]["source_recording_id"] = "other"
    else:
        bundle["recording"].append({**bundle["recording"][0], "recording_id": "r2"})
        bundle["split"][0]["split"] = "train"
        bundle["split"].append(
            {**bundle["split"][0], "recording_id": "r2", "split": "test"}
        )
    assert validate_bundle(bundle, {"source"})


@pytest.mark.parametrize(
    "field,value",
    [
        ("recording_id", []),
        ("split", []),
        ("annotation_type", {}),
        ("duration_seconds", True),
        ("duration_seconds", float("inf")),
    ],
)
def test_legacy_validator_malformed_input(field, value):
    record = {
        "recording_id": "a",
        "source": "source",
        "source_url": "https://example.org",
        "audio_path": "a.wav",
        "license_id": None,
        "license_verified": False,
        "taxon": "unknown",
        "scientific_name": None,
        "region": None,
        "annotation_type": "unlabeled",
        "annotation_method": "unknown",
        "split": "unassigned",
    }
    record[field] = value
    assert validate_record(record)


def test_legacy_export_does_not_invent_events():
    bundle = bundle_example()
    output = legacy_records(bundle, {"source"})
    assert validate_record(output[0]) == []
    assert output[0]["events"] == []
    assert output[0]["original_annotation_records"] == bundle["annotation"]


def test_legacy_export_preserves_event_times():
    bundle = bundle_example()
    bundle["annotation"][0]["annotation_type"] = "event"
    assert legacy_records(bundle, {"source"})[0]["events"] == [
        {"start_seconds": 0, "end_seconds": 2, "label": "unchanged"}
    ]


def test_legacy_export_rejects_ambiguous_original():
    bundle = bundle_example()
    bundle["asset"] = []
    bundle["annotation"] = []
    with pytest.raises(ValueError, match="selected original"):
        legacy_records(bundle, {"source"})


def test_commercial_bundle_gate():
    bundle = bundle_example()
    assert bundle_redistribution_errors(bundle) == []
    bundle["asset"][0]["sha256"] = "0" * 64
    assert bundle_redistribution_errors(bundle)
    bundle["rights"] = []
    assert bundle_redistribution_errors(bundle)


@pytest.mark.parametrize("tables", [None, [], {"recording": None}, {"mystery": []}])
def test_bad_table_container(tables):
    assert validate_bundle(tables, set())


def test_exact_decimal_cap_constant(tmp_path):
    inv = Inventory(tmp_path)
    assert inv.audit()["available_bytes"] == 30_000_000_000
    with pytest.raises(BudgetExceeded):
        inv.put("too-big", [], 30_000_000_001, PROVENANCE)
    assert list(inv.payload.iterdir()) == []


def test_inventory_schema_version_is_checked(tmp_path):
    inv = Inventory(tmp_path, 10)
    with sqlite3.connect(inv.state / "inventory.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        db.execute("PRAGMA user_version=99")
    with pytest.raises(InventoryError, match="schema version"):
        Inventory(tmp_path, 10)


def test_bundle_matches_measured_inventory(tmp_path):
    inv = Inventory(tmp_path, 10)
    bundle = bundle_example()
    asset = bundle["asset"][0]
    assert validate_inventory(bundle, inv)
    inv.put(asset["path"], [b"abc"], 3, PROVENANCE, HASH)
    assert validate_inventory(bundle, inv) == []
    asset["size_bytes"] = 4
    assert validate_inventory(bundle, inv)


def test_valid_processed_lineage():
    bundle = bundle_example()
    derived = {
        **bundle["asset"][0],
        "asset_id": "processed",
        "path": "derived/a.wav",
        "kind": "processed",
        "parent_asset_id": "a",
        "transformation": {"method": "test-only"},
    }
    bundle["asset"].append(derived)
    assert validate_bundle(bundle, {"source"}) == []
    bundle["asset"][0]["kind"] = "archive"
    assert validate_bundle(bundle, {"source"})
