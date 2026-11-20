# Local datasets

This directory contains local training and evaluation datasets used by the
WildGuard model services. Dataset archives and extracted media are intentionally
excluded from version control because they can be large and may have independent
license or redistribution requirements.

## Current product use

The active MVP is deer spotting for the driver interface. Existing deer species
map to the shared object-detection label `animal` in a separate, reproducible
training view, while original datasets and source labels remain unchanged for
downstream species/hazard classification.

The current local sources provide a useful baseline but are not yet a complete
driver-safety dataset:

- ENA24 and Alberta contain deer bounding boxes suitable for detector training
  after their formats, label IDs, and splits are normalized.
- Oregon Wildlife and the Deer Detection dataset add deer imagery but do not
  provide equivalent ground-truth detection boxes.
- Wildlife Very Dark adds challenging low-light imagery, but its image-level
  labels do not replace road-scene bounding boxes.
- Wildlife Near Roads & Cities supplies useful geospatial context; its packaged
  visual sample is small and lacks bounding boxes.

Priority gaps are road/dashcam bounding boxes, night and headlight conditions,
small distant deer, weather and motion blur, hard driving negatives, and
continuous encounter videos for tracking and alert evaluation. Elk and moose
road data follow deer in the driver roadmap. Hiking-dangerous-species and audio
datasets are separate later tracks.

See [`../../docs/product-direction.md`](../../docs/product-direction.md) for the
label policy, evaluation criteria, and delivery order.

Generate the reproducible one-class YOLO view from ENA24 and Alberta with:

```bash
uv run python -m scripts.derive_deer_driver_dataset
```

The generated dataset is written to `data/derived/deer-driver-v1/`. It uses
relative symbolic links to avoid duplicating source images, includes one
deterministically selected negative image per positive image in each source,
and records source/license/split provenance in `manifest.jsonl`. Generated
derived data is ignored by Git; the preparation script is the source of truth.

Convert an approved Label Studio video-track export into sampled, training-only
YOLO hard examples with:

```bash
uv run python -m scripts.convert_label_studio_video_to_yolo \
  path/to/label-studio-export.json \
  --video path/to/source-video.mp4 \
  --output data/derived/driver-video-hard-examples-v1 \
  --keyframes-only
```

The converter interpolates enabled video tracks, samples positive frames,
ignores empty legacy tracks, writes frame/track provenance to `manifest.jsonl`,
and maps the sole label to class `0: animal`. A complete source video must stay
in one dataset split; these frames are training-only and must not be used to
claim performance on that same encounter. Prefer `--keyframes-only` until the
interpolated boxes have been visually reviewed. Use repeatable
`--exclude-frame FRAME` arguments to omit a known bad keyframe while preserving
that decision in `summary.json`.

Combine the frozen v1 benchmark with approved training-only video hard examples:

```bash
uv run python -m scripts.derive_driver_animal_v2
```

This writes `data/derived/driver-animal-v2/` as a symlinked, reproducible YOLO
view. It preserves the v1 validation and test sets exactly, adds video frames
only to training, records component provenance, and rejects exact image content
that crosses dataset splits. The default command includes both reviewed video
supplements. Use repeated `--hard-examples PATH` options to select a different
set of training-only supplements.

Create a reviewed animal-free video supplement with:

```bash
uv run python -m scripts.extract_video_hard_negatives \
  path/to/source-video.mp4 \
  --start-seconds 0 --end-seconds 5.75 --interval-seconds 0.25 \
  --output data/derived/driver-video-hard-negatives-v1
```

Only use intervals that have been watched completely and confirmed to contain
no target animals. Hard negatives belong in training only. They are useful for
correcting a known failure mode, but performance on their source clip is not an
independent evaluation result.

## Deer Camera Traps (Kaggle)

`deer-cameratraps/deer-cameratraps.zip` is the original archive downloaded from
the Kaggle dataset
[`winnerbishal/deer-cameratraps`](https://www.kaggle.com/datasets/winnerbishal/deer-cameratraps).
Kaggle reports an MIT license. Reproduce the download with:

```bash
kaggle datasets download -d winnerbishal/deer-cameratraps \
  -p data/datasets/deer-cameratraps
```

The original archive is preserved, and its contents are extracted to
`deer-cameratraps/Lila.v1.3k/`. The 4.32 GB archive has 5,163 entries: 2,064
train images with matching YOLO labels, 517 validation images with matching
labels, and a one-class `Deer` configuration. Its `data.yaml` references a test
split, but no test images or labels are included. A preparation script should
audit duplicates/camera sequences and map its positive boxes to the shared
`animal` detection class. Do not mix near-duplicate frames across train,
validation, or test splits.

## Oregon wildlife

`oregon-wildlife.zip` is a species-organized image-classification dataset. Keep
the original archive here and extract or transform it through a reproducible
preparation script rather than editing the source data in place.

Before using or redistributing the dataset, record its source, license, version,
and any required attribution.

## Wildlife Very Dark

The Hugging Face dataset `yin30lei/wildlife_very_dark` is downloaded and saved
locally under `wildlife_very_dark/`. Reproduce the download from the project
root with:

```bash
uv run python -m scripts.download_wildlife_very_dark
```

## Alberta Wildlife v1

`alberta-wildlife-v1/` is the YOLOv8 export of the public Roboflow Universe
project [`apoorvs-workspace-evhrh/alberta-wildlife_2`, version 1](https://universe.roboflow.com/apoorvs-workspace-evhrh/alberta-wildlife_2/dataset/1).
It is licensed under CC BY 4.0.

The downloaded export contains 2,835 images and matching label files across 13
classes. Roboflow published every image in the training split, so the `valid`
and `test` paths referenced by `data.yaml` do not exist yet. Create held-out
splits with grouping and duplicate checks before using the dataset for training
or evaluation. The annotations are highly imbalanced toward `Cow` and `Horse`,
and 1,078 label files contain no objects.

## Wildlife Near Roads & Cities

`wildlife-near-roads-cities/` is a local snapshot of the Hugging Face dataset
[`EDK-Earth/wildlife-near-roads-cities`](https://huggingface.co/datasets/EDK-Earth/wildlife-near-roads-cities),
licensed under CC BY 4.0. Reproduce the download with:

```bash
uv run python -m scripts.download_wildlife_near_roads_cities
```

The repository describes 30,743 geospatial records labeled as bird (12,000),
deer (11,266), raccoon (3,420), coyote (1,948), fox (1,174), or turtle (935).
The CSV, GeoJSON, and Parquet metadata files cover the full record set and load
locally. The packaged representative image archive contains only 100 images,
all labeled `Deer`; it is not a visually representative sample of all six
classes. Although the dataset card emphasizes US street-level imagery, the
metadata also includes records from Canada, Europe, Australia, and elsewhere.
Labels come from query-driven visual matching and do not include bounding
boxes, so they should be audited before use as ground truth.

Datasets:
https://www.kaggle.com/datasets/virtualdvid/oregon-wildlife
https://universe.roboflow.com/ds/AiVyqzbpJ9?key=8ANUi4P2zh

#Hugging face 1
from datasets import load_dataset
ds = load_dataset("yin30lei/wildlife_very_dark")
