"""Connected leakage groups, deterministic splits and protected official holdouts."""

import hashlib
import json


def group_and_split(records, duplicate_edges=(), seed=42, ratios=(0.8, 0.1, 0.1)):
    """Group source/session/site/recordist and duplicate relations before splitting.

    Unknown site/session/recordist records stay unassigned unless an official test
    holdout applies. Conflicting official splits quarantine the whole component.
    Official evaluation cannot be redesignated by this function.
    """
    if len(ratios) != 3 or any(r < 0 for r in ratios) or abs(sum(ratios) - 1) > 1e-9:
        raise ValueError("three nonnegative ratios must sum to one")
    records = list(records)
    by_id = {r["recording_id"]: r for r in records}
    if len(by_id) != len(records):
        raise ValueError("duplicate recording ID")
    parent = {rid: rid for rid in by_id}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    keys = {}
    for rid, r in sorted(by_id.items()):
        if r["source_id"] == "pnw_cnet_v5" and r.get("source_split") != "test":
            raise ValueError("PNW v5 is a protected evaluation source")
        if r.get("source_split") not in {None, "train", "val", "test"}:
            raise ValueError("unknown official source split")
        for field in ("source_recording_id", "site_id", "session_id", "recordist_id"):
            if r.get(field):
                # Identity namespace must be explicit when sites span releases.
                namespace = r.get("identity_namespace", r["source_id"])
                key = (namespace, field, r[field])
                if key in keys:
                    union(rid, keys[key])
                keys[key] = rid
        for ancestor in r.get("parent_recording_ids", []):
            if ancestor not in by_id:
                raise ValueError("missing parent recording")
            union(rid, ancestor)
    for edge in duplicate_edges:
        if edge["left"] not in by_id or edge["right"] not in by_id:
            raise ValueError("duplicate edge references missing recording")
        union(edge["left"], edge["right"])
    groups = {}
    for rid in sorted(by_id):
        groups.setdefault(find(rid), []).append(rid)
    config = {"version": "connected-holdout-v1", "seed": seed, "ratios": ratios}
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True).encode()
    ).hexdigest()
    output = []
    for members in groups.values():
        group_id = hashlib.sha256(json.dumps(members).encode()).hexdigest()
        official = {by_id[r].get("source_split") for r in members} - {None}
        reason = None
        if len(official) > 1:
            split, reason = "excluded", "conflicting_official_splits"
        elif official:
            split, reason = next(iter(official)), "official_source_split_preserved"
        elif any(
            not all(by_id[r].get(f) for f in ("site_id", "session_id", "recordist_id"))
            for r in members
        ):
            split, reason = "unassigned", "unknown_leakage_identity"
        else:
            score = (
                int(hashlib.sha256(f"{seed}:{group_id}".encode()).hexdigest()[:16], 16)
                / 2**64
            )
            split = (
                "train"
                if score < ratios[0]
                else "val"
                if score < sum(ratios[:2])
                else "test"
            )
        for rid in members:
            output.append(
                {
                    "schema_version": "1.0.0",
                    "recording_id": rid,
                    "group_id": group_id,
                    "split": split,
                    "reason": reason,
                    "seed": seed,
                    "algorithm_version": config["version"],
                    "config_sha256": config_hash,
                }
            )
    return sorted(output, key=lambda r: r["recording_id"])
