const API_ORIGIN = "http://127.0.0.1:8010";
const SESSION_KEY = "wildguard.session.events";
const eventsRoot = document.querySelector("#admin-events");
let serverEvents = [];

function readBrowserEvents() {
  try {
    const value = JSON.parse(localStorage.getItem(SESSION_KEY) || "[]");
    return Array.isArray(value)
      ? value.filter((event) => event && typeof event === "object")
      : [];
  } catch {
    return [];
  }
}

function readEvents() {
  return serverEvents.length ? serverEvents : readBrowserEvents();
}

function addText(parent, tag, value, className) {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  parent.append(node);
  return node;
}

function renderEvents() {
  const events = readEvents();
  document.querySelector("#session-count").textContent = String(events.length);
  eventsRoot.replaceChildren();
  if (!events.length) {
    addText(eventsRoot, "div", "Run the hiker audio test or analyze a driver video to populate this local session log.", "admin-empty");
    return;
  }
  events.forEach((event) => {
    const article = document.createElement("article");
    article.className = "admin-event";
    const copy = document.createElement("div");
    addText(copy, "h3", event.result || "Wildlife event");
    addText(copy, "p", `${event.modality} · ${event.model} · ${event.source}`);
    addText(copy, "p", `${new Date(event.created_at).toLocaleString()} · score ${Number(event.score || 0).toFixed(3)}${event.cached ? " · cached" : ""}`);
    addText(article, "span", event.decision || "RECORDED", "event-badge");
    article.prepend(copy);
    const flow = document.createElement("div");
    flow.className = "admin-event-flow";
    const steps = Array.isArray(event.flow) ? event.flow : [];
    steps.forEach((step, index) => {
      addText(flow, "span", step);
      if (index < steps.length - 1) addText(flow, "i", "→");
    });
    article.append(flow);
    eventsRoot.append(article);
  });
}

function downloadName(response, format) {
  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return match?.[1] || `wildguard-session.${format === "ai" ? "md" : format}`;
}

async function exportSession(format, button) {
  const status = document.querySelector("#export-status");
  const original = button.querySelector("strong").textContent;
  button.disabled = true;
  button.querySelector("strong").textContent = format === "ai" ? "Generating locally…" : "Preparing…";
  status.textContent = format === "ai"
    ? "Qwen2.5-Coder 7B is reviewing a read-only copy of the session records…"
    : `Preparing the deterministic ${format.toUpperCase()} export…`;
  try {
    const response = await fetch(`${API_ORIGIN}/session/events/export?format=${format}`, {cache: "no-store"});
    if (!response.ok) {
      let message = `Export failed (${response.status})`;
      try {
        const payload = await response.json();
        if (payload.detail) message = payload.detail;
      } catch {
        // The API may return a non-JSON proxy error.
      }
      throw new Error(message);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = downloadName(response, format);
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    status.textContent = format === "ai"
      ? `AI report downloaded · ${response.headers.get("x-wildguard-model") || "local model"} · source logs unchanged.`
      : `${format.toUpperCase()} session log downloaded.`;
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "Export failed.";
  } finally {
    button.disabled = false;
    button.querySelector("strong").textContent = original;
  }
}

async function refreshHealth() {
  const runtime = document.querySelector("#runtime-status");
  try {
    const [healthResponse, eventsResponse] = await Promise.all([
      fetch(`${API_ORIGIN}/health`, {cache: "no-store"}),
      fetch(`${API_ORIGIN}/session/events?limit=50`, {cache: "no-store"}),
    ]);
    if (!healthResponse.ok) throw new Error(`API ${healthResponse.status}`);
    const health = await healthResponse.json();
    serverEvents = eventsResponse.ok ? await eventsResponse.json() : [];
    document.querySelector("#api-status").textContent = "Online";
    document.querySelector("#video-cache").textContent = Number.isInteger(health.persistent_video_cache_size)
      ? `${health.video_cache_size} / ${health.persistent_video_cache_size}`
      : "Restart API";
    document.querySelector("#description-queue").textContent = String(health.description_queue_size ?? "—");
    runtime.className = "runtime-status online";
    runtime.innerHTML = "<i></i> Local API online";
  } catch {
    serverEvents = [];
    document.querySelector("#api-status").textContent = "Offline";
    document.querySelector("#video-cache").textContent = "—";
    document.querySelector("#description-queue").textContent = "—";
    runtime.className = "runtime-status offline";
    runtime.innerHTML = "<i></i> Local API unavailable";
  }
  renderEvents();
}

document.querySelector("#refresh-admin").addEventListener("click", refreshHealth);
document.querySelectorAll("[data-export-format]").forEach((button) => {
  button.addEventListener("click", () => exportSession(button.dataset.exportFormat, button));
});
document.querySelector("#clear-events").addEventListener("click", async () => {
  localStorage.removeItem(SESSION_KEY);
  try {
    const response = await fetch(`${API_ORIGIN}/session/events`, {method: "DELETE"});
    if (!response.ok) throw new Error(`API ${response.status}`);
    serverEvents = [];
  } catch {
    // Keep the page usable when the local API is not running.
  }
  renderEvents();
});
window.addEventListener("storage", renderEvents);
refreshHealth();
