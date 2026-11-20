(() => {
  "use strict";

  const API_ORIGIN = "http://127.0.0.1:8010";
  const hero = document.querySelector(".hero");
  const demo = hero.querySelector(".hiker-demo");
  const demoButton = hero.querySelector("#field-demo-button");
  const upload = hero.querySelector("#field-audio-upload");
  const uploadLabel = hero.querySelector(".audio-upload");
  const audio = hero.querySelector("#field-audio");
  const audioToggle = hero.querySelector("#field-audio-toggle");
  const phoneState = hero.querySelector("#phone-state");
  const phoneSpecies = hero.querySelector("#phone-species");
  const phoneDetail = hero.querySelector("#phone-detail");
  const watchState = hero.querySelector("#watch-state");
  const watchSpecies = hero.querySelector("#watch-species");
  const watchNote = hero.querySelector("#watch-note");
  const resultTitle = hero.querySelector("#field-result-title");
  const resultNote = hero.querySelector("#field-result-note");
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const demoAudioUrl = audio.src;
  let uploadedAudioUrl = "";

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

  function speciesLabel(value) {
    return value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());
  }

  function setBusy(busy) {
    demoButton.disabled = busy;
    upload.disabled = busy;
    uploadLabel.setAttribute("aria-disabled", String(busy));
    demoButton.querySelector(".play-label").textContent = busy ? "Analyzing locally…" : "Run coyote field test";
  }

  function showAnalyzing(filename) {
    demo.dataset.state = "analyzing";
    phoneState.textContent = "Analyzing locally";
    phoneSpecies.textContent = "Listening…";
    phoneDetail.textContent = filename;
    watchState.textContent = "ANALYZING";
    watchSpecies.textContent = "Sound nearby";
    watchNote.textContent = "Local model";
    resultTitle.textContent = "AnimalCLAP is listening";
    resultNote.textContent = "The audio is processed on this machine.";
  }

  function showResult(analysis) {
    const species = speciesLabel(analysis.possible_species);
    demo.dataset.state = "detected";
    phoneState.textContent = "Possible wildlife sound";
    phoneSpecies.textContent = species;
    phoneDetail.textContent = `Similarity ${analysis.similarity.toFixed(3)} · margin ${analysis.score_margin.toFixed(3)}`;
    watchState.textContent = "CAUTION";
    watchSpecies.textContent = `${species} possible`;
    watchNote.textContent = "Stay aware";
    resultTitle.textContent = `Possible species: ${species}`;
    resultNote.textContent = "Advisory similarity result—not a probability or confirmed identification.";
  }

  function showError(message) {
    demo.dataset.state = "error";
    phoneState.textContent = "Analysis unavailable";
    phoneSpecies.textContent = "Try again";
    phoneDetail.textContent = message;
    watchState.textContent = "MODEL OFFLINE";
    watchSpecies.textContent = "No result";
    watchNote.textContent = "Check service";
    resultTitle.textContent = "Local inference did not complete";
    resultNote.textContent = message;
  }

  async function analyzeAudio(file) {
    setBusy(true);
    showAnalyzing(file.name);
    const body = new FormData();
    body.append("audio", file);
    try {
      const response = await fetch(`${API_ORIGIN}/audio/analyze`, {method:"POST", body});
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `Audio API returned ${response.status}`);
      }
      const payload = await response.json();
      showResult(payload.analysis);
      rememberSessionEvent({
        id: payload.audio_id,
        created_at: new Date().toISOString(),
        modality: "Audio",
        source: file.name,
        result: `Possible ${speciesLabel(payload.analysis.possible_species)}`,
        model: "AnimalCLAP",
        score: payload.analysis.similarity,
        decision: "CAUTION",
        cached: false,
        flow: ["Audio clip", "AnimalCLAP", "Species ranking", "Caution", "Phone + watch"],
      });
    } catch (error) {
      showError(error.message);
    } finally {
      setBusy(false);
      upload.value = "";
    }
  }

  demoButton.addEventListener("click", async () => {
    audio.src = demoAudioUrl;
    audio.currentTime = 0;
    audio.play().catch(() => {});
    try {
      const response = await fetch(audio.src);
      if (!response.ok) throw new Error("Demo audio could not be loaded");
      const blob = await response.blob();
      await analyzeAudio(new File([blob], "coyote-field-demo.ogg", {type:blob.type || "audio/ogg"}));
    } catch (error) {
      showError(error.message);
      setBusy(false);
    }
  });

  upload.addEventListener("change", () => {
    const file = upload.files[0];
    if (!file) return;
    if (uploadedAudioUrl) URL.revokeObjectURL(uploadedAudioUrl);
    uploadedAudioUrl = URL.createObjectURL(file);
    audio.src = uploadedAudioUrl;
    audio.play().catch(() => {});
    analyzeAudio(file);
  });

  audioToggle.addEventListener("click", () => {
    if (audio.paused) {
      if (audio.ended) audio.currentTime = 0;
      audio.play().catch(() => {});
    } else {
      audio.pause();
    }
  });
  audio.addEventListener("play", () => {
    audioToggle.disabled = false;
    audioToggle.textContent = "Pause audio";
  });
  audio.addEventListener("pause", () => {
    audioToggle.textContent = audio.ended ? "Replay audio" : "Resume audio";
  });
  audio.addEventListener("ended", () => {
    audioToggle.disabled = false;
    audioToggle.textContent = "Replay audio";
  });

  document.addEventListener("visibilitychange", () => { if (document.hidden) audio.pause(); });

  const trailStops = [...document.querySelectorAll(".hoof-stop")].map(link => ({
    link,
    section:document.getElementById(link.hash.slice(1))
  }));
  let activeStop = -1;
  let trailFrame = 0;

  function updateTrail() {
    trailFrame = 0;
    let next = 0;
    for (let index = 0; index < trailStops.length; index++) {
      if (trailStops[index].section.getBoundingClientRect().top <= innerHeight * .35) next = index;
    }
    if (window.scrollY > 0 && window.scrollY + innerHeight >= document.documentElement.scrollHeight - 2) {
      next = trailStops.length - 1;
    }
    if (next === activeStop) return;
    trailStops.forEach(({link},index) => {
      link.classList.toggle("is-passed",index <= next);
      if (index === next) link.setAttribute("aria-current","location");
      else link.removeAttribute("aria-current");
    });
    activeStop = next;
  }

  function scheduleTrail() {
    if (!trailFrame) trailFrame = requestAnimationFrame(updateTrail);
  }
  addEventListener("scroll",scheduleTrail,{passive:true});
  addEventListener("resize",scheduleTrail);
  addEventListener("load",scheduleTrail);
  updateTrail();

  for (const card of document.querySelectorAll(".feature-card")) {
    const trigger = card.querySelector(".feature-replay");
    let finish;
    trigger.addEventListener("click", () => {
      clearTimeout(finish);
      card.classList.remove("is-replaying");
      void card.offsetWidth;
      card.classList.add("is-replaying");
      finish = setTimeout(() => card.classList.remove("is-replaying"), 1050);
    });
  }

  // The texture is static; pointer and click effects reveal portions of it.
  const panelSurfaces = ".hero-copy,.hiker-demo,.feature-card,.app-frame,.audience-grid article,.principles-layout > div,.section-heading,.workspace-heading,.editorial-heading";
  const ringSections = [...document.querySelectorAll("main > section")];
  let waves = [];
  function clearWaves() {
    for (const {layer,animation} of waves) {
      animation.cancel();
      layer.remove();
    }
    waves = [];
  }
  reducedMotion.addEventListener("change",clearWaves);

  function pulseFrom(event) {
    if (reducedMotion.matches || event.target.closest(panelSurfaces + ",a,button,summary,input,label")) return;
    clearWaves();
    const bounds = ringSections.map(section => section.getBoundingClientRect());
    const {clientX:x,clientY:y} = event;
    const reach = Math.ceil(Math.max(...bounds.flatMap(box => [
      Math.hypot(box.left-x,box.top-y), Math.hypot(box.right-x,box.top-y),
      Math.hypot(box.left-x,box.bottom-y), Math.hypot(box.right-x,box.bottom-y)
    ])) + 150);
    const duration = Math.min(3200,Math.max(1100,reach / 1.6));
    waves = ringSections.map((section,index) => {
      const layer = document.createElement("span");
      layer.className = "grain-wave";
      layer.setAttribute("aria-hidden","true");
      layer.style.setProperty("--wave-x",x - bounds[index].left + "px");
      layer.style.setProperty("--wave-y",y - bounds[index].top + "px");
      section.prepend(layer);
      const animation = layer.animate([
        {offset:0,"--wave-radius":"0px",opacity:.17},
        {offset:.10,"--wave-radius":reach * .10 + "px",opacity:.46},
        {offset:.78,"--wave-radius":reach * .78 + "px",opacity:.35},
        {offset:1,"--wave-radius":reach + "px",opacity:0}
      ],{duration,easing:"linear"});
      animation.addEventListener("finish",() => {
        layer.remove();
        waves = waves.filter(wave => wave.animation !== animation);
      },{once:true});
      return {layer,animation};
    });
  }

  for (const section of ringSections) {
    let pointerFrame = 0;
    let pointerX = 0;
    let pointerY = 0;

    function clearHighlight() {
      cancelAnimationFrame(pointerFrame);
      pointerFrame = 0;
      section.classList.remove("has-grain-focus");
    }

    section.addEventListener("pointermove", event => {
      if (event.pointerType === "touch" || event.target.closest(panelSurfaces)) {
        clearHighlight();
        return;
      }
      pointerX = event.clientX;
      pointerY = event.clientY;
      if (pointerFrame) return;
      pointerFrame = requestAnimationFrame(() => {
        pointerFrame = 0;
        const bounds = section.getBoundingClientRect();
        section.style.setProperty("--ring-x",(pointerX - bounds.left) + "px");
        section.style.setProperty("--ring-y",(pointerY - bounds.top) + "px");
        section.classList.add("has-grain-focus");
      });
    },{passive:true});
    section.addEventListener("click",pulseFrom);
    section.addEventListener("pointerleave",clearHighlight);
  }
})();
