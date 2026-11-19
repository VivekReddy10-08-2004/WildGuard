"""Generated corruption fixtures and native-stderr regressions; no source audio."""

import hashlib
import json
import sys

import numpy as np
import pytest

from scripts.wildlife_audio.diagnostics import (
    apply_retained_diagnosis,
    consensus,
    retain_diagnosis,
)
from scripts.wildlife_audio.ffmpeg import diagnostic_errors
from scripts.wildlife_audio.integrity import (
    AudioError,
    checked_worker_result,
    decode_audio,
    sequential_blocks,
)
from scripts.wildlife_audio.mp3 import crc16, scan_mp3
from scripts.wildlife_audio.process import run_bounded
from scripts.wildlife_audio.storage import Inventory, InventoryError


def frame(side=None):
    header = bytes.fromhex("fffa90c0")  # synthetic MPEG-1 Layer III, mono, CRC
    side = bytes(17) if side is None else side
    crc = crc16(header[2:] + side).to_bytes(2, "big")
    return header + crc + side + bytes(417 - 4 - 2 - 17)


def synthetic_mp3(tmp_path):
    file = tmp_path / "synthetic.mp3"
    # Legal ID3 padding, no audio data copied from any source recording.
    file.write_bytes(b"ID3\x03\x00\x00\x00\x00\x1f\x76" + bytes(4086) + frame() * 10)
    return file


def test_frame_scanner_and_real_decode_ignore_metadata_duration_estimates(tmp_path):
    file = synthetic_mp3(tmp_path)
    structure = scan_mp3(file)
    assert structure["frame_count"] == structure["protected_frames"] == 10
    assert structure["audio_start_byte"] == 4096
    assert structure["encoded_samples"] == 11520
    decoded = decode_audio(file)
    assert decoded["frames"] == 11520
    assert decoded["duration_seconds"] == 11520 / 44100
    assert decoded["decoder_diagnostics"]["exit_code"] == 0
    assert decoded["decoder_diagnostics"]["error_lines"] == []


@pytest.mark.parametrize(
    "damage",
    ["crc", "header", "truncated", "junk", "reservoir", "big_values", "part_bits"],
)
def test_corrupt_mp3_rejected_before_acceptance(tmp_path, damage):
    file = synthetic_mp3(tmp_path)
    data = bytearray(file.read_bytes())
    if damage == "crc":
        data[4096 + 4] ^= 1
    elif damage == "header":
        data[4096 + 417] = 0
    elif damage == "truncated":
        data = data[:-1]
    elif damage == "junk":
        data.extend(b"unexplained-trailer")
    else:
        side = int.from_bytes(bytes(17), "big")
        if damage == "reservoir":
            side |= 511 << (136 - 9)
        elif damage == "big_values":
            side |= 511 << (136 - 18 - 12 - 9)
        else:
            side |= 4095 << (136 - 18 - 12)
        data[4096 : 4096 + 417] = frame(side.to_bytes(17, "big"))
    file.write_bytes(data)
    with pytest.raises(ValueError):
        scan_mp3(file)
    with pytest.raises(AudioError):
        decode_audio(file)


def test_raw_native_stderr_is_fatal_despite_exit_zero_and_samples():
    command = [
        sys.executable,
        "-c",
        "import os;os.write(2,b'dequantization failed!\\n');print('{\"frames\":100}')",
    ]
    response = run_bounded(command)
    assert response["exit_code"] == 0
    assert json.loads(response["stdout"])["frames"] == 100
    with pytest.raises(AudioError, match="dequantization failed"):
        checked_worker_result(response)


def test_native_output_limits_fail_closed():
    response = run_bounded([sys.executable, "-c", "print('x'*10000)"], stdout_limit=100)
    assert response["overflow"]
    with pytest.raises(AudioError, match="overflow"):
        checked_worker_result(response)


def test_decode_worker_timeout_is_fatal():
    response = run_bounded(
        [sys.executable, "-c", "import time;time.sleep(20)"], timeout=0.1
    )
    assert response["timed_out"] is True
    with pytest.raises(AudioError, match="timeout=True"):
        checked_worker_result(response)


def test_actual_eof_never_pads_to_estimated_length():
    class Reader:
        frames = 10000

        def __init__(self):
            self.blocks = [np.ones((3, 1)), np.ones((2, 1)), np.ones((0, 1))]

        def read(self, *args, **kwargs):
            return self.blocks.pop(0)

    assert sum(len(b) for b in sequential_blocks(Reader())) == 5


def evidence():
    structure = {
        "has_timing_header": False,
        "crc_failures": 0,
        "unaccounted_bytes": 0,
        "encoded_samples": 11520,
    }
    ff = {
        "frames": 11520,
        "decoder_diagnostics": {
            "exit_code": 0,
            "error_lines": [],
            "timed_out": False,
            "stderr_overflow": False,
        },
    }
    mpg = {
        "exit_code": 0,
        "error_lines": [],
        "timed_out": False,
        "overflow": False,
        "exact_frame_coverage": True,
        "frames": 11520,
    }
    return structure, ff, mpg


@pytest.mark.parametrize(
    "failure", ["ffmpeg_error", "mpg_error", "short_output", "crc", "lenient_only"]
)
def test_consensus_does_not_accept_lenient_or_partial_results(failure):
    structure, ff, mpg = evidence()
    assert consensus(structure, ff, mpg)
    if failure == "ffmpeg_error":
        ff["decoder_diagnostics"]["error_lines"] = ["error despite zero exit"]
    elif failure == "mpg_error":
        mpg["error_lines"] = ["dequantization failed"]
    elif failure == "short_output":
        mpg["frames"] -= 1152
    elif failure == "crc":
        structure["crc_failures"] = 1
    else:
        ff = {}
    assert not consensus(structure, ff, mpg)


def test_ffmpeg_zero_exit_does_not_hide_logged_decode_errors():
    assert diagnostic_errors("[mp3] error decoding\n")
    assert diagnostic_errors("[mp3] overread, skip 3\n")
    assert diagnostic_errors("[mp3] CRC mismatch 123\n")
    assert diagnostic_errors("Input: mp3\nsize=123\n") == []


def test_explicit_state_review_preserves_bytes_and_provenance(tmp_path):
    inv = Inventory(tmp_path / "inventory", 10000)
    original = b"synthetic-inventory-object"
    item = inv.put("original/a.mp3", [original], len(original), {"source": "synthetic"})
    before = inv.audit()["assets"][0]
    with inv._db() as db:
        db.execute("UPDATE assets SET state='quarantined' WHERE path='original/a.mp3'")
    structure, ff, mpg = evidence()
    report = {
        "policy": "strict-ffmpeg-plus-standalone-mpg123-full-frame-consensus-v1",
        "assets": [
            {
                "path": item["path"],
                "input_sha256": item["sha256"],
                "classification": "clean",
                "structure": structure,
                "strict_ffmpeg": ff,
                "mpg123": mpg,
            }
        ],
    }
    retained = retain_diagnosis(inv, report, "reports/review.json")
    after = apply_retained_diagnosis(inv, retained["path"])["assets"][0]
    assert after["state"] == "ready"
    assert after["provenance"] == before["provenance"]
    assert (
        hashlib.sha256((inv.payload / item["path"]).read_bytes()).hexdigest()
        == item["sha256"]
    )
    report["assets"][0]["mpg123"]["error_lines"] = ["corrupt frame"]
    retained = retain_diagnosis(inv, report, "reports/bad-review.json")
    with pytest.raises(InventoryError):
        apply_retained_diagnosis(inv, retained["path"])
