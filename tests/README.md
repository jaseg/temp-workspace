# Layout testing

The coil generator is tested by generating footprints for a corpus of shapes and parameters and checking the resulting
copper geometry with automated geometric checks. The checks only look at what ends up in the footprint (tracks, arcs,
vias, pads) and at the user-facing intent (outline, annular width, turns, trace width, clearance), so the same harness
can compare different layout implementations.

Prerequisite: `src/kicoil/skeleton.wasm` (built from `cgal_skeleton_core`, or copied from a release zip:
`unzip -j de.jaseg.kicoil-v0.11.1.zip plugins/kicoil/skeleton.wasm -d src/kicoil/`).

## Files

- `geomcheck.py`: the checker. `extract_copper(footprint)` flattens a footprint into straight segments (arcs are
  discretized to 0.5 µm), vias and pads; `intent_from_model(model)` derives the intended geometry;
  `check_layout(copper, intent)` returns a `Report`.
- `corpus.py`: about 600 deterministic test cases (`corpus('full')`, or `corpus('quick')` for every 7th case).
- `run_corpus.py`: runs the corpus in parallel, prints a summary, writes per-case JSON and renders SVGs of failing cases.
- `test_layout.py`: pytest suite. Runs the quick corpus plus regression tests for specific bugs. `--full-corpus` runs
  everything.

## What is checked

| Property | Check |
|---|---|
| Connectivity | Centerline graph (endpoints joined within 1 nm, vias join layers) must be a simple path from pad 1 to pad 2: no open ends, no branches, no orphaned segments. Dangling stubs next to pads are counted separately. |
| Winding | Total angle swept by the path around a point in the coil's hole must equal the number of turns (sign by direction). Catches lost, doubled or reversed turns. |
| Backtracking | Consecutive segments on one layer that reverse direction (> 170°). |
| Crossings | Same-layer centerlines of segments that are far apart along the conductor must not intersect. |
| Clearance | Edge-to-edge distance between copper of *different turns* (more than max(4·(w+c), ¼ inner perimeter) apart along the conductor path) must be at least the clearance. Track-to-track and via-related violations are reported separately (worst deficit in mm and relative to the clearance). |
| Spacing uniformity | Sampled edge-to-edge distance to the neighboring turn, relative to the clearance (min, 5th and 95th percentile), and `pitch_ratio` = (w + c) / nominal pitch, i.e. how much of the available pitch the layout turns into copper. |
| Outline conformance | *Core coverage*: every spiral layer, inflated by half a pitch, must cover the band from ½ pitch to annular width − ½ pitch inside the outline (uncovered area means wasted space or a missing turn). *Overshoot*: no copper outside the envelope from −w/2 to annular width + w/2 (allowing via stubs). *Undershoot*: every point of the outline within one pitch of copper. |

A case passes when connectivity is intact, there are no crossings, track and via clearance deficits are at most 5 % of
the clearance, the winding is within 0.05 turns, and conformance holds (uncovered < 5 %, undershoot < 1.25 pitches,
overshoot < max(0.05 mm, w/10)). Requests that the generator rejects with a `ValueError` are reported as `rejected`; a
clear rejection of an infeasible request is acceptable, a crash (`error`) is not.

## Corpus

Shapes: square, rectangles (2:1, 5:1), trapezoid, regular 3/5/6/8/24-gons, ellipses, rounded rectangle, rectangles with
tiny and small chamfers, rectangles with nearly collinear extra vertices (with and without jitter), stars, circular
sectors (45°, 90°, 180°), L, U and D shapes, random convex and random star-shaped polygons, and circles.

Parameters: annular width at 30 %, 60 % and 90 % of the outline's maximum inscribed radius; turns/twists from 2/1 to
21/8 (only co-prime pairs); single layer; clockwise. Sweeps vary the annular width in 3 % steps and the outline scale by
±1–3 % on seven base shapes, which exposes layouts that break under small tweaks. Dense cases use 30–31 turns.

## Usage

```bash
uv run --group dev pytest tests
```

```bash
uv run python tests/run_corpus.py --kind full --out results.json --svg-dir failures/ -v
```

```bash
PYTHONPATH=/path/to/other/checkout/src uv run python tests/run_corpus.py --out other.json
```

```bash
uv run python tests/run_corpus.py --impl geometry_alt_cornerflat
```

`--impl MODULE` loads `kicoil.MODULE` instead of `kicoil.geometry`. `--filter SUBSTR` selects cases by name. With
`RENDER_ALL=1` every case is rendered, not only failures. The SVGs show both copper layers, the outline, violations
(orange), crossings and the location of the minimum turn spacing (magenta) and a heat map of the spacing on the first
layer (green: spacing matches w+c, blue: looser, red: tighter).
