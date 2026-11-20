const API_ORIGIN = "http://127.0.0.1:8010";
const form = document.querySelector("#video-form");
const fileInput = document.querySelector("#video-file");
const status = document.querySelector("#analysis-status");
const comparison = document.querySelector("#video-comparison");
const original = document.querySelector("#original-video");
const annotated = document.querySelector("#annotated-video");
const decisionPanel = document.querySelector("#decision-panel");
const guidanceResult = document.querySelector("#guidance-result");
let originalUrl;

function rememberSessionEvent(event) {
  const key = "wildguard.session.events";
  let events = [];
  try {
    const stored = JSON.parse(localStorage.getItem(key) || "[]");
    if (Array.isArray(stored)) events = stored;
  } catch {}
  events.unshift(event);
  localStorage.setItem(key, JSON.stringify(events.slice(0, 20)));
}

function addText(parent, tag, text) {
  const node = document.createElement(tag);
  node.textContent = text;
  parent.append(node);
  return node;
}

function renderGuidance(payload) {
  guidanceResult.replaceChildren();
  addText(guidanceResult, "strong", payload.message);
  if (payload.status !== "supported") return;

  const guidance = document.createElement("ul");
  payload.guidance.forEach((text) => addText(guidance, "li", text));
  guidanceResult.append(guidance);

  const sources = document.createElement("div");
  addText(sources, "strong", "Sources: ");
  payload.sources.forEach((source, index) => {
    if (index) sources.append(document.createTextNode(" · "));
    const link = document.createElement("a");
    const url = new URL(source.url);
    link.href = url.protocol === "https:" ? url.href : "#";
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = `${source.title} — ${source.section}`;
    sources.append(link);
  });
  guidanceResult.append(sources);
}

function renderDecision(event) {
  const detections = event.detections;
  const bestConfidence = detections.length
    ? Math.max(...detections.map((item) => item.max_confidence))
    : 0;
  decisionPanel.replaceChildren();
  addText(decisionPanel, "h2", `Alert: ${event.decision.alert_level}`);
  addText(
    decisionPanel,
    "p",
    `${detections.length} tracked animal${detections.length === 1 ? "" : "s"} · highest confidence ${(bestConfidence * 100).toFixed(0)}%`,
  );
  if (event.decision.reason_codes.length) {
    addText(decisionPanel, "p", `Reason: ${event.decision.reason_codes.join(", ")}`);
  }
  decisionPanel.hidden = false;
}

async function loadAutomaticGuidance(event) {
  if (!event.detections.length) {
    guidanceResult.textContent = "No animal was detected, so no encounter guidance was selected.";
    return;
  }
  guidanceResult.textContent = "Selecting verified guidance for this encounter…";
  const roadOverlap = event.detections.some((item) => item.road_overlap);
  const response = await fetch(`${API_ORIGIN}/guidance`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event_id: event.event_id,
      species: "animal",
      species_source: "detector",
      user_context: "driver",
      scene_context: roadOverlap ? "roadway" : "roadside",
      jurisdiction: "US-ME",
      question: "What should I do?",
    }),
  });
  if (!response.ok) throw new Error(`Guidance API returned ${response.status}`);
  renderGuidance(await response.json());
}

function synchronizeVideos() {
  if (Math.abs(annotated.currentTime - original.currentTime) > 0.15) {
    annotated.currentTime = original.currentTime;
  }
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForAnnotatedVideo(url) {
  for (let attempt = 0; attempt < 240; attempt += 1) {
    const response = await fetch(`${url}?ready=${Date.now()}`, {
      method: "HEAD",
      cache: "no-store",
    });
    if (response.ok) return;
    await delay(500);
  }
  throw new Error("Annotated preview did not finish in time");
}

original.addEventListener("play", () => {
  synchronizeVideos();
  annotated.playbackRate = original.playbackRate;
  annotated.play().catch(() => {});
});
original.addEventListener("pause", () => annotated.pause());
original.addEventListener("seeking", synchronizeVideos);
original.addEventListener("timeupdate", synchronizeVideos);
original.addEventListener("ratechange", () => {
  annotated.playbackRate = original.playbackRate;
});
original.addEventListener("ended", () => annotated.pause());

fileInput.addEventListener("change", () => {
  if (originalUrl) URL.revokeObjectURL(originalUrl);
  const file = fileInput.files[0];
  if (!file) return;
  originalUrl = URL.createObjectURL(file);
  original.src = originalUrl;
  annotated.removeAttribute("src");
  annotated.load();
  comparison.hidden = false;
  decisionPanel.hidden = true;
  status.textContent = "Original loaded. Select Detect animals to create the comparison.";
  guidanceResult.textContent = "Guidance will appear after video analysis detects an animal.";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;
  const button = form.querySelector("button");
  const upload = new FormData();
  upload.append("video", file);
  button.disabled = true;
  status.textContent = "Running local animal detection…";
  try {
    const response = await fetch(`${API_ORIGIN}/videos/analyze`, {
      method: "POST",
      body: upload,
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `Video API returned ${response.status}`);
    }
    const analysis = await response.json();
    if (!analysis.annotated_video_url) throw new Error("No annotated video was created");
    comparison.hidden = false;
    renderDecision(analysis.event);
    const bestConfidence = analysis.event.detections.length
      ? Math.max(...analysis.event.detections.map((item) => item.max_confidence))
      : 0;
    rememberSessionEvent({
      id: analysis.event.event_id,
      created_at: new Date().toISOString(),
      modality: "Video",
      source: analysis.filename,
      result: `${analysis.event.detections.length} tracked animal${analysis.event.detections.length === 1 ? "" : "s"}`,
      model: "YOLO26n + ByteTrack",
      score: bestConfidence,
      decision: analysis.event.decision.alert_level,
      cached: analysis.cached,
      flow: ["Road video", "YOLO26n", "ByteTrack", "Decision engine", "Alert + guidance"],
    });
    const resultSource = analysis.cached
      ? "Previously analyzed — reused the local detection result."
      : `Detection complete: analyzed ${analysis.processed_frames} sampled frames.`;
    status.textContent = `${resultSource} Rendering the annotated preview for ${analysis.duration_seconds.toFixed(1)} seconds of video…`;
    loadAutomaticGuidance(analysis.event).catch((error) => {
      guidanceResult.textContent = `Guidance service unavailable. ${error.message}`;
    });

    const annotatedUrl = new URL(analysis.annotated_video_url, API_ORIGIN).href;
    waitForAnnotatedVideo(annotatedUrl)
      .then(() => {
        original.pause();
        original.currentTime = 0;
        annotated.src = annotatedUrl;
        annotated.load();
        status.textContent = `${analysis.cached ? "Cached detection" : "Detection"} and annotated preview ready. Use the Original controls to play both views together.`;
      })
      .catch((error) => {
        status.textContent = `Detection completed, but the annotated preview failed: ${error.message}`;
      });
  } catch (error) {
    status.textContent = `Analysis failed: ${error.message}`;
    guidanceResult.textContent = "Guidance is unavailable because video analysis did not complete.";
  } finally {
    button.disabled = false;
  }
});
