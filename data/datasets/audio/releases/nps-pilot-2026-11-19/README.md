# NPS pilot — blocked on native MP3 decoder errors

**Historical incident snapshot.** The subsequent
[multi-decoder investigation](../nps-pilot-diagnosis-2026-11-19/README.md) resolves
the technical block without replacing or altering any original. The JSON records
in this directory preserve the earlier decision; they are not the latest verdict.

Status: **not released; further acquisition stopped**. This directory contains
permitted metadata only. Audio binaries remain in the approved local scratch
inventory; no persistent resampled or derived audio was created.

| Original source label | Actual bytes | Strict native decode |
| --- | ---: | --- |
| Coyotes | 161,398 | Passed |
| Elk bugle | 331,926 | Quarantined: dequantization error |
| Spotted Bat | 113,333 | Passed |
| Couch's Spadefoot Toad | 586,960 | Passed |
| Alligator | 412,592 | Quarantined: dequantization errors |
| Crickets | 587,671 | Passed |
| **Total retained original audio** | **2,193,880** | **4 passed; 2 quarantined** |

All six exact approved URLs were acquired. Individual retained NPS source pages
reference those URLs, credit NPS for the audio, and fall under the gallery's
public-domain/download statement. Rights evidence, attribution, ETags, actual
sizes and SHA-256 hashes are recorded per asset. All size/ETag/hash checks pass.
No publisher SHA-256 was supplied: the recorded SHA-256 values were computed
locally and reconciled with the inventory.

The pinned SoundFile/libsndfile decoder printed native mpg123 dequantization
errors for Elk bugle and Alligator while returning exit code zero and no Python
exception. The current validator failed to surface those native errors. All six
downloads had completed before the tool returned the diagnostics; acceptance
was stopped when observed. Isolated subprocess checks reproduced the errors
for those two files, which are now quarantined in place and still counted.
Whether the underlying issue is source corruption or decoder compatibility is
unresolved. No repair, re-encoding, replacement or redownload was attempted.

Earlier internal machine-generated success summaries are superseded by this
directory and the local `authoritative/` metadata. They are retained internally
as incident evidence, not published as accepted QC. Full decoding is **not**
certified for the pilot. The native-error reporting gap remains an engineering
blocker before any further acquisition; metadata tests do not repair that gap.

Exact managed-inventory accounting:

- Original audio: **2,193,880 bytes**, including **744,518 quarantined bytes**.
- Added QC/manifests, including superseded incident artifacts: **224,713 bytes**.
- Total additional retained managed payload: **2,418,593 bytes**, below 3,193,880.
- Entire managed payload, including existing research material: **85,105,863 bytes**.
- Persistent derived audio: **0 bytes**. SQLite control overhead is separate.

Labels remain six unverified source-provided weak clip labels: five species-level
name mappings and one coarse cricket group. No expert species listening review,
event timestamps, individual recordist identity or recording date is invented.
Four records remain unassigned; two are excluded for decoder errors. No training
or evaluation split is released. Exact encoded hashes are unique; the four clean
decodes have no detected acoustic duplicates. Acoustic results for the two flagged
files are not accepted as a valid duplicate audit.

Both PNW test archives and all additional audio sources remain untouched.

`bundle.json` and per-table JSONL preserve source metadata and unknown values.
`strict_decoder_diagnostics.json` and `qc.json` explain the failed gate.
`summary.json` is the authoritative retained-byte/status summary. Canonical schema,
rights-contract and legacy structural checks pass, while inventory acceptance
correctly rejects the two quarantined assets.

Validation run: **159 tests passed, 1 skipped** on Python 3.12.14. The skip is the
existing Windows symlink-permission test; lint and formatting checks pass. These
include four metadata regression tests for the real blocked pilot. Passing tests
do not certify the two flagged MP3s or resolve the native-error reporting defect.
