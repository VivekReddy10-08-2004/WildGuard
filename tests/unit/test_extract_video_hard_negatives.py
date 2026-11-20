import pytest

from scripts.extract_video_hard_negatives import sample_frame_indices


def test_sample_frame_indices_includes_reviewed_endpoints() -> None:
    assert sample_frame_indices(
        fps=30.0,
        start_seconds=0.0,
        end_seconds=1.0,
        interval_seconds=0.25,
    ) == [0, 8, 15, 22, 30]


def test_sample_frame_indices_rejects_invalid_interval() -> None:
    with pytest.raises(ValueError, match="positive"):
        sample_frame_indices(
            fps=30.0,
            start_seconds=0.0,
            end_seconds=1.0,
            interval_seconds=0.0,
        )
