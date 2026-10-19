// Application controller: builds the parameter form from the server's field specs, renders
// through /api/render (debounced), persists through PUT /api/config, and handles
// import/export/reset. Geometry lives entirely in Python; nothing here computes shapes.

import "./components/pb-param.js";
import "./components/pb-preview2d.js";
import "./components/pb-preview3d.js";
import "./components/pb-section.js";

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
const MESH_DELAY = 400; // ms after a render: the PCB layout takes a second or two

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
let meshTimer = 0;

// ----------------------------------------------------------------------------- API helpers
async function api(method, url, body, { raw = false } = {}) {
  const init = { method, headers: {} };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(url, init);
  const data = await res.json().catch(() => ({}));
  if (raw) return { ok: res.ok, status: res.status, data };
  if (!res.ok) throw new Error(data.error || `${method} ${url} failed (${res.status})`);
  return data;
}

// ----------------------------------------------------------------------------- form
function buildForm(specs, presets = []) {
  form.replaceChildren();
  const groups = new Map();
  for (const spec of specs) {
    if (!groups.has(spec.group)) {
      const fs = document.createElement("fieldset");
      const legend = document.createElement("legend");
      legend.textContent = spec.group;
      fs.append(legend);
      groups.set(spec.group, fs);
      form.append(fs);
    }
    const param = document.createElement("pb-param");
    param.spec = spec;
    params.set(spec.name, param);
    groups.get(spec.group).append(param);
  }
  // Body: compute the smallest box (width, length, height) that holds the payload.
  const fit = Object.assign(document.createElement("button"), {
    type: "button",
    className: "group-action",
    textContent: "Fit box to payload",
    title: "Smallest width, length and height that hold the payload, minimizing the "
      + "pattern's bounding box. Glue tab and thickness are kept.",
  });
  fit.addEventListener("click", () => payloadAction({ action: "fit" }));
  groups.get("Body")?.append(fit);

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
  groups.get("Payload")?.querySelector("legend").after(presetParam);
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
  if (showMesh) scheduleMesh();
}

// ----------------------------------------------------------------------------- PCB mesh
function setMesh(pcb) {
  preview2d.setMesh(pcb);
  preview3d.setMesh(pcb);
}

function toggleMesh() {
  showMesh = !showMesh;
  preview2d.meshShown = preview3d.meshShown = showMesh;
  if (showMesh) scheduleMesh(0);
  else {
    meshSeq++; // drop a layout in flight
    clearTimeout(meshTimer);
    setMesh(null);
  }
}

/** Lay out the PCB for the current design and show its copper (the old one goes at once:
 *  it no longer matches the pattern). */
function scheduleMesh(delay = MESH_DELAY) {
  const seq = ++meshSeq;
  clearTimeout(meshTimer);
  setMesh(null);
  meshTimer = setTimeout(async () => {
    if (!lastValid) return;
    setStatus("Laying out the mesh…");
    const { ok, data } = await api("POST", "/api/pcb", { config: lastValid.config }, { raw: true })
      .catch((err) => ({ ok: false, data: { error: err.message } }));
    if (seq !== meshSeq) return;
    if (!ok) {
      setStatus(`Mesh: ${data.error || "layout failed"}`, true);
      return;
    }
    setMesh(data);
    const m = data.meshes;
    const missed = m.front.unreached + m.back.unreached;
    setStatus(`Mesh: ${m.front.cells} + ${m.back.cells} cells of ${m.front.cell} mm`
      + (missed ? `, ${missed} out of reach` : ""), missed > 0);
  }, delay);
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
  const rows = [
    ["Outside (w × h × l)", `${[info.outer_width, info.outer_height, info.outer_length].map((v) => v.toFixed(2)).join(" × ")} mm`],
    ["Front / back straight edge", pair(info.front_edge_length, info.edge_length)],
    ["Circumference", info.circumference],
    ["Front / back panel width", pair(info.front_panel_width, info.back_panel_width)],
    ["Front / back fold sagitta", pair(info.front_fold_sagitta, info.back_fold_sagitta)],
    ["Front / back fold radius", pair(info.front_fold_radius, info.back_fold_radius)],
    ["Outer / inner flap cut sagitta", pair(info.front_cut_sagitta, info.back_cut_sagitta)],
    ["Glue-tab taper", info.glue_tab_taper],
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
  const body = new FormData();
  body.append("file", file, file.name);
  const { ok, data } = await api("POST", "/api/import", body, { raw: true });
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
  setStatus("Laying out the PCB…");
  try {
    const res = await fetch("/api/pcb/files", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: lastValid.config }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || `export failed (${res.status})`);
    }
    saveBlob(await res.blob(), fileName("-pcb.zip"));
    setStatus("Up to date");
  } catch (err) {
    setStatus(`PCB export failed: ${err.message}`, true);
    showBanner(`PCB export failed: ${err.message}`);
  }
}

async function resetToDefaults() {
  const { config } = await api("GET", "/api/defaults");
  hideBanner();
  writeForm(config);
  scheduleRender(0);
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
  $("#banner-close").addEventListener("click", hideBanner);
  setupDragAndDrop();
  await render();
}

main().catch((err) => {
  setStatus("Failed to start", true);
  showBanner(`Failed to start: ${err.message}`);
});
