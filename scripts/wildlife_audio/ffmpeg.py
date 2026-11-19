"""Strict MP3 decoding to memory pipes; no fallback, resync or persistent PCM."""

import re
import subprocess
import threading

import imageio_ffmpeg
import numpy as np

STRICT_FLAGS = "crccheck+bitstream+explode"
ERROR_PATTERN = re.compile(
    r"error|failed|invalid|corrupt|CRC mismatch|overread|bits_left|"
    r"conceal|underflow|overrun|backstep",
    re.IGNORECASE,
)


def diagnostic_errors(stderr):
    """Preserve the entire log; error/concealment diagnostics are fatal even at rc=0."""
    return [line for line in stderr.splitlines() if ERROR_PATTERN.search(line)]


def command(path):
    return [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-nostdin",
        "-nostats",
        "-v",
        "info",
        "-xerror",
        "-max_error_rate",
        "0",
        "-err_detect",
        STRICT_FLAGS,
        "-protocol_whitelist",
        "file,pipe",
        "-f",
        "mp3",
        "-c:a",
        "mp3float",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-c:a",
        "pcm_f32le",
        "-f",
        "f32le",
        "pipe:1",
    ]


def pcm_blocks(path, structure, diagnostics=None, timeout=120):
    """Yield native-rate float32 blocks; final process/log checks must complete."""
    process = subprocess.Popen(
        command(path),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    log = bytearray()
    overflow = []
    expired = []

    def stderr_reader():
        while chunk := process.stderr.read(4096):
            remaining = 131072 - len(log)
            log.extend(chunk[: max(0, remaining)])
            if len(chunk) > remaining:
                overflow.append(True)
                process.kill()
                break

    def stop():
        expired.append(True)
        process.kill()

    reader = threading.Thread(target=stderr_reader)
    timer = threading.Timer(timeout, stop)
    timer.daemon = True
    reader.start()
    timer.start()
    total = 0
    width = structure["channels"] * 4
    maximum = structure["encoded_samples"] * width
    try:
        while chunk := process.stdout.read(32768):
            total += len(chunk)
            if total > maximum or len(chunk) % width:
                raise ValueError(
                    "FFmpeg output exceeds framing bound or has partial samples"
                )
            block = np.frombuffer(chunk, dtype="<f4").reshape(-1, structure["channels"])
            if not np.isfinite(block).all():
                raise ValueError("nonfinite decoded MP3 samples")
            yield block
        code = process.wait()
        reader.join()
        stderr = log.decode("utf-8", errors="replace")
        info = {
            "command": command(path),
            "exit_code": code,
            "stderr": stderr,
            "error_lines": diagnostic_errors(stderr),
            "timed_out": bool(expired),
            "stderr_overflow": bool(overflow),
            "pcm_bytes": total,
            "pcm_format": "float32-little-endian",
        }
        if diagnostics is not None:
            diagnostics.update(info)
        if expired or overflow or code != 0 or info["error_lines"]:
            raise ValueError(f"strict FFmpeg decode failed (exit={code}): {stderr}")
        if total == 0:
            raise ValueError("MP3 decoder produced no samples")
        frames = total // width
        if (
            not structure["has_timing_header"]
            and frames != structure["encoded_samples"]
        ):
            raise ValueError("MP3 decoder did not consume every framed sample")
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.wait()
        reader.join()
        process.stdout.close()
        process.stderr.close()
