// Runs the yanartas-pillowbox Python package in Pyodide, off the main thread.
// Messages in: {id, method, path, content, stored}; out: {id, reply} or {id, error};
// plus one {ready: true} or {failed: message} once start-up is over.

const here = (path) => new URL(path, import.meta.url);

// Artifacts cannot serve .zip or .whl files, so binaries ship base64-encoded as text.
async function fetchBase64(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`could not load ${url.pathname.split("/").pop()} (${res.status})`);
  const bin = atob((await res.text()).trim());
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

/** A package shipped in base64 parts (<name>.<i>.b64.txt, see build.py). */
async function fetchParts(dir, name, count) {
  const parts = await Promise.all(Array.from({ length: count }, (_, i) =>
    fetch(here(`${dir}/${name}.${i}.b64.txt`)).then((r) => {
      if (!r.ok) throw new Error(`could not load ${name} (${r.status})`);
      return r.text();
    })));
  const bin = atob(parts.map((p) => p.trim()).join(""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

async function stdLibURL() {
  const bytes = await fetchBase64(here("./pyodide/python_stdlib.zip.b64.txt"));
  return URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
}

// Pyodide fetches its packages from indexURL by file name: serve the encoded copies.
const encoded = new Map(); // file name under ./pyodide/ -> parts it ships in
const realFetch = self.fetch.bind(self);
self.fetch = (input, init) => {
  // (Pyodide passes a URL object)
  const url = new URL(input instanceof Request ? input.url : String(input), import.meta.url);
  const name = url.pathname.split("/").pop();
  if (url.href === here(`./pyodide/${name}`).href && encoded.has(name)) {
    return fetchParts("./pyodide", name, encoded.get(name)).then((bytes) => new Response(bytes));
  }
  return realFetch(input, init);
};

let py = null;

const api = (async () => {
  const { loadPyodide } = await import("./pyodide/pyodide.mjs");
  py = await loadPyodide({
    indexURL: here("./pyodide/").href,
    stdLibURL: await stdLibURL(),
  });
  py.FS.mkdirTree("/home/pyodide/yanartas_pillowbox");
  const listing = await fetch(here("./py/files.json"));
  if (!listing.ok) throw new Error(`could not load the module list (${listing.status})`);
  await Promise.all((await listing.json()).map(async (name) => {
    const res = await fetch(here(`./py/${name}`));
    if (!res.ok) throw new Error(`could not load ${name} (${res.status})`);
    py.FS.writeFile(`/home/pyodide/${name}`, await res.text());
  }));
  py.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
  return py.pyimport("pb_api");
})();

// The PCB layout's dependencies (shapely, gerbonara and the rtree stand-in), loaded on the
// first PCB request: most sessions never need them, and they take a while.
let pcb = null;
function loadPcb() {
  pcb ??= (async () => {
    const res = await fetch(here("./py/pcb.json"));
    if (!res.ok) throw new Error(`could not load the PCB package list (${res.status})`);
    const { packages, files, parts, wheels, stubs } = await res.json();
    for (const name of files) encoded.set(name, parts[name]);
    await py.loadPackage(packages);
    py.runPython(`import ${packages.join(", ")}`); // (loadPackage only logs a failure)
    for (const name of wheels) {
      py.unpackArchive(await fetchParts("./py/wheels", name, parts[name]), "whl");
    }
    for (const name of stubs) {
      const r = await fetch(here(`./py/stubs/${name}`));
      if (!r.ok) throw new Error(`could not load ${name} (${r.status})`);
      const path = `/home/pyodide/${name}`;
      py.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
      py.FS.writeFile(path, await r.text());
    }
    py.runPython("import importlib; importlib.invalidate_caches()");
    // The mesh settling in WebAssembly (sfc.py calls self.yanartasMesh.settle); without
    // it (a build with --no-wasm) sfc settles in numpy, far slower.
    try {
      const mesh = await import("./mesh/yanartas_mesh_wasm.js");
      await mesh.default({ module_or_path: here("./mesh/yanartas_mesh_wasm_bg.wasm") });
      self.yanartasMesh = mesh;
      console.info("mesh settling: WebAssembly ready");
    } catch (err) {
      console.warn("mesh settling in WebAssembly unavailable:", err);
    }
  })();
  pcb.catch(() => { pcb = null; }); // (try again on the next request)
  return pcb;
}

api.then(
  () => self.postMessage({ ready: true }),
  (err) => self.postMessage({ failed: String(err?.message ?? err) }),
);

self.onmessage = async ({ data }) => {
  const { id, method, path, content, stored } = data;
  try {
    const pbApi = await api;
    if (path.startsWith("/api/pcb")) await loadPcb();
    self.postMessage({ id, reply: pbApi.serve(method, path, content ?? null, stored ?? null) });
  } catch (err) {
    self.postMessage({ id, error: String(err?.message ?? err) });
  }
};
