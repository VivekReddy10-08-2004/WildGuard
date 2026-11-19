# Foundation quality-control report

Date: 2026-11-19. Base branch: `ram_audio`, commit
`bfa5da8a0d0b67b0dbbd60442ecb725ec5adacd5`.

## Validation performed

- Python 3.12.14 on Windows; pytest 9.2.0.
- `python -m pytest tests/unit tests/integration -q`: **99 passed, 1 skipped**.
- The skipped test requires permission to create a Windows symbolic link.
  Real hard-link and junction rejection tests passed; POSIX symlink coverage is
  included in the Linux CI matrix but has not been run locally.
- Ruff 0.17.6 lint passed for all new Python modules/tests and the updated legacy
  validator. Formatting was applied and checked before publication.
- Existing four manifest tests remain intact and pass.
- Tests use synthetic byte streams and generated metadata only. No real wildlife
  recordings were acquired, relabeled or redistributed.

Coverage includes the exact decimal cap constant, small-cap boundary admission,
retained processed copies, oversize streams, unused reservation release,
source checksum mismatch, hash/size tampering, untracked/missing files, portable
path traversal, Windows aliases/alternate streams, single-writer exclusion,
real subprocess termination, recovery idempotence, missing partial recovery,
inventory schema versioning, recording-level commercial rights rejection,
schema validation, cross-table references, lineage, annotation bounds, split-group
conflicts, compatibility export and measured inventory reconciliation.

CI is configured for Python 3.12 on Windows and Linux, with no third-party audio
downloads. Remote CI status must be checked separately from these local results.

## Corpus status

Imported recordings: **0**. Retained third-party audio bytes: **0**.
Approved recording-level rights reviews: **0**.
Existing `sources.json` and `DOWNLOAD_LINKS.md` research was preserved unchanged.
No species coverage, acoustic accuracy, decoded integrity or leakage-free dataset
release is claimed by these foundation tests.

## Proposed pilot, not acquired

`data/datasets/audio/pilot_proposal.json` records six NPS source pages and original
media URLs. HTTP HEAD advertised lengths were inspected without fetching audio
bodies on 2026-11-19.

| Original source label | Advertised original bytes |
| --- | ---: |
| Coyotes | 161,398 |
| Elk bugle | 331,926 |
| Spotted Bat | 113,333 |
| Couch's Spadefoot Toad | 586,960 |
| Alligator | 412,592 |
| Crickets | 587,671 |
| **Total** | **2,193,880** |

These are exact advertised file lengths at inspection, not checksummed download
sizes or decoded/processed sizes. ETags are recorded as HTTP metadata, not assumed
to be SHA-256. Recheck length and rights before acquisition. Recordings remain
clip-label candidates, not verified species/event ground truth. Crickets remain a
coarse group label. Original evidence, manifests and derivatives need additional
reservations; no processed outputs are proposed yet.

## Remaining work and operational limits

- Select the authoritative local SSD root and keep all copies under one ledger.
- Review per-asset commercial/training/redistribution permissions and archive
  original evidence; registry-level claims alone cannot approve an asset.
- Implement bounded source adapters before any acquisition.
- Add full audio decoding, annotation import/verification, taxonomy normalization,
  acoustic deduplication and leakage-resistant split generation in later stages.
- Inventory protects managed writes and detects tampering; it cannot constrain
  unrelated programs writing elsewhere or act as a hostile-process sandbox.
- Remote storage, automated extraction, destructive cleanup and replicated audio
  are not implemented. SQLite control overhead is outside the payload byte cap.
