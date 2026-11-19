"""Offline multi-decoder MP3 diagnosis with explicit evidence and state review."""

import hashlib
import json
import subprocess
import sys
import threading
from pathlib import Path

import imageio_ffmpeg

from scripts.wildlife_audio.ffmpeg import diagnostic_errors
from scripts.wildlife_audio.integrity import decode_audio
from scripts.wildlife_audio.mp3 import scan_mp3
from scripts.wildlife_audio.paths import safe_path
from scripts.wildlife_audio.process import run_bounded
from scripts.wildlife_audio.storage import InventoryError, sha256_file


def probe_native(path, backend):
    response = run_bounded(
        [
            sys.executable,
            "-m",
            "scripts.wildlife_audio.probe_worker",
            backend,
            str(path),
        ],
        stdout_limit=200_000,
    )
    try:
        decoded = json.loads(response["stdout"])
    except ValueError:
        decoded = {"error": "invalid probe JSON"}
    stderr = response["stderr"].decode("utf-8", errors="replace")
    return {
        "exit_code": response["exit_code"],
        "stderr": stderr,
        "timed_out": response["timed_out"],
        "overflow": response["overflow"],
        "native_error_lines": diagnostic_errors(stderr),
        "decoded": decoded,
        "acceptance_vote": False,
    }


def probe_mpg123(path, executable, structure):
    """Strict standalone mpg123: no resync, no Frankenstein streams, no quiet flag."""
    executable = Path(executable).absolute()
    args = [
        str(executable),
        "--no-resync",
        "--no-frankenstein",
        "--no-control",
        "--no-visual",
        "--encoding",
        "s16",
        "--stdout",
        path.name,
    ]
    child = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=path.parent,
    )
    stderr = bytearray()
    overflow = []
    expired = []

    def collect():
        while chunk := child.stderr.read(4096):
            remaining = 131072 - len(stderr)
            stderr.extend(chunk[: max(0, remaining)])
            if len(chunk) > remaining:
                overflow.append(True)
                child.kill()
                break

    def timeout():
        expired.append(True)
        child.kill()

    reader = threading.Thread(target=collect)
    timer = threading.Timer(120, timeout)
    timer.daemon = True
    reader.start()
    timer.start()
    count = 0
    digest = hashlib.sha256()
    maximum = structure["encoded_samples"] * structure["channels"] * 2
    try:
        while chunk := child.stdout.read(32768):
            count += len(chunk)
            if count > maximum:
                overflow.append(True)
                child.kill()
                break
            digest.update(chunk)
        code = child.wait()
        reader.join()
    finally:
        timer.cancel()
        if child.poll() is None:
            child.kill()
        child.wait()
        reader.join()
        child.stdout.close()
        child.stderr.close()
    text = stderr.decode("utf-8", errors="replace")
    frames = count // (structure["channels"] * 2)
    return {
        "command": [executable.name, *args[1:]],
        "exit_code": code,
        "stderr": text,
        "error_lines": diagnostic_errors(text),
        "timed_out": bool(expired),
        "overflow": bool(overflow),
        "frames": frames,
        "pcm_bytes": count,
        "pcm_sha256": digest.hexdigest(),
        "pcm_format": "signed16-little-endian",
        "duration_seconds": frames / structure["sample_rate_hz"],
        "sample_rate_hz": structure["sample_rate_hz"],
        "channels": structure["channels"],
        "exact_frame_coverage": count == maximum,
        "binary_sha256": sha256_file(executable),
    }


def consensus(structure, ffmpeg, mpg123):
    """Never accept on sample production, exit status alone, or a lenient decoder."""
    ff = ffmpeg.get("decoder_diagnostics", {})
    return bool(
        not structure["has_timing_header"]
        and structure["crc_failures"] == 0
        and structure["unaccounted_bytes"] == 0
        and ff.get("exit_code") == 0
        and not ff.get("error_lines")
        and not ff.get("timed_out")
        and not ff.get("stderr_overflow")
        and ffmpeg.get("frames") == structure["encoded_samples"]
        and mpg123.get("exit_code") == 0
        and not mpg123.get("error_lines")
        and not mpg123.get("timed_out")
        and not mpg123.get("overflow")
        and mpg123.get("exact_frame_coverage") is True
        and mpg123.get("frames") == structure["encoded_samples"]
    )


def diagnose(inventory, relative_paths, mpg123_executable):
    """Read originals only; produce evidence without changing any asset's state."""
    measured = {row["path"]: row for row in inventory.audit()["assets"]}
    version = run_bounded([str(mpg123_executable), "--version"], stdout_limit=16384)
    if version["exit_code"] != 0:
        raise ValueError("standalone mpg123 is unavailable")
    report = {
        "schema_version": "1.0.0",
        "operation": "offline-diagnosis-no-audio-writes",
        "policy": "strict-ffmpeg-plus-standalone-mpg123-full-frame-consensus-v1",
        "ffmpeg_version": imageio_ffmpeg.get_ffmpeg_version(),
        "ffmpeg_binary_sha256": sha256_file(Path(imageio_ffmpeg.get_ffmpeg_exe())),
        "mpg123_version": (version["stdout"] + version["stderr"]).decode(
            "utf-8", errors="replace"
        ),
        "assets": [],
    }
    for relative in relative_paths:
        path = safe_path(inventory.payload, relative)
        row = measured.get(relative)
        if not row or sha256_file(path) != row["sha256"]:
            raise InventoryError("diagnostic input not verified in inventory")
        item = {
            "path": relative,
            "input_sha256": row["sha256"],
            "input_bytes": row["size"],
            "prior_inventory_state": row["state"],
            "classification": "quarantined",
        }
        try:
            structure = scan_mp3(path)
            item["structure"] = structure
        except ValueError as exc:
            item.update(
                classification="rejected",
                reason=f"structural damage or unsupported framing: {exc}",
            )
            report["assets"].append(item)
            continue
        for backend in ("soundfile-blocks", "soundfile-eof", "dr_mp3"):
            item[backend] = probe_native(path, backend)
        item["mpg123"] = probe_mpg123(path, mpg123_executable, structure)
        try:
            item["strict_ffmpeg"] = decode_audio(path, expected_sha256=row["sha256"])
            # Preserve the full log, using portable paths in public metadata.
            diag = item["strict_ffmpeg"]["decoder_diagnostics"]
            diag["command"][0] = Path(diag["command"][0]).name
            diag["command"] = [
                path.name if arg == str(path) else arg for arg in diag["command"]
            ]
            diag["stderr"] = diag["stderr"].replace(str(path), path.name)
        except ValueError as exc:
            item["strict_ffmpeg"] = {"error": str(exc)}
        clean = consensus(structure, item["strict_ffmpeg"], item["mpg123"])
        item.update(
            classification="clean" if clean else "quarantined",
            consensus_passed=clean,
            reason=(
                "Complete frames/CRCs and two strict independent decoders agree; "
                "no corruption detected. Legacy bundled decoder diagnostics retained."
                if clean
                else "Decoder disagreement or strict validation failure; excluded."
            ),
        )
        auxiliary = item["dr_mp3"].get("decoded", {})
        item["dr_mp3"]["exact_frame_coverage"] = (
            auxiliary.get("frames") == structure["encoded_samples"]
        )
        if sha256_file(path) != row["sha256"]:
            raise InventoryError("input changed during diagnosis")
        report["assets"].append(item)
    report["counts"] = {
        state: sum(a["classification"] == state for a in report["assets"])
        for state in ("clean", "quarantined", "rejected")
    }
    return report


def retain_diagnosis(inventory, report, relative):
    data = (
        json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()
    if len(data) > 300_000:
        raise ValueError("diagnostic metadata exceeds bound")
    return inventory.put(
        relative, [data], len(data), {"kind": "multi-decoder diagnosis"}
    )


def apply_retained_diagnosis(inventory, report_path):
    """Apply an explicit retained report; keep original bytes/provenance unchanged."""
    rows = {r["path"]: r for r in inventory.audit()["assets"]}
    record = rows.get(report_path)
    if not record or record["state"] != "ready":
        raise InventoryError("retained diagnostic report required")
    path = safe_path(inventory.payload, report_path)
    if sha256_file(path) != record["sha256"]:
        raise InventoryError("diagnostic report changed")
    report = json.loads(path.read_text("utf-8"))
    if (
        report.get("policy")
        != "strict-ffmpeg-plus-standalone-mpg123-full-frame-consensus-v1"
    ):
        raise InventoryError("unknown diagnostic decision policy")
    with inventory._db() as db:
        for item in report["assets"]:
            if item["classification"] == "clean" and not consensus(
                item["structure"], item["strict_ffmpeg"], item["mpg123"]
            ):
                raise InventoryError("report cannot clear a strict validation failure")
            new_state = "ready" if item["classification"] == "clean" else "quarantined"
            row = rows.get(item["path"])
            if not row or row["sha256"] != item["input_sha256"]:
                raise InventoryError("diagnosis does not match inventoried original")
            db.execute(
                "UPDATE assets SET state=? WHERE path=? AND sha256=?",
                (new_state, item["path"], item["input_sha256"]),
            )
    return inventory.audit()
