# Acquisition and processing engineering QC

Date: 2026-11-19. Base: `ram_audio` commit
`6d5b04722de3ba2047c07424287e6e338cd15abf`.

Local verification: Python 3.12.14, pytest 9.2.0, Ruff 0.17.6.
**155 passed, 1 skipped** across unit/integration tests. The skipped test needs
Windows symlink creation privileges. Hard-link and junction tests pass. Windows
and Linux CI are configured; remote results are separate from this local record.
Lint passes for all implementation modules and old/new audio tests.

Tests are network-free and generate synthetic signals. Covered behavior includes
authorization refusal before network access, reservation before transport reads,
budget refusal, redirects outside the source host, changed sizes/ETags, truncated
streams, source checksums, counted quarantine, archive paths, metadata extraction,
WAV/FLAC/OGG/MP3 full decoding, invalid RIFF/nonfinite data, unsupported codecs,
gain/cropped and exact-PCM duplicate cases, native ultrasonic profiles, raw
annotation preservation, focal negatives, source identities, unknown/coarse/
ambiguous taxonomy, connected grouping, official holdout protection, and offline
CLI/report integration.

One initial test expected independent WAV and FLAC encodings of a float waveform
to have identical PCM. Their integer rounding differed. The fixture now encodes
the FLAC from the actual decoded WAV integer samples, testing true PCM identity;
the separate acoustic test still exercises gain and cropping. No test failure
remains in the final local run.

## Real metadata checks

- Only the user-requested 70,644,301-byte v5 repository ZIP was fetched; publisher
  MD5 matched and a SHA-256 inventory record was created.
- Selected metadata extraction was bounded and inventoried. The large training
  CSV was sampled through the ZIP stream. No third-party script/model was run.
- The actual Test Set 2 annotation CSV was parsed without changing its rows:
  8,500 candidates, 7,538 focal positives, 962 focal rejections.
- Seven NPS source/rights HTML snapshots were retained; six audio HEAD sizes and
  ETags were rechecked. No NPS audio body was fetched.
- Both PNW test archives remain undownloaded. Original field-audio reuse remains
  unapproved, and Test Set 2 stays evaluation-only.

Existing research entries and their source IDs are preserved. PNW v5 is appended
as a distinct unresolved-rights source. The previous source-review queue and
legacy validator remain intact; canonical annotation v1.1 is additive.

## Limits and blockers

The acoustic matcher is a bounded pilot implementation, not a completeness claim
for arbitrary transforms or a bulk corpus. Similarity candidates are held together
for leakage protection and require review. Larger comparisons fail closed and
need a reviewed indexing stage. Seeded group ratios do not guarantee class balance.
Actual audio accuracy, duration, sound quality and site independence cannot be
verified until approved acquisition and listening checks occur.

Pending: exact six-file audio approval; permanent local-storage placement;
post-download decode/checksum/label review; individual exact-asset redistribution
reviews; and PNW release-author clarification of original-audio license scope.
No processed audio copy or test-to-training redesignation is requested.
