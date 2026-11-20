(() => {
  "use strict";

  const hero = document.querySelector(".hero");
  const encounter = hero.querySelector(".encounter");
  const play = hero.querySelector(".encounter-play");
  const openRecord = hero.querySelector(".encounter-record");
  const label = encounter.querySelector(".encounter-label");
  const title = encounter.querySelector(".encounter-title");
  const note = encounter.querySelector(".encounter-note");
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const video = encounter.querySelector(".encounter-video");
  const mute = encounter.querySelector(".encounter-mute");
  const frames = [
    {key:"ready", label:"Simulated encounter", title:"Barred owl at dawn", note:"A fly-in, a call, and a field record. Animated scene with synthesized audio."},
    {key:"audio", label:"1 of 3 · Audio", title:"A call in the canopy", note:"The owl settles on a branch and calls. The call is synthesized."},
    {key:"camera", label:"2 of 3 · Image", title:"A view of the perch", note:"The wider view keeps the owl and the surrounding forest in frame."},
    {key:"record", label:"3 of 3 · Observation", title:"Barred owl", note:"Example audio record · Birch Loop · 08:55"}
  ];
  let current = 0;
  let filmUnavailable = false;

  function stepMode() {
    return reducedMotion.matches || filmUnavailable;
  }

  function updatePlay() {
    const playing = !video.paused && !video.ended;
    const complete = current === frames.length - 1;
    play.dataset.playing = String(playing);
    let text = "Play case with sound";
    if (stepMode()) text = complete ? "Restart encounter" : current ? "Next moment" : "Step through encounter";
    else if (playing) text = "Pause case";
    else if (video.ended) text = "Replay case";
    else if (video.currentTime > 0) text = "Resume case";
    else if (video.muted) text = "Play muted case";
    play.querySelector(".play-label").textContent = text;
  }

  function showFrame(index) {
    if (current === index) return;
    current = index;
    const frame = frames[index];
    encounter.dataset.frame = frame.key;
    label.textContent = frame.label;
    title.textContent = frame.title;
    note.textContent = frame.note;
    openRecord.hidden = frame.key !== "record";
    updatePlay();
  }

  function showStill() {
    video.pause();
    video.hidden = true;
    mute.hidden = true;
    encounter.classList.remove("has-film");
  }

  function filmFallback() {
    if (!video.hasAttribute("src") || filmUnavailable) return;
    filmUnavailable = true;
    showStill();
    showFrame(0);
    note.textContent = "The film could not play. You can step through the illustrated encounter.";
    updatePlay();
  }

  function syncFilm() {
    if (stepMode() || video.hidden) return;
    const time = video.currentTime;
    showFrame(time >= 8.6 ? 3 : time >= 5.16 ? 2 : time >= 2.22 ? 1 : 0);
  }

  play.addEventListener("click", async () => {
    if (stepMode()) {
      showFrame(current === frames.length - 1 ? 1 : current + 1);
      return;
    }
    if (!video.paused && !video.ended) {
      video.pause();
      updatePlay();
      return;
    }
    if (!video.hasAttribute("src")) video.src = video.dataset.src;
    if (video.ended) video.currentTime = 0;
    try {
      await video.play();
    } catch {
      if (!stepMode() && !document.hidden) filmFallback();
    }
  });

  video.addEventListener("playing", () => {
    if (stepMode() || document.hidden) {
      video.pause();
      return;
    }
    video.hidden = false;
    mute.hidden = false;
    encounter.classList.add("has-film");
    syncFilm();
    updatePlay();
  });
  video.addEventListener("pause",updatePlay);
  video.addEventListener("timeupdate",syncFilm);
  video.addEventListener("ended",() => {
    if (stepMode() || video.hidden) return;
    showFrame(3);
    updatePlay();
  });
  video.addEventListener("error",filmFallback);
  mute.addEventListener("click", () => { video.muted = !video.muted; });
  video.addEventListener("volumechange", () => {
    mute.textContent = video.muted ? "Unmute" : "Mute";
    updatePlay();
  });

  reducedMotion.addEventListener("change", () => {
    const refocus = document.activeElement === mute || document.activeElement === openRecord;
    showStill();
    if (video.readyState) video.currentTime = 0;
    showFrame(0);
    updatePlay();
    if (refocus) play.focus();
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) video.pause(); });
  openRecord.addEventListener("click", () => {
    video.pause();
    document.dispatchEvent(new CustomEvent("wildguard:open-observation",{detail:"WG-DEMO-003"}));
  });
  play.hidden = false;
  updatePlay();

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
  const panelSurfaces = ".hero-copy,.encounter,.feature-card,.app-frame,.audience-grid article,.principles-layout > div,.section-heading,.workspace-heading,.editorial-heading";
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
