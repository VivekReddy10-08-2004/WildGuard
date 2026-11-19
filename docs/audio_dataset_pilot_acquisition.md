# Pilot acquisition report — approval pending

Checked 2026-11-19. No audio acquisition is approved by this report. Exact specs,
ETags, evidence hashes and false approval flags are in
`data/datasets/audio/pilot_acquisition_report.json` and `nps_access_reviews.json`.

## Six-file NPS pilot

| Original source label | Exact original audio URL | Maximum bytes |
| --- | --- | ---: |
| Coyotes | https://www.nps.gov/nps-audiovideo/legacy/mp3/nri/avElement/nri-CoyotesMOJA.mp3 | 161,398 |
| Elk bugle | https://www.nps.gov/nps-audiovideo/legacy/mp3/nri/avElement/nri-ElkBuglingGRSA.mp3 | 331,926 |
| Spotted Bat | https://www.nps.gov/nps-audiovideo/legacy/mp3/nri/avElement/nri-SpottedBatYOSE.mp3 | 113,333 |
| Couch's Spadefoot Toad | https://www.nps.gov/nps-audiovideo/legacy/mp3/nri/avElement/nri-CouchsSpadefootToadSaguaroNP.mp3 | 586,960 |
| Alligator | https://www.nps.gov/nps-audiovideo/legacy/mp3/nri/avElement/nri-AlligatorEVER1.mp3 | 412,592 |
| Crickets | https://www.nps.gov/nps-audiovideo/legacy/mp3/nri/avElement/nri-Cricket.mp3 | 587,671 |
| **Total original MP3 bytes** | | **2,193,880** |

Sizes and ETags were rechecked by HTTP HEAD. No audio body was fetched. The download
adapter will reject length/ETag changes; header information is not a substitute
for content checksum, full decode or listening review.

The [NPS gallery](https://www.nps.gov/subjects/sound/gallery.htm) states that its
audio selections are public domain and downloadable, with appropriate credit.
Each selected source page credits NPS for its audio and identifies the recording
location. Seven exact HTML snapshots are retained and SHA-256-inventoried. Image
credits are kept separate from audio credits. This supports bounded original-file
inspection; individual content and exact-asset redistribution reviews remain
pending until actual bytes are acquired and hashed.

Verified source-page classes are two terrestrial mammals, one bat, one amphibian,
one reptile and one coarse insect group. These are source labels, not independently
verified species ground truth. Cricket species remain unknown. No vocalization
timestamps are inferred. No bird files are proposed.

Additional payload allowance: **1,000,000 bytes** for QC/manifests. No retained
processed audio is proposed; decoding/fingerprints stream in memory. Thus this
approval request adds at most **3,193,880 payload bytes**. Existing inspected
repository/source evidence occupies **82,687,270 bytes**; the planned payload
ceiling is **85,881,150 bytes**, below the 30,000,000,000-byte cap. SQLite control
overhead and software dependencies require separate disk space. All retained
audio, copies, archives and quarantine remain under the one managed ledger.

The current metadata-inspection root is the local `audio-research-stage3` directory
under this chat's permitted scratch workspace, outside OneDrive. Retain or migrate
that complete inventory/payload together to the chosen permanent local SSD before
long-term collection. Do not duplicate audio to another root or backend outside
the shared budget. No remote audio store is enabled.

## PNW-Cnet v5 — original audio not cleared

Pinned release: [Zenodo 17955691](https://zenodo.org/records/17955691), version
2025.12.29; DOI 10.5281/zenodo.17955691. This is separate from the older PNW release.

| Archive | Exact API content URL | Compressed bytes | Acquisition |
| --- | --- | ---: | --- |
| v5_Repo_Files.zip | https://zenodo.org/api/records/17955691/files/v5_Repo_Files.zip/content | 70,644,301 | Inspected with publisher MD5 verification |
| Test_Set_1.zip | https://zenodo.org/api/records/17955691/files/Test_Set_1.zip/content | 6,570,263,187 | Not downloaded; spectrogram evaluation set |
| Test_Set_2.zip | https://zenodo.org/api/records/17955691/files/Test_Set_2.zip/content | 7,515,853,849 | Not downloaded; not approved |

Repository ZIP SHA-256:
`8b251c3a621c6de82e020ea01e4ada87211f66abdda4d529e30b9f2ed71156e0`.
Its published MD5 matched `88ac331574821bd7c79094b10f246f1d`.
The central directory totals 393,382,736 uncompressed bytes. Only selected bounded
metadata members were retained; the model was not executed and the large training
CSV was inspected by streaming its header/sample rather than making a full copy.

**Rights evidence:** the release landing page shows an authors' copyright
statement; the API exposes `license.id = cc-by-4.0`. The archive has no separate
license file or license grant in its README/code. A copyright statement can coexist
with CC BY, but the available evidence does not resolve the displayed discrepancy
and original field-audio scope. Therefore no original-audio use, training or public
redistribution is approved here. Obtain release-specific confirmation covering
Test_Set_2 audio; personal recreation alone is not treated as a permission grant.

The parsed Test Set 2 manifest contains 8,500 focal candidates across 85 classes:
7,538 reviewed focal positives and 962 focal rejections. This is candidate-review
data, not exhaustive onset/offset annotation or an unbiased prevalence sample.

| Non-bird target | Reviewed focal positives in Test Set 2 |
| --- | ---: |
| Coyote | 81 |
| Chipmunk spp. | 95 |
| American pika | 100 |
| Deer snort, genus-level | 99 |
| Douglas squirrel rattle | 94 |
| Bullfrog | 99 |
| Frog chorus, coarse | 98 |
| Cricket, coarse | 98 |
| Buzzing insect (`Fly` source code), coarse | 100 |

Wolf, elk, juvenile black bear, wildcat and Douglas-squirrel chirp classes have
zero Test Set 2 candidates. Their nonzero Test Set 1 counts refer to spectrograms,
not confirmed downloadable original audio. Domestic dog is not counted as a wild
terrestrial target. Human-class metadata exists, but the release says its human
audio was omitted. Audio file counts and actual clip contents remain unverified.

Expanded Test Set 2 size, audio/spectrogram byte breakdown and subset-selection
capability remain unknown. Do not assume the compressed archive size is the final
storage requirement. Its official evaluation designation is protected in code.
Training use requires separate explicit redesignation and a new evaluation plan;
no such redesignation is implemented or approved.
