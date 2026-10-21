// Serves the app's /api/* requests from Python running in the browser (pyworker.js), so the
// unchanged frontend works without the Flask server. Settings persist in browser storage.
// Loaded before app.js.

const STORE_KEY = "yanartas-pillowbox.config";
const LOCAL_CMD =
  "uvx --from git+https://github.com/jaseg/temp-workspace@yanartas-pillowbox yanartas-pillowbox";

const pending = new Map();
let seq = 0;
let startError = null;

const statusEl = () => document.getElementById("status");

function banner(message) {
  const box = document.getElementById("banner");
  const text = document.getElementById("banner-text");
  if (!box || !text) return;
  text.textContent = message;
  box.hidden = false;
}

const started = performance.now();
const tick = setInterval(() => {
  const s = Math.round((performance.now() - started) / 1000);
  const el = statusEl();
  if (el) el.textContent = `Starting the geometry engine (Python in your browser)… ${s} s`;
}, 500);

let progress = null; // (the PCB layout's latest progress event, from the worker)

function onMessage({ data }) {
  if (data.progress) {
    progress = data.progress;
    return;
  }
  if (data.ready) {
    clearInterval(tick);
    return;
  }
  if (data.failed) {
    clearInterval(tick);
    startError = data.failed;
    for (const { reject } of pending.values()) reject(new Error(startError));
    pending.clear();
    banner(`The geometry engine could not start in this view (${startError}). `
      + `You can run the tool on your own computer instead: ${LOCAL_CMD}`);
    return;
  }
  const entry = pending.get(data.id);
  if (!entry) return;
  pending.delete(data.id);
  if (data.error) entry.reject(new Error(data.error));
  else entry.resolve(JSON.parse(data.reply));
}

function startWorker() {
  const w = new Worker(new URL("./pyworker.js", import.meta.url), { type: "module" });
  w.onmessage = onMessage;
  w.onerror = (e) => {
    e.preventDefault?.();
    onMessage({ data: { failed: e.message || "the worker failed to load" } });
  };
  return w;
}

let worker = startWorker();

/** Cancel the PCB layout under way: Python runs it in one go, so the worker goes (and every
 *  request it had: the layout's answers "cancelled") and a fresh one starts. */
function cancelLayout() {
  worker.terminate();
  const cancelled = JSON.stringify({ error: "the mesh layout was cancelled", cancelled: true, errors: {} });
  for (const { resolve } of pending.values()) {
    resolve({ status: 409, content: cancelled, type: "application/json" });
  }
  pending.clear();
  progress = null;
  worker = startWorker();
}

function call(request) {
  if (startError) return Promise.reject(new Error(startError));
  const id = ++seq;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, ...request });
  });
}

function readStore() {
  try {
    return localStorage.getItem(STORE_KEY);
  } catch {
    return null;
  }
}

function writeStore(config) {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(config));
  } catch {
    // Storage blocked (private window, previews): settings just are not remembered.
  }
}

const realFetch = window.fetch.bind(window);

window.fetch = async (input, init = {}) => {
  const url = new URL(typeof input === "string" ? input : input.url, location.href);
  if (url.origin !== location.origin || !url.pathname.startsWith("/api/")) {
    return realFetch(input, init);
  }
  const method = (init.method || "GET").toUpperCase();
  if (method === "GET" && url.pathname === "/api/progress") { // (the worker is busy laying out)
    return new Response(JSON.stringify({ progress }), {
      status: 200, headers: { "Content-Type": "application/json" },
    });
  }
  if (method === "POST" && url.pathname === "/api/pcb/cancel") {
    cancelLayout();
    return new Response(JSON.stringify({ cancelled: true }), {
      status: 200, headers: { "Content-Type": "application/json" },
    });
  }
  if (method === "POST" && url.pathname === "/api/pcb") progress = null;
  let content = init.body ?? null;
  if (content instanceof FormData) {
    const file = content.get("file");
    content = file ? await file.text() : "";
  }
  const stored = method === "GET" && url.pathname === "/api/config" ? readStore() : null;
  const reply = await call({ method, path: url.pathname, content, stored });
  if (method === "PUT" && url.pathname === "/api/config" && reply.status === 200) {
    writeStore(JSON.parse(reply.content).config);
  }
  let payload = reply.content;
  if (reply.encoding === "base64") { // binary (the PCB files' zip)
    const bin = atob(payload);
    payload = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) payload[i] = bin.charCodeAt(i);
  }
  return new Response(payload, { status: reply.status, headers: { "Content-Type": reply.type } });
};

// Downloads go through the viewer's "downloads" capability (plain download links are blocked
// in the artifact frame); app.js calls this instead of clicking a blob link.
window.pbSave = async (blob, name) => {
  const downloads = await window.claude?.use?.("downloads");
  if (!downloads) {
    banner(`Downloads are not available in this view, so ${name} could not be saved.`);
    return;
  }
  try {
    await downloads.save({ filename: name, data: blob });
  } catch (err) {
    if (err?.code !== "declined") banner(`Could not save ${name}: ${err?.message ?? err}`);
  }
};
