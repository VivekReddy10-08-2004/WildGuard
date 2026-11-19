# Wildlife audio acquisition links — 30 GB cap

**Status:** source research only; no third-party audio has been uploaded. This is a curated link catalogue, not a verified list of licensed recordings. Do not download entire archives simply because they are listed.

## Hard limit
The final collected audio must not exceed **30,000,000,000 bytes** (30 decimal GB). Record actual downloaded and extracted audio sizes before accepting any selection. Leave temporary extraction headroom and keep archives outside the final dataset directory. No source is automatically approved for public redistribution.

## Highest-value multi-taxon sources
| Source | Access link | Reuse / validation condition |
| --- | --- | --- |
| USGS NABat acoustic release (2026) | https://www.usgs.gov/data/north-american-bat-monitoring-program-nabat-acoustic-data-release | CC0 release; individual metadata may include model-generated labels. Prioritize manually confirmed labels; select budgeted subsets. |
| Xeno-canto land mammals | https://www.gbif.org/dataset/80f94317-a61f-477f-af06-037632ad6e3b | Species and provenance metadata; verify original audio access, individual licenses and North American location before download. |
| Western Soundscape Archive | https://westernsoundscape.org/ | Wildlife mammals, reptiles and amphibians. Audio copying and redistribution require recordist permission. |
| Cornell Macaulay Library | https://www.macaulaylibrary.org/ | Mammal, reptile, amphibian and bird media; obtain required permissions, do not scrape. |
| Cry Wolf Project | https://www.thecrywolfproject.com/ | Wolf research; no confirmed bulk download or reuse rights. |
| Xeno-canto Anura | https://www.gbif.org/dataset/bcf8d1fc-6bf0-4f57-9076-7d9ae2828ec2 | Location-filtered amphibian metadata; verify audio rights per recording. |
| Animal Diversity Web frog calls | https://animaldiversity.org/collections/frog_calls/ | Individual frog audio download links, mainly North American species; confirm reuse/training rights. |
| Amphibian monitoring pilot | https://bp-sensr.github.io/gf-amphibians/ | Field audio and calling-index research; access/rights unverified. |

## Open bird datasets (optional, limited share)
| Dataset | Access link | Archive size reported by host |
| --- | --- | --- |
| Powdermill Eastern North American bird soundscapes | https://zenodo.org/records/4656848 | MP3 archive 182.3 MB + annotations 434.3 kB; original WAV archive 1.4 GB, avoid duplicate storage. |
| Sierra Nevada annotated bird soundscapes | https://zenodo.org/records/7050014 | Soundscape ZIP 3.2 GB, plus annotations. |
| Eastern North American forest soundscapes v2 | https://zenodo.org/records/20038954 | Entire release ~27.7 GB: DO NOT download whole archive for this 30 GB multi-taxon objective. Choose justified subsets only after license review. |
| BirdVox | https://wp.nyu.edu/birdvox/codedata/ | Several different releases and label types; pin specific version and verify license. |

## Discovery tools (not license grants)
- Earth Species alp-data: https://github.com/earthspecies/alp-data
- BEANS benchmarks: https://github.com/earthspecies/beans (whole set needs ~300 GB including processing; never download whole set)
- NABat Acoustic ML v2 (model/code): https://www.usgs.gov/data/north-american-bat-monitoring-program-nabat-acoustic-ml-version-200

## Selection quality controls
1. Prefer wild, geographically documented North American recordings over staged, zoo or sound-effect clips.
2. Preserve original label/provenance. Separate expert-verified labels from automated identifications.
3. Prefer species and behavior diversity, recording-site diversity, and clean independent evaluation over hours per species.
4. Enforce species-/site-/session-aware training/validation/test split without cross-split leaks.
5. Check individual source licenses and attribution *before training* and public redistribution.
6. Verify source checksums where provided. Decode and audit sampled audio.
7. Include natural background and non-target sounds for false-positive assessment.
8. Note that an animal may be present without vocalizing; audio alone is never a wildlife safety guarantee.
