"""Fully decode supported audio without retaining a processed audio copy."""

import hashlib
import json
import math

import numpy as np
import soundfile as sf

from scripts.wildlife_audio.storage import sha256_file


class AudioError(ValueError):
    """Unusable, unsupported, inconsistent or unbounded audio."""


def decode_audio(path, expected_sha256=None, max_seconds=3600, max_channels=8):
    """Read every frame; failures never become accepted labels or audio assets.

    libsndfile supports WAV/FLAC/OGG/MP3 here; unsupported codecs (e.g. AAC) fail.
    Canonical PCM hashes are decoder-version-sensitive for lossy codecs.
    """
    if (
        isinstance(max_seconds, bool)
        or not isinstance(max_seconds, (int, float))
        or not math.isfinite(max_seconds)
        or max_seconds <= 0
        or type(max_channels) is not int
        or max_channels <= 0
    ):
        raise AudioError("invalid decoder bounds")
    checksum = sha256_file(path)
    if expected_sha256 is not None and checksum != expected_sha256:
        raise AudioError("encoded SHA-256 mismatch")
    with path.open("rb") as stream:
        header = stream.read(12)
    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        if int.from_bytes(header[4:8], "little") + 8 > path.stat().st_size:
            raise AudioError("truncated RIFF container")
    try:
        with sf.SoundFile(path) as audio:
            if audio.format not in {"WAV", "WAVEX", "FLAC", "OGG", "MP3", "RF64"}:
                raise AudioError("unsupported container")
            if (
                not 0 < audio.channels <= max_channels
                or not 0 < audio.samplerate <= 768_000
                or audio.frames <= 0
                or audio.frames / audio.samplerate > max_seconds
            ):
                raise AudioError("invalid or over-limit decoded dimensions")
            pcm = hashlib.sha256(
                json.dumps(
                    {
                        "version": 1,
                        "sample_rate": audio.samplerate,
                        "channels": audio.channels,
                    },
                    sort_keys=True,
                ).encode()
            )
            total = clipped = silent = samples = 0
            peak = 0.0
            for block in audio.blocks(blocksize=8192, dtype="float32", always_2d=True):
                if not np.isfinite(block).all():
                    raise AudioError("nonfinite audio samples")
                total += len(block)
                if total > audio.samplerate * max_seconds:
                    raise AudioError("decoded stream exceeds duration bound")
                absolute = np.abs(block)
                peak = max(peak, float(absolute.max(initial=0)))
                clipped += int(np.count_nonzero(absolute >= 0.999))
                silent += int(np.count_nonzero(absolute < 1e-6))
                samples += block.size
                pcm.update(block.astype("<f4", copy=False).tobytes())
            if total != audio.frames:
                raise AudioError("decoded frame count differs from header")
            return {
                "sha256": checksum,
                "size_bytes": path.stat().st_size,
                "pcm_sha256": pcm.hexdigest(),
                "frames": total,
                "duration_seconds": total / audio.samplerate,
                "sample_rate_hz": audio.samplerate,
                "channels": audio.channels,
                "format": audio.format,
                "subtype": audio.subtype,
                "peak": peak,
                "clipped_fraction": clipped / samples,
                "silent_fraction": silent / samples,
                "decoder": (
                    f"soundfile={sf.__version__};libsndfile={sf.__libsndfile_version__}"
                ),
                "flags": (["silent"] if peak < 1e-6 else [])
                + (["clipping"] if clipped / samples > 0.01 else []),
            }
    except (sf.LibsndfileError, RuntimeError) as exc:
        raise AudioError(f"full decode failed: {exc}") from exc
