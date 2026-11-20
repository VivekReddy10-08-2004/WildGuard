# Driver client

Owns short driving-video upload, synchronized original/annotated playback,
backend-evaluated alert display, and source-grounded encounter guidance. It
uploads through `POST /videos/analyze`; the returned annotated WebM is served
from the local evidence route.

The hero includes a lightweight CSS/SVG explainer that loops through road
scanning, animal detection, and driver warning. It is decorative, does not
represent live sensor state, and becomes a static final frame when reduced
motion is enabled.

The runtime warms YOLO once at API startup and samples every second source frame
through one streaming FP16 call on CUDA. The alert and guidance return before
the 720p annotated preview finishes rendering; the browser polls the local
evidence route and attaches the preview when it is complete. Source video
resolution and detection coordinates remain unchanged.

The API keeps the eight most recent video responses in a process-local LRU
cache keyed by video bytes and detector configuration. Re-uploading identical
content reuses its event and evidence URLs even when the filename changes.

When the event contains an `animal` detection, the client automatically sends
its road-overlap context to `POST /guidance`. Generic detector labels receive
only reviewed species-neutral roadway passages. A future confirmed-species
flow can select species-specific guidance.

The client displays decisions; it does not calculate or override alert levels.
