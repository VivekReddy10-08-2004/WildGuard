"""Tests for wildlife audio manifest structural validation."""

from scripts.validate_wildlife_audio_manifest import validate_record


def example():
    return {
        "recording_id": "example-1", "source": "example", "source_url": "https://example.org/1",
        "audio_path": "clips/one.wav", "license_id": None, "license_verified": False,
        "taxon": "mammal", "scientific_name": None, "region": "North America",
        "annotation_type": "clip", "annotation_method": "unknown", "split": "unassigned",
    }


def test_valid_example():
    assert validate_record(example()) == []


def test_rejects_path_traversal():
    record = example()
    record["audio_path"] = "../outside.wav"
    assert any("escape root" in e for e in validate_record(record))


def test_rejects_bad_event():
    record = example()
    record["annotation_type"] = "event"
    record["events"] = [{"start_seconds": 5, "end_seconds": 2, "label": "wolf"}]
    assert any("time bounds" in e for e in validate_record(record))


def test_rejects_unverified_license_claim():
    record = example()
    record["license_verified"] = True
    assert any("license_id" in e for e in validate_record(record))
