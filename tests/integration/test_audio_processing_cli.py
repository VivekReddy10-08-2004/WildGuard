"""Exercise the offline processing command without any audio acquisition."""

import json
import subprocess
import sys

import numpy as np
import soundfile as sf

from scripts.wildlife_audio.storage import Inventory


def test_processing_cli_synthetic(tmp_path):
    root = tmp_path / "inventory"
    file = tmp_path / "signal.wav"
    sf.write(file, np.sin(np.arange(32000) * 0.2) * 0.2, 16000)
    data = file.read_bytes()
    Inventory(root).put(
        "original/synthetic.wav", [data], len(data), {"source": "synthetic-test"}
    )
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "recordings": [
                    {
                        "recording_id": "synthetic",
                        "path": "original/synthetic.wav",
                        "source_id": "synthetic",
                        "source_recording_id": "synthetic",
                        "original_labels": [],
                        "site_id": None,
                        "session_id": None,
                        "recordist_id": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.wildlife_audio",
            "analyze",
            str(root),
            str(catalog),
            "--save-relative",
            "reports/qc.json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["failures"] == []
    assert report["splits"][0]["split"] == "unassigned"
    assert (root / "payload/reports/qc.json").is_file()
