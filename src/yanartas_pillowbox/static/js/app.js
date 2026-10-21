// Application controller: builds the parameter form from the server's field specs, renders
// through /api/render (debounced), persists through PUT /api/config, and runs
// import/export/reset. Geometry lives entirely in Python; nothing here computes shapes.

import "./components/pb-param.js";
import "./components/pb-preview2d.js";
import "./components/pb-preview3d.js";
import "./components/pb-section.js";
import { initPanels, maximizeButton } from "./panels.js";

const RENDER_DELAY = 60; // ms; server round-trip is a few ms, so previews update well < 300 ms
const SAVE_DELAY = 600;

const $ = (sel) => document.querySelector(sel);
const form = $("#params");
const preview2d = $("#preview2d");
const preview3d = $("#preview3d");
const sectionView = $("#section");
const statusEl = $("#status");
const downloadBtn = $("#btn-download");
const scadBtn = $("#btn-scad");
const pcbBtn = $("#btn-pcb");
const PROGRESS_POLL = 500; // ms between looks at a running layout's progress
const GROUPS_KEY = "pb-groups"; // which settings groups are open (per viewer)
const SIDEBAR_KEY = "pb-sidebar"; // whether the settings are collapsed (per viewer)
const FIRST_GROUP = "Payload"; // shown first, and the only group open at first
const MESH_GROUP = "PCB mesh"; // holds the Generate mesh button, progress and log
const NOT_YET = "Mesh not yet generated: Generate mesh, in the PCB mesh settings";

const params = new Map(); // name -> <pb-param>
let payloadPresets = []; // board sizes from /api/defaults
let presetParam = null; // the "Board preset" <pb-param> (not a config field)
let lastValid = null; // {config, svg, model, info}
let savedJson = null;
let renderSeq = 0;
let renderTimer = 0;
let saveTimer = 0;
let showMesh = false; // the previews show the PCB layout's security mesh
let meshSeq = 0;
let meshData = null; // the generated PCB layout (/api/pcb's reply), for meshConfig
let meshConfig = null; // the config (JSON) it was generated for
let meshRun = null; // the generation under way (a promise of its reply)

// ----------------------------------------------------------------------------- API helpers
async function api(method, url, content, { raw = false } = {}) {
  const init = { method, headers: {} };
  if (content instanceof FormData) init.body = content;
  else if (content !== undefined) {
    init.body = JSON.stringify(content);
    init.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(url, init);
  const data = await res.json().catch(() => ({}));
  if (raw) return { ok: res.ok, status: res.status, data };
  if (!res.ok) throw new Error(data.error || `${method} ${url} failed (${res.status})`);
  return data;
}

// ----------------------------------------------------------------------------- storage
function loadPref(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback; // (no storage in private windows, sandboxes, …)
  }
}

function savePref(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // (then only for as long as the page)
  }
}

// ----------------------------------------------------------------------------- form
function buildForm(specs, presets = []) {
  form.replaceChildren();
  const groups = new Map();
  const open = loadPref(GROUPS_KEY, { [FIRST_GROUP]: true });
  // (the payload's group first: what goes in the box decides the rest)
  const ordered = [...specs.filter((s) => s.group === FIRST_GROUP),
    ...specs.filter((s) => s.group !== FIRST_GROUP)];
  for (const spec of ordered) {
    if (!groups.has(spec.group)) {
      const group = document.createElement("details");
      group.className = "group";
      group.open = Boolean(open[spec.group]);
      const summary = document.createElement("summary");
      summary.textContent = spec.group;
      group.append(summary);
      group.addEventListener("toggle", () => {
        open[spec.group] = group.open;
        savePref(GROUPS_KEY, open);
      });
      groups.set(spec.group, group);
      form.append(group);
    }
    const param = document.createElement("pb-param");
    param.spec = spec;
    params.set(spec.name, param);
    groups.get(spec.group).append(param);
  }
  groups.get(MESH_GROUP)?.append(meshControls());
  // Shell: compute the smallest box (width, length, height) that holds the payload.
  const fit = Object.assign(document.createElement("button"), {
    type: "button",
    className: "group-action",
    textContent: "Fit box to payload",
    title: "Smallest width, length and height that hold the payload, minimizing the "
      + "pattern's bounding box. Glue tab and thickness are kept.",
  });
  fit.addEventListener("click", () => payloadAction({ action: "fit" }));
  groups.get("Shell")?.append(fit);

  // Payload: board presets fill in width, depth and height (UI only, not a setting).
  payloadPresets = presets;
  presetParam = document.createElement("pb-param");
  presetParam.className = "wide"; // long board names
  presetParam.spec = {
    name: "payload_preset",
    label: "Board preset",
    kind: "choice",
    help: "Approximate sizes of common boards, long side along the box. Heights include "
      + "connectors and stacked add-on boards; check your own board.",
    choices: [
      { value: "", label: "Custom" },
      ...presets.map((p) => ({
        value: p.id, label: `${p.label} (${p.depth} × ${p.width} × ${p.height})`, group: p.group,
      })),
    ],
  };
  presetParam.addEventListener("pb-change", () => {
    const preset = payloadPresets.find((p) => p.id === presetParam.value);
    if (!preset) return;
    params.get("payload_width").value = preset.width;
    params.get("payload_depth").value = preset.depth;
    params.get("payload_height").value = preset.height;
  });
  groups.get("Payload")?.querySelector("summary").after(presetParam);
}

/** The mesh's controls, for its settings group: generate (and cancel), the layout's progress
 *  and its log (collapsed: the latest line). */
function meshControls() {
  const box = document.createElement("div");
  box.className = "mesh-run";
  box.innerHTML = `
    <div class="buttons">
      <button type="button" id="btn-generate" class="primary"
        title="Lay out the PCB's security mesh for this design (and show it)">Generate mesh</button>
      <button type="button" id="btn-cancel" hidden title="Stop the mesh layout">Cancel</button>
    </div>
    <progress id="mesh-progress" max="1" value="0" hidden aria-label="Mesh layout progress"></progress>
    <details class="mesh-log" id="mesh-log" hidden>
      <summary id="mesh-log-latest"></summary>
      <ol id="mesh-log-list" aria-label="Mesh layout log"></ol>
    </details>`;
  box.querySelector("#btn-generate").addEventListener("click", () => generateMesh());
  box.querySelector("#btn-cancel").addEventListener("click", cancelMesh);
  return box;
}

/** Show the preset matching the current payload size, or "Custom". */
function syncPreset() {
  if (!presetParam) return;
  const c = readForm();
  const match = payloadPresets.find((p) =>
    p.width === c.payload_width && p.depth === c.payload_depth && p.height === c.payload_height);
  presetParam.value = match ? match.id : "";
}

/** Run a payload action on the server and apply the resulting config. */
async function payloadAction(request) {
  const { ok, data } = await api("POST", "/api/payload", { config: readForm(), ...request }, { raw: true });
  if (!ok) {
    showErrors(data.errors || {});
    if (!data.errors || !Object.keys(data.errors).length) showBanner(data.error || "Payload action failed");
    setStatus(data.error || "Payload action failed", true);
    return;
  }
  writeForm(data.config);
  setStatus("Updating…");
  scheduleRender(0);
}

function readForm() {
  const config = {};
  for (const [name, p] of params) config[name] = p.value;
  return config;
}

function writeForm(config) {
  for (const [name, p] of params) if (name in config) p.value = config[name];
  syncPreset();
}

function showErrors(errors) {
  for (const [name, p] of params) p.error = errors[name] || "";
  const general = Object.entries(errors).filter(([k]) => !params.has(k));
  if (general.length) showBanner(general.map(([, v]) => v).join("; "));
}

// ----------------------------------------------------------------------------- status
function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

function showBanner(message) {
  $("#banner-text").textContent = message;
  $("#banner").hidden = false;
}

function hideBanner() {
  $("#banner").hidden = true;
}

// ----------------------------------------------------------------------------- render/save
function scheduleRender(delay = RENDER_DELAY) {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(render, delay);
}

async function render() {
  const seq = ++renderSeq;
  const config = readForm();
  let result;
  try {
    result = await api("POST", "/api/render", { config }, { raw: true });
  } catch (err) {
    if (seq === renderSeq) setStatus(`Server unreachable: ${err.message}`, true);
    return;
  }
  if (seq !== renderSeq) return; // a newer edit is already in flight
  if (!result.ok) {
    const errors = result.data.errors || {};
    showErrors(errors);
    if (!Object.keys(errors).length) showBanner(result.data.error || "Render failed");
    const n = Object.keys(errors).length;
    setStatus(`${n || "An"} invalid value${n === 1 ? "" : "s"} — previews show the last valid design`, true);
    downloadBtn.disabled = scadBtn.disabled = pcbBtn.disabled = true;
    return;
  }
  showErrors({});
  const { svg, model, section, info, dimensions, payload } = result.data;
  lastValid = { config: result.data.config, svg, model, section, info };
  preview2d.update(svg, info, dimensions.pattern);
  preview3d.update(model, dimensions.model, payload);
  sectionView.update(section, dimensions.section, payload);
  renderDerived(info, payload);
  downloadBtn.disabled = scadBtn.disabled = pcbBtn.disabled = false;
  setStatus("Up to date");
  scheduleSave(lastValid.config);
  checkMeshCurrent(lastValid.config);
}

// ----------------------------------------------------------------------------- PCB mesh
function setMesh(pcb) {
  preview2d.setMesh(pcb);
  preview3d.setMesh(pcb);
  renderMeshStats(pcb);
  updateMeshNote();
}

/** The views' note about the mesh: shown with it on but none to show (none generated yet,
 *  or not for this design). */
function updateMeshNote() {
  const text = showMesh && !meshData ? (meshRun ? "Laying out the mesh…" : NOT_YET) : null;
  preview2d.meshNote = preview3d.meshNote = text;
}

/** The mesh is out of date once the design changes (the next Generate mesh lays it out). */
function checkMeshCurrent(config) {
  if (meshData && JSON.stringify(config) !== meshConfig) {
    meshData = meshConfig = null;
    setMesh(null);
    setStatus("Design changed: the mesh is out of date");
  }
}

/** The mesh's figures, under their own title in the Derived geometry box (none: hidden). */
function renderMeshStats(pcb) {
  $("#mesh-stats").hidden = !pcb;
  if (!pcb) return;
  const { front, back } = pcb.meshes;
  const m = (mm) => `${(mm / 1000).toFixed(2)} m`;
  const both = (f) => `${f(front)} / ${f(back)}`;
  const sfc = front.algorithm === "sfc";
  // (spacing: the share of the traces' measured sides within the nominal space -5 / +20 %,
  // and over twice it, how much of them is below it and the widest gap; skew: the worst
  // neighbouring pair of each mesh)
  const pct = (x, key) => `${((100 * x.spacing[key]) / Math.max(x.spacing.measured, 1e-9)).toFixed(1)} %`;
  const share = (x) => pct(x, "within");
  const wide = (x) => `${pct(x, "wide")}, ≤ ${x.spacing.largest.toFixed(2)} mm`;
  const below = (x) => `${x.spacing.below.toFixed(1)} mm`;
  // (coverage: how much the copper's local share of the area varies, and where it falls
  // under 70 % of the nominal: holes between runs)
  const cover = (x) =>
    `${(100 * x.density.spread).toFixed(1)} % / ${(100 * x.density.thin).toFixed(2)} %`;
  const worst = (x, key) => Math.max(0, ...x.skew.map((p) => p[key]));
  const skew = (x) => `${worst(x, "total").toFixed(1)} / ${worst(x, "local").toFixed(1)} mm`;
  const rows = [
    ["Layout", sfc ? "Space-filling curve" : "KiMesh grid"],
    ["Traces per side", `${front.traces}`],
    ...(sfc
      ? [["Curve graph cells (front / back)", both((x) => x.cells)]]
      : [
          ["Cell size", `${front.cell.toFixed(2)} mm`],
          ["Cells (front / back)", both((x) => x.cells)],
        ]),
    ...(front.unreached + back.unreached
      ? [[sfc ? "Panels out of reach" : "Cells out of reach", both((x) => x.unreached), true]]
      : []),
    ["Longest trace (front / back)", both((x) => m(x.longest))],
    ["Longest trace", `${m(pcb.longest_trace.length)} (${pcb.longest_trace.net})`],
    ...(front.average_space != null && back.average_space != null
      ? [[`Average space, set least ${pcb.space.toFixed(2)} mm (front / back)`,
          both((x) => `${x.average_space.toFixed(3)} mm`)]]
      : []),
    ["Space within −5…+20 % (front / back)", both(share)],
    ["Below nominal space (front / back)", both(below), front.spacing.under + back.spacing.under > 0],
    ["Gaps over twice the space, widest (front / back)", both(wide)],
    ...(front.density && back.density
      ? [["Coverage spread / thin area (front / back)", both(cover),
          front.density.thin + back.density.thin > 0.001]]
      : []),
    ["Pair skew, total / local (front)", skew(front)],
    ["Pair skew, total / local (back)", skew(back)],
  ];
  $("#mesh-derived").replaceChildren(...rows.flatMap(([k, v, bad]) => {
    const dt = Object.assign(document.createElement("dt"), { textContent: k });
    const dd = Object.assign(document.createElement("dd"), { textContent: v });
    if (bad) dd.classList.add("bad");
    return [dt, dd];
  }));
}

/** Spinner on the Mesh buttons while the layout runs; Generate becomes Cancel. */
function setMeshBusy(busy) {
  preview2d.meshBusy = preview3d.meshBusy = busy;
  $("#btn-generate").disabled = busy;
  $("#btn-cancel").hidden = !busy;
}

/** The views' Mesh buttons: show or hide the mesh (generated with Generate mesh). */
function toggleMesh() {
  showMesh = !showMesh;
  preview2d.meshShown = preview3d.meshShown = showMesh;
  setMesh(showMesh ? meshData : null);
}

/** Lay out the PCB for the current design and show its copper. Resolves with the layout, or
 *  null (failed: the error dialog says why; cancelled). */
function generateMesh() {
  if (meshRun) return meshRun;
  if (!lastValid) return Promise.resolve(null);
  const config = lastValid.config;
  const seq = ++meshSeq;
  showMesh = true;
  preview2d.meshShown = preview3d.meshShown = true;
  meshData = meshConfig = null;
  clearLog();
  logLine("Laying out the mesh…");
  setStatus("Laying out the mesh…");
  setMeshBusy(true);
  const request = api("POST", "/api/pcb", { config }, { raw: true })
    .catch((err) => ({ ok: false, data: { error: err.message } }));
  meshRun = (async () => {
    setMesh(null);
    const { ok, data } = await watchProgress(request, seq);
    meshRun = null;
    setMeshBusy(false);
    if (seq !== meshSeq) return null;
    if (!ok) {
      setMesh(null);
      if (data.cancelled) {
        logLine("Cancelled");
        setStatus("Mesh layout cancelled");
        return null;
      }
      const message = data.error || "the layout failed";
      logLine(`Failed: ${message}`, true);
      setStatus(`Mesh layout failed: ${message}`, true);
      showError("Mesh layout failed", message);
      return null;
    }
    meshData = data;
    meshConfig = JSON.stringify(config);
    setMesh(showMesh ? data : null);
    const missed = data.meshes.front.unreached + data.meshes.back.unreached;
    const done = missed ? `Mesh laid out; ${missed} cells out of reach` : "Mesh laid out";
    logLine(done);
    setStatus(done, missed > 0);
    // (the design changed meanwhile: out of date at once)
    if (lastValid) checkMeshCurrent(lastValid.config);
    return meshData;
  })();
  updateMeshNote();
  return meshRun;
}

/** Stop the layout under way (its request then answers "cancelled"). */
async function cancelMesh() {
  logLine("Cancelling…");
  await api("POST", "/api/pcb/cancel").catch(() => null);
}

/** `request`'s reply; while it runs, the layout's progress (polled) on the bar, in the
 *  status line and the log (a line per phase, its step updated in place). */
async function watchProgress(request, seq) {
  const bar = $("#mesh-progress");
  let running = true;
  request.finally(() => { running = false; });
  bar.value = 0;
  bar.hidden = false;
  try {
    while (running && seq === meshSeq) {
      await Promise.race([request, new Promise((r) => setTimeout(r, PROGRESS_POLL))]);
      if (!running || seq !== meshSeq) break;
      const reply = await api("GET", "/api/progress").catch(() => null);
      const e = reply?.progress;
      if (!e || !running || seq !== meshSeq) continue;
      bar.value = e.done;
      const text = describeProgress(e);
      setStatus(`Laying out the mesh… ${Math.round(100 * e.done)} % (${text})`);
      logLine(text, false, `${e.stage} ${e.phase}`);
    }
    return await request;
  } finally {
    bar.hidden = true;
  }
}

function clearLog() {
  $("#mesh-log-list").replaceChildren();
  $("#mesh-log").hidden = true;
}

/** A line in the mesh's log, and in its summary (`key`: one line per key, updated in
 *  place: each layer's phase, its steps). */
function logLine(text, error = false, key = null) {
  const list = $("#mesh-log-list");
  const t = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  let li = key ? [...list.children].find((l) => l.dataset.key === key) : null;
  if (!li) {
    li = list.appendChild(document.createElement("li"));
    if (key) li.dataset.key = key;
  }
  li.textContent = `${t}  ${text}`;
  li.classList.toggle("error", error);
  $("#mesh-log-latest").textContent = text;
  $("#mesh-log").hidden = false;
  list.scrollTop = list.scrollHeight;
}

/** A progress event in a few words: "F.Cu: settle 12/40, skew 3.1/2.0/1.2 mm". */
function describeProgress(e) {
  let text = `${e.stage ? `${e.stage}: ` : ""}${e.phase}`;
  if (e.steps > 1) text += ` ${e.step}/${e.steps}`;
  // (settling's lengths swing wide before they are steered and matched: shown from then on)
  if (e.phase === "match" && e.apart?.length) {
    text += `, skew ${e.apart.map((a) => a.toFixed(1)).join("/")} mm`;
  }
  return text;
}

/** A modal dialog with an error (OK closes it). */
function showError(title, message) {
  const dialog = $("#error-dialog");
  $("#error-title").textContent = title;
  $("#error-text").textContent = message;
  if (!dialog.open) dialog.showModal();
}

function scheduleSave(config) {
  const json = JSON.stringify(config);
  clearTimeout(saveTimer); // also drops a pending save of an older, now-superseded config
  if (json === savedJson) return;
  saveTimer = setTimeout(async () => {
    try {
      const res = await api("PUT", "/api/config", { config });
      savedJson = json;
      if (res.saved === false) setStatus(`Could not save settings: ${res.error}`, true);
      else setStatus("Saved");
    } catch (err) {
      setStatus(`Could not save settings: ${err.message}`, true);
    }
  }, SAVE_DELAY);
}

function pair(a, b) {
  return `${a.toFixed(2)} / ${b.toFixed(2)} mm`;
}

function renderDerived(info, payload) {
  const outside = ["Outside (w × h × l)", `${[info.outer_width, info.outer_height, info.outer_length].map((v) => v.toFixed(2)).join(" × ")} mm`];
  // (two pieces: both panels alike, each piece made twice)
  const panels = info.pieces === 2 ? [
    ["Pieces", "2 identical (one print side out, one in)"],
    ["Straight edge", info.front_edge_length],
    ["Panel width", info.front_panel_width],
    ["Fold sagitta / radius", pair(info.front_fold_sagitta, info.front_fold_radius)],
    ["Outer / inner flap cut sagitta", pair(info.front_cut_sagitta, info.back_cut_sagitta)],
    ["Glue-tab taper (top / bottom)", pair(info.glue_tab_taper, info.glue_tab_taper_end)],
  ] : [
    ["Front / back straight edge", pair(info.front_edge_length, info.edge_length)],
    ["Circumference", info.circumference],
    ["Front / back panel width", pair(info.front_panel_width, info.back_panel_width)],
    ["Front / back fold sagitta", pair(info.front_fold_sagitta, info.back_fold_sagitta)],
    ["Front / back fold radius", pair(info.front_fold_radius, info.back_fold_radius)],
    ["Outer / inner flap cut sagitta", pair(info.front_cut_sagitta, info.back_cut_sagitta)],
    ["Glue-tab taper", info.glue_tab_taper],
  ];
  const rows = [
    outside,
    ...panels,
    ...(info.end_width_increase == null ? [] : [
      ["Ends wider / taller by", pair(info.end_width_increase, info.end_height_increase)],
    ]),
  ];
  $("#derived").replaceChildren(...rows.flatMap(([k, v]) => {
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = typeof v === "number" ? `${v.toFixed(2)} mm` : v;
    return [dt, dd];
  }));
  if (!payload.empty) {
    // True distance from the payload to the box surface; must be at least the required clearance.
    const c = payload.clearance;
    const dt = Object.assign(document.createElement("dt"), { textContent: "Payload clearance" });
    const dd = Object.assign(document.createElement("dd"), {
      textContent: c < 0 ? "does not fit" : `${c.toFixed(2)} mm`,
      title: `Clearance required: ${payload.min_clearance} mm`,
    });
    if (!payload.fits) dd.classList.add("bad");
    $("#derived").append(dt, dd);
  }
}

// ----------------------------------------------------------------------------- import/export
async function importFile(file) {
  if (!file) return;
  const upload = new FormData();
  upload.append("file", file, file.name);
  const { ok, data } = await api("POST", "/api/import", upload, { raw: true });
  if (!ok) {
    showBanner(`Could not import “${file.name}”: ${data.error || "unknown error"}`);
    return;
  }
  hideBanner();
  writeForm(data.config);
  setStatus(`Imported ${file.name}`);
  scheduleRender(0);
}

function fileName(suffix) {
  const c = lastValid.config;
  const n = (v) => String(Math.round(v * 10) / 10);
  return `pillowbox-${n(c.width)}x${n(c.length)}x${n(c.height)}mm${suffix}`;
}

function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function download() {
  if (!lastValid) return;
  saveBlob(new Blob([lastValid.svg], { type: "image/svg+xml" }), fileName(".svg"));
}

async function downloadScad() {
  if (!lastValid) return;
  const name = fileName("-interior.scad");
  try {
    const res = await fetch("/api/scad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: lastValid.config }),
    });
    if (!res.ok) throw new Error(`export failed (${res.status})`);
    saveBlob(await res.blob(), name);
  } catch (err) {
    showBanner(`OpenSCAD export failed: ${err.message}`);
  }
}

async function downloadPcb() {
  if (!lastValid) return;
  pcbBtn.classList.add("busy");
  pcbBtn.disabled = true;
  try {
    // (the files are the generated mesh's: laid out first, if not yet for this design)
    const config = lastValid.config;
    if (!meshData || JSON.stringify(config) !== meshConfig) {
      if (!(await generateMesh())) return;
    }
    setStatus("Writing the PCB files…");
    const res = await fetch("/api/pcb/files", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `export failed (${res.status})`);
    }
    saveBlob(await res.blob(), fileName("-pcb.zip"));
    setStatus("Up to date");
  } catch (err) {
    setStatus(`PCB export failed: ${err.message}`, true);
    showError("PCB export failed", err.message);
  } finally {
    pcbBtn.classList.remove("busy");
    pcbBtn.disabled = !lastValid;
  }
}

async function resetToDefaults() {
  const { config } = await api("GET", "/api/defaults");
  hideBanner();
  writeForm(config);
  scheduleRender(0);
}

/** The top bar's button: collapse the settings (the previews take the width), or show them. */
function setupSidebar() {
  const button = $("#btn-sidebar");
  const layout = $(".layout");
  const apply = (collapsed) => {
    if (collapsed) layout.dataset.sidebar = "collapsed";
    else delete layout.dataset.sidebar;
    button.setAttribute("aria-expanded", String(!collapsed));
    button.title = collapsed ? "Show the settings" : "Hide the settings";
  };
  apply(loadPref(SIDEBAR_KEY, false));
  button.addEventListener("click", () => {
    const collapsed = !layout.dataset.sidebar;
    apply(collapsed);
    savePref(SIDEBAR_KEY, collapsed);
  });
}

function setupDragAndDrop() {
  const zone = $("#dropzone");
  let depth = 0;
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
  window.addEventListener("dragenter", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth++;
    zone.hidden = false;
  });
  window.addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
  window.addEventListener("dragleave", () => {
    depth = Math.max(0, depth - 1);
    if (!depth) zone.hidden = true;
  });
  window.addEventListener("drop", (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0;
    zone.hidden = true;
    importFile(e.dataTransfer.files[0]);
  });
}

// ----------------------------------------------------------------------------- boot
async function main() {
  const [defaults, current] = await Promise.all([api("GET", "/api/defaults"), api("GET", "/api/config")]);
  buildForm(defaults.fields, defaults.payload_presets);
  writeForm(current.config);
  savedJson = JSON.stringify(current.config);

  form.addEventListener("pb-change", () => {
    syncPreset();
    setStatus("Updating…");
    scheduleRender();
  });
  form.addEventListener("submit", (e) => e.preventDefault());
  form.addEventListener("pb-action", (e) => {
    if (e.detail.action === "maximize") payloadAction({ action: "maximize", field: e.detail.name });
  });

  // Link parameters and dimensions: focusing or hovering a field highlights its dimensions
  // in every view; clicking a dimension focuses its field.
  let focused = null;
  const highlight = (param) => {
    for (const view of [preview2d, preview3d, sectionView]) view.highlight(param);
  };
  form.addEventListener("focusin", (e) => {
    focused = e.target.closest("pb-param")?.name ?? null;
    highlight(focused);
  });
  form.addEventListener("focusout", () => {
    focused = null;
    highlight(null);
  });
  form.addEventListener("mouseover", (e) => highlight(e.target.closest("pb-param")?.name ?? focused));
  form.addEventListener("mouseleave", () => highlight(focused));
  document.addEventListener("pb-dim-click", (e) => params.get(e.detail.param)?.focusInput());
  $("#btn-import").addEventListener("click", () => $("#file-input").click());
  $("#file-input").addEventListener("change", (e) => {
    importFile(e.target.files[0]);
    e.target.value = "";
  });
  $("#btn-reset").addEventListener("click", resetToDefaults);
  downloadBtn.addEventListener("click", download);
  scadBtn.addEventListener("click", downloadScad);
  pcbBtn.addEventListener("click", downloadPcb);
  document.addEventListener("pb-mesh-toggle", toggleMesh);
  setupSidebar();
  $("#stats > header").append(maximizeButton($("#stats")));
  $("#banner-close").addEventListener("click", hideBanner);
  setupDragAndDrop();
  await render();
}

initPanels($(".layout")); // (dividers and maximizing work before the first render)
main().catch((err) => {
  setStatus("Failed to start", true);
  showBanner(`Failed to start: ${err.message}`);
});
