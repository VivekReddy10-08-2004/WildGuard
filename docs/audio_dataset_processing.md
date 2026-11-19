# Bounded audio acquisition and processing

This stage extends the foundation on `ram_audio`. No NPS audio or PNW test audio
was acquired during implementation. Only the explicitly requested PNW repository
archive and source/rights metadata were retained for inspection.

## Install and offline processing

Python 3.12:

```powershell
python -m pip install -r requirements-audio-processing.txt
python -m scripts.wildlife_audio analyze D:\WildGuardAudio D:\metadata\catalog.json --save-relative reports/pilot-qc.json
```

Use POSIX relative paths (`reports/pilot-qc.json`) for `--save-relative`, including
on Windows.
The report is admitted through the same byte inventory, with a 1,000,000-byte
default report limit. Output is also printed as JSON. All analysis is offline.

A catalog has a `recordings` array with `recording_id`, `source_id`,
`source_recording_id`, `path` (relative to managed payload), `original_labels`
(unmodified strings), and explicit `site_id`, `session_id`, `recordist_id`
(null where unknown). Optional `source_split`, `identity_namespace`,
`parent_recording_ids` and `rights_review` support grouping and rights QC.
An optional `annotations` array carries canonical rows; each recording can specify
`asset_id` (otherwise its recording ID is used). Annotation windows/channels are
checked against fully decoded dimensions, and official split metadata must agree.
The QC report preserves valid annotation payloads and excludes groups with errors.

The analyzer audits inventory first, fully decodes every input, records encoded
and decoded-PCM hashes, normalizes labels against the pinned mapping, identifies
duplicate relations, groups leakage identities and reports split decisions.
Malformed audio is reported as a failure and its entire leakage group is excluded.
Inventory `ready` means a complete transport/storage object, not audio validation
or training approval. `release_ready` remains false: this stage produces QC, not
an automatically authorized dataset release.

## Explicit acquisition

```powershell
python -m scripts.wildlife_audio acquire D:\WildGuardAudio D:\metadata\spec.json --approval D:\metadata\approval.json --rights D:\metadata\access-review.json
```

The spec fields match `DownloadSpec`: source ID, source recording ID, exact HTTPS
URL, payload path, exact expected bytes, optional SHA-256, publisher MD5 and ETag.
`adapters.nps_spec` builds original-MP3 specs from reviewed NPS entries;
`adapters.pnw_spec` accepts only the pinned v5 release and enabled filenames.
The production transport restricts source hosts and validates every redirect.

Approval must be exactly `{url, expected_bytes, approved: true}`. Download rights
must independently match source, recording and URL, name a reviewer, and reference
retained evidence objects by inventory path and SHA-256. Approval files are trusted
local operator inputs, not cryptographic evidence of user identity. All committed
NPS proposal approval flags are false. `policy.json` leaves unattended acquisition
disabled; only the explicit exact-file approval path is supported.

Reservations are durable before the HTTP body is read. Content-Length, actual
stream length, supplied ETag and publisher checksums are checked. SHA-256 is always
computed. Missing publisher SHA-256 is recorded honestly, never replaced with an
ETag or MD5 labeled as SHA-256. Failure retains counted quarantine bytes, with no
automatic retry, overwrite or deletion. Source changes require renewed review.
The transfer has a 20-second socket timeout and a 600-second overall deadline.

Archive inspection does not use `extractall`. Only selected bounded metadata
members may be retained, through the inventory; unsafe paths, links and duplicate
member names are rejected. There is no general bulk-audio extraction command.

## Decoding and duplicate evidence

Pinned SoundFile/libsndfile handles WAV, FLAC and OGG in isolated workers, using
actual reads to EOF. MP3 uses strict FFmpeg plus contiguous frame/side-info/CRC
validation. Native stderr and logged decode errors fail acceptance even on exit
zero. See [decoder diagnostics](audio_decoder_diagnostics.md) for the resolved
NPS incident, independent review policy and exact decoder differences. AAC/M4A
and other unsupported codecs fail explicitly. Dimension, duration, finite-sample,
RIFF truncation and checksum checks run; silence and clipping are QC flags.
Default limits are one hour, eight channels and 768 kHz. Original audio is never
resampled or overwritten. Decoder versions are included because lossy PCM hashes
may depend on the decoder.

Exact encoded SHA-256 and decoded PCM matches are distinguished. Acoustic matching
uses normalized quarter-second spectral windows to propose substantial overlaps
and gain/re-encoding variants. Audible comparison features use 16 kHz; ultrasonic
recordings at 96 kHz or above retain their native rate/profile. Fingerprints are
not retained audio copies. Acoustic candidates are not confirmed duplicates and
are never deleted automatically; candidate pairs stay in one leakage group.
This pilot matcher is not a guarantee of detecting every transformation. It
explicitly refuses searches exceeding 100,000 recording pairs or 2,000,000
alignment cells per pair; QC then excludes splits rather than claiming completion.
A scalable reviewed indexing stage is required before bulk field-audio deduplication.

## Annotation and taxonomy semantics

NPS page labels are weak clip labels. No times, annotator identities, confidence
values or species verification are fabricated. Original pages/transcripts remain
the provenance evidence, separate from later listening review.

The PNW Test Set 2 importer preserves every original CSV field and the manifest
SHA-256/row number. `TOP1DIST` stays a model prediction score, never a human-label
confidence. `MANUAL_ID=No` rejects only the focal class, not every animal in the
clip. `OFFSET` and `DURATION` describe the reviewed source window, not precise
vocalization boundaries. These offsets must be checked against acquired clip
duration before acceptance. Human-class rows exist but corresponding audio is
omitted according to the release description.

Canonical annotations use additive schema version 1.1.0, retaining 1.0.0 support.
New fields include `focal_present`, prediction score, source split, channel and
manifest lineage. A negative focal review retains the focal label but has
`focal_present: false` and no positive species taxon ID. Consumers must not treat
all rows with a label as positive examples. Legacy export never turns a negative
review or fixed window into a positive onset/offset event.

The small pinned taxonomy snapshot uses explicitly local concept IDs, not invented
ITIS/GBIF identifiers. Unknown and ambiguous labels remain unresolved. Chipmunk and
deer groups remain at genus level; cricket, frog-chorus and buzzing-insect source
classes remain coarse. In particular, the PNW code `Fly` does not establish an
insect order or species. Mapping a name is not verifying an animal in audio.

## Split protection and licensing

Source recording, site, session, recordist, parent and duplicate relations form
connected components. Identity namespaces make cross-release grouping explicit.
Official holdouts are preserved; conflicting official splits exclude the group.
Missing leakage identities cause unassigned data, not invented independent test
examples. New group assignments use seeded hash ratios, not promised exact class
balance. QC exposes resulting coverage; class-balanced allocation is not claimed.

PNW v5 is explicitly evaluation-only in both grouping and processing APIs. There
is no redesignation override. Training on it would require a separately approved,
documented policy/code change and a new independent evaluation plan.

Personal recreational use is not treated as a license waiver. Acquisition rights
and commercial redistribution approvals remain different gates. Neither access
to metadata, an open-download link, nor a source registry flag approves audio use.
PNW original audio remains blocked while the landing/API license scope discrepancy
is unresolved. Copyright ownership and a CC license can coexist; the conservative
block here records incomplete scope verification, not a determination that CC BY
can never apply.
