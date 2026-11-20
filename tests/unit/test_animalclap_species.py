from pathlib import Path

import numpy as np
import pytest

from model_services.audio.animalclap.app import resolve_audio_path
from model_services.audio.animalclap.infer_species import make_windows, read_manifest
from model_services.audio.animalclap.runtime import format_analysis


def test_make_windows_pads_and_overlaps() -> None:
    windows = make_windows(np.arange(12, dtype=np.float32), 10, 5)
    assert [(start, end) for start, end, _ in windows] == [(0, 10), (5, 12)]
    assert windows[-1][2].shape == (10,)
    assert np.all(windows[-1][2][7:] == 0)


def test_read_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "data.csv"
    manifest.write_text("species,audio_file\ncoyote,clip.ogg\n", encoding="utf-8")
    assert read_manifest(manifest) == [{"species": "coyote", "audio_file": "clip.ogg"}]


def test_format_analysis_uses_cautious_possible_species_wording() -> None:
    result = format_analysis(
        ("coyote", "wolf"),
        np.asarray([0.7, 0.5], dtype=np.float32),
    )

    assert result.possible_species == "coyote"
    assert result.score_margin == 0.2
    assert result.message == (
        "Possible wildlife sound detected — possible species: coyote"
    )


def test_audio_path_cannot_escape_evidence_root(tmp_path: Path) -> None:
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    outside = tmp_path / "outside.ogg"
    outside.touch()

    with pytest.raises(ValueError, match="inside the evidence"):
        resolve_audio_path(str(outside), evidence_root)
