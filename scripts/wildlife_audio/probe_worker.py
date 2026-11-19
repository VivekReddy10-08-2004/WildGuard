"""Forensic-only native decoder probes; never used as the acceptance backend."""

import hashlib
import json
import sys
from pathlib import Path


def main():
    backend, filename = sys.argv[1:3]
    try:
        if Path(filename).stat().st_size > 10_000_000:
            raise ValueError("auxiliary pilot probe exceeds input bound")
        if backend == "dr_mp3":
            import miniaudio

            decoded = miniaudio.mp3_read_file_s16(filename)
            result = {
                "backend": "dr_mp3/minimp3",
                "version": miniaudio.__version__,
                "sample_rate_hz": decoded.sample_rate,
                "channels": decoded.nchannels,
                "frames": decoded.num_frames,
                "duration_seconds": decoded.duration,
                "pcm_format": "signed16-native-endian",
                "pcm_sha256": hashlib.sha256(decoded.samples.tobytes()).hexdigest(),
            }
        else:
            import soundfile as sf

            from scripts.wildlife_audio.integrity import sequential_blocks

            digest = hashlib.sha256()
            total = 0
            with sf.SoundFile(filename) as audio:
                estimate = audio.frames
                blocks = (
                    audio.blocks(blocksize=8192, dtype="float32", always_2d=True)
                    if backend == "soundfile-blocks"
                    else sequential_blocks(audio)
                )
                for block in blocks:
                    total += len(block)
                    digest.update(block.astype("<f4", copy=False).tobytes())
                result = {
                    "backend": backend,
                    "version": (
                        f"soundfile={sf.__version__};"
                        f"libsndfile={sf.__libsndfile_version__}"
                    ),
                    "header_estimated_frames": estimate,
                    "frames": total,
                    "sample_rate_hz": audio.samplerate,
                    "channels": audio.channels,
                    "duration_seconds": total / audio.samplerate,
                    "pcm_format": "float32-little-endian",
                    "pcm_sha256": digest.hexdigest(),
                }
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
