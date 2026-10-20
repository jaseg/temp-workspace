# Rust core

The mesh layout's settling (`sfc._settle`, `sfc._match`) in Rust: about 15x the numpy
code's speed on four cores (the default box: settling 125 s instead of about 30 min).
`sfc.py` uses it when the extension is installed and its own numpy code otherwise
(`SETTLE_NATIVE`); its constants stay in `sfc.py` and are passed in.

| Crate | Role |
| --- | --- |
| `core` (`pillowbox-mesh-core`) | The algorithm. `parallel` (default): per-vertex work on all cores (rayon). |
| `python` (`pillowbox_mesh`) | The PyO3 extension: `settle_traces(lines, pitch, edge, zones, keep, params, progress)`. |
| `wasm` | The browser build (wasm-bindgen; to come). |

```sh
uv tool run maturin build --release -m rust/python/Cargo.toml -o dist/
uv pip install dist/pillowbox_mesh-*.whl          # (into the project's environment)
cargo test --release --manifest-path rust/Cargo.toml
```

## Design

- **What Python keeps:** the geometry that needs shapely (the edge's points: the area's
  edge and the zones' borders but at the curve's joins; the zones' rings; the exit's box).
  Rust gets plain arrays.
- **Neighbours:** a flat bucket grid (a counting sort by cell), cells half the search
  radius (5 x 5 cells a look-up). The edge's grid is asked first whether anything is near
  at all: most vertices are far from the edge. Zones: an even-odd ray test against the
  zones' edges, bucketed by height.
- **Steps:** each phase of a step (centring, steering, smoothing, clearance, respacing) is
  data-parallel per vertex from one snapshot, with a barrier between phases.
- **Progress:** a callback after every step with the phase (`settle`, `match`), the step
  and the most there may be, vertices, vertices looked at and moved, vertex-segment pairs
  measured, and each neighbouring pair's length difference.

## Plan

1. Core: settling and length matching (done), unit tests against small cases.
2. Python: the extension (done); status lines and a progress bar in the CLI.
3. Threads: per vertex within a step (done, rayon). Panels as units: settling keeps every
   vertex in its zone, so a panel needs only its own copper; the steering's bookkeeping
   (each trace's length gained by place along the curve) is shared once a step. In the
   browser that maps onto one Web Worker per panel (no shared memory needed).
4. WebAssembly: the core built for the browser, run in the Pyodide worker's place for the
   settling, a progress bar in the web UI from the workers' messages.
5. Later: the rest of the curve layout (CVT graph, matching, relaxation, lanes).
