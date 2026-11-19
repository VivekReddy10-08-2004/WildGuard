"""Conservative recording-level commercial redistribution gate."""

import re

from scripts.wildlife_audio.schema import validate


def redistribution_errors(review, source_id, source_recording_id, asset_sha256):
    """A registry flag, page title or metadata license is never an approval."""
    errors = validate("rights", review)
    if errors:
        return errors
    if review["status"] != "approved":
        errors.append("recording-level review is not approved")
    if (review["source_id"], review["source_recording_id"], review["asset_sha256"]) != (
        source_id,
        source_recording_id,
        asset_sha256,
    ):
        errors.append("rights review does not match exact recording and asset")
    if re.search(
        r"(?i)(non.?commercial|(?:^|-)NC(?:-|$)|(?:^|-)ND(?:-|$)|no.?derivatives)",
        review["license_id"] or "",
    ):
        errors.append("restrictive license is not eligible for commercial derivatives")
    return errors


def bundle_redistribution_errors(tables):
    """Run after validate_bundle; require exact original-asset reviews per recording.

    Derivatives follow their checked lineage. This checks recorded decisions,
    not whether a reviewer correctly interpreted a license or supplied evidence.
    """
    reviews = {r["review_id"]: r for r in tables.get("rights", [])}
    errors = []
    for recording in tables.get("recording", []):
        rid = recording["recording_id"]
        originals = [
            a
            for a in tables.get("asset", [])
            if a["recording_id"] == rid and a["kind"] == "original"
        ]
        review = reviews.get(recording["rights_review_id"])
        if not originals or review is None:
            errors.append(f"{rid}: original asset and recording-level review required")
            continue
        for asset in originals:
            errors.extend(
                f"{rid}: {error}"
                for error in redistribution_errors(
                    review,
                    recording["source_id"],
                    recording["source_recording_id"],
                    asset["sha256"],
                )
            )
    return errors
