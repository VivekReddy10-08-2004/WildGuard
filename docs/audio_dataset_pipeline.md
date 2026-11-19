# Wildlife audio contracts and integration

The original foundation implements stages 1 and 2. The subsequent bounded
acquisition/processing stage is documented in [audio_dataset_processing.md](audio_dataset_processing.md).
That stage adds decoding, source annotation import, conservative taxonomy mapping,
duplicate candidates and protected grouping, without automatically acquiring audio.

## Version 1.0.0 contracts

Schemas live in `data/datasets/audio/schema/` and declare JSON Schema 2020-12.
Each row requires `schema_version: "1.0.0"`. Unknown top-level fields are rejected;
original source metadata and annotations retain their original structure inside
explicit provenance fields. Unknown facts are null, never invented values.

| Table key | Schema | Purpose |
| --- | --- | --- |
| `recording` | `recording.schema.json` | Source identity, original labels/annotations, taxonomy and geographic evidence, context, site/session/recordist IDs |
| `asset` | `asset.schema.json` | Actual file path, bytes, SHA-256, optional decoded properties, transformation and parent asset |
| `annotation` | `annotation.schema.json` | Clip, event, fixed window or unlabeled; raw annotation, annotation method and verification |
| `split` | `split.schema.json` | Group membership, train/val/test/unassigned/excluded, algorithm/config/seed |
| `provenance` | `provenance.schema.json` | Registry source ID, original metadata and snapshot hash, exact release/record, URL and retrieval timestamp |
| `rights` | `rights.schema.json` | Recording-level, exact-asset rights review and evidence |

An interchange bundle is a JSON object whose keys are the table keys above and
whose values are arrays. Tables may also be kept as separate deterministic JSONL
files by future acquisition tooling. The current validator checks schema versions,
unique IDs, foreign references, registry source IDs, parent cycles, annotation
duration bounds and cross-split group conflicts. It does not compute groups or
verify declared durations by decoding; those are later-stage responsibilities.

```powershell
python -m scripts.wildlife_audio validate D:\metadata\bundle.json
python -m scripts.wildlife_audio validate D:\metadata\bundle.json --redistributable
python -m scripts.wildlife_audio validate D:\metadata\bundle.json --redistributable --audio-root D:\WildGuardAudio
python -m scripts.wildlife_audio export-legacy D:\metadata\bundle.json
python scripts/validate_wildlife_audio_manifest.py D:\metadata\manifest.jsonl --audio-root D:\WildGuardAudio\payload
```

`export-legacy` prints deterministic per-row JSON to stdout. Keep the full bundle
as the authoritative representation; the legacy shape cannot express all fields.
It requires one explicitly selected original per recording. Genuine event times
are copied unchanged; window tags are retained as raw annotations and are never
converted to vocalization onsets/offsets. Legacy structural validation is not an
authorization or label-accuracy audit. Do not write manifests into the managed
payload by shell redirection; retain them through the bounded inventory writer.

## Licensing and provenance

Existing `sources.json` IDs are authoritative discovery references and are not
rewritten. `DOWNLOAD_LINKS.md` remains research, including its caveats about
capture context, duplicate galleries and zero-occurrence class names. A source's
`license_verified` flag does not authorize individual recordings.

`source_reviews.json` is a separate recording-level review queue. It initially
contains no approvals. Each future row must match `rights.schema.json`, including
the source/recording ID, exact original SHA-256, license evidence, reviewer/time,
attribution and conditions. Preserve the raw annotation and licensing evidence
files byte-for-byte, inventory them, and record their hashes; a parsed metadata
dictionary alone does not replace the original source document.

For redistributable material, a review must explicitly permit commercial use,
training, redistribution and derivatives and have retained evidence. NC/ND
licenses, pending reviews and unknown permissions fail the commercial gate.
The `--redistributable` check validates recorded approvals against original asset
hashes. It cannot decide whether a human reviewer interpreted a license correctly
or whether external evidence really grants those rights. A storage write alone
never makes an asset eligible for training/export.

Prioritize geographically supported wild terrestrial mammals, bats, amphibians,
reptiles and insects. Species range does not establish recording location. Use
coarse/unresolved labels where appropriate; do not infer an insect species from
an illustrative photograph. Preserve time expansion and ultrasound information
for bats; no default resampling is performed. Captive/staged/unknown context stays
explicit and must not silently enter an evaluation of wild encounters.

## Remaining stages

Next: dataset-specific metadata parsers and bounded download adapters, full decode
and annotation audit, pinned taxonomy mapping, exact/acoustic deduplication,
site/session/source-aware splitting, then release manifests and coverage reports.
Before pilot acquisition, refresh source research, approve recording-level rights,
recheck exact byte counts, and budget evidence plus all processing outputs.
`policy.json` leaves unattended acquisition disabled. The subsequent stage requires
exact-file approval and retained rights evidence before its downloader runs.
