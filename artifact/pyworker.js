// Runs the yanartas-pillowbox Python package in Pyodide, off the main thread.
// Messages in: {id, method, path, body, stored}; out: {id, reply} or {id, error};
// plus one {ready: true} or {failed: message} once start-up is over.

import { loadPyodide } from "./pyodide/pyodide.mjs";

const PY_FILES = [
  "pb_api.py",
  "yanartas_pillowbox/__init__.py",
  "yanartas_pillowbox/config.py",
  "yanartas_pillowbox/crosssection.py",
  "yanartas_pillowbox/geometry.py",
  "yanartas_pillowbox/svg.py",
  "yanartas_pillowbox/dimensions.py",
  "yanartas_pillowbox/payload.py",
  "yanartas_pillowbox/presets.py",
  "yanartas_pillowbox/scad.py",
];

// Artifacts cannot serve .zip files, so the standard library ships base64-encoded as text.
async function stdLibURL() {
  const res = await fetch(new URL("./pyodide/python_stdlib.zip.b64.txt", import.meta.url));
  if (!res.ok) throw new Error(`could not load the Python standard library (${res.status})`);
  const bin = atob((await res.text()).trim());
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
}

const api = (async () => {
  const py = await loadPyodide({
    indexURL: new URL("./pyodide/", import.meta.url).href,
    stdLibURL: await stdLibURL(),
  });
  py.FS.mkdirTree("/home/pyodide/yanartas_pillowbox");
  await Promise.all(PY_FILES.map(async (name) => {
    const res = await fetch(new URL(`./py/${name}`, import.meta.url));
    if (!res.ok) throw new Error(`could not load ${name} (${res.status})`);
    py.FS.writeFile(`/home/pyodide/${name}`, await res.text());
  }));
  py.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
  return py.pyimport("pb_api");
})();

api.then(
  () => self.postMessage({ ready: true }),
  (err) => self.postMessage({ failed: String(err?.message ?? err) }),
);

self.onmessage = async ({ data }) => {
  const { id, method, path, body, stored } = data;
  try {
    const handler = await api;
    self.postMessage({ id, reply: handler.handle(method, path, body ?? null, stored ?? null) });
  } catch (err) {
    self.postMessage({ id, error: String(err?.message ?? err) });
  }
};
