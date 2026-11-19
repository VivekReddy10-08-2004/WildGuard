"""Exact and conservative acoustic duplicate grouping, with auditable evidence."""

import math

import numpy as np
from scipy.signal import resample_poly

from scripts.wildlife_audio.integrity import decode_audio, pcm_blocks


def quarter_blocks(blocks, rate):
    """Reblock only samples actually decoded; retain no audio outside memory."""
    pending = None
    wanted = max(1, rate // 4)
    for block in blocks:
        pending = block if pending is None else np.concatenate([pending, block])
        while len(pending) >= wanted:
            yield pending[:wanted]
            pending = pending[wanted:]
    if pending is not None and len(pending):
        yield pending


def fingerprint(path, max_seconds=3600):
    """Quarter-second spectral windows, gain invariant; ultrasound stays native.

    No fingerprint-only match is a confirmed duplicate. Candidate edges are kept
    together for leakage prevention until reviewed. No audio copies are written.
    """
    info = decode_audio(path, max_seconds=max_seconds)
    rate = info["sample_rate_hz"]
    target = rate if rate >= 96_000 else 16_000
    profile = f"ultrasound-native-{rate}" if rate >= 96_000 else "audible-16000"
    vectors = []
    for block in quarter_blocks(pcm_blocks(path, max_seconds), rate):
        mono = block.mean(axis=1)
        if rate != target:
            divisor = math.gcd(rate, target)
            mono = resample_poly(mono, target // divisor, rate // divisor)
        if len(mono) < target // 8 or float(np.max(np.abs(mono), initial=0)) < 1e-6:
            vectors.append(None)
            continue
        power = np.abs(np.fft.rfft(mono * np.hanning(len(mono)))) ** 2
        frequencies = np.fft.rfftfreq(len(mono), 1 / target)
        edges = np.geomspace(30, target * 0.49, 33)
        bands = np.array(
            [
                np.sum(power[(frequencies >= lo) & (frequencies < hi)])
                for lo, hi in zip(edges[:-1], edges[1:], strict=True)
            ]
        )
        vector = np.log1p(bands / max(float(bands.sum()), 1e-20) * 10000)
        vector -= vector.mean()
        norm = np.linalg.norm(vector)
        vectors.append((vector / norm).round(5).tolist() if norm > 1e-8 else None)
    return {
        **info,
        "fingerprint_version": "spectral-quarter-eof-v2",
        "profile": profile,
        "window_seconds": 0.25,
        "vectors": vectors,
    }


def acoustic_candidate(left, right, threshold=0.985, min_windows=8):
    """Detect substantial overlapping excerpts/re-encodings; report best similarity."""
    if (
        left["profile"] != right["profile"]
        or left["fingerprint_version"] != right["fingerprint_version"]
    ):
        return None
    a, b = left["vectors"], right["vectors"]
    if len(a) > len(b):
        a, b = b, a
    needed = max(min_windows, math.ceil(len(a) * 0.8))
    if len(a) * len(b) > 2_000_000:
        raise ValueError(
            "acoustic alignment exceeds pilot bound; use a reviewed indexing stage"
        )
    best = None
    for offset in range(-len(a) + needed, len(b) - needed + 1):
        pairs = [
            (x, b[i + offset])
            for i, x in enumerate(a)
            if x is not None and 0 <= i + offset < len(b) and b[i + offset] is not None
        ]
        if len(pairs) < needed:
            continue
        scores = np.sum(
            np.array([p[0] for p in pairs]) * np.array([p[1] for p in pairs]), axis=1
        )
        score = float(np.mean(scores))
        if score >= threshold and (best is None or score > best["similarity"]):
            best = {
                "similarity": score,
                "overlap_windows": len(pairs),
                "offset_windows": offset,
                "status": "candidate_requires_review",
            }
    return best


def duplicate_edges(items):
    """items: recording IDs -> fingerprint results. No candidate is auto-deleted."""
    edges = []
    ids = sorted(items)
    if len(ids) * (len(ids) - 1) // 2 > 100_000:
        raise ValueError("duplicate search exceeds pilot pair budget")
    for n, left in enumerate(ids):
        for right in ids[n + 1 :]:
            a, b = items[left], items[right]
            if a["sha256"] == b["sha256"]:
                reason, detail = "encoded_sha256", {"status": "confirmed_exact"}
            elif a["pcm_sha256"] == b["pcm_sha256"]:
                reason, detail = "decoded_pcm", {"status": "confirmed_pcm"}
            else:
                reason, detail = "acoustic", acoustic_candidate(a, b)
                if detail is None:
                    continue
            edges.append({"left": left, "right": right, "reason": reason, **detail})
    return edges
