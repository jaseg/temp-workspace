# Rust core

The security mesh's curve layout (see ARCHITECTURE.md, Space-filling curve), the only
implementation of it: the graph (`graph.rs`, with `poly.rs`), the relaxation and growth
(`curve.rs`), the lanes (`lanes.rs`), settling and length matching (`settle.rs`).
`sfc.py` prepares what needs shapely on whole regions and calls it, natively through the
PyO3 extension (a dependency of the package, built from `rust/python` by `uv sync`), in
the browser through the WebAssembly build. Its constants stay in `sfc.py` and are passed in
by name. On the default box a side takes about 2 min on four cores, nearly all settling.
License: AGPL-3.0-or-later.

| Crate | Role |
| --- | --- |
| `core` (`yanartas-mesh-core`) | The algorithm. `parallel` (default): per-vertex work on all cores (rayon). |
| `python` (`yanartas-mesh`, module `yanartas_mesh`) | The PyO3 extension: `curve_graph`, `relax_curve`, `offset_lanes`, `settle_traces` (each with the constants by name and a progress callback; `_cells` for tests). |
| `wasm` (`yanartas-mesh-wasm`) | The browser build (wasm-bindgen, `--target web`, SIMD): the same four on flat typed arrays; `artifact/build.py` builds it, `sfc._browser_core` calls it. |

```sh
uv sync                                                   # (builds and installs the extension)
cargo test --release --manifest-path rust/Cargo.toml
rustup target add wasm32-unknown-unknown                  # (for artifact/build.py)
cargo install wasm-bindgen-cli --version <rust/Cargo.lock's wasm-bindgen>
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

1. Core: settling and length matching (done), unit tests against small cases (done).
2. Python: the extension (done); status lines and a progress bar in the CLI (done).
3. Threads: per vertex within a step (done, rayon). Panels as units: settling keeps every
   vertex in its zone, so a panel needs only its own copper; the steering's bookkeeping
   (each trace's length gained by place along the curve) is shared once a step. In the
   browser that maps onto one Web Worker per panel (no shared memory needed).
4. WebAssembly: the core built for the browser and called from the Pyodide worker (done;
   same results as native to 1e-13), the web UI's progress bar (done). Per-panel workers:
   to come.
5. The rest of the curve layout: the graph, relaxation and lanes (done).
6. Later: panels as separate workers in the browser.
