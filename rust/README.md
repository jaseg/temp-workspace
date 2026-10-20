# Rust core

The security mesh's settling and length matching (see ARCHITECTURE.md, Space-filling
curve, 9. Settling), the only implementation of them: `sfc.py` prepares what needs shapely
and calls it, natively through the PyO3 extension (a dependency of the package, built from
`rust/python` by `uv sync`), in the browser through the WebAssembly build. Its constants
stay in `sfc.py` and are passed in by name. On the default box, settling takes about 2 min
on four cores. License: AGPL-3.0-or-later.

| Crate | Role |
| --- | --- |
| `core` (`yanartas-mesh-core`) | The algorithm. `parallel` (default): per-vertex work on all cores (rayon). |
| `python` (`yanartas-mesh`, module `yanartas_mesh`) | The PyO3 extension: `settle_traces(lines, pitch, edge, zones, keep, params, progress)`. |
| `wasm` (`yanartas-mesh-wasm`) | The browser build (wasm-bindgen, `--target web`): `settle(...)` on flat typed arrays; `artifact/build.py` builds it. |

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
5. Later: the rest of the curve layout (CVT graph, matching, relaxation, lanes).
