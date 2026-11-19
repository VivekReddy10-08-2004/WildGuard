"""Pinned, evidence-linked name mappings; no fuzzy species guessing."""

import hashlib
import json


def normalize(label, snapshot):
    """Return unknown, ambiguous, higher-rank or resolved while retaining raw label.

    IDs in this project snapshot are local concepts, not invented ITIS/GBIF IDs.
    Changing a mapping changes its snapshot checksum and requires a new release.
    """
    raw = label
    key = label.strip().casefold() if isinstance(label, str) else ""
    digest = hashlib.sha256(
        json.dumps(
            snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    matches = [
        t
        for t in snapshot["taxa"]
        if key
        and key in {str(x).casefold() for x in [t["scientific_name"], *t["aliases"]]}
    ]
    result = {
        "original_label": raw,
        "taxonomy_version": snapshot["version"],
        "taxonomy_sha256": digest,
        "status": "unknown",
        "taxon_id": None,
        "scientific_name": None,
        "rank": None,
        "candidates": [],
    }
    if len(matches) > 1:
        result.update(
            status="ambiguous", candidates=sorted(t["taxon_id"] for t in matches)
        )
    elif len(matches) == 1:
        taxon = matches[0]
        result.update(
            status="resolved" if taxon["rank"] == "species" else "higher_rank",
            taxon_id=taxon["taxon_id"],
            scientific_name=taxon["scientific_name"],
            rank=taxon["rank"],
        )
    return result
