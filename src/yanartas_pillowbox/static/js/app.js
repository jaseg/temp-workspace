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

const params = new Map(); // name -> <pb-param>
let fields = [];
// Values of config fields that have no form input (e.g. line colors); kept so renders,
// saves and imports carry them through unchanged.
let hiddenValues = {};
let lastValid = null; // {config, svg, model, info}
let savedJson = null;
let renderSeq = 0;
let renderTimer = 0;
let saveTimer = 0;

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
function buildForm(specs) {
  fields = specs;
  form.replaceChildren();
  const groups = new Map();
  for (const spec of specs) {
    if (spec.hidden) continue;
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
}

function readForm() {
  const config = { ...hiddenValues };
  for (const [name, p] of params) config[name] = p.value;
  return config;
}

function writeForm(config) {
  hiddenValues = {};
  for (const spec of fields) if (spec.hidden && spec.name in config) hiddenValues[spec.name] = config[spec.name];
  for (const [name, p] of params) if (name in config) p.value = config[name];
  updateVisibility();
}

function updateVisibility() {
  const values = readForm();
  for (const spec of fields) {
    if (!spec.dependsOn || !params.has(spec.name)) continue;
    params.get(spec.name).hidden = values[spec.dependsOn.field] !== spec.dependsOn.value;
  }
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
    downloadBtn.disabled = true;
    return;
  }
  showErrors({});
  const { svg, model, section, info, dimensions } = result.data;
  lastValid = { config: result.data.config, svg, model, section, info };
  const c = lastValid.config;
  const legend = [
    { label: "Cut", color: c.color_cut },
    { label: "Straight fold", color: c.color_fold_straight },
    { label: "Curved fold", color: c.color_fold_curved },
    { label: "Glue-tab fold", color: c.color_fold_glue },
  ];
  preview2d.update(svg, info, legend, dimensions.pattern);
  const foldColors = {
    straight: c.color_fold_straight, curved: c.color_fold_curved, glue: c.color_fold_glue,
  };
  preview3d.update(model, foldColors, dimensions.model);
  sectionView.update(section, foldColors, dimensions.section);
  renderDerived(info);
  downloadBtn.disabled = false;
  setStatus("Up to date");
  scheduleSave(lastValid.config);
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

function renderDerived(info) {
  const rows = [
    ["Straight edge (corner to corner)", info.edge_length],
    ["Circumference", info.circumference],
    ["Panel width (½ circumference)", info.panel_width],
    ["Curved-fold sagitta", info.fold_sagitta],
    ["Curved-fold radius", info.fold_radius],
    ["Curved-fold arc length", info.fold_arc_length],
    ["Flap cut sagitta", info.cut_sagitta],
    ["Flap cut radius", info.cut_radius],
    ["Min. glue-tab taper", info.min_glue_tab_taper],
  ];
  $("#derived").replaceChildren(...rows.flatMap(([k, v]) => {
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = `${v.toFixed(2)} mm`;
    return [dt, dd];
  }));
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

function download() {
  if (!lastValid) return;
  const c = lastValid.config;
  const n = (v) => String(Math.round(v * 10) / 10);
  const name = `pillowbox-${n(c.width)}x${n(c.length)}x${n(c.height)}mm.svg`;
  const url = URL.createObjectURL(new Blob([lastValid.svg], { type: "image/svg+xml" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
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
  buildForm(defaults.fields);
  writeForm(current.config);
  savedJson = JSON.stringify(current.config);

  form.addEventListener("pb-change", () => {
    updateVisibility();
    setStatus("Updating…");
    scheduleRender();
  });
  form.addEventListener("submit", (e) => e.preventDefault());

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
  $("#banner-close").addEventListener("click", hideBanner);
  setupDragAndDrop();
  await render();
}

main().catch((err) => {
  setStatus("Failed to start", true);
  showBanner(`Failed to start: ${err.message}`);
});
