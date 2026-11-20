# WildGuard product direction

## Decision

WildGuard is a shared wildlife-awareness platform with application-specific
detection pipelines. It is not a single model that must recognize every North
American animal equally well in every environment.

The applications share ingestion, normalized event contracts, tracking,
storage, alert delivery, privacy, consent, and observability. They may use
different model weights, label maps, confidence thresholds, risk policies, and
evaluation datasets.

## Application priorities

| Application | Priority animals | Environment and behavior |
| --- | --- | --- |
| Driver safety | Deer first; elk and moose next | Road scenes, headlights, darkness, distance, weather, motion blur, and fast warning latency |
| Hiking safety | Bears, mountain lions, and wolves | Trail and phone-camera scenes, nearby encounters, occlusion, and conservative danger alerts |
| Wildlife monitoring | Broad North American wildlife | General camera-trap and observation workflows using the existing 26-class YOLO baseline |
| Audio monitoring | Wolves, coyotes, and other identifiable vocalizations | A separate audio pipeline with event gating, classification, and its own validation |

## Active MVP: driver deer spotting

The first deliverable is a driver-facing deer warning feature operating on a
recorded video or dashcam-like stream.

### Initial label policy

- Use `animal` as the shared bounding-box class emitted by object detection.
- Map white-tailed deer, mule deer, and black-tailed deer to `animal` for
  detection, while retaining `deer` as the downstream driver-hazard/species
  classification.
- Keep original source labels in dataset metadata so the mapping is reversible
  and a later classifier can learn exact taxa.
- Treat elk and moose as later explicit hazard classes rather than silently
  classifying them as deer. Their detection label is still `animal`.
- Keep bear as a generic operational class for early hiking work; exact bear
  species is not an MVP requirement.

### Runtime pipeline

```text
video or dashcam frames
        -> animal object detector
        -> multi-frame tracking
        -> deer / elk / moose / unknown-animal classifier
        -> persistence and duplicate suppression
        -> roadway/distance risk signals
        -> alert policy and cooldown
        -> visual/audio driver warning
```

Image-trained YOLO weights can run on video frame by frame. Detection,
classification, tracking, and alert policy are separate responsibilities: the
detector locates generic animals, the classifier estimates the relevant taxon,
the tracker associates detections over time, and the policy determines whether
the evidence is strong and relevant enough to interrupt the driver. For the
current deer-only training view, every positive `animal` box is known to be a
deer, but the runtime object contract does not encode that assumption.

### MVP success criteria

Evaluate the feature as a safety pipeline, not only as an image classifier.
Record at least:

- animal recall and precision at the bounding-box level;
- deer classification recall and precision within detected animal boxes;
- false alerts per hour of non-deer driving video;
- missed deer events per evaluated drive or clip set;
- detection distance or apparent object-size bands;
- day, dusk, night, headlight, weather, and motion-blur slices;
- alert latency from first visible deer and end-to-end inference latency;
- frame-to-frame stability and duplicate alerts per encounter.

Thresholds for a demonstration may be selected after baseline evaluation. No
claim of production safety should be made until representative road video and
failure cases have been independently tested.

## Model strategy

### Shared baseline

The existing `UWyo/wildlife-north-american-wildlife` 26-class YOLO model remains
useful for broad wildlife monitoring and as the starting benchmark for driver
and hiking tasks. Its broad class coverage does not guarantee sufficient
road-scene deer recall.

### Driver detector

Start by evaluating the existing detector on all deer sources. Then create a
derived, reproducible animal-detection training view whose current positives
are deer and that normalizes compatible bounding-box annotations without
modifying the original datasets. Fine-tune only if the baseline misses the MVP
criteria.

The derived view should use group-aware train, validation, and test splits,
retain dataset provenance, and prevent near-duplicate frames or camera
sequences from crossing split boundaries.

### Hiking detector

Use a separate evaluation and tuning track for generic bear, mountain lion, and
wolf encounters. This work follows the driver MVP and should not block it.

### Audio detector

Audio is an independent pipeline. Visual YOLO weights are not reused for audio.
Generic sound-event models may provide event gating, while species or taxon
recognition requires a bioacoustic model plus WildGuard-specific validation.

## Dataset implications

Current datasets provide a workable deer baseline, particularly white-tailed
deer bounding boxes, classification images, camera-trap imagery, and useful
non-deer negatives. They do not yet fully represent driver deployment.

The highest-priority additions are:

1. Licensed deer bounding boxes from actual road or dashcam viewpoints.
2. Night, headlight, glare, rain, snow, fog, distance, and motion-blur cases.
3. Negative driving video containing signs, vegetation, livestock, people,
   vehicles, and reflective objects likely to cause false alerts.
4. Continuous clips containing complete encounters for tracking, alert latency,
   false-alert, and duplicate-alert evaluation.
5. Later, road-scene elk and moose boxes for expansion beyond deer.

Oregon folder labels and classification-only datasets can support evaluation,
representation learning, or reviewed pseudo-labeling, but they are not direct
substitutes for ground-truth detection boxes.

## Delivery order

1. Establish a reproducible deer-positive animal-detection benchmark.
2. Normalize the available deer bounding-box datasets into a derived training
   view while preserving their originals.
3. Add video inference, tracking, persistence filtering, and event aggregation.
4. Build a minimal driver warning interface around recorded clips.
5. Collect and evaluate representative road/night video and tune the alert
   policy before fine-tuning when possible.
6. Fine-tune the road-animal detector if baseline errors justify it.
7. Expand driver detection to elk and moose.
8. Develop hiking and audio pipelines as separate application tracks.

The current derivation command is:

```bash
uv run python -m scripts.derive_deer_driver_dataset
```

After reviewing road-video tracks in Label Studio, generate the v2 training
view with:

```bash
uv run python -m scripts.derive_driver_animal_v2
```

`driver-animal-v2` freezes the existing v1 validation and test splits while
adding approved road-video hard examples from the Tesla and Oh Deer dashcam
videos only to training. A source encounter used in training is excluded from
model-selection and generalization claims.

It creates `data/derived/deer-driver-v1/` from ENA24 and Alberta, maps compatible
deer boxes to the shared `animal` object class, adds balanced negatives, and
writes a provenance manifest containing the original deer labels. Source
datasets remain unchanged.

The deer fine-tuning comparison is reproducible with:

```bash
uv run python -m scripts.train_deer_detector \
  --initialization both \
  --epochs 60 \
  --patience 12 \
  --image-size 640 \
  --batch-size 64 \
  --workers 8
```

This preserves the broad 26-class checkpoint, trains separate one-class models
from the wildlife and official COCO initializations, selects using validation
mAP50–95, and evaluates only the selected checkpoint on the test split.

The completed comparison selected the wildlife initialization:

| Initialization | Validation mAP50 | Validation mAP50–95 |
| --- | ---: | ---: |
| Wildlife checkpoint | 0.930 | 0.702 |
| COCO checkpoint | 0.921 | 0.678 |

That v1 model scored 0.892 mAP50, 0.671 mAP50–95, 0.884 precision, and 0.847
recall at 640 px on the untouched 193-image test split. It remains at
`storage/models/driver_animal/best.pt` for rollback.

The current v2 model continues from that checkpoint using `driver-animal-v2`,
30 epochs, and 960 px inputs. Under an identical 960 px comparison, test
mAP50–95 improved from 0.632 to 0.650 and recall from 0.838 to 0.847, while
precision changed from 0.916 to 0.893. On the 31 reviewed road-video training
frames, detections matched at confidence 0.25 and IoU 0.50 increased from 0 to
23. The runnable checkpoint and machine-readable record are
`storage/models/driver_animal_v2/best.pt` and
`storage/models/driver_animal_v2/training_summary.json`. These local runtime
artifacts are excluded from version control.

### Hard-negative transfer experiment (v3)

The v3 experiment adds 24 manually reviewed animal-free frames from the Tesla
clip to the training split only, then continues from v2 with a lower learning
rate. Reproduce the training views and run with:

```bash
uv run python -m scripts.extract_video_hard_negatives \
  "data/datasets/Youtube_Deer/Tesla Model 3 Autopilot Hits Deer.mp4" \
  --start-seconds 0 --end-seconds 5.75 --interval-seconds 0.25 \
  --output data/derived/driver-video-hard-negatives-v1
uv run python -m scripts.derive_driver_animal_v2 \
  --dataset-name driver-animal-v3 \
  --output data/derived/driver-animal-v3 \
  --hard-examples data/derived/driver-video-hard-examples-v1 \
  --hard-examples data/derived/driver-video-hard-examples-oh-deer-v1 \
  --hard-examples data/derived/driver-video-hard-negatives-v1
uv run python -m scripts.train_driver_animal_v3
```

The selected epoch reduced Tesla detections from 109 to 46 at confidence 0.10
and removed the false-positive burst near 4.2 seconds while retaining the main
pre-impact detection. Frozen test mAP50–95 moved from 0.650 to 0.647; precision
rose from 0.893 to 0.926 and recall fell from 0.847 to 0.829. On two unseen
clips, manual spot checks found new false alarms on trucks and road structures.
Keep v2 as the default and treat v3 as evidence that narrow hard-negative
tuning helps a known scene but does not replace diverse independent negatives.

### Nano deployment experiment

Train the COCO-initialized YOLO26n model on the same v3 training view without
changing the frozen validation or test splits:

```bash
uv run python -m scripts.train_driver_animal_nano
```

The selected 40-epoch checkpoint contains 2.53 million parameters and occupies
5.5 MB. It scored 0.660 test mAP50–95, 0.873 precision, and 0.838 recall. Under
the same evaluation invocation, YOLO26s v2 scored 0.651, 0.901, and 0.847.
YOLO26n inference was 3.34 ms/image versus 4.50 ms/image for v2 on the RTX 4090
batch benchmark. On Tesla it detects the pre-impact animal from 6.20 seconds
with no earlier false event. Independent video tests show substantially more
low-confidence alerts at 0.10, so begin the live demo at 0.25 and retain
temporal confirmation rather than making every individual box an alert.

## Non-goals for the first MVP

- Equal performance across all 26 wildlife classes.
- Exact deer species identification.
- Exact bear species identification.
- Audio species recognition in the visual detector.
- Production safety guarantees based only on camera-trap or still-image tests.
