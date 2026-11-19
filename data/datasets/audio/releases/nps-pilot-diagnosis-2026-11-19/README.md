# NPS MP3 investigation — technical integrity resolved

Verdict: **6 technically clean, 0 quarantined, 0 rejected assets** under the
reviewed strict full-frame consensus policy. This is not a species-label audit
or approval for additional acquisition. All six files, their input SHA-256 hashes,
and original provenance records are unchanged. No replacements were downloaded,
no originals deleted, and no persistent PCM/resampled/re-encoded audio was created.

## Independent results for the two previously blocked recordings

| Original | Complete MPEG frames | FFmpeg exit / seconds | Standalone mpg123 exit / seconds | Protected-frame CRC failures |
| --- | ---: | --- | --- | ---: |
| Elk bugle | 788 | 0 / 20.58448979591837 | 0 / 20.58448979591837 | 0 |
| Alligator | 981 | 0 / 25.626122448979594 | 0 / 25.626122448979594 | 0 |

FFmpeg 7.1 (`mp3float`) ran with `-xerror -max_error_rate 0 -err_detect
crccheck+bitstream+explode`, retaining info-level logs and checking for error,
overread/concealment and CRC diagnostics regardless of exit code. It decoded every
framed sample with no such diagnostics. Standalone mpg123 1.33.7 ran independently
with `--no-resync --no-frankenstein`, also decoding every sample without errors.
No lenient recovery or resynchronization was needed. All byte ranges in both
streams are accounted for as contiguous complete frames or recognized ID3 tags.

`comparison-v1.json` records the complete commands, stderr, exit codes, sample
counts, durations, input hashes, decoded PCM hashes, scanner results and executable
hashes for all six originals. FFmpeg's canonical PCM is float32 little-endian;
standalone mpg123's probe PCM is signed16 little-endian. Different decoded hashes
across formats/decoders are expected and are not treated as identical PCM. Only
source input hashes are required to remain unchanged.

## What failed in the earlier pipeline

1. The pinned SoundFile 0.13.1/libsndfile 1.2.2 backend still emits
   `error: dequantization failed!` for Elk (one message) and Alligator (three).
   Its process exits zero. The exact messages and both old block/EOF probes remain
   in the comparison report; they have not been hidden or reinterpreted as success.
   These failures do not reproduce in the current standalone mpg123 or strict
   independent FFmpeg decoder.
2. `SoundFile.blocks()` trusts the decoder's estimated MP3 frame length. On these
   inputs it yielded samples past actual EOF, overstating durations and producing
   invalid tail/PCM-hash measurements. The previous frame-count equality check
   could not detect this because the iterator itself used that estimate.

These are verified acceptance/length-handling defects and a bundled-decoder
compatibility failure. No source corruption was detected by the complete-frame,
CRC and independent strict decoding checks. The exact internal bundled-mpg123
defect/version is not exposed by the wheel, so no unsupported upstream bug ID or
specific internal cause is asserted.

An auxiliary miniaudio 1.61 dr_mp3/minimp3 probe exits zero without diagnostics but
returns one fewer 1,152-sample frame on five CRC-protected files. That short result
is explicitly recorded and **has no acceptance vote**. It illustrates why sample
production or exit zero alone is insufficient. The corroborating independent pair
is strict FFmpeg plus standalone mpg123, whose complete counts agree exactly.

## Code changes and review policy

- MP3 ingestion selects the strict FFmpeg backend before decoding, with contiguous
  frame/side-info/CRC validation. It never retries a failed decoder through a lenient
  fallback. Non-MP3 SoundFile decoding uses actual sequential reads to EOF.
- Native libraries run in bounded workers; stderr, timeout, output overflow,
  invalid metadata and nonzero exit codes fail acceptance. FFmpeg logs remain in
  successful results; error/concealment lines are fatal even if exit status is zero.
- Fingerprints use the same strict PCM source and real EOF. No stale SoundFile
  block tail is fingerprinted. PCM/fingerprint versions are explicitly updated.
- Reclassification requires a retained, hashed report and two strict independent
  decoders consuming every framed sample, with intact input hashes and no CRC
  failures. Confirmed structural damage is rejected and remains physically
  quarantined; disagreement remains quarantined. No original is deleted.

`state_transition.json` records the explicit two-file quarantine clearance and
unchanged provenance. `bundle.json` and table manifests contain corrected measured
durations and codec properties; original source records/annotations are unchanged.
The old incident and incorrect internal success artifacts remain historical
evidence, clearly superseded. No alternate official source is needed or claimed
as the same recording, and none was downloaded.

## QC and storage

All six encoded hashes remain unique; the refreshed strict-PCM duplicate audit
finds no acoustic candidate pairs. All six splits remain unassigned because
independent recording-session/recordist identities are unknown. All labels remain
unverified source clip labels: five species-level name mappings and one coarse
cricket group. No expert species review or event timestamps are invented.

- Original audio: **2,193,880 bytes**, unchanged.
- New audio acquired in this investigation: **0 bytes**.
- Persistent derived audio: **0 bytes**.
- Retained managed QC/provenance metadata including history: **408,985 bytes**.
- Entire managed payload: **85,290,135 bytes**; SQLite control overhead is separate.
- Tests: **178 passed, 1 skipped** locally; skip is the existing Windows symlink
  permission test. Ruff lint passes. Tests include generated CRC/side-information
  damage, truncation, reservoir errors, zero-exit native stderr, overflow, timeouts,
  real EOF, strict consensus and preservation of original bytes/provenance.

Audio processing remains local/offline. Only permitted metadata, code and reports
enter Git. Both PNW test archives remain undownloaded,
and no larger acquisition is authorized.
