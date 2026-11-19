"""CLI integration using synthetic files and a local SQLite database only."""

import json
import subprocess
import sys
from pathlib import Path


def test_offline_storage_cli(tmp_path):
    root = tmp_path / "managed"
    for command in ("init", "audit", "recover"):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.wildlife_audio", command, str(root)],
            capture_output=True,
            text=True,
            check=True,
        )
        report = json.loads(result.stdout)
        assert report["actual_bytes"] == 0
        assert report["cap_bytes"] == 30_000_000_000


def test_legacy_cli_malformed_id_reports_error(tmp_path):
    manifest = tmp_path / "malformed.jsonl"
    manifest.write_text(json.dumps({"recording_id": []}) + "\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "scripts/validate_wildlife_audio_manifest.py", str(manifest)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "recording_id must be nonempty" in result.stdout
    assert "Traceback" not in result.stderr


def test_source_registry_and_review_queue_remain_separate():
    registry = json.loads(Path("data/datasets/audio/sources.json").read_text("utf-8"))
    reviews = json.loads(
        Path("data/datasets/audio/source_reviews.json").read_text("utf-8")
    )
    assert len(registry["sources"]) >= 18
    assert len({s["id"] for s in registry["sources"]}) == len(registry["sources"])
    assert reviews["reviews"] == []
