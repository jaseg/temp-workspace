# Layout testing

The coil generator is tested by generating footprints for a corpus of shapes and parameters and checking the resulting
copper geometry with automated geometric checks. The checks only look at what ends up in the footprint (tracks, arcs,
vias, pads) and at the user-facing intent (outline, annular width, turns, trace width, clearance), so the same harness
can compare different layout implementations.

Prerequisite: `src/kicoil/skeleton.wasm` (built from `cgal_skeleton_core`, or copied from a release zip:
`unzip -j de.jaseg.kicoil-v0.11.1.zip plugins/kicoil/skeleton.wasm -d src/kicoil/`).

## Files

- `geomcheck.py`: the checker. `extract_copper(footprint)` flattens a footprint into straight segments (arcs are
  discretized to 0.5 µm), vias and pads, and lists copper items it cannot interpret; `intent_from_model(model)` derives
  the intended geometry; `check_layout(copper, intent)` returns a `Report`. `Report.failure_kinds(clearance, w)` names
  the failed checks, `Report.passed(...)` is true when there are none.
- `corpus.py`: about 600 deterministic test cases (`corpus('full')`, or `corpus('quick')` for every 7th case).
- `run_corpus.py`: runs the corpus in parallel, prints a summary, writes per-case JSON and renders SVGs of failing cases.
- `compare_results.py`: compares the JSON of several runs (e.g. two implementations, or before/after a change).
- `test_layout.py`: pytest suite. Runs the quick corpus plus regression tests for specific bugs. `--full-corpus` runs
  everything.
- `test_geomcheck.py`: mutation tests for the checker. Takes clean layouts of a few corpus cases, injects one defect
  at a time (gaps, deleted or duplicated segments, pushed vertices, joints pushed across the neighboring turn, shorted
  turns, vias moved outside, grown or defective vias, narrow tracks, oversized, undersized or displaced pads, copper
  dots between turns or outside the outline, copper on an inner layer, a via shorting pad 1 to pad 2, stray vias,
  jumpers, long dead ends at a pad, hairpins, mirrored copper) and asserts that the checker reports the right kind of
  failure. It also asserts that legitimate variations (a track end inside a via or pad, a short piece of track inside
  a via or pad, dots of the trace width on the conductor, a track drawn as two overlapping collinear pieces, split,
  reversed or shuffled segments, aligned rectangular pads, terminal pads on the outer via ring) pass.

## What is checked

| Property | Check |
|---|---|
| Stray copper | Tracks on copper layers other than the coil's layer pair, pads other than 1 and 2, and copper the checker does not interpret (copper rectangles, circles, polygons, curves, text, filled zones, custom pads) are errors. |
| Track width | Every emitted track (and dot) must have the intended trace width (within 1 % or 1 µm). `min_width`/`max_width` are reported. |
| Vias | Every via must be plated, have copper on both layers of the pair, a drill smaller than its diameter, and the intended diameter and drill (within 1 % or 1 µm; the base implementation clips the via diameter to the trace width, and `intent_from_model` reads the clipped value). Failures are reported as `via`. |
| Pad size | Pads 1 and 2 must be at least the intended pad size (`Intent.pad_size`, by default the trace width) in every direction (`pad size`). Larger pads are allowed; their clearance and conformance are checked. |
| Dots | A zero-length track is a round dot of copper of its stroke width. Dots are checked as copper bodies: attached to the track (or via, or pad) whose copper contains their center, otherwise counted as orphaned copper; their clearance to other turns, their width and their overshoot are checked like any other copper. |
| Connectivity | Copper must form a simple path from pad 1 to pad 2 that uses every segment exactly once. Track ends are joined when they coincide (1 nm), when a dangling end lies inside a via's or pad's copper, or when two collinear pieces of track on one layer overlap and each one's dangling end lies on the other (1 µm). Vias join the layers. Reports open ends, branches, orphaned segments, duplicate segments (an exact copy, or a loose piece lying on another track), stray vias (fewer than two track connections), and shorts (pad 1 and pad 2 joined by via or pad copper, or a path that bypasses segments). Dangling stubs at a pad that are no longer than the pad plus three times the via offset, and track lying entirely within a via or pad, are counted as `stubs` and do not fail a case. A jumper that connects distant parts of the conductor always shows up as a branch (a node with three or more track connections), a stray via or a pad 1 to pad 2 short. |
| Winding | Total angle swept by the path around a point in the coil's hole must equal the number of turns (sign by direction). Catches lost, doubled or reversed turns. |
| Backtracking | Consecutive segments on one layer that reverse direction (> 170°), e.g. a hairpin inside the track's own lane. |
| Crossings | Same-layer centerlines of segments that are not neighbors along the conductor must not intersect (strict crossing; touching shows up as zero clearance). |
| Clearance | Edge-to-edge distance between copper of *different turns* must be at least the clearance. Copper belongs to different turns when it is at least half a turn apart in cumulative winding angle around the coil's center (measured at the closest points); only without a center (or for copper off the path) does distance along the conductor (more than max(4·(w+c), ¼ inner perimeter)) decide. Track-track (and dots), via-track/via-via and pad-track/pad-via/pad-pad violations are reported separately (worst deficit in mm and relative to the clearance). Deficits between parts of the same turn (the conductor folding onto itself at a tight tip, or a hairpin inside its own lane, which is a backtrack) are counted as `self_overlaps` and do not fail a case, unless the copper touches itself at least 0.18 turns apart (`self short`, part of a turn is shorted). See *Same turn or different turn* below. |
| Spacing uniformity | Sampled edge-to-edge distance to the neighboring turn, relative to the clearance (min, 5th and 95th percentile), and `pitch_ratio` = (narrowest emitted track width + c) / nominal pitch, i.e. how much of the available pitch the layout turns into copper. |
| Outline conformance | *Core coverage*: every spiral layer, inflated by half a pitch, must cover the band from ½ pitch to annular width − ½ pitch inside the outline (uncovered area means wasted space or a missing turn). *Overshoot*: no copper (tracks, dots, vias, pads) outside the envelope from −w/2 to annular width + w/2 (0.05 mm tolerance, independent of the trace width). Near a via or a terminal pad, copper may extend as far as a via of the intended diameter at the intended via offset reaches (offset + intended via radius, with three times the offset with staggered vias), so terminal pads may sit on the outer via ring; pads whose corners stick out further (e.g. a rotated square pad at a curved arm start when the via is no larger than the trace) fail. *Via offset*: every via center must lie within the intended via offset (three times that with staggered vias) of the band between outline and inner outline. *Undershoot*: every point of the outline within one pitch of copper. |

A case passes when none of the checks fails: connectivity intact, no stray copper, vias intact and of the intended size,
terminal pads at least as large as intended, track widths as intended, no
crossings, no backtracks, no self shorts, track, pad and via clearance deficits at most 5 % of the clearance, via centers within
0.05 mm of the intended via offset, the winding within 0.05 turns, and conformance holds (uncovered < 5 %,
undershoot < 1.25 pitches, overshoot < 0.05 mm). `run_corpus.py` stores the names of the failed checks per case in
`failures` and prints a count per kind. Requests that the generator rejects with a `ValueError` are reported as
`rejected`; a clear rejection of an infeasible request is acceptable, a crash (`error`) is not. (`test_corpus_case` in
`test_layout.py` still asserts its own, shorter list of conditions.)

### Same turn or different turn

Two pieces of copper of the same conductor that come too close are only a clearance violation when they belong to
different turns. The checker tells them apart by the difference in cumulative winding angle around the coil's center
between the two closest points: adjacent turns differ by about one turn, and copper at least half a turn apart counts as
different turns. Pieces closer than π/2·(w+c) along the conductor are never compared (corners and arcs of wide tracks).
The path length fallback (copper more than max(4·(w+c), ¼ inner perimeter) apart along the conductor counts as different
turns) only applies when there is no center: on the corpus it never decided a case when a center was available, but it
classified a long hairpin inside its own lane as a different turn.

Below half a turn, a clearance deficit is a *self overlap*: the conductor folding onto itself at a tight tip of the
outline (a star point, an ellipse's narrow end) or at a corner of a wide trace. That does not fail a case, except when
the copper actually touches itself (deficit ≥ c) at least `SELF_SHORT_SEP` = 0.18 turns apart: then the copper shorts part
of a turn (`self short`). Measured over the full corpus with all four layout implementations, copper contacts at tip folds
are less than 0.14 turns apart, while a trace several mm wide that wraps around a hole smaller than itself (a0.90 n3k1
cases: sector 90/180, square, D shape, random convex, star6, triangle) touches itself 0.22 to 0.5 turns further on; 0.18
lies in the middle of that gap. Before, with half a turn as the only threshold, the same wrap passed in one case
(`sector180_a0.90_n3k1`, contacts of 9-15 c at 0.26-0.46 turns) and failed in another (`octagon_a0.90_n3k1`, 2.4 c at
about 0.5 turns). Remaining edges: the base implementation's `sector90_a0.90_n3k1` has a contact of 11 c at 0.14 turns
(at the sector's apex), which passes as a fold; contacts of wraps closer than π/2·(w+c) along the conductor are not
checked.

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

`--impl MODULE` loads `kicoil.MODULE` instead of `kicoil.geometry`. Workers are started with the `forkserver` method
(wasmtime runs threads, and forking a process that has run the wasm module can deadlock), `-j 1` runs in-process. `--filter SUBSTR` selects cases by name. With
`RENDER_ALL=1` every case is rendered, not only failures. The SVGs show both copper layers, the outline, violations
(orange), crossings and the location of the minimum turn spacing (magenta) and a heat map of the spacing on the first
layer (green: spacing matches w+c, blue: looser, red: tighter).
