// Serves the app's /api/* requests from Python running in the browser (pyworker.js), so the
// unchanged frontend works without the Flask server. Settings persist in browser storage.
// Loaded before app.js.

const STORE_KEY = "yanartas-pillowbox.config";
const LOCAL_CMD =
  "uvx --from git+https://github.com/jaseg/temp-workspace@yanartas-pillowbox yanartas-pillowbox";

const worker = new Worker(new URL("./pyworker.js", import.meta.url), { type: "module" });
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

worker.onmessage = ({ data }) => {
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
};

worker.onerror = (e) => {
  e.preventDefault?.();
  worker.onmessage({ data: { failed: e.message || "the worker failed to load" } });
};

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
  let body = init.body ?? null;
  if (body instanceof FormData) {
    const file = body.get("file");
    body = file ? await file.text() : "";
  }
  const stored = method === "GET" && url.pathname === "/api/config" ? readStore() : null;
  const reply = await call({ method, path: url.pathname, body, stored });
  if (method === "PUT" && url.pathname === "/api/config" && reply.status === 200) {
    writeStore(JSON.parse(reply.body).config);
  }
  let payload = reply.body;
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
