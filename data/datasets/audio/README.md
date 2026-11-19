# WildGuard North American wilderness audio

This directory contains **metadata and reproducible tooling**, not redistributed recordings.

## Scope
North American mammals (especially predators and ungulates), reptiles, amphibians, bats, insects, and birds. Do not treat a species occurring in North America as proof that a recording was made there. Keep geographic origin and taxonomy separate.

## Data policy
- Never bulk-redistribute third-party audio without explicit recording-level rights.
- Record source URL, source recording ID, license, geographic provenance, and annotation method.
- Distinguish manually verified species labels from machine predictions.
- Never manufacture timestamps, confidence scores, or species identities.
- Keep source audio in local storage (ignored by Git) or a separately approved storage backend.
- Hold out entire recording sessions, sites, and source recordings when evaluating models.
- Sound detection is not evidence that an animal is nearby or dangerous; silence does not prove safety.

## Dataset manifest
Use one JSON object per line. Required fields:
`recording_id`, `source`, `source_url`, `audio_path`, `license_id`,
`license_verified`, `taxon`, `scientific_name`, `region`,
`annotation_type`, `annotation_method`, `split`.
Optional `events` contains `start_seconds`, `end_seconds`, and `label` for genuine event annotations.
Use null for unknown metadata, not guessed values.

Run `python scripts/validate_wildlife_audio_manifest.py /path/to/manifest.jsonl --audio-root /path/to/dataset`.

## Acquisition status
No third-party audio has been imported or licensed by this commit. See `sources.json` for a source-review queue. A source listed there is **not** automatically approved for download or training.

## Engineering foundation (stages 1–2)

Versioned contracts are in `schema/`; `source_reviews.json` contains no approved
recordings. Existing source research remains separate from recording-level rights.
Commercial redistribution requires explicit recording/asset-specific review;
source-level license flags alone never satisfy this gate.

See [pipeline contracts](../../../docs/audio_dataset_pipeline.md) and
[local/offline storage](../../../docs/audio_dataset_storage.md) for setup and commands.
The SQLite inventory enforces a hard 30,000,000,000-byte ceiling on all managed
payload, including originals, processed copies, archives, partials and quarantine.
No downloader is enabled. Existing manifest validation remains supported.
