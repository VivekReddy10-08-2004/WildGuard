"""Validate the real metadata-only blocked pilot; no audio/network dependency."""

import json
from pathlib import Path

from scripts.validate_wildlife_audio_manifest import validate_record
from scripts.wildlife_audio.rights import bundle_redistribution_errors
from scripts.wildlife_audio.schema import validate_bundle

ROOT = Path("data/datasets/audio/releases/nps-pilot-2026-11-19")


def read(name):
    return json.loads((ROOT / name).read_text("utf-8"))


def test_pilot_is_blocked_and_within_authorized_budget():
    summary = read("summary.json")
    assert summary["status"] == "blocked_native_decoder_errors"
    assert summary["release_ready"] is False
    assert summary["recording_count"] == 6
    assert summary["strict_decode_passed_count"] == 4
    assert summary["quarantined_count"] == 2
    assert summary["original_audio_bytes"] == 2_193_880
    assert summary["retained_metadata_bytes"] <= 1_000_000
    assert summary["additional_retained_payload_bytes"] == (
        summary["original_audio_bytes"] + summary["retained_metadata_bytes"]
    )
    assert summary["additional_retained_payload_bytes"] <= 3_193_880
    assert summary["persistent_derived_audio_bytes"] == 0


def test_native_decoder_errors_are_not_accepted_as_success():
    diagnostics = read("strict_decoder_diagnostics.json")
    bad = [r for r in diagnostics["files"] if not r["strict_decode_passed"]]
    assert {r["source_label"] for r in bad} == {"Elk bugle", "Alligator"}
    assert all("dequantization failed" in r["native_stderr"] for r in bad)
    # This real incident proves exit-code-only validation is insufficient.
    assert all(r["child_exit_code"] == 0 for r in bad)
    qc = read("qc.json")
    assert qc["all_full_decodes_passed"] is False
    assert len(qc["expected_inventory_acceptance_errors"]) == 2


def test_real_bundle_preserves_valid_metadata_and_unknown_labels():
    bundle = read("bundle.json")
    registry = json.loads(Path("data/datasets/audio/sources.json").read_text("utf-8"))
    assert validate_bundle(bundle, {r["id"] for r in registry["sources"]}) == []
    assert bundle_redistribution_errors(bundle) == []
    assert all(a["annotation_type"] == "clip" for a in bundle["annotation"])
    assert all(a["verification"] == "unverified" for a in bundle["annotation"])
    assert all(a["confidence"] is None for a in bundle["annotation"])
    assert all(r["recorded_at"] is None for r in bundle["recording"])
    assert {r["split"] for r in bundle["split"]} == {"unassigned", "excluded"}
    for row in (ROOT / "legacy_manifest.jsonl").read_text("utf-8").splitlines():
        assert validate_record(json.loads(row)) == []


def test_only_exact_approved_sources_and_originals_are_manifested():
    authorization = read("authorization.json")
    receipts = read("receipts.json")["files"]
    assert {(r["url"], r["actual_bytes"]) for r in receipts} == {
        (r["url"], r["expected_bytes"]) for r in authorization["approved_urls"]
    }
    assert sum(r["actual_bytes"] for r in receipts) == 2_193_880
    assert len({r["sha256"] for r in receipts}) == 6
    assert all(a["kind"] == "original" for a in read("bundle.json")["asset"])
    assert all(p.suffix in {".json", ".jsonl", ".md"} for p in ROOT.iterdir())
