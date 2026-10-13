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
| `pb_api.py` | Python side of the API. It mirrors `server.py` route by route; `tests/test_artifact_api.py` keeps the two in step. Settings are stored by the caller, not on disk. |
| `pyworker.js` | Web worker that starts Pyodide, loads the modules and answers requests. |
| `pyshim.js` | Loaded before `app.js`. It routes `fetch("/api/…")` to the worker and keeps settings in `localStorage`. Downloads go through the Artifact viewer's `downloads` capability. |
| `build.py` | Assembles `dist/`. |

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
