from pathlib import Path

import numpy as np

from model_services.audio.animalclap.infer_species import make_windows, read_manifest


def test_make_windows_pads_and_overlaps() -> None:
    windows = make_windows(np.arange(12, dtype=np.float32), 10, 5)
    assert [(start, end) for start, end, _ in windows] == [(0, 10), (5, 12)]
    assert windows[-1][2].shape == (10,)
    assert np.all(windows[-1][2][7:] == 0)


def test_read_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "data.csv"
    manifest.write_text("species,audio_file\ncoyote,clip.ogg\n", encoding="utf-8")
    assert read_manifest(manifest) == [{"species": "coyote", "audio_file": "clip.ogg"}]
