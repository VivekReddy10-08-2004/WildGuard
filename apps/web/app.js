/* This workspace is illustrative; the hiker hero above it owns real audio inference. */
(() => {
  "use strict";
  const records = [
    {id:"WG-DEMO-001",name:"Moose",emoji:"🫎",kind:"Camera",confidence:94,time:"09:42",date:"Nov 20, 2026",area:"North Ridge",risk:"Observe from a distance",x:29,y:33},
    {id:"WG-DEMO-002",name:"Red fox",emoji:"🦊",kind:"Camera",confidence:89,time:"09:18",date:"Nov 20, 2026",area:"Pine Trail",risk:"No hazard determined",x:68,y:54},
    {id:"WG-DEMO-003",name:"Coyote",emoji:"🐺",kind:"Audio",confidence:87,time:"08:55",date:"Nov 20, 2026",area:"Birch Loop",risk:"Possible species; stay aware",x:50,y:72},
    {id:"WG-DEMO-004",name:"White-tailed deer",emoji:"🦌",kind:"Camera",confidence:96,time:"08:27",date:"Nov 20, 2026",area:"Fern Crossing",risk:"No hazard determined",x:81,y:27},
    {id:"WG-DEMO-005",name:"Grizzly bear",emoji:"🐻",kind:"Audio",confidence:72,time:"07:48",date:"Nov 20, 2026",area:"Cedar Grove",risk:"Possible species; do not infer danger",x:22,y:71},
    {id:"WG-DEMO-006",name:"Wolf",emoji:"🐺",kind:"Audio",confidence:91,time:"07:12",date:"Nov 20, 2026",area:"West Meadow",risk:"Possible species; stay aware",x:58,y:18}
  ];
  const defaults = {view:"overview",filter:"All",search:"",share:false,history:true,sound:false};
  const state = {...defaults};
  const root = document.getElementById("workspace-content");
  const labels = {overview:"Overview",detections:"Detections",insights:"Insights",assistant:"Field guide",privacy:"Privacy & consent"};
  const escapeHTML = s => String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const flowSteps=r=>r.kind==="Audio"?["Audio clip","FastAPI","AnimalCLAP","Species ranking","Event contract","Phone + watch caution"]:["Video / image","FastAPI","YOLO26n + ByteTrack","Decision engine","SmolVLM2","Evidence + guidance"];
  const eventFlow=r=>`<div class="event-flow" aria-label="${r.kind} event processing flow">${flowSteps(r).map((step,index)=>`<span><small>${String(index+1).padStart(2,"0")}</small>${step}</span>${index<flowSteps(r).length-1?'<i aria-hidden="true">→</i>':""}`).join("")}</div>`;
  let toastTimer;
  function toast(message){const el=document.getElementById("toast");el.textContent=message;el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{el.hidden=true},3300);}
  const header=(k,title,subtitle,action="")=>`<div class="app-title-row"><div><p class="app-eyebrow">${k}</p><h2 class="app-title">${title}</h2><p class="app-subtitle">${subtitle}</p></div>${action}</div>`;
  const eventRow=r=>`<div class="event-row"><span class="event-emoji" aria-hidden="true">${r.emoji}</span><div class="event-row-info"><strong>${escapeHTML(r.name)}</strong><small>${r.kind} · ${r.time}</small></div><div class="event-score">${r.confidence}%</div>${eventFlow(r)}</div>`;
  function overview(){return header("GOOD MORNING, EXPLORER","Your field overview","See how observations are captured, processed, and turned into local alerts.",'<button class="app-button" data-action="view-detections">View all detections ↗</button>')+
    `<div class="stats-grid"><div class="stat-card"><div class="stat-label">Observations <span>◎</span></div><div class="stat-value">06</div><div class="stat-foot">Logged encounters</div></div><div class="stat-card"><div class="stat-label">Species recorded <span>✳</span></div><div class="stat-value">06</div><div class="stat-foot">Distinct species</div></div><div class="stat-card"><div class="stat-label">Sensors connected <span>◉</span></div><div class="stat-value">00</div><div class="stat-foot">Sensors disconnected</div></div></div>
    <div class="dashboard-grid"><div class="panel"><div class="panel-title"><div><h3>Application event map</h3><small>How WildGuard turns field evidence into useful local awareness</small></div><span class="map-live-label">LOCAL PIPELINES</span></div><div class="function-map" role="group" aria-label="WildGuard audio and video application workflows">
      <article class="function-lane audio-lane"><header><span>ON FOOT</span><strong>Hear wildlife nearby</strong></header><button class="function-evidence" data-record="WG-DEMO-003" aria-label="Open the sample coyote audio event"><i aria-hidden="true">♫</i><span><small>Audio evidence</small><b>Possible coyote call</b></span><em>87%</em></button><div class="function-rail" aria-label="Audio processing stages"><span>Microphone</span><i>→</i><span>AnimalCLAP</span><i>→</i><span>Species ranking</span></div><footer><b>CAUTION</b><span>Mirrored to phone + watch</span></footer></article>
      <div class="function-contract" aria-label="Shared event contract"><span>SHARED EVENT</span><strong>Evidence + timestamp</strong><small>Local · reviewable · private</small></div>
      <article class="function-lane video-lane"><header><span>ON THE ROAD</span><strong>See animals ahead</strong></header><button class="function-evidence" data-record="WG-DEMO-004" aria-label="Open the sample deer camera event"><i aria-hidden="true">▣</i><span><small>Road video</small><b>Animal tracked ahead</b></span><em>96%</em></button><div class="function-rail" aria-label="Video processing stages"><span>Video</span><i>→</i><span>YOLO26n</span><i>→</i><span>ByteTrack</span></div><footer><b>WARNING</b><span>Alert + annotated evidence</span></footer></article>
      <div class="function-guidance"><span>VERIFIED GUIDANCE</span><strong>Decision engine acts on structured evidence</strong><small>SmolVLM descriptions stay advisory and cannot create or suppress the alert.</small></div>
    </div></div>
    <div class="panel"><div class="panel-title"><h3>Recent observations</h3><button class="app-button" data-action="view-detections">See all ↗</button></div>${records.slice(0,5).map(eventRow).join("")}</div></div>`;}
  function detections(){let list=records.filter(r=>(state.filter==="All"||r.kind===state.filter)&&(`${r.name} ${r.kind} ${r.area}`.toLowerCase().includes(state.search.toLowerCase())));return header("OBSERVATION EXPLORER","Detections","Find an observation and open its record.",'<button class="app-button" data-action="export">Export all observations ↓</button>')+
   `<div class="filter-row" role="group" aria-label="Filter by detection type">${["All","Camera","Audio"].map(f=>`<button class="filter-chip ${state.filter===f?"active":""}" data-filter="${f}" aria-pressed="${state.filter===f}">${f==="All"?"All types":f}</button>`).join("")}<input class="search-field" id="event-search" type="search" placeholder="Search observations…" aria-label="Search detections" value="${escapeHTML(state.search)}" /></div><div class="event-list">${list.length?list.map(r=>`<article class="event-card"><span class="event-emoji" aria-hidden="true">${r.emoji}</span><div class="event-details"><h3>${escapeHTML(r.name)}</h3><p>${r.id} · ${r.area}</p><div class="event-detail-meta"><span>◷ ${r.time}</span><span>◎ ${r.kind}</span></div></div><div><strong style="font-size:12px">${r.confidence}%</strong><div class="score-bar"><i style="width:${r.confidence}%"></i></div></div><button class="app-button" data-record="${r.id}">Details ↗</button>${eventFlow(r)}</article>`).join(""):'<div class="empty-state">No observations match. Try another filter or search.</div>'}</div>`;}
  function insights(){const counts=[3,6,4,8,5,7,6];return header("PATTERNS & CONTEXT","Field insights","Review activity and how observations were captured.",'<button class="app-button" data-action="export">Export all observations ↓</button>')+
  `<div class="stats-grid"><div class="stat-card"><div class="stat-label">Observations in the log</div><div class="stat-value">06</div><div class="stat-foot">Current log</div></div><div class="stat-card"><div class="stat-label">Capture modalities</div><div class="stat-value">02</div><div class="stat-foot">Camera and audio</div></div><div class="stat-card"><div class="stat-label">Live data sources</div><div class="stat-value">00</div><div class="stat-foot">Backend disconnected</div></div></div><div class="dashboard-grid"><div class="panel"><div class="panel-title"><h3>Activity over seven days</h3></div><div class="insight-chart" role="img" aria-label="Observations from Monday to Sunday: 3, 6, 4, 8, 5, 7, and 6">${counts.map((v,i)=>`<div class="chart-col"><span style="height:${v*11}%"></span><small>${["M","T","W","T","F","S","S"][i]} · ${v}</small></div>`).join("")}</div><p class="chart-legend">Observations per day</p></div><div class="panel"><div class="panel-title"><h3>Capture methods</h3><small>6 observations</small></div><div style="padding-top:13px"><div class="detail-line"><span>◉ Camera</span><strong>3 (50%)</strong></div><div class="detail-line"><span>♫ Audio</span><strong>3 (50%)</strong></div><div class="detail-line"><span>Consented research events</span><strong>0 connected</strong></div><div class="detail-line"><span>Active model services</span><strong>0 connected</strong></div></div></div></div>`;}
  function privacy(){return header("YOUR DATA, YOUR CHOICE","Privacy & consent","Manage your field preferences.")+
  `<div class="privacy-card"><div><h3>Share observations for research</h3><p>Choose whether observations can be shared for research.</p></div><button type="button" class="toggle" role="switch" aria-label="Share observations for research demo preference" aria-checked="${state.share}" data-toggle="share"><span></span></button></div>
  <div class="privacy-card"><div><h3>Keep personal event history</h3><p>Choose whether to keep a personal encounter history.</p></div><button type="button" class="toggle" role="switch" aria-label="Keep personal history demo preference" aria-checked="${state.history}" data-toggle="history"><span></span></button></div>
  <div class="privacy-card"><div><h3>Enable alert sounds</h3><p>Choose whether alerts should have sound.</p></div><button type="button" class="toggle" role="switch" aria-label="Alert sounds demo preference" aria-checked="${state.sound}" data-toggle="sound"><span></span></button></div><button class="app-button" data-action="reset">Reset demo preferences ↻</button>`;}
  function assistant(){return header("LOCAL FIELD GUIDE","Ask the field guide","Look up observations or ask how the field workspace works.")+
  `<div class="chatbox"><div class="chat-messages" id="chat-messages"><div class="message"><small>FIELD GUIDE</small>Ask about recent observations, using WildGuard offline, or privacy preferences.</div></div><form class="chat-compose" id="demo-chat-form"><input id="demo-chat-input" maxlength="240" autocomplete="off" required aria-label="Message to field guide" placeholder="Ask about an observation…" /><button type="submit">Send ↗</button></form></div><div class="suggestion-row"><button data-question="What species are in the examples?">Species recorded</button><button data-question="How does privacy work?">Privacy approach</button><button data-question="Does this work offline?">Offline architecture</button></div>`;}
  function render(){document.querySelectorAll(".side-link").forEach(b=>{const on=b.dataset.view===state.view;b.classList.toggle("active",on);if(on)b.setAttribute("aria-current","true");else b.removeAttribute("aria-current");});document.getElementById("current-view-label").textContent=labels[state.view];root.innerHTML=({overview,detections,insights,assistant,privacy}[state.view])();const status=document.querySelector(".no-results-status");status.textContent=state.view==="detections"?(root.querySelector(".empty-state")?.textContent||root.querySelectorAll(".event-card").length+" observations found"):"";}
  function showView(v){if(!labels[v])return;state.view=v;state.search="";state.filter="All";render();}
  function showRecord(id, opener = document.activeElement){
    const record = records.find(item => item.id === id);
    if (!record || document.querySelector(".detail-modal-native")) return;
    const modal = document.createElement("dialog");
    modal.className = "detail-modal-native";
    modal.setAttribute("aria-labelledby", "observation-title");
    modal.setAttribute("aria-describedby", "demo-disclosure");
    modal.innerHTML = '<form method="dialog"><button class="modal-close" aria-label="Close observation" autofocus>×</button></form><p class="app-eyebrow"></p><h2 id="observation-title"></h2><dl></dl>';
    modal.querySelector(".app-eyebrow").textContent = record.id;
    modal.querySelector("h2").textContent = record.emoji + " " + record.name;
    const details = [["Modality",record.kind],["Classification score",record.confidence+"%"],["Observed at",record.date+", "+record.time],["Area",record.area],["Context",record.risk]];
    for (const [label,value] of details) {
      const row = document.createElement("div");
      row.className = "detail-line";
      const term = document.createElement("dt"), info = document.createElement("dd");
      term.textContent = label;
      info.textContent = value;
      row.append(term,info);
      modal.querySelector("dl").append(row);
    }
    modal.insertAdjacentHTML("beforeend",eventFlow(record));
    modal.addEventListener("close",() => {
      modal.remove();
      if(opener?.isConnected) opener.focus();
    });
    modal.addEventListener("click",event => {
      const box = modal.getBoundingClientRect();
      if(event.target===modal&&(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)) modal.close();
    });
    document.body.append(modal);
    modal.showModal();
  }
  document.addEventListener("wildguard:open-observation", event => {
    showView("detections");
    const opener = [...root.querySelectorAll("[data-record]")].find(button => button.dataset.record === event.detail);
    if (!opener) return;
    document.getElementById("workspace").scrollIntoView({behavior:"instant"});
    showRecord(event.detail,opener);
  });
  function exportCSV(){const cols=["id","name","kind","confidence","time","date","area"];const csv=["# SYNTHETIC WILDGUARD DEMO DATA — NOT REAL DETECTIONS",cols.join(","),...records.map(r=>cols.map(c=>'"'+String(r[c]).replace(/"/g,'""')+'"').join(","))].join("\r\n");const url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));const a=document.createElement("a");a.href=url;a.download="wildguard-demo-synthetic-observations.csv";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),500);toast("Synthetic sample CSV exported.");}
  function scriptedResponse(q){const s=q.toLowerCase();if(/privacy|consent|share|data/.test(s))return "WildGuard's intended architecture is private by default. Research access must require explicit consent and be checked by the backend. The demo switches do not update real permissions.";if(/offline|internet|cloud|local/.test(s))return "The repository describes a local-first system using on-device or local hardware, without required cloud service dependencies. This page itself is a static frontend demo.";if(/species|animal|example|sighting|detection/.test(s))return "The observation log includes moose, red fox, coyote, white-tailed deer, grizzly bear, and wolf.";return "I don't have an answer in the field guide for that question.";}
  root.addEventListener("click",e=>{const record=e.target.closest("[data-record]");if(record)return showRecord(record.dataset.record,record);const filter=e.target.closest("[data-filter]");if(filter){state.filter=filter.dataset.filter;render();root.querySelector("[data-filter="+state.filter+"]").focus({preventScroll:true});return;}const toggle=e.target.closest("[data-toggle]");if(toggle){const key=toggle.dataset.toggle;state[key]=!state[key];toggle.setAttribute("aria-checked",String(state[key]));toast("Preference updated.");return;}const action=e.target.closest("[data-action]");if(action){if(action.dataset.action==="export")return exportCSV();if(action.dataset.action==="view-detections"){showView("detections");root.querySelector("#event-search").focus({preventScroll:true});return;}if(action.dataset.action==="reset"){Object.assign(state,{share:false,history:true,sound:false});render();root.querySelector("[data-action=reset]").focus({preventScroll:true});return toast("Preferences reset.");}}const q=e.target.closest("[data-question]");if(q){addChat(q.dataset.question);}});
  root.addEventListener("input",e=>{if(e.target.id==="event-search"){const caret=e.target.selectionStart;state.search=e.target.value;render();const input=document.getElementById("event-search");input.focus();input.setSelectionRange(caret,caret);}});
  root.addEventListener("submit",e=>{if(e.target.id==="demo-chat-form"){e.preventDefault();const input=document.getElementById("demo-chat-input");const q=input.value.trim();if(q)addChat(q);input.value="";}});
  function addChat(q){const messages=document.getElementById("chat-messages");if(!messages)return;for(const [who,msg] of [["user",q],["bot",scriptedResponse(q)]]){const node=document.createElement("div");node.className="message"+(who==="user"?" user":"");const lbl=document.createElement("small");lbl.textContent=who==="user"?"YOU":"FIELD GUIDE";node.append(lbl,document.createTextNode(msg));messages.append(node);}messages.scrollTop=messages.scrollHeight;}
  document.querySelectorAll("[data-view]").forEach(b=>b.addEventListener("click",()=>showView(b.dataset.view)));
  document.querySelectorAll("[data-open-view]").forEach(b=>b.addEventListener("click",()=>{showView(b.dataset.openView);document.getElementById("workspace").scrollIntoView({behavior:matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth"});}));
  document.getElementById("demo-reset").addEventListener("click",()=>{Object.assign(state,defaults);render();toast("Demo reset to defaults.");});
  const menuButton=document.querySelector(".menu-toggle"),menu=document.getElementById("mobile-menu");
  menuButton.addEventListener("click",()=>{const isOpen=menuButton.getAttribute("aria-expanded")==="true";menuButton.setAttribute("aria-expanded",String(!isOpen));menu.hidden=isOpen;});
  menu.querySelectorAll("a").forEach(a=>a.addEventListener("click",()=>{menu.hidden=true;menuButton.setAttribute("aria-expanded","false");}));
  document.addEventListener("keydown",event=>{
    if(event.key!=="Escape"||menu.hidden)return;
    menu.hidden=true;
    menuButton.setAttribute("aria-expanded","false");
    menuButton.focus();
  });
  render();
})();
