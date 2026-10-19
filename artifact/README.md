# In-browser build (Pyodide)

Runs the web UI without the Flask server. The package's geometry modules run in the
browser under [Pyodide](https://pyodide.org) 0.26.4, and the frontend is unchanged. This is
how the UI is published as a claude.ai Artifact.

```sh
uv run python artifact/build.py            # writes artifact/dist/
python -m http.server -d artifact/dist     # then open /local-test.html
```

The first build downloads the Pyodide npm tarball to `artifact/.cache/` and checks its
sha512 against the registry's integrity hash. Pass `--pyodide-tgz FILE` to use a local copy.

| File | Role |
| --- | --- |
| `pb_api.py` | Python side of the API. It routes requests to the package's `api` module like `server.py` does; `tests/test_artifact_api.py` keeps the two in step. Settings are stored by the caller, not on disk. |
| `pyworker.js` | Web worker that starts Pyodide, loads the modules listed in `py/files.json` and answers requests. |
| `pyshim.js` | Loaded before `app.js`. It routes `fetch("/api/…")` to the worker and keeps settings in `localStorage`. Downloads go through the Artifact viewer's `downloads` capability. |
| `build.py` | Assembles `dist/`. |
| `stubs/rtree/` | Stand-in for `rtree`, which needs a C library Pyodide lacks. gerbonara imports it at the top of `gerbonara.cad.kicad.pcb` for a trace look-up index the PCB layout never uses; the stand-in fails loudly if anything does. |

`dist/index.html` is the page body for an Artifact; the viewer adds the document skeleton.
`dist/local-test.html` is the same page as a full document.

The build changes the frontend in only a few ways, all to fit the Artifact viewer:
- Downloads use `window.pbSave` instead of a blob link.
- The OpenSCAD file is saved as `.scad.txt`, because the downloads allowlist has no `.scad`.
- `app.css` follows the viewer's `data-theme` setting.
- Pages get a 16 px side gutter.

Other constraints of the viewer:
- No inline scripts and no import maps.
- Scripts load only from the page's own files, so three.js is shipped alongside the page.
- `.zip` files are not served, so the Python standard library ships base64-encoded as text.

**PCB layout.** The layout needs shapely and gerbonara. `build.py` bundles shapely (with
numpy, from Pyodide's CDN, checked against the tarball's `pyodide-lock.json`), click, and the
gerbonara wheel (from PyPI, checked against a pinned sha256; installed without its
dependencies: quart only serves its own web UI, and `stubs/rtree` stands in for rtree). They
ship base64-encoded in parts of at most 4 MB (`py/pcb.json` lists them; artifact files may be
16 MB at most) and the worker loads them on the first PCB request, serving Pyodide's package
loader through a `fetch` wrapper. Laying out the default box takes about 3 s (the first
time about 6 s, with the loading), its zip of files about 20 s. The zip reply
travels base64-encoded (`encoding: "base64"`), and `pyshim.js` decodes it.
