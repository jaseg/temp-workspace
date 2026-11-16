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
- `test_flat_corners.py`: the flat corner layout (constant depth around corners, wider spacing, vias at flat corners,
  no ramps on the edges of cut protrusions, argument checks, debug output, a shape shared between coils) and the arm
  phase.
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
| Backtracking | Consecutive segments on one layer that reverse direction (> 170°), e.g. a hairpin inside the track's own lane. A reversal whose reversing piece lies completely within one via's or pad's copper does not count. |
| Crossings | Same-layer centerlines of segments that are not neighbors along the conductor must not intersect (strict crossing; touching shows up as zero clearance). |
| Clearance | Edge-to-edge distance between copper of *different turns* must be at least the clearance. Copper belongs to different turns when it is at least half a turn apart in cumulative winding angle around the coil's center (measured at the closest points); only without a center (or for copper off the path) does distance along the conductor (more than max(4·(w+c), ¼ inner perimeter)) decide. Track-track (and dots), via-track/via-via and pad-track/pad-via/pad-pad violations are reported separately (worst deficit in mm and relative to the clearance). Deficits between parts of the same turn (the conductor folding onto itself at a tight tip, or a hairpin inside its own lane, which is a backtrack) are counted as `self_overlaps` and do not fail a case, unless the copper touches itself at least 0.18 turns apart (`self short`, part of a turn is shorted) or, less than 0.18 turns apart, at least 6·(w+c) apart along the conductor (`self merge`, a stretch of the turn is shorted). Copper that leaves its own via and comes back to touch it is a self short as well (`own_via_shorts`), however close to the via along the conductor; copper that never left the via is the conductor's arrival. See *Same turn or different turn* below. |
| Spacing uniformity | Sampled edge-to-edge distance to the neighboring turn, relative to the clearance (min, 5th and 95th percentile), and `pitch_ratio` = (narrowest emitted track width + c) / nominal pitch, i.e. how much of the available pitch the layout turns into copper. |
| Outline conformance | *Core coverage*: every spiral layer, inflated by half a pitch, must cover the band from ½ pitch to annular width − ½ pitch inside the outline (uncovered area means wasted space or a missing turn). Depths are Euclidean: the inner contour is the true inward offset of the outline, round around reflex corners (D44); the uncovered fraction is relative to the band the envelope admits (below), whose area is the mitered band's for outlines without reflex corners sharper than 120°. *Overshoot*: no copper (tracks, dots, vias, pads) outside the envelope from −w/2 to annular width + w/2 (0.05 mm tolerance, independent of the trace width); around reflex corners the envelope also takes in the mitered offset, cut off at twice the depth (`ENVELOPE_MITER_LIMIT`). Near a via or a terminal pad, copper may extend as far as a via of the intended diameter at the intended via offset reaches (offset + intended via radius, with three times the offset with staggered vias), so terminal pads may sit on the outer via ring; pads whose corners stick out further (e.g. a rotated square pad at a curved arm start when the via is no larger than the trace) fail. *Via offset*: every via center must lie within the intended via offset (three times that with staggered vias) of the band between outline and inner outline. *Undershoot*: every point of the outline within one pitch of copper. |

A case passes when none of the checks fails: connectivity intact, no stray copper, vias intact and of the intended size,
terminal pads at least as large as intended, track widths as intended, no
crossings, no backtracks, no self shorts or self merges, track, pad and via clearance deficits at most 5 % of the clearance, via centers within
0.05 mm of the intended via offset, the winding within 0.05 turns, and conformance holds (uncovered < 5 %,
undershoot < 1.25 pitches, overshoot < 0.05 mm). `run_corpus.py` stores the names of the failed checks per case in
`failures` and prints a count per kind. Requests that the generator rejects with a `ValueError` are reported as
`rejected`; a clear rejection of an infeasible request is acceptable, a crash (`error`) is not. `test_corpus_case` in
`test_layout.py` asserts the same checks except outline coverage. Failure kinds a case shows on the full corpus
that are limitations of the layout, not defects, are listed in `data/known_failures.json` (regenerate it with
`run_corpus.py --known-failures` after reviewing a change) and xfail there: the a0.90 n3k1 cases of the main corpus,
where three turns in 90 % of the inscribed radius make the trace (and the via) 4-10 mm wide and the innermost turn
wraps around a hole smaller than the trace (self short), the self merges of hairpins into arms narrower than the trace
(`narrow_slot`, the C, U and comb at 90 %, slender ellipses), and a few via clearance deficits where a via as wide as
the trace does not fit the hole.

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
of a turn (`self short`). Measured over the full corpus, copper contacts at tip folds
are less than 0.14 turns apart, while a trace several mm wide that wraps around a hole smaller than itself (a0.90 n3k1
cases: sector 90/180, square, D shape, random convex, star6, triangle) touches itself 0.22 to 0.5 turns further on; 0.18
lies in the middle of that gap. Before, with half a turn as the only threshold, the same wrap passed in one case
(`sector180_a0.90_n3k1`, contacts of 9-15 c at 0.26-0.46 turns) and failed in another (`octagon_a0.90_n3k1`, 2.4 c at
about 0.5 turns). Self shorts are also checked between a via or pad and track of its own turn. On the full corpus they fail
`sector180_a0.90_n3k1`, and with other layouts tried also `rect40x20_a0.90_n3k1` and
`roundrect_a0.90_n3k1`, where the inner via (as wide as the 5.9-7.3 mm trace) sits in a hole 2-2.5 mm tall and touches the
track 0.38-0.43 turns before it. Closer than π/2·(w+c) + via radius along the conductor, copper touching its own via is
a self short only when it comes back: followed along the conductor away from the via, the center line first gets farther
from the via than r + w/2 + c (the copper clears the via) and later its copper touches the via (deficit
min(r + w/2 + c − d, X + c, M − d) ≥ c, with d the distance to the via center, M its largest value and X the largest
d − (r + w/2 + c) between the via and the point). Copper that never cleared the via is the conductor's arrival, however
tightly it curves: the wide innermost turns of `rstar0_a0.90_n3k1` or `circle30x6_n2k1` overlap their via for 7-11 mm
of path that way, as one piece of copper, and pass. The rule does not use the winding center, so it does not depend on
the outline's orientation (e.g. the
triangle at 96 %, 4 turns: the innermost turn runs out to a corner and back past its via). Track-track contacts of
wraps closer than π/2·(w+c) along the conductor are not checked.

Since same-turn contacts are measured along the whole contact (below), a corner of the innermost turn close to the
center whose copper merges over 1.6-1.9·(w+c) at 0.18-0.46 turns counts as a self short, too: 15 a0.90 n3k1 cases of
kicoil's full corpus (all of which fail conformance anyway).

Copper of one turn that touches itself less than 0.18 turns further on is a *self touch* (`self_touches`,
`max_self_touch_bypass`: the conductor length between the pieces): the two sides of a hairpin, where a turn runs into a
tip or an arm of the outline and back, merging. At a corner of angle α the copper merges over w/sin(α/2) of conductor,
which is local for ordinary corners. When the pieces are at least `SELF_MERGE_BYPASS` = 6·(w+c) apart along the
conductor (the merge of a tip sharper than about 19°, or of a hairpin into a narrow arm), the merged copper shorts a
stretch of the turn of six pitches or more: a `self merge`, which fails. The corpus has no gap at that length (tips reach
6.3·(w+c), hairpins into arms start at 6.1), so the threshold is the geometric one; see docs/DEFECTS.md, D37.

Same-turn contacts are measured over the whole stretch where two plain tracks are close, not only at their closest
points: both center lines are sampled at a quarter of the trace width, each sample paired with its closest point on the
other track, the ends of the stretch of it that its copper touches, and the points where the pair starts to count (π/2·(w+c)
along the conductor, 0.18 turns in winding angle); the end of the longest contact is located by bisection; vias and pads
against a track likewise. The
closest points of two long legs of a V lie at its tip, so before, the bypassed length (and whether a corner close to the
center counted as a self short) depended on how the conductor was cut into segments (D39). The coil's center is
GEOS's interior point of the inset outline, except that its rounding-dependent choices (a vertex in the middle of the
extent, two equally wide stretches of a symmetric hole) are made deterministically (D40).

## Corpus

Shapes: square, rectangles (2:1, 5:1), trapezoid, regular 3/5/6/8/24-gons, ellipses, rounded rectangle, rectangles with
tiny and small chamfers, rectangles with nearly collinear extra vertices (with and without jitter), stars, circular
sectors (45°, 90°, 180°), L, U and D shapes, random convex and random star-shaped polygons, and circles.

Extra families in their own modules (`tests/corpus_<family>.py`, selected alone with `--kind <family>`): `round`
(`corpus_round.py`: polygonal circles with 16 to 1024 vertices and the analytic circle of the same size, a 2500 vertex
blob, a 1000 vertex outline with coordinates rounded to 1 µm, ellipses from 2:1 to 20:1, superellipses, smooth blobs,
stadium, rounded rectangle, egg, teardrop, bean, noisy circles, nearly collinear runs, short edges, D shape, circle with a
sharp tip). A case may declare failure kinds it is known to show in the fixed layout, with the reason
(`known_failures`, e.g. the backtrack of turns reversing at the sharp tips of the deeper offsets of the 20:1 ellipse); `test_corpus_case` xfails those
instead of asserting them.

Concave family (`corpus_concave.py`, `--kind concave`, 143 cases): a plush-shark silhouette (91 vertices, as a polygon
and as `data/shark.svg` loaded through `SVGShape`: a path that repeats its start point and is clockwise in its own
numbers, i.e. has a negative shoelace area, so that `SVGShape` has to reverse it; on screen, y down, it appears
counter-clockwise; `test_concave.py` also imports the other orientation and the path without the repeated point,
`test_svg_import.py` pins that the fixture takes the reorientation branch),
bean, heart, crescent, C, rounded L and U, cross, comb, star with rounded tips and a dumbbell. For non-convex outlines
the straight skeleton's first split event limits the annular width (`Skeletonator.max_depth`), often far below the
inscribed radius, so the annular widths are 30/60/90 % of each shape's split depth. The heart's cusp gets a round
joint (D43), which lifts its split depth from 1.6 to 10.1 mm: `heart` keeps the annular widths
of the mitered skeleton (0.48–1.44 mm, the cases of that defect), `heartdeep` uses the new depth. Turns/twists n5k1, n8k3, n13k4,
single layer, clockwise. Cases with a documented limitation of the layout carry `known_issue`, which names the
failure kinds it explains; `test_layout.py` xfails such a case only when all of its failure kinds are among them.

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

`--impl MODULE` loads `kicoil.MODULE` instead of `kicoil.geometry`. Workers are started with the `forkserver` method
(wasmtime runs threads, and forking a process that has run the wasm module can deadlock), `-j 1` runs in-process. `--filter SUBSTR` selects cases by name. With
`RENDER_ALL=1` every case is rendered, not only failures. The SVGs show both copper layers, the outline, violations
(orange), crossings and the location of the minimum turn spacing (magenta) and a heat map of the spacing on the first
layer (green: spacing matches w+c, blue: looser, red: tighter).
