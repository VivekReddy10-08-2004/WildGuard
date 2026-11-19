"""Isolated, bounded full decoding with fatal native diagnostics and real EOF."""

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from scripts.wildlife_audio.mp3 import scan_mp3
from scripts.wildlife_audio.process import run_bounded
from scripts.wildlife_audio.storage import sha256_file


class AudioError(ValueError):
    """Unusable, unsupported, inconsistent or unbounded audio."""


def is_mp3(path):
    with Path(path).open("rb") as stream:
        header = stream.read(12)
    return (
        header[:3] == b"ID3"
        or (len(header) >= 2 and header[0] == 255 and header[1] & 224 == 224)
        or Path(path).suffix.lower() == ".mp3"
    )


def sequential_blocks(audio, blocksize=8192):
    """Use actual returned frames; SoundFile.blocks() trusts estimated lengths."""
    while True:
        block = audio.read(blocksize, dtype="float32", always_2d=True)
        if len(block) == 0:
            break
        yield block


def pcm_blocks(path, max_seconds=3600):
    """Shared PCM source for fingerprints: MP3 always uses the strict backend."""
    if is_mp3(path):
        from scripts.wildlife_audio.ffmpeg import pcm_blocks as ffmpeg_blocks

        yield from ffmpeg_blocks(path, scan_mp3(path, max_seconds))
    else:
        with sf.SoundFile(path) as audio:
            yield from sequential_blocks(audio)


def _measure(blocks, rate, channels, max_seconds):
    digest = hashlib.sha256(
        json.dumps(
            {"version": 2, "sample_rate": rate, "channels": channels}, sort_keys=True
        ).encode()
    )
    raw_digest = hashlib.sha256()
    frames = samples = clipped = silent = 0
    peak = 0.0
    for block in blocks:
        if not np.isfinite(block).all():
            raise AudioError("nonfinite audio samples")
        frames += len(block)
        if frames > rate * max_seconds:
            raise AudioError("decoded stream exceeds duration bound")
        absolute = np.abs(block)
        peak = max(peak, float(absolute.max(initial=0)))
        clipped += int(np.count_nonzero(absolute >= 0.999))
        silent += int(np.count_nonzero(absolute < 1e-6))
        samples += block.size
        data = block.astype("<f4", copy=False).tobytes()
        digest.update(data)
        raw_digest.update(data)
    if frames == 0:
        raise AudioError("empty decoded audio")
    return {
        "frames": frames,
        "duration_seconds": frames / rate,
        "pcm_sha256": digest.hexdigest(),
        "raw_pcm_sha256": raw_digest.hexdigest(),
        "pcm_hash_version": "dimensioned-float32-le-v2",
        "peak": peak,
        "clipped_fraction": clipped / samples,
        "silent_fraction": silent / samples,
        "flags": (["silent"] if peak < 1e-6 else [])
        + (["clipping"] if clipped / samples > 0.01 else []),
    }


def _decode_local(path, max_seconds, max_channels):
    """Worker-only implementation. Public acceptance must inspect its stderr."""
    path = Path(path)
    checksum = sha256_file(path)
    if is_mp3(path):
        import imageio_ffmpeg

        from scripts.wildlife_audio.ffmpeg import pcm_blocks as ffmpeg_blocks

        structure = scan_mp3(path, max_seconds)
        if structure["channels"] > max_channels:
            raise AudioError("invalid or over-limit decoded dimensions")
        diagnostics = {}
        result = _measure(
            ffmpeg_blocks(path, structure, diagnostics),
            structure["sample_rate_hz"],
            structure["channels"],
            max_seconds,
        )
        result.update(
            sample_rate_hz=structure["sample_rate_hz"],
            channels=structure["channels"],
            format="MP3",
            subtype="MPEG_LAYER_III",
            mp3_structure=structure,
            decoder=f"FFmpeg={imageio_ffmpeg.get_ffmpeg_version()};mp3float",
            decoder_diagnostics=diagnostics,
        )
    else:
        with path.open("rb") as stream:
            header = stream.read(12)
        if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
            if int.from_bytes(header[4:8], "little") + 8 > path.stat().st_size:
                raise AudioError("truncated RIFF container")
        with sf.SoundFile(path) as audio:
            if audio.format not in {"WAV", "WAVEX", "FLAC", "OGG", "RF64"}:
                raise AudioError("unsupported container")
            if (
                not 0 < audio.channels <= max_channels
                or not 0 < audio.samplerate <= 768000
                or audio.frames <= 0
                or audio.frames / audio.samplerate > max_seconds
            ):
                raise AudioError("invalid or over-limit decoded dimensions")
            result = _measure(
                sequential_blocks(audio), audio.samplerate, audio.channels, max_seconds
            )
            if result["frames"] != audio.frames:
                raise AudioError("decoded frame count differs from header")
            result.update(
                sample_rate_hz=audio.samplerate,
                channels=audio.channels,
                format=audio.format,
                subtype=audio.subtype,
                decoder=f"soundfile={sf.__version__};libsndfile={sf.__libsndfile_version__}",
            )
    if result["channels"] > max_channels or sha256_file(path) != checksum:
        raise AudioError("audio dimensions invalid or input changed during decode")
    return {"sha256": checksum, "size_bytes": path.stat().st_size, **result}


def checked_worker_result(response):
    stderr = response["stderr"].decode("utf-8", errors="replace")
    if response["timed_out"] or response["overflow"] or stderr:
        raise AudioError(
            f"native decoder diagnostics (exit={response['exit_code']}, "
            f"timeout={response['timed_out']}, overflow={response['overflow']}): "
            f"{stderr}"
        )
    try:
        result = json.loads(response["stdout"])
    except (ValueError, UnicodeDecodeError) as exc:
        raise AudioError("decoder worker returned invalid metadata") from exc
    if response["exit_code"] != 0 or "error" in result:
        raise AudioError(result.get("error", "decoder worker failed"))
    return result


def decode_audio(path, expected_sha256=None, max_seconds=3600, max_channels=8):
    """Reject native stderr even when a library produces samples and returns zero."""
    if (
        isinstance(max_seconds, bool)
        or not isinstance(max_seconds, (int, float))
        or not math.isfinite(max_seconds)
        or max_seconds <= 0
        or type(max_channels) is not int
        or max_channels <= 0
    ):
        raise AudioError("invalid decoder bounds")
    path = Path(path).absolute()
    checksum = sha256_file(path)
    if expected_sha256 is not None and checksum != expected_sha256:
        raise AudioError("encoded SHA-256 mismatch")
    response = run_bounded(
        [
            sys.executable,
            "-m",
            "scripts.wildlife_audio.decode_worker",
            str(path),
            str(max_seconds),
            str(max_channels),
        ],
        timeout=130,
    )
    result = checked_worker_result(response)
    if result["sha256"] != checksum or sha256_file(path) != checksum:
        raise AudioError("input changed during isolated decode")
    return result
