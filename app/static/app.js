// Shots UI. Plain JS, no build step. All state lives in project.json on disk;
// the page polls for changes so edits made by Claude Code show up on their own.

const S = { cfg: null, projects: [], name: null, data: null, mtime: 0,
  tab: "board", active: null, selected: new Set(), modal: null };

const $ = (sel, el = document) => el.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const IMG = /\.(png|jpe?g|webp|gif)$/i;
const fileUrl = (rel) => `/files/${encodeURIComponent(S.name)}/${rel.split("/").map(encodeURIComponent).join("/")}`;

async function api(method, url, body) {
  const opt = { method, headers: {} };
  if (body instanceof FormData) opt.body = body;
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  const r = await fetch(url, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || j.detail || `${r.status} ${r.statusText}`);
  return j;
}
const P = (path = "") => `/api/projects/${encodeURIComponent(S.name)}${path}`;

function toast(msg, err = false) {
  const t = $("#toast"); t.textContent = msg; t.className = err ? "err" : ""; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), err ? 6000 : 2500);
}
async function run(fn) { try { return await fn(); } catch (e) { toast(e.message, true); console.error(e); } }
async function copy(text, what = "Copied") {
  try { await navigator.clipboard.writeText(text); toast(`${what}: ${text.slice(0, 80)}`); }
  catch { prompt("Copy this:", text); }
}

// ---------- routing ----------

async function boot() {
  S.cfg = await api("GET", "/api/config");
  const name = decodeURIComponent(location.hash.slice(1));
  if (name) await openProject(name); else await showProjects();
  setInterval(poll, 3000);
}
window.addEventListener("hashchange", () => {
  const name = decodeURIComponent(location.hash.slice(1));
  if (name !== S.name) name ? openProject(name) : showProjects();
});

async function showProjects() {
  S.name = null; S.data = null;
  S.projects = await api("GET", "/api/projects");
  render();
}
async function openProject(name) {
  S.name = name; S.active = null; S.selected = new Set();
  await run(reload);
  if (!S.data) { location.hash = ""; return; }
  S.active = S.data.shots[0]?.id || null;
  render();
}
async function reload() {
  const d = await api("GET", P());
  S.data = d; S.mtime = d._mtime;
  if (S.active && !d.shots.some((s) => s.id === S.active)) S.active = d.shots[0]?.id || null;
  for (const id of [...S.selected]) if (!d.shots.some((s) => s.id === id)) S.selected.delete(id);
}
async function refresh() { await reload(); render(); }

async function poll() {
  if (!S.name || !S.data) return;
  const busy = document.activeElement && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if (busy || S.modal) return;
  const { mtime } = await api("GET", P("/mtime")).catch(() => ({}));
  if (mtime && mtime !== S.mtime) await refresh();
}

// ---------- render ----------

function render() {
  const keep = [...document.querySelectorAll("[data-scroll]")].map((el) => [el.dataset.scroll, el.scrollTop]);
  $("#app").innerHTML = S.name && S.data ? projectView() : projectsView();
  for (const [k, top] of keep) { const el = $(`[data-scroll="${k}"]`); if (el) el.scrollTop = top; }
}

function projectsView() {
  return `<div class="projects">
    <h1>Shots</h1>
    <div class="muted">Projects folder: ${esc(S.cfg.projects_dir)}</div>
    <div class="row" style="margin-top:20px">
      <input id="newTitle" placeholder="New project title, e.g. Client Name – Spring Spot">
      <button class="primary" data-act="newProject">New project</button>
    </div>
    <div class="project-list">
      ${S.projects.map((p) => `<div class="project-item" data-act="open" data-name="${esc(p.name)}">
        <div><strong>${esc(p.title)}</strong> <span class="muted">${esc(p.name)}</span></div>
        <div class="muted">${p.shots} shots · ${new Date(p.updated * 1000).toLocaleString()}</div></div>`).join("")
        || `<div class="empty">No projects yet.</div>`}
    </div></div>`;
}

function projectView() {
  const d = S.data, cfg = S.cfg, warn = [];
  if (!cfg.fal_ready) warn.push("No fal key: add it to config.json to enable Send to fal.ai");
  if (!cfg.blender_found) warn.push("Blender not found at blender_path (config.json): in-app previs render disabled");
  if (!cfg.ffmpeg_found) warn.push("ffmpeg not found: animatic export disabled (brew install ffmpeg)");
  const tab = (id, label) => `<button class="${S.tab === id ? "on" : ""}" data-act="tab" data-tab="${id}">${label}</button>`;
  const body = { board: boardView, writing: writingView, assets: assetsView, jobs: jobsView }[S.tab]();
  const running = d.jobs.filter((j) => !["done", "error"].includes(j.status)).length;
  return `<header class="top">
      <button class="link" data-act="home">◀ Projects</button>
      <h1>${esc(d.title)}</h1>
      <div class="tabs">${tab("board", "Board")}${tab("writing", "Script & Scenes")}${tab("assets", "Characters & Sets")}${tab("jobs", `Jobs${running ? ` (${running})` : ""}`)}</div>
      <div class="grow"></div>
      <button class="small" data-act="copyCmd" data-cmd="/breakdown ${esc(S.name)}">Copy /breakdown</button>
    </header>
    ${warn.length ? `<div class="warnbar">${warn.map(esc).join(" · ")}</div>` : ""}
    ${body}`;
}

function media(file, meta = {}, { thumb = false } = {}) {
  if (!file) return thumb ? "no previs yet" : `<div class="empty">No previs or render yet</div>`;
  if (IMG.test(file)) return `<img class="preview" src="${fileUrl(file)}">`;
  const frag = meta.start != null ? `#t=${meta.start},${meta.end}` : thumb ? "#t=0.1" : "";
  return thumb
    ? `<video src="${fileUrl(file)}${frag}" muted preload="metadata" playsinline data-hover></video>`
    : `<video src="${fileUrl(file)}${frag}" controls preload="metadata" playsinline></video>`;
}
const currentVersion = (shot) => shot.versions.filter((v) => v.file === shot.current).pop();

function boardView() {
  const d = S.data;
  const scenes = new Map(d.scenes.map((s) => [s.id, s]));
  const groups = [];
  for (const shot of d.shots) {
    const last = groups[groups.length - 1];
    if (last && last.scene === shot.scene_id) last.shots.push(shot);
    else groups.push({ scene: shot.scene_id, shots: [shot] });
  }
  const card = (shot) => {
    const v = currentVersion(shot);
    const pending = shot.notes.filter((n) => n.status === "pending").length;
    return `<div class="card ${S.active === shot.id ? "active" : ""} ${S.selected.has(shot.id) ? "selected" : ""}" data-act="pick" data-id="${shot.id}">
      <div class="thumb">${media(shot.current, v?.meta, { thumb: true })}
        ${v ? `<span class="pill kind ${v.kind === "seedance" ? "ok" : ""}">${esc(v.kind)} v${v.v}</span>` : ""}
        <input type="checkbox" class="check" data-act="sel" data-id="${shot.id}" ${S.selected.has(shot.id) ? "checked" : ""}></div>
      <div class="meta"><div class="row"><strong>${esc(shot.id)}</strong><span class="muted">${esc(shot.duration)}s</span>
        <div class="grow"></div>${pending ? `<span class="pill warn">${pending} note${pending > 1 ? "s" : ""}</span>` : ""}</div>
        <div class="t muted">${esc(shot.title || shot.description || "—")}</div></div></div>`;
  };
  const ins = (after) => `<div class="insert"><button title="Insert shot here" data-act="insertShot" data-after="${after}">+</button></div>`;
  const strip = groups.map((g) => {
    const sc = scenes.get(g.scene);
    return `<div class="scene-block"><div class="scene-head"><h2>${esc(sc ? `${sc.id} ${sc.title}` : "No scene")}</h2>
      <span class="muted">${esc(sc?.description || "").slice(0, 140)}</span></div>
      <div class="strip">${g.shots.map((s) => card(s) + ins(s.id)).join("")}</div></div>`;
  }).join("");
  const n = S.selected.size;
  return `<div class="board">
    <div class="board-main" data-scroll="board">
      <div class="selbar">
        ${n ? `<strong>${n} selected</strong>
          <button class="primary" data-act="openPrompt">Build Seedance prompt</button>
          <button data-act="clearSel">Clear</button>`
        : `<span class="muted">Tick shots to build a multi-shot Seedance generation.</span>`}
        <div class="grow"></div><button data-act="insertShot" data-after="">+ Shot at start</button>
        <button data-act="insertShot" data-after="__end">+ Shot at end</button>
      </div>
      ${d.shots.length ? strip : `<div class="empty">No shots yet. Write the script, then run <b>/breakdown ${esc(S.name)}</b> in Claude Code, or add shots by hand.</div>`}
    </div>
    <div class="panel" data-scroll="panel">${shotPanel()}</div></div>`;
}

function bind(c, id, field, value, type = "text") {
  return `data-bind="${c}|${id}|${field}" data-type="${type}"`;
}

function idChecks(c, item, field, kind) {
  const list = S.data[kind];
  if (!list.length) return `<span class="muted">none in project yet</span>`;
  return `<div class="checks">${list.map((a) => `<label><input type="checkbox" data-toggle="${c}|${item.id}|${field}|${a.id}"
    ${item[field].includes(a.id) ? "checked" : ""}>${esc(a.name || a.id)}</label>`).join("")}</div>`;
}

function shotPanel() {
  const shot = S.data.shots.find((s) => s.id === S.active);
  if (!shot) return `<div class="muted">Select a shot.</div>`;
  const v = currentVersion(shot);
  const b = shot.blender || {};
  const id = shot.id;
  const pending = shot.notes.filter((n) => n.status === "pending").length;
  return `<div class="row"><h2>${esc(id)}</h2><div class="grow"></div>
      <button class="small" data-act="promptOne" data-id="${id}">Seedance prompt</button>
      <button class="small" data-act="deleteShot" data-id="${id}">Delete</button></div>
    <div style="margin-top:10px">${media(shot.current, v?.meta)}</div>
    ${v?.meta?.span ? `<div class="muted" style="font-size:12px;margin-top:4px">Part of a ${v.meta.span.length}-shot generation; playing its planned ${v.meta.start}–${v.meta.end}s (approximate).</div>` : ""}

    <label>Title</label><input value="${esc(shot.title)}" ${bind("shots", id, "title")}>
    <div class="two">
      <div><label>Scene</label><select ${bind("shots", id, "scene_id")}>
        <option value="">—</option>${S.data.scenes.map((s) => `<option value="${s.id}" ${s.id === shot.scene_id ? "selected" : ""}>${esc(s.id)} ${esc(s.title)}</option>`).join("")}</select></div>
      <div><label>Duration (s)</label><input type="number" step="0.5" min="1" value="${esc(shot.duration)}" ${bind("shots", id, "duration", null, "number")}></div>
    </div>
    <label>Shot description (what we see)</label><textarea ${bind("shots", id, "description")}>${esc(shot.description)}</textarea>
    <label>Camera (lens, framing, move)</label><textarea ${bind("shots", id, "camera")}>${esc(shot.camera)}</textarea>
    <label>Action / performance</label><textarea ${bind("shots", id, "action")}>${esc(shot.action)}</textarea>
    <label>Characters in shot</label>${idChecks("shots", shot, "character_ids", "characters")}
    <label>Environments / sets</label>${idChecks("shots", shot, "environment_ids", "environments")}

    <div class="section"><div class="row"><h3>Notes</h3><span class="muted">${pending} pending</span><div class="grow"></div>
      <button class="small" data-act="copyCmd" data-cmd="/apply-notes ${esc(S.name)} ${id}" ${pending ? "" : "disabled"}>Copy /apply-notes</button></div>
      <div class="row" style="margin-top:8px">
        <select id="noteType" style="width:120px">${["framing", "blocking", "timing", "camera", "acting", "general"].map((t) => `<option>${t}</option>`).join("")}</select>
        <input id="noteText" placeholder="e.g. push in slower, land on a CU by 3s">
        <button data-act="addNote" data-id="${id}">Add</button></div>
      <div style="margin-top:8px">${shot.notes.slice().reverse().map((n) => `<div class="note ${n.status}">
        <div class="row"><span class="pill">${esc(n.type)}</span><span class="muted">${n.status}</span><div class="grow"></div>
          <label class="row" style="margin:0" title="Include this note in the Seedance prompt"><input type="checkbox" data-act="noteToPrompt" data-id="${id}" data-note="${n.id}" ${n.to_prompt ? "checked" : ""}> in prompt</label>
          <button class="small" data-act="noteStatus" data-id="${id}" data-note="${n.id}" data-status="${n.status === "done" ? "pending" : "done"}">${n.status === "done" ? "Reopen" : "Done"}</button>
          <button class="small" data-act="delNote" data-id="${id}" data-note="${n.id}">×</button></div>
        <div style="margin-top:4px">${esc(n.text)}</div>
        ${n.reply ? `<div class="muted" style="margin-top:4px">↳ ${esc(n.reply)}</div>` : ""}</div>`).join("") || `<div class="muted">No notes.</div>`}</div></div>

    <div class="section"><h3>Versions</h3>
      <div class="versions" style="margin-top:6px">${shot.versions.slice().reverse().map((ver) => `<div class="version ${ver.file === shot.current ? "on" : ""}" data-act="setCurrent" data-id="${id}" data-file="${esc(ver.file)}">
        <span class="pill ${ver.kind === "seedance" ? "ok" : ""}">${esc(ver.kind)}</span><strong>v${ver.v}</strong>
        <span class="muted grow">${esc(ver.file.split("/").pop())}</span><span class="muted" style="font-size:11px">${new Date(ver.created).toLocaleString()}</span></div>`).join("") || `<div class="muted">None yet.</div>`}</div>
      <div class="row" style="margin-top:8px"><select id="upKind" style="width:110px"><option>previs</option><option>still</option><option>seedance</option></select>
        <input type="file" id="upFile" accept="video/*,image/*"><button data-act="uploadVersion" data-id="${id}">Add</button></div></div>

    <div class="section"><h3>Blender previs</h3>
      <div class="three"><div><label>.blend (in project)</label><input value="${esc(b.file)}" placeholder="blender/sc010.blend" ${bind("shots", id, "blender.file")}></div>
        <div><label>Start</label><input type="number" value="${esc(b.start)}" ${bind("shots", id, "blender.start", null, "number")}></div>
        <div><label>End</label><input type="number" value="${esc(b.end)}" ${bind("shots", id, "blender.end", null, "number")}></div></div>
      <label>Camera object</label><input value="${esc(b.camera)}" placeholder="CAM_${id}" ${bind("shots", id, "blender.camera")}>
      <div class="row" style="margin-top:8px"><button data-act="render" data-id="${id}" ${S.cfg.blender_found && b.file ? "" : "disabled"}>Render previs (Workbench)</button>
        <span class="muted" style="font-size:12px">Re-renders after you change the .blend by hand.</span></div></div>

    <div class="section"><h3>Prompt extras</h3>
      <label>Extra prompt text for this shot</label><textarea ${bind("shots", id, "prompt_extra")}>${esc(shot.prompt_extra)}</textarea>
      <label>Override (replaces this shot's whole prompt section if filled)</label><textarea ${bind("shots", id, "prompt_override")}>${esc(shot.prompt_override)}</textarea></div>`;
}

function writingView() {
  const d = S.data;
  return `<div class="page" data-scroll="writing">
    <div class="cols">
      <div><label>Title</label><input value="${esc(d.title)}" data-pbind="title">
        <label>Outline</label><textarea class="big" data-pbind="outline">${esc(d.outline)}</textarea>
        <label>Script</label><textarea class="big" style="min-height:420px" data-pbind="script">${esc(d.script)}</textarea></div>
      <div><label>Look / style (goes at the top of every Seedance prompt)</label>
        <textarea data-pbind="style.look">${esc(d.style?.look)}</textarea>
        <label>Keep consistent (wardrobe, props, lighting, continuity: every prompt)</label>
        <textarea data-pbind="style.consistency">${esc(d.style?.consistency)}</textarea>
        <div class="row" style="margin:18px 0 8px"><h2>Scenes</h2><div class="grow"></div>
          <button class="small" data-act="copyCmd" data-cmd="/breakdown ${esc(S.name)}">Copy /breakdown</button>
          <button class="small" data-act="addScene">+ Scene</button></div>
        ${d.scenes.map((s) => `<div class="box"><div class="row"><strong>${esc(s.id)}</strong>
            <input value="${esc(s.title)}" placeholder="Scene title" ${bind("scenes", s.id, "title")}>
            <button class="small" data-act="addShotToScene" data-scene="${s.id}">+ Shot</button>
            <button class="small" data-act="deleteScene" data-id="${s.id}">×</button></div>
          <label>Description</label><textarea ${bind("scenes", s.id, "description")}>${esc(s.description)}</textarea>
          <label>Characters</label>${idChecks("scenes", s, "character_ids", "characters")}
          <label>Environments</label>${idChecks("scenes", s, "environment_ids", "environments")}
          <div class="muted" style="margin-top:6px;font-size:12px">${d.shots.filter((x) => x.scene_id === s.id).map((x) => x.id).join(", ") || "no shots"}</div></div>`).join("")
          || `<div class="muted">No scenes yet.</div>`}
      </div></div></div>`;
}

function assetsView() {
  const col = (kind, label) => `<div><div class="row" style="margin-bottom:8px"><h2>${label}</h2><div class="grow"></div>
      <button class="small" data-act="addAsset" data-kind="${kind}">+ Add</button></div>
    ${S.data[kind].map((a) => `<div class="box"><div class="row"><input value="${esc(a.name)}" placeholder="Name" ${bind(kind, a.id, "name")}>
        <button class="small" data-act="deleteAsset" data-kind="${kind}" data-id="${a.id}">×</button></div>
      <label>Description (used in prompts)</label><textarea ${bind(kind, a.id, "description")}>${esc(a.description)}</textarea>
      <div class="imgs">${a.images.map((img) => `<div class="img"><img src="${fileUrl(img)}">
        <button class="small" data-act="delImage" data-kind="${kind}" data-id="${a.id}" data-file="${esc(img)}">×</button></div>`).join("")}</div>
      <div class="row" style="margin-top:8px"><input type="file" multiple accept="image/*" data-upload="${kind}|${a.id}"></div></div>`).join("")
      || `<div class="muted">None yet.</div>`}</div>`;
  return `<div class="page" data-scroll="assets"><div class="cols">${col("characters", "Character sheets")}${col("environments", "Environment / set sheets")}</div></div>`;
}

function jobsView() {
  return `<div class="page"><div class="row" style="margin-bottom:10px"><h2>Jobs</h2><div class="grow"></div>
    <button class="small" data-act="refresh">Refresh</button><button class="small" data-act="clearJobs">Clear finished</button></div>
    <table><tr><th>Job</th><th>Kind</th><th>Shots</th><th>Status</th><th>Started</th></tr>
    ${S.data.jobs.map((j) => `<tr><td>${esc(j.id)}</td><td>${esc(j.kind)}${j.endpoint ? `<div class="muted">${esc(j.endpoint)}</div>` : ""}</td>
      <td>${esc(j.shot_ids.join(", "))}</td>
      <td><span class="pill ${j.status === "done" ? "ok" : j.status === "error" ? "err" : "warn"}">${esc(j.status)}</span>
        ${j.error ? `<pre class="err">${esc(j.error)}</pre>` : ""}</td>
      <td class="muted">${new Date(j.created).toLocaleString()}</td></tr>`).join("") || `<tr><td colspan="5" class="muted">No jobs yet.</td></tr>`}
    </table></div>`;
}

// ---------- prompt / fal dialog ----------

function openPromptDialog(ids) {
  const order = S.data.shots.map((s) => s.id).filter((id) => ids.includes(id));
  S.modal = { ids: order, mode: "clips", animatic: null, built: null };
  buildPrompt();
}
async function buildPrompt() {
  const m = S.modal;
  const out = await run(() => api("POST", P("/prompt"), { shot_ids: m.ids, mode: m.mode, animatic: m.animatic }));
  if (!out) return;
  m.built = out; m.endpoint = m.endpoint || out.endpoint;
  renderModal();
}
function renderModal() {
  const m = S.modal, el = $("#modal");
  if (!m) { el.hidden = true; el.innerHTML = ""; return; }
  const b = m.built;
  el.hidden = false;
  el.innerHTML = `<div class="dialog">
    <div class="row"><h2>Seedance request: ${m.ids.join(", ")}</h2><div class="grow"></div><button data-act="closeModal">Close</button></div>
    <div class="row wrap" style="margin-top:12px">
      <label style="margin:0">Video reference</label>
      <select id="mMode" style="width:auto">
        <option value="clips" ${m.mode === "clips" ? "selected" : ""}>Each shot's previs as its own @Video</option>
        <option value="animatic" ${m.mode === "animatic" ? "selected" : ""}>One combined animatic</option>
        <option value="none" ${m.mode === "none" ? "selected" : ""}>No video (text + images only)</option></select>
      ${m.mode === "animatic" ? `<button data-act="exportAnimatic" ${S.cfg.ffmpeg_found ? "" : "disabled"}>${m.animatic ? "Re-export" : "Export"} animatic</button>
        ${m.animatic ? `<span class="muted">${esc(m.animatic)}</span>` : ""}` : ""}
      <button data-act="rebuild">Rebuild from shots</button>
    </div>
    ${b?.warnings?.length ? `<div class="warnings">⚠ ${b.warnings.map(esc).join("<br>⚠ ")}</div>` : ""}
    <div class="muted" style="font-size:12px;margin-top:8px">Planned length ${b?.planned_seconds ?? "?"}s. "local:" paths upload to fal storage on send.
      Check the field names against the model's API page on fal; edit freely below.</div>
    <label>Seedance prompt (edit freely; "Rebuild from shots" discards edits)</label>
    <textarea id="mPrompt" style="min-height:260px;font-family:inherit;font-size:13px">${esc(b?.payload?.prompt || "")}</textarea>
    <label>fal endpoint</label><input id="mEndpoint" value="${esc(m.endpoint || "")}">
    <label>Other request fields (JSON)</label><textarea id="mPayload" style="min-height:140px">${esc(JSON.stringify(Object.fromEntries(Object.entries(b?.payload || {}).filter(([k]) => k !== "prompt")), null, 2))}</textarea>
    <div class="row" style="margin-top:12px"><button data-act="copyPrompt">Copy prompt text</button><div class="grow"></div>
      <button class="primary" data-act="sendFal" ${S.cfg.fal_ready ? "" : "disabled title='Add fal_key to config.json'"}>Send to fal.ai</button></div></div>`;
}

// ---------- events ----------

async function patchBind(el) {
  const [c, id, field] = el.dataset.bind.split("|");
  let value = el.value;
  if (el.dataset.type === "number") value = value === "" ? null : Number(value);
  let body;
  if (field.includes(".")) {
    const [top, sub] = field.split(".");
    const item = S.data[c].find((x) => x.id === id);
    body = { [top]: { ...(item[top] || {}), [sub]: value } };
  } else body = { [field]: value };
  const item = await run(() => api("PATCH", P(`/items/${c}/${id}`), body));
  if (item) { Object.assign(S.data[c].find((x) => x.id === id), item); bumpMtime(); }
}
async function patchProject(el) {
  const field = el.dataset.pbind;
  let body;
  if (field.startsWith("style.")) body = { style: { ...(S.data.style || {}), [field.slice(6)]: el.value } };
  else body = { [field]: el.value };
  await run(() => api("PATCH", P(), body));
  Object.assign(S.data, body); bumpMtime();
}
async function bumpMtime() { const r = await api("GET", P("/mtime")).catch(() => null); if (r) S.mtime = r.mtime; }

document.addEventListener("change", async (e) => {
  const el = e.target;
  if (el.dataset.bind) return patchBind(el);
  if (el.dataset.pbind) return patchProject(el);
  if (el.dataset.toggle) {
    const [c, id, field, val] = el.dataset.toggle.split("|");
    const item = S.data[c].find((x) => x.id === id);
    const list = el.checked ? [...new Set([...item[field], val])] : item[field].filter((x) => x !== val);
    await run(() => api("PATCH", P(`/items/${c}/${id}`), { [field]: list }));
    return refresh();
  }
  if (el.dataset.upload) {
    const [kind, id] = el.dataset.upload.split("|");
    for (const f of el.files) {
      const fd = new FormData(); fd.append("file", f);
      await run(() => api("POST", P(`/items/${kind}/${id}/images`), fd));
    }
    return refresh();
  }
  if (el.id === "mMode") { S.modal.mode = el.value; return buildPrompt(); }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.id === "noteText") $(`[data-act="addNote"]`)?.click();
  if (e.key === "Enter" && e.target.id === "newTitle") $(`[data-act="newProject"]`)?.click();
  if (e.key === "Escape" && S.modal) { S.modal = null; renderModal(); }
});

document.addEventListener("mouseover", (e) => { if (e.target.matches?.("video[data-hover]")) e.target.play().catch(() => {}); });
document.addEventListener("mouseout", (e) => { if (e.target.matches?.("video[data-hover]")) e.target.pause(); });

const actions = {
  home: () => { location.hash = ""; },
  open: (el) => { location.hash = encodeURIComponent(el.dataset.name); },
  newProject: async () => {
    const title = $("#newTitle").value.trim() || "Untitled";
    const r = await run(() => api("POST", "/api/projects", { title }));
    if (r) location.hash = encodeURIComponent(r.name);
  },
  tab: (el) => { S.tab = el.dataset.tab; render(); },
  refresh,
  copyCmd: (el) => copy(el.dataset.cmd, "Paste into Claude Code"),
  pick: (el, e) => { if (e.target.dataset.act === "sel") return; S.active = el.dataset.id; render(); },
  sel: (el, e) => { e.stopPropagation(); el.checked ? S.selected.add(el.dataset.id) : S.selected.delete(el.dataset.id); render(); },
  clearSel: () => { S.selected.clear(); render(); },
  insertShot: async (el) => {
    const after = el.dataset.after === "__end" ? null : el.dataset.after;
    const shot = await run(() => api("POST", P("/items/shots"), { after }));
    if (shot) { S.active = shot.id; await refresh(); }
  },
  addShotToScene: async (el) => {
    const last = S.data.shots.filter((s) => s.scene_id === el.dataset.scene).pop();
    const shot = await run(() => api("POST", P("/items/shots"), { after: last ? last.id : null, scene_id: el.dataset.scene }));
    if (shot) { S.active = shot.id; S.tab = "board"; await refresh(); }
  },
  deleteShot: async (el) => {
    if (!confirm(`Delete ${el.dataset.id}? Its media files stay on disk.`)) return;
    await run(() => api("DELETE", P(`/items/shots/${el.dataset.id}`))); await refresh();
  },
  addScene: async () => { await run(() => api("POST", P("/items/scenes"), {})); await refresh(); },
  deleteScene: async (el) => {
    if (!confirm(`Delete scene ${el.dataset.id}? Shots keep their content.`)) return;
    await run(() => api("DELETE", P(`/items/scenes/${el.dataset.id}`))); await refresh();
  },
  addAsset: async (el) => { await run(() => api("POST", P(`/items/${el.dataset.kind}`), {})); await refresh(); },
  deleteAsset: async (el) => {
    if (!confirm("Delete this sheet? Image files stay on disk.")) return;
    await run(() => api("DELETE", P(`/items/${el.dataset.kind}/${el.dataset.id}`))); await refresh();
  },
  delImage: async (el) => {
    await run(() => api("DELETE", P(`/items/${el.dataset.kind}/${el.dataset.id}/images?file=${encodeURIComponent(el.dataset.file)}`)));
    await refresh();
  },
  addNote: async (el) => {
    const text = $("#noteText").value.trim(); if (!text) return;
    await run(() => api("POST", P(`/shots/${el.dataset.id}/notes`), { text, type: $("#noteType").value }));
    await refresh();
  },
  noteStatus: async (el) => { await run(() => api("PATCH", P(`/shots/${el.dataset.id}/notes/${el.dataset.note}`), { status: el.dataset.status })); await refresh(); },
  noteToPrompt: async (el) => { await run(() => api("PATCH", P(`/shots/${el.dataset.id}/notes/${el.dataset.note}`), { to_prompt: el.checked })); await refresh(); },
  delNote: async (el) => { await run(() => api("DELETE", P(`/shots/${el.dataset.id}/notes/${el.dataset.note}`))); await refresh(); },
  setCurrent: async (el) => { await run(() => api("PATCH", P(`/items/shots/${el.dataset.id}`), { current: el.dataset.file })); await refresh(); },
  uploadVersion: async (el) => {
    const f = $("#upFile").files[0]; if (!f) return toast("Pick a file first", true);
    const fd = new FormData(); fd.append("file", f); fd.append("kind", $("#upKind").value);
    await run(() => api("POST", P(`/shots/${el.dataset.id}/versions`), fd)); await refresh();
  },
  render: async (el) => {
    const j = await run(() => api("POST", P(`/shots/${el.dataset.id}/render`)));
    if (j) { toast(`Rendering ${el.dataset.id}… (Jobs tab)`); await refresh(); }
  },
  promptOne: (el) => openPromptDialog([el.dataset.id]),
  openPrompt: () => openPromptDialog([...S.selected]),
  closeModal: () => { S.modal = null; renderModal(); },
  rebuild: () => buildPrompt(),
  exportAnimatic: async () => {
    toast("Exporting animatic…");
    const r = await run(() => api("POST", P("/animatic"), { shot_ids: S.modal.ids }));
    if (r) { S.modal.animatic = r.file; await buildPrompt(); }
  },
  copyPrompt: () => copy($("#mPrompt").value, "Prompt copied"),
  sendFal: async () => {
    let payload;
    try { payload = { prompt: $("#mPrompt").value, ...JSON.parse($("#mPayload").value || "{}") }; }
    catch { return toast("Other request fields: JSON is not valid", true); }
    const endpoint = $("#mEndpoint").value.trim();
    if (!confirm(`Send ${S.modal.ids.length} shot(s) to ${endpoint}? This is a paid generation.`)) return;
    const j = await run(() => api("POST", P("/fal"), { shot_ids: S.modal.ids, endpoint, payload }));
    if (j) { S.modal = null; renderModal(); S.tab = "jobs"; toast("Sent to fal.ai: the result will replace the shot when it lands"); await refresh(); }
  },
  clearJobs: async () => { await run(() => api("DELETE", P("/jobs"))); await refresh(); },
};

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-act]");
  if (!el || el.disabled) return;
  const fn = actions[el.dataset.act];
  if (fn) fn(el, e);
});

// jobs finish in the background; poll a little faster while any are running
setInterval(() => {
  if (S.data?.jobs?.some((j) => !["done", "error"].includes(j.status)) && !S.modal) poll();
}, 1500);

boot().catch((e) => toast(e.message, true));
