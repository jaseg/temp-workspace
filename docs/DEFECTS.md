# Defects found in the original code and how they were fixed

Baseline: upstream commit `7fe1f45` ("Update kicad addon metadata description", v0.11.1). Line numbers refer to that
commit. Corpus numbers come from `tests/run_corpus.py --kind full` (588 cases), evaluated with the checker in
`tests/geomcheck.py`. See `tests/README.md` for what the checks mean.

| | original | fixed |
|---|---|---|
| connectivity broken | 258 | 0 |
| crossings between turns | 63 | 0 |
| wrong number of turns (winding) | 217 | 0 |
| track clearance deficit > 5 % | 454 | 0 |
| via clearance deficit > 5 % | 408 | 0 |
| crashes / rejected requests | 1 / 85 | 0 / 17 (all infeasible) |

The second review added 48 cases with narrow features of the outline (`narrow_*`: a T, a keyhole, a finger and a
slot), the third review 48 more (a finger narrowing in two steps, an L-shaped finger, a finger with a side branch and a
tapered finger; 698 cases in all). On the first 48:

| | original | first fixes | now |
|---|---|---|---|
| connectivity broken | 17 | 2 | 0 |
| crossings between turns | 12 | 1 | 0 |
| track clearance deficit > 5 % | 45 | 10 | 1 (one turn folding onto itself around the slot, warned; D28) |
| via clearance deficit > 5 % | 33 | 0 | 0 |

On the 48 cases of the third review (`narrow_stepped/lfinger/branch/taper_*`; the original code rejects 24 of them):

| | original (24 laid out) | second fixes | now |
|---|---|---|---|
| connectivity broken | 5 | 10 | 0 |
| crossings between turns | 2 | 0 | 0 |
| track clearance deficit > 5 % | 23 | 0 | 0 |
| via clearance deficit > 5 % | 14 | 0 | 0 |

Entries from the second review:

| | defect | also in the original? |
|---|---|---|
| D24 | `KeyError` when a vertex coordinate lies near a 6th-decimal rounding boundary | yes |
| D25 | keepout outline self-intersects, huge miter spikes at sharp tips | yes |
| D26 | clockwise polygons crash; orientation test fooled by a repeated start point | yes |
| D27 | circles rendered without arcs lose clearance to the chords | yes |
| D28 | turns fold onto themselves in narrow protrusions and notches | yes |
| D29 | trace width + clearance branch: 2-decimal rounding, wrong advice, no hint | yes (rounding, advice); the missing measured-spacing hint matters since D7 |
| D1, D4, D7, D8, D10, D22 | `spiral()` argument order / NaN; merge tolerance from the distance to the origin; slow spacing measurement; silently tightened render settings; via offset through the center of circles; kicad-pcb export still failing in gerbonara | no, first version of the fixes |
| D7, D8, D22, D28 (third review) | spacing measurement memory quadratic on dense outlines; render tolerance clearance/40 lost up to 5 % (two-sided), division by zero at clearance 0; kicad-pcb straight tracks on layer "False"; protrusion cut only once per track and oblique for L shapes, fold warning missed tapered fingers | no, second version of the fixes (D29's wording also corrected) |

Every entry was checked by an independent reviewer against the original code (reproduction where practical) and
corrected where it overstated or misdescribed something. Where a corpus case is given as the symptom, it fails with the
original code and passes the corresponding check with the fixed code. Entries marked *latent* have no visible symptom
in the corpus. Three bugs in the first version of the fixes were found the same way and are described with the fix they
belong to (D2, D3, D10). A second review found more problems in the fixes (D1, D4, D7, D8, D10, D22, described with
those entries) and six more defects of the original code (D24–D29); a third review found problems in the second
version (D7, D8, D22, D28, also described with those entries). The remaining 17 rejections are annular widths beyond the straight-skeleton collapse depth
(stars, L/U shapes, the neck) and one circle whose pitch is smaller than the requested clearance.

---

## Spiral geometry (`skeletonator.py`)

### D1. Vertices on a turn boundary are emitted twice, so the spiral folds back on itself

**Defect.** `do_spiral` emits each spiral turn separately. A turn keeps an edge unless it lies wholly outside `[t_start, t_end]`, and the bounds are checked with `isclose` (`tp2 < t_start`, l. 289, and `tp1 > t_end`, l. 291). For each kept edge it emits the edge's *end* vertex. When a vertex angle coincides with a turn boundary, the edge that starts exactly at `t_end` is still accepted, and its end vertex, which belongs to the next turn, is emitted. This happens on every turn for regular polygons, and approximately for rectangles. If the boundary is not a whole number (e.g. 6.5, which is hexagon vertex 3), the next turn also keeps the edge ending at `t_start`. It emits the boundary vertex and then that vertex again, so the track runs A→B→A→B: three copies of one segment, nearly coincident for rectangles, where the next turn recomputes the vertex angles at a different radius (D2). At a whole-number boundary the per-turn angle list starts at `floor(t_start)`, so the result is one vertex emitted twice in a row, a zero-length segment.

**Symptom.** Branches in the conductor graph, and a winding error of whole turns because the checker counts every copy of the folded segment. Example: `hexagon_a0.30_n13k1` has 6 fold-backs in its 13→6.5 arm, giving 12 branches and a winding error of +2.0 turns (6 × 2 extra passes × 1/6 turn). For regular polygons the vertex angles do not depend on size, so a size tweak does not help (all `sweep_hexagon_*` cases keep their branches). Whether a boundary lands on a vertex depends on the turns and twists.

**Fix.** `do_spiral` is rewritten on top of a new `Skeletonator.spiral(t1, t2, d1, d2)`. It emits the start point, then every vertex instance with `t1 <= angle < t2` exactly once in angle order (`iter_vertex_angles`), then the end point. Consecutive identical points are dropped. In the first version of this fix, `spiral(t1, t2)` with
t2 < t1 silently returned a straight two-point segment and `iter_vertex_angles` never terminated for a NaN angle (both
*latent*, every caller swaps the arguments first; found in the second review). `spiral` now handles t2 < t1 by
computing the arm the other way round and reversing it, and rejects non-finite angles and depths with a `ValueError`.

### D2. Vertex angles are recomputed for every turn and every arm

**Defect.** The angle coordinate of a vertex (which sets the spiral's depth there) comes from the outline's edge
lengths at a reference radius `r_ref`. `do_spiral` recomputes it for each turn, at that turn's inner radius
(l. 268–269). `project_point` does the same for the via and pad positions at whatever `r_ref` it is given (l. 224;
`r_ref` defaults to `r`). Edges grow or shrink as the outline is offset, so the same vertex gets a different angle on
each turn and on each arm. Neighboring turns are then not one pitch apart at a vertex but `pitch · (1 + Δangle)`, and
arms of twisted coils drift into each other.

**Symptom.** Large clearance deficits and crossings on shapes whose edge-length proportions change with depth
(random polygons and random stars, sectors, less so chamfered rectangles). Shapes whose edges all keep equal length
(regular polygons, the symmetric stars) are not affected. With only this defect neutralized in the original code,
`rstar0_a0.60_n7k3` goes from a deficit of 15.4× to 1.0× the clearance and `rconvex0_a0.60_n7k3` loses its crossing.
The remaining violations come from other defects.

**Fix.** The angle of every vertex is fixed once per shape (`Skeletonator.set_angle_reference`, called with the
annular width). Each edge gets an angle span proportional to its *shortest* length over the depth range the spiral
uses. This bounds the slope of the spiral relative to every edge at every depth. Edges that collapse before the inner
turn get a span of zero, so several vertices can share one angle. A spiral arm traverses such a group at constant
depth. `_locate` resolves the tie to the first vertex of the group for arm ends, vias and pads alike. Resolving it to
the last vertex instead leaves a branch at the collapsed tip of `ellipse3to1_a0.60_n5k1`. `snap_angle` also snaps
computed arm angles onto vertex angles to remove floating point noise; no corpus case was found that fails without it.
Vertex angles are quantized to multiples of 2⁻⁴⁰ revolutions so that `revolution + angle` is exact. Without that, a
group at angle 0.49999999999999994 rounded to x.5 and the tie went to the wrong end of the group: an arm end cut a
25 mm chord across the tip of `ellipse3to2_a0.90_n9k4`. That was a bug in the first version of this fix, found in
review. `r_ref` is still accepted by the API but ignored.

### D3. The usable depth is the depth of the *last* split event, not the first

**Defect.** In `Skeletonator.__init__` (l. 178–180), the depth limit is updated with
`self.min_radius = min(n1.time, self.radius)` for every "divergent" node. That compares against the full radius, not
against the running minimum, so the result is the time of whichever divergent node comes last in CGAL's output. It can
only overestimate the limit.

**Symptom.** Annular widths between the first and the last split depth pass the width check. Projection then fails
in `project_arc` (l. 208) with an unrelated "out of bounds" error. No corpus case shows this on its own (the only
outline affected is roundrect, whose divergent nodes are all D4 artifacts: 5.35 instead of 4.96). Reproduced with a
60x20 rectangle with two V notches (split depths 0.48 and 1.70): the limit is 1.70, and width 0.8 fails with
"r=8.580 is out of bounds [0, 7.6840]".

**Fix.** The limit is the minimum time over all nodes marked divergent (`max_depth`, also exposed as `min_radius` for
compatibility). In the V-notch repro the limit is now 0.48: 0.4 passes and 0.8 is rejected with a clear message.
Splits are detected with the D4 rule, applied to *groups* of nodes joined by constant-time edges: a group with more
than one way up is a split. The first version of this fix tested single nodes and missed a neck pinching off between
two reflex corners (CGAL emits two equal-time nodes joined by a constant-time edge, each with one way up), leaving the
limit at the full radius (7.0 instead of 1.0 for the verifier's notched rectangle). Corpus shape `neck` covers this.

### D4. Coincident skeleton nodes are taken for split events, and arc direction relies on CGAL's output order

**Defect.** Vertex tracks follow `arc_map[n1] = n2`. That map is built in `Skeletonator.__init__` (l. 177–181) in the order the C++ wrapper writes each edge. The wrapper writes `he->vertex()` and then `he->opposite()->vertex()` of the halfedge with the larger id. Nothing guarantees that this points inward in time. In the corpus it always does (0 outward edges in 61 distinct outlines), so this part is latent. Randomly reversing edges breaks the original. Any node that is the source of two edges is treated as a split ("divergent"). At degenerate events CGAL emits several coincident vertices joined by zero-length edges. When their coordinates are bit-identical, as at the rounded corners of `roundrect`, `compute_skeleton` merges them into one node (it keys on exact `(x, y, t)`). Their zero-length edges then become self-loops, so the node gets several `arc_map` entries and looks divergent, even in a convex polygon. Stars and sectors produce the same thing with distinct nodes. Coincident nodes at the center of regular polygons are leaves in the original and do no harm there.

**Symptom.** Convex rounded rectangles are rejected far below their real depth. 12 corpus cases are affected, all `roundrect*`. Example: `roundrect_a0.90_n9k4` gives "Annular width (11.25) is too large. Must be less than 5.35", although the shape is convex and 12.5 deep. The shallowest false split is at 4.96; 5.35 is what D3 makes of it.

**Fix.** Coincident nodes are merged: same position and time within 1e-6 × the outline's coordinate scale. Self-loops are dropped. The skeleton is used as an undirected graph, and a track always steps to the neighbor with strictly greater time, so CGAL's edge order no longer matters. A node, or a group of nodes joined by constant-time edges, with more than one way up is a real split or vertex event (D3); a track that reaches a group with one way up follows it to the exit. A track ends at such a node, or where no neighbor is higher (the outline has collapsed). Depths past the end of a track are clamped to its last node (`track_position`). With this, `roundrect_a0.90_n9k4` gets depth limit 12.5 and is generated. It still fails the conformance check (uncovered 0.22), which is not caused by this defect.

The first version of this fix took the merge tolerance from the largest absolute coordinate (1e-6 × max |x|, |y|), so
it depended on how far the polygon sits from the origin, not on its size (found in the second review). Moved to
(1e5, 1e5), `chamfer_tiny` lost its 0.05 mm chamfer nodes; a 10 mm square at 1e7 had all nodes merged into one, every
track had a single node, and `max_depth` still came out as 5. The tolerances are now 3e-7 × the bounding box diagonal
(merge) and 1e-9 × the diagonal (constant-time edges), each plus 1e-10 × the largest |coordinate|, which covers the 12
significant digits skeleton.wasm prints. A skeleton in which any vertex track degenerates raises a `ValueError`.

### D5. Debug file written on every call

**Defect.** `compute_skeleton` (`skeletonator.py` l. 135) writes its input polygon to a hard-coded `/tmp/debug.txt`. It runs every time an `OffsetShape` is built, which covers every shape except `CircleShape`. The write raises an error when the file can't be created: on Windows when `\tmp` does not exist on the current drive (`FileNotFoundError`), and on Unix when `/tmp/debug.txt` already belongs to another user (`PermissionError`). Runs that happen at the same time overwrite each other's file.

**Fix.** Removed.

### D6. `do_spiral` default end radius is a depth (latent)

**Defect.** When `r2` is omitted, `do_spiral` uses `self.min_radius` (l. 249), which is a depth limit, not a radius.
The out-of-bounds message in `project_arc` (l. 208) mixes the two up the same way. No caller relies on the default, so
there is no visible symptom.

**Fix.** The default is `self.radius - self.max_depth`, the radius at the depth limit; the message gives the valid
radius range.

---

## Trace sizing and vias (`geometry.py`, `PlanarInductor`)

### D7. Trace width is sized from a circle formula that does not hold for polygons

**Defect.** The distance between neighboring turns is estimated as `spiral_pitch · cos(alpha)` (l. 402–407), with the
spiral's inclination `alpha` computed as if the shape were a circle. For polygon shapes, `inner_radius` /
`outer_radius` are skeleton depths, not geometric radii, so `alpha` is meaningless. Even for circles, averaging alpha
between the two innermost turns slightly underestimates the inclination of the innermost one (≈ 0.012 mm in
`circle30x6_n5k3`). Above all, on polygons two neighboring turns come closest at convex corners. The turn leaving a
corner runs at a slope `s` relative to the edge, so the next turn's corner point is only about `p · (1 − s · cot(θ/2))`
away. That depends on the corner angle, the number of twists and the depth, and the formula ignores it. The trace width
`projected_pitch − clearance` therefore regularly leaves less than the requested clearance.

**Symptom.** `square40_a0.30_n8k3` (w = 1.348 mm, estimated pitch 1.498 mm): all 50 violations sit at corners, where a
turn's corner point comes within 1.44–1.46 mm of the next outer turn, 24–37 % of the clearance short. D7 is one of
several causes behind the 454 of 502 checked cases with a clearance deficit > 5 % (many of them also have D1–D4
crossings or broken connectivity).

**Fix.** `PlanarInductor` computes the center lines of all arms first (`spiral_center_lines`) and measures the actual
smallest distance between different turns on each layer (`measure_turn_spacing` → `min_turn_spacing`, grid-accelerated
segment distances, capped at the nominal pitch). Pieces of the same arm count as different turns only when they are at
least half a revolution apart, judged on sub-segments of ≤ 0.05 revolutions. Trace width (or clearance, if the width is
given) is derived from that measurement. As a result traces are narrower where the geometry forces it (median
(w+c)/pitch 0.93 instead of 0.99), and `square40_a0.30_n8k3` now has no violations. Across the corpus no case is
short by more than 5 % of the clearance; 12 circle cases keep a residual of at most 4.3 % (arc approximation, D8), one
polygon case 1.2 % at a via. A trace width ≤ 0 is now a clear `ValueError` (see D11). Where the annular width reaches
into a part of the outline that collapses before the innermost turn (e.g. the tip of a 3:1 ellipse at 53–74 % depth
with 4 twists), turns can meet and the measured spacing is near 0; such requests are now rejected with a message that
names the location and the cause, instead of being rendered with crossings and shorts.

The first version of this measurement was pure Python and slow, and `PlanarInductor` always runs it (the GUI on every
parameter change, on the Tk main thread). Measured on the review machine: the GUI's default circle (50/25 mm, n=7,
k=4) took 0.65 s, a 100 mm circle (n=41, k=5) 5.1 s, 1000-vertex outlines 1.5–14 s; the original code took about 0.01 s.
`min_turn_spacing` and `via_track_clearance` are now vectorized with numpy: pairs of pieces come from a uniform grid
(each piece entered into the cells its box, grown by half the search radius, touches; a pair is evaluated only in the
cell holding the lower left corner of the boxes' intersection), and bounding-box distances prune pairs before the exact
segment distance. The search radius is the nominal pitch instead of 1.5 pitches, since the result is capped at the
pitch anyway. The sampling is unchanged, so the result is the same: at most 2e-15 mm difference from the pure Python
version on a sample of 80 corpus cases, a brute-force check in the tests, and identical trace widths and pitch ratios on all 602
previous corpus cases. Same cases now: 0.04 s, 0.43 s, 0.24–0.86 s (found in the second review).
That version still built all pairs of pieces of a grid cell at once. On a finely subdivided outline with few turns (an
SVG import) a cell holds thousands of pieces of one turn: a one-turn spiral of 16 000 points with a 20 mm pitch took
20 s and 2.4 GB, 32 000 points 84 s and 9.2 GB, and an 8000-vertex circle outline (n=2) 8 s and 0.8 GB in
`PlanarInductor` (found in the third review). The pieces are now grouped into chunks of up to 64 consecutive pieces of
one arm (about a quarter pitch long); chunk pairs come from the grid, chunk pairs whose pieces all belong to one turn
are skipped as a whole, the others are expanded in order of increasing box distance in batches of at most 10^6 piece
pairs (the grid also splits crowded cells), and pairs that cannot beat the current minimum are skipped. Same three
cases now: 0.5 s and 0.2 GB, 0.9 s and 0.3 GB, 0.4 s; the results and all corpus trace widths are unchanged.

### D8. Arc approximation eats into the clearance

**Defect.** For circles, `arc_approximate` replaces the spiral with circular arcs. Its default tolerance is 0.02 mm, which is 13 % of the default 0.15 mm clearance, and it is checked only at the input points (64 per turn), not between them. The trace width does not allow for this error. Nearly all of the loss comes from the tolerance itself: on the symptom case, sampling at 256 points per turn with the 0.02 mm tolerance changes nothing. There are also two latent bugs that the corpus never reaches. First, for fewer than 5 points the function emits an arc and then falls through to the general case (missing `return`, l. 78–79). That gives a duplicate arc, or a `ValueError` when an out-of-tolerance 4-point run is split into a 2-point piece. Second, collinear points divide by zero.

**Symptom.** `circle50x25_n11k5`: 12 % of the clearance missing (0.018 mm). With the original code and only the tolerance capped, this drops to 0.9 %.

**Fix.** The effective tolerance is capped at clearance / 40. Arcs are fitted to at least 256 points per turn. The early return is added (runs of 3–4 points are still emitted unchecked as a single arc). Collinear point runs are split instead of dividing by zero. The case now loses 0.09 % of the clearance.
The first version tightened the user's `--arc-tolerance` / `--circle-segments` (GUI: "Arc Tolerance", "Circle
Segments") silently, so larger values had no visible effect (found in the second review). Both now default to
automatic (`None`); an explicitly given value that has to be tightened is reported with a logged warning, and the CLI
and GUI help state the rule (`PlanarInductor.effective_render_options`). A third review found that both neighboring
turns can deviate by the tolerance towards each other, so clearance/40 still cost up to 4.4 % of the clearance
(circle 200/190 mm, clearance 0.5 mm) and 5.1 % (4/3 mm, 0.05 mm). The tolerance and the polyline chord error are now
clearance/80 (at least 0.5 µm, so that clearance 0 no longer divides by zero), which bounds the loss at clearance/40
(measured: 0.16 % and 0.83 % for those two cases); the arc tolerance note is only given for circles drawn with arcs.

### D9. Via ring overlap check crashes when a via is wider than the inner ring

**Defect.** The check for overlapping vias uses the circle formula `2·asin((d_via + clearance)/2 / r_ring)`
(l. 467, 470). Its argument is greater than 1 as soon as one via plus its clearance is wider than the inner via ring
(`r_ring = inner_radius - via_offset`). This holds for any shape, circles included. It happens when the annulus is deep
and the via diameter has been clipped up to a wide trace (l. 455-457). For polygons the formula is only approximate
anyway, because the vias are not placed on a circle. The outer ring's angle is computed but never checked.

**Symptom.** `ValueError: math domain error` at l. 467 for 57 corpus cases: every 3- and 5-turn case at 90 % depth
(38 convex and 18 reflex polygons, e.g. `square40_a0.90_n3k1`, where the via is clipped to 10.66 mm on a 2 mm inner
ring) plus `circle30x6_n2k1`. The 9- and 16-turn cases at the same depth are not affected.

**Fix.** The via positions are computed with the shape's own projection (`via_positions`). Their smallest center
distance across both rings (`via_ring_spacing`) is compared with via diameter plus clearance. A warning is emitted with
the actual numbers. The original never checked the outer ring, or inner vias against outer vias; that is now covered too. All 57 cases
now generate; 5 of them pass, the others fail on unrelated checks (mostly spacing uniformity in very deep annuli).

### D10. Vias wider than the trace collide with tilted neighboring turns

**Defect.** When the via is wider than the trace, the automatic via offset `(d_via − w)/2` (l. 459–461) lines up the
via's edge with the trace's edge in the radial direction only. Next to a neighboring turn that runs at an angle (many
twists), the sides of the via come closer than the clearance. The original only checked vias against each other
(l. 478–480), never against tracks.

**Symptom.** 408 cases had via clearance violations beyond the 5 % tolerance (472 had at least one). All 408 also break
track clearance (D7). With the D7 fix but no via-offset adjustment, all 8 inner vias of `triangle_a0.60_n21k8` were
still short, by up to 13 %.

**Fix.** `via_track_clearance` measures the distance from every via to the arm center-line segments. Arm segments are first
split into pieces of at most 0.05 revolutions; pieces within half a turn of where that arm enters the via are skipped. With an automatic via offset, the shared
offset (both rings) grows, for at most 10 steps, until the vias clear. It stops early if the gap stops improving, if the
inner vias would go past the collapse depth (`OffsetShape.max_via_offset`), or if vias would overlap each other. With a
user-given offset, or when no offset works, a warning gives the via's position and the gap. The first version of this fix
skipped only whole segments, so a long segment crossing the half-turn boundary was measured against its own via. In
`subdiv_rect_jitter_a0.90_n3k1` that reported a false gap of −5 mm and pushed the offset to its maximum, creating real
violations; found in review and fixed by the splitting. The loop also had no upper bound for circles: `CircleShape` had
no `max_via_offset`, so with vias wider than the hole the inner ring was pushed through the center, where the vias of a
2-twist coil swapped places, the overlap check never fired and the radial stubs crossed the hole (circle 20/1 mm, n=9,
k=2, 2 mm vias: via offset 1.725 mm, ring radius −1.2 mm, 4 crossings; found in the second review). Circles now have
`max_via_offset` = inner radius (divided by 3 for a staggered inner ring, which reaches three offsets inwards), the
automatic offset is clamped to it from the start, and a user-given offset beyond it gives a warning. A negative gap is
reported as "overlaps a neighboring turn by X mm" instead of "is only −X mm away".

### D11. NameError instead of an error message when the clearance exceeds the pitch

**Defect.** The message for "clearance larger than the projected spiral pitch" references undefined names
`clearance` and `projected_spiral_pitch` (l. 434). If the message had worked, the code would have gone on to compute a
negative trace width (l. 435), since the branch only warns. The auto-clearance branch (l. 439–441) has the same
problem: a trace width larger than the pitch only warns and produces a negative clearance.

**Symptom.** `circle20x18_n16k5`: `NameError: name 'clearance' is not defined`.

**Fix.** Correct names, and both "auto width" and "auto clearance" branches raise `ValueError` when the result would be
≤ 0 (comparison `>=` on values rounded to 3 decimals; the auto-clearance branch used 2 decimals and its message said
"Reduce clearance" where it meant the trace width).

### D12. Single-layer mode ignores the twists reset when computing angles

**Defect.** For `layers == 1`, twists are forced to 1 (l. 409–411). This happens only after `sector_angle = 2π / twists` (l. 393), `sweeping_angle = sector_angle * turns_per_layer` (l. 398) and `projected_spiral_pitch` (l. 401–406) have been computed from the requested value. The one arm that is left still sweeps 2π·turns/k.

**Symptom.** A single-layer coil requested with twists k > 1 (reachable via `--single-layer --twists k`, or the GUI's default twists=4) winds only turns/k revolutions. Because the pitch is computed from the full turn count, these revolutions span the whole annulus at k times the nominal pitch. Example: circle 50x25 with n=5, k=3 sweeps 1.67 rev, and geomcheck measures winding 2 instead of 5. No corpus case covers this, because all single-layer cases use twists=1.

**Fix.** The turns/twists validation and the single-layer reset now run before `turns_per_layer`, `sector_angle` and `sweeping_angle` are computed. With n=5, k=3 the coil now winds 5 revolutions, the same as with k=1.

### D13. Track length and resistance computed for one sector instead of one arm

**Defect.** `compute_spiral(a1=0, a2=self.sector_angle)` (l. 496) measures a spiral that covers the full outer-to-inner radial span in a single sector (1/twists of a revolution). l. 498 then multiplies it by twists and layers, as if it were a full arm. A real arm (as drawn in `render_footprint`) spans `sweeping_angle`, i.e. turns / layers / twists revolutions.

**Symptom.** Reported track length, and with it resistance, is too low whenever turns/layers > 1. The error grows with turns/layers, but stays below that factor because the radial part of the length does not scale with angle. Measured reported/rendered length: circle50x25_n5k1 0.40, circle30x6_n11k5 0.26, circle50x25_n16k5 0.14 (turns/layers = 8, error factor 7.1). Cases with turns/layers = 1 (circle50x25_n2k1) are exact.

**Fix.** Measures the spiral from 0 to `sweeping_angle`. The reported length is now within 2% of the rendered track length on the cases checked.

### D14. Dangling stubs at the terminal pads

**Defect.** At `i == 0`, no via is placed at the outer via position (outer radius + via offset). The pads go on the
outer radius itself, at the arm end (l. 617). But the two lines from the arm ends to the unused via position are still
drawn (l. 607–608). With a via offset > 0, they stick out of the coil as dead-end copper.

**Symptom.** 66 cases. In 62 of them the checker reports 2 stubs (e.g. `circle20x18_n5k3`). In 4 cases with a thin
trace, the stub is longer than 2 pad diameters and is reported as 2 open ends instead (e.g. `circle20x18_n8k3`, open
ends at (10.25, 0)).

**Fix.** No connecting lines for `i == 0`. Pad 1 sits on the start of the first layer-0 arm, pad 2 on the end of the
last layer-1 arm (the same point as before, now taken from the actual arm ends). Zero-length connection lines (via
offset 0) are no longer emitted either.

### D15. Twists of 0 accepted

**Defect.** `sector_angle = 2*pi / self.twists` (l. 393) runs before any twists validation. So `twists = 0` crashes there with a bare `ZeroDivisionError` instead of a `ValueError`. The later check `if self.twists < 0` (l. 416) would allow 0 anyway. Its message ("PlanarInductor.turns must be 0 or more") names the wrong parameter and gives the wrong bound.

**Fix.** The turns and twists checks now come first in `__post_init__`, before the division and the single-layer reset. `twists < 1` is rejected with a `ValueError` that names twists.

### D16. `turns = 0` crashes with ZeroDivisionError

**Defect.** `spiral_pitch = (outer_radius - inner_radius) / turns_per_layer` (l. 399) runs before the check
`if self.turns < 1` (l. 413). With `turns = 0` it divides by zero first, so the check never fires.

**Symptom.** `PlanarInductor(CircleShape(20, 10), 0, 1)`: `ZeroDivisionError: float division by zero`.

**Fix.** `turns` and `twists` are checked at the start of `__post_init__`, before anything is derived from them.

### D17. Annular widths ≤ 0, or equal to the collapse depth, accepted

**Defect.** `OffsetShape.__post_init__` only rejects `annular_width > min_radius` (l. 165). It accepts zero and
negative widths, which give a zero or negative pitch, and a width exactly equal to the depth limit, where the inner turn
has zero length.

**Symptom.** `RectangleShape(20, 10, 0)` and `RectangleShape(20, 10, -1)` are accepted and `PlanarInductor` then dies
with D11's `NameError`. `RectangleShape(20, 10, 5.0)` (depth limit 5.0) raises `ZeroDivisionError` in the alpha formula
(l. 404).

**Fix.** `annular_width <= 0` raises "Annular width must be positive"; the upper bound is `annular_width >= max_depth`,
matching the message "Must be less than …".

---

## Shapes, CLI and export

### D18. Shape `slug` / `desc` format strings broken

**Defect.** `CircleShape.slug` and `OffsetShape.slug` lack the `f` prefix (l. 123, 172), so they return the template text unformatted. `OffsetShape.desc` (l. 177) references `self.radius`, which does not exist (only `outer_radius` / `inner_radius` are set).

**Symptom.** Every circle coil generated without an explicit footprint name gets the literal name `planar-coil-circle_{self.outer_diameter:.2f}x{self.inner_diameter:.2f}-n…` from `default_footprint_name`. The `OffsetShape` defaults are never reached by the shipped shapes, because all six subclasses override both properties. A subclass that relies on them gets a literal slug, and `render_footprint` fails with `AttributeError`. Not visible in the corpus (its polygon shim overrides both); reproduced with a minimal script.

**Fix.** Added the `f` prefixes. The `OffsetShape` `slug` / `desc` now use `annular_width` in place of the nonexistent `radius`.

### D19. SVG import computes a wrong bounding box

**Defect.** `SVGShape` computes `min_y = max(x…)` and `max_x = min(y…)` (l. 350–351). The "is (0, 0) inside the bbox"
recenter test therefore fires whenever max(x) > 0 or min(y) < 0. As a result, a polygon that contains the origin but is not
centered on it is still moved to its centroid, and the warning prints the wrong bounds. A polygon lying entirely at x<0, y>0
is never recentered.

**Symptom.** No corpus case uses SVG input. With a minimal script, a square from (-5,-5) to (15,15) is shifted to
-10..10 with a spurious warning, and a square from (-30,10) to (-10,30) is left far from the origin.

**Fix.** Correct min/max of x and y.

### D20. Stray debug print

**Defect.** `RegularPolygonShape.__post_init__` prints its polygon (l. 315).

**Fix.** Removed.

### D21. `kicoil trapezoid` crashes

**Defect.** `cli.py` uses `TrapezoidShape` (l. 283) without importing it.

**Fix.** Imported.

### D22. `--format kicad-pcb` crashes

**Defect.** `kicad.footprint_to_board` references undefined `zones`, `lines` and `pads` (l. 46–48) and ignores arcs.

**Fix.** Uses the footprint's zones, lines, arcs (as `TrackArc`) and through-hole pads. The first version of this fix
still failed inside gerbonara (1.6.0): `Board.empty_board()` cannot serialize even an empty board (`MappingError` on
the empty `legacy_footprints` list), and the SMD terminal pads were dropped, since only through-hole pads become vias.
`footprint_to_board` now sets `legacy_footprints` to `None` (which the serializer skips, as for a parsed board without
legacy footprints) and puts the two terminal pads on the board in a small footprint of their own (`<name>-terminals`).
The second version still wrote every straight track segment (all tracks of polygon shapes, via connections and the
single-layer bridge) with `(layer "False")` and a stray `locked`: gerbonara's `TrackSegment.from_footprint_line` passes
layer and locked positionally in the wrong order. The segments and arcs are now built with keyword arguments.
A test runs `kicoil --format kicad-pcb` for a circle, a rectangle and a single-layer circle, parses the result back
with gerbonara and checks that every segment, arc and via is on the coil's copper layers; the board has not been opened
in KiCad here.

### D23. Keepout zone outline closes on a duplicate point

**Defect.** For polygon shapes, `OffsetShape.offset_exterior` (geometry.py l. 199–200) returns the raw generator of `do_spiral(0, 1, ...)` (one full revolution). That revolution ends on its start point, and D1's turn-boundary double emission repeats that point once more. The keepout polygon therefore ends with two extra copies of its first vertex, which are two zero-length edges (a hexagon gives 8 points instead of 6). The generator also yields `(point, r_ref)` pairs, not points. `render_footprint` (l. 628) unpacks each pair as `x, y`, which works only because gerbonara's `XYCoord` takes the coordinates from a tuple `x` and ignores `y`. `CircleShape` is not affected.

**Fix.** `offset_exterior` unwraps the pairs to plain points and drops the closing point (`[:-1]`). The other copy is no longer emitted since D1's rewrite of `do_spiral`. The outline now has exactly one point per vertex (6 for a hexagon, 4 for a rectangle).

---

## Found in the second review

### D24. Polygon vertices matched to skeleton nodes by rounded coordinates

**Defect.** `Skeletonator.__init__` (`skeletonator.py` l. 182–189) finds the skeleton node of each polygon vertex by
the key `(round(x, 6), round(y, 6))`. The polygon goes into skeleton.wasm with full precision, but the wasm prints its
output with 12 significant digits. When a coordinate lies within about 5·10^(m−12) of an `xxx.xxxxxx5` rounding
boundary (m integer digits), the two sides round differently and the lookup fails. The first version of the fixes kept
the key.

**Symptom.** `KeyError: (22.092783, -20.0)` for the rectangle with x = ±22.092782500010948, y = ±20. 3 of 1000
random-phase 64-gons of radius 40 mm fail, 7 of 300 at radius 300 mm, 4 of 300 at 800 mm; large SVG imports are at
risk.

**Fix.** Each vertex is matched to the *nearest* contour (time 0) skeleton node, searched in a window of 1e-6 × the
bounding box diagonal (plus a float precision floor); a vertex without a node within that window is a `RuntimeError`.
0 of 300 random 64-gons fail at either radius.

### D25. Keepout outline extrapolated from the skeleton

**Defect.** The keepout zone is the outline offset outwards by the keepout margin (CLI default 5 mm). For polygon
shapes it is made by extrapolating every vertex along its first skeleton arc to a negative depth (`project_arc` with
`t < 0`, l. 205; since D1 `track_position`). That is a mitered outward offset only until the first event of the
*exterior* skeleton: short edges between reflex vertices shrink, invert and make the outline cross itself, and the
miter at a sharp convex tip grows without bound.

**Symptom.** At margin 5 mm the keepout polygon is self-intersecting for the `neck` outline and for a 90° sector with a
6 mm inner diameter (also for the neck at 1 mm). On the 5-point star (50/25 mm) the keepout reaches 11.3 mm from the
outline.

**Fix.** `OffsetShape.offset_exterior` with a positive margin computes a real outward offset
(`skeletonator.offset_polygon_outward`): offset edges joined by miters at convex corners, cut off (beveled) at twice the
margin; at reflex corners the mitered inner corner where both edges are long enough for it, else a detour through the
vertex itself. Every point of this raw curve lies inside the offset region, so the boundary of the unbounded face of the
curve's arrangement (all self-intersections and collinear overlaps split, outer face traced with rightmost turns) is the
outer boundary of the offset region; bays that close up are filled. No new dependency (numpy only finds overlapping
segment boxes). The result equals shapely's `buffer(margin, join_style='mitre', mitre_limit=2)` exterior to within 4e-16
of the area on all 30 corpus outlines, a sector, a T, a slot and a C shape at four margins, and on 300 random
star-shaped polygons. Rectangles, regular polygons up to the triangle, and all other corners up to 120° keep their
plain miter. Inward offsets (margin ≤ 0) are unchanged. `track_position` documents that negative depths are only a local
extrapolation (still used for the outer via ring).

### D26. Clockwise polygons

**Defect.** Nothing normalizes the orientation of a polygon outline: skeleton.wasm rejects clockwise input, and
`Skeletonator` passes it on as given. `SVGShape` reverses clockwise paths, but both `polygon_is_clockwise` helpers
(`geometry.py` l. 97, `skeletonator.py` l. 46) look only at the extreme vertex and its two neighbors. SVG paths often
repeat the start point before `Z`; when that point is the extreme vertex, one neighbor is a duplicate, the determinant is
0 and the polygon counts as counter-clockwise.

**Symptom.** A clockwise outline in an `OffsetShape` subclass: skeleton.wasm prints "Polygon must be counter-clockwise"
and `RuntimeError: Error computing straight skeleton.` The SVG path `M -5 -5 L -5 5 L 5 5 L 5 -5 L -5 -5 Z` fails the
same way.

**Fix.** `Skeletonator` normalizes its input (`clean_polygon`): consecutive duplicates (including a closing point equal
to the first point) are dropped, the signed shoelace area decides the orientation, and a clockwise polygon is reversed
with vertex 0 kept as vertex 0; fewer than 3 distinct points, non-finite coordinates or zero area raise a `ValueError`.
`OffsetShape` uses the normalized outline as its `polygon`. Both `polygon_is_clockwise` helpers use the shoelace area.

### D27. Circles rendered without arcs lose clearance

**Defect.** With `approximate_arcs=False` (`--no-approximate-arcs`), circles are drawn as polylines with
`circle_segments` points per turn (default 64, l. 538). The chords cut inside the spiral by up to r·(1 − cos(π/64)),
about 0.03 mm at r = 25 mm, which the trace width does not allow for. D8 fixed only the arc path.

**Symptom.** Circle 50/25 mm, n=11, clearance 0.15 mm with 64 segments: up to 16 % of the clearance missing (worst with
twists > 1, where the arms' vertices do not line up).

**Fix.** Polyline circles get at least as many segments per turn as a chord error of clearance/80 on the outer radius
needs (257 for this case); a smaller explicit value is raised with a warning (see D8). The same case now loses at most
0.5 % of the clearance (0.0007 mm).

### D28. Turns fold onto themselves in narrow protrusions and notches

**Defect.** The spiral follows the offset outline at every depth. Where two parallel sides of a protrusion collapse onto
each other inside the annulus (the stem of a T, a finger, the tab of a keyhole), the offset outline just above the
collapse depth T has a sliver of width 2·(T − depth), and a turn at that depth runs into the sliver and back out: its
copper folds onto itself along the whole protrusion. Neither the original nor the measured spacing (D7, which ignores
pieces of the same turn) account for it. A turn running around a notch narrower than the pitch (a slot) folds the same
way.

**Symptom.** On the new `narrow_*` corpus cases, with the first version of the fixes: clearance deficits of up to 18× the
clearance (`narrow_finger_w6.0_n4k1`), the path touching itself (reported as a branch: `narrow_finger_w6.0_n9k4`,
`narrow_keyhole_w7.0_n7k3`) and a crossing between the folded turn and a via connection (`narrow_slot_w10.0_n4k1`, where
the parts of the square beside the slot collapse at 9.5 mm inside the 10 mm annulus). The original code shows deficits
of the same size on these cases (16.5× for `narrow_tshape_w5.0_n4k1`, 18.3× for `narrow_finger_w6.0_n4k1`), mixed with
its other defects.

**Fix.** Protrusions are cut (`Skeletonator.set_fold_limit`, set by `PlanarInductor` to half the nominal pitch): the
vertices inside a protrusion (tracks that enter a constant-time skeleton group with one way up somewhere other than at
its exit) jump at depth T − pitch/2 onto the protrusion's mouth and follow the mouth from there. The mouth is spanned by
the tracks that reach the group's exit from outside (usually the two reflex corners at its base); each tip lands on the
chord between the mouth vertices before and after it in outline order (orthogonal projection, clamped to the chord,
kept in outline order), so each stays on its own side. Where the mouth has a single vertex (its other side is an edge,
as for the parts of a square beside a slot), the tips move along the protrusion's axis at the mouth onto the line
through that vertex. Protrusions are cut in order of increasing T, each on the tracks as cut by the shallower ones.
Turns that would have run into a sliver narrower than one pitch cut straight across its mouth (logged as info); turns
that still enter have their two sides at least one pitch apart. A protrusion without a mouth is left alone and gives a
warning. (Moving the tips to the mouth's mean point instead, as first tried, turned the side edges into chords that
dipped up to 0.25 mm below the annulus in `narrow_slot_w10.0_n9k4`.) The first version of this cut (found in the third
review) stopped after the first protrusion a track passed through: in a finger narrowing in steps, or with a side
branch, the inner tips were cut only at the inner mouth and still ran up the outer protrusion's axis while the outer
protrusion's other vertices were cut at its mouth, so one turn ran up the axis and straight back (a zero-width hairpin:
connectivity broken in 10 of the new `narrow_stepped/branch` cases, and in all three alternative layouts). It also
moved each tip along the direction from its own entry node to the exit, which is oblique for a bent (L-shaped)
protrusion: the tips landed up to 0.6 mm inside the outline, and the measured spacing, and with it the trace width of the
whole coil, dropped to 33–63 % of the straight-finger value (`narrow_lfinger_w3.0_n9k4`: 0.07 mm instead of 0.50 mm).
Folds around notches cannot be cut without moving copper outside the outline;
`min_turn_spacing` now also reports the closest approach of two pieces of the same turn that are far apart along the
conductor (more than π × their distance plus a pitch, or more than 4 × (trace width + clearance), which catches
the converging sides of a tapered finger that the first criterion missed), and `PlanarInductor` warns when that is less
than trace width plus clearance (it does not short different turns). None of the other 95 `narrow_*` cases has a
connectivity, crossing, winding, backtrack, track clearance or via clearance problem any more, and nothing changed on
the 602 previous corpus cases. 26 of the 48 fail the checker's coverage test, mostly because the cut-off part of a protrusion stays uncovered;
4 of them passed before the cut (3 only because the checker counts a fold shorter than its `s_far` path distance as a
harmless self-overlap). In the full corpus the fold warning also appears for
`ellipse3to1_a0.90_n16k5` and `sector180_a0.90_n3k1`, where a 90 % annulus reaches deep into a narrow tip; there the
checker counts the fold as a self-overlap.

### D29. Error messages when both trace width and clearance are given

**Defect.** In the branch where both trace width and clearance are given (l. 445–449), the "trace width larger than the
pitch" check rounds to 2 decimals (the other branches to 3 since D11) and says "Reduce clearance" where the trace width
is the problem. Neither message there says that the pitch is the *measured* smallest spacing, or where it is.

**Symptom.** Original code, rectangle 50×40 mm, annular width 10 mm, n=10, k=3, clearance 0.2 mm (projected pitch
1.992 mm): trace width 2.004 mm is rejected with "Given trace width of 2.00 mm is larger than the projected spiral pitch
of 1.99 mm. Reduce clearance or increase the size of the coil" (reducing the clearance cannot help), and 1.804 mm with
"Actual clearance for 1.80 mm trace is 0.19 mm, which is lower than the given clearance of 0.20 mm", where the rounded
numbers add up to the pitch. The missing hint is worse since D7 measures the spacing: in the first version of the fixes
the same rectangle measures 1.885 mm at the corners, and trace width 1.75 mm is rejected with "Actual clearance for
1.75 mm trace is 0.14 mm", which gives no reason (the original accepts 1.75 mm against its 1.992 mm pitch).

**Fix.** All four messages use 3 decimals, name the parameter to reduce ("Reduce trace width to at most 1.685 mm, reduce
the clearance or increase the size of the coil") and, when the measured spacing is below the nominal pitch, give it,
the nominal pitch and the location, with the likely cause (corners and steep spirals, or a collapsing narrow part of the
outline).

---

## Found on round and dense outlines

Found with the `round` corpus family (polygonal circles, ellipses, smooth blobs and dense SVG-like outlines with up to
2500 vertices).

### D30. Straight skeleton runs out of memory on outlines with many tiny reflex corners

**Defect.** A dense smooth outline whose coordinates are rounded to 1 µm (as an SVG or DXF export writes them) has
thousands of tiny reflex corners: the rounding noise turns up to 40 % of the vertices concave. CGAL's straight skeleton
looks for split events of every reflex vertex against every edge, and the nearly degenerate input makes it fall back to
exact rational arithmetic. Time and memory grow with (vertices × reflex vertices): about 0.1 ms and 1.2 kB per unit
for clean outlines (stars, gears), 0.2 ms and 2.4 kB for coordinates rounded to 1 µm. Nothing limited this, and when
skeleton.wasm aborted, the error surfaced as a bare `wasmtime.Trap` (the same for a self-intersecting outline, which
fails CGAL's `is_simple_2` precondition).

**Symptom.** `svg_like(40, 3000, Random(4242))` from the round corpus (3000 vertices, 1261 reflex): "libc++abi:
bad_alloc" after 349 s here (400–650 s reported), then a `Trap` from `PlanarInductor`. With 1000 vertices (184 reflex,
`round_svg1000r_a0.60_n8k3`) the skeleton takes 31 s and the case 197 s. The original code passes the outline to the
same skeleton.wasm unchanged: the 3000-vertex outline fails the same way there (bad_alloc after 349 s at 4 GB RSS).

**Fix.** `Skeletonator._skeleton_of`: when vertices × reflex vertices exceeds 25 000 (the main corpus stays below 1
600), the skeleton is computed for the outline without its rounding noise (`remove_reflex_jitter`), if that at least
halves the cost: reflex vertices are removed, shallowest first, as long as every input vertex they cover is within 1 µm
of the replacing chord (outlines with real reflex corners, such as `round_noisy_l`, 256 × 118 with one shallow corner,
are left alone). Removing a reflex vertex only adds area, so the simplified outline (`Skeletonator.skeleton_poly`)
contains the input and stays within 1 µm of it. Its neighbors become less convex, and those that turn reflex are
removed in turn, so nearly collinear convex vertices go too; only vertex 0 is always kept. The removed vertices stay
vertices of the spiral (`Skeletonator.poly`, `_spiral_vertices`): each is projected onto its chord and gets a track
(`_chord_track`) that moves like a collinear vertex of the full outline's skeleton, straight inwards along the offset
chord until the track of one of the chord's end vertices reaches it, then on that track. So the angle reference keeps
one vertex per outline vertex. `Skeletonator.outline` and `OffsetShape.polygon` (keepout zone, checker) stay the input.
skeleton.wasm can address at most 4 GB, and clean outlines need about 1.2 kB per unit (a 2000-vertex star with 1000
reflex corners: 183 s, 2.46 GB), so an outline whose cost stays above 3 500 000 cannot fit and is rejected at once with a
`ValueError` that gives the counts. Below that it runs, e.g. a 1500-vertex circle with 5 µm noise (not simplified:
238 s, 2.4 GB). skeleton.wasm's stderr is captured: a non-simple outline is a `ValueError` ("not a simple polygon"), a bad_alloc
a `ValueError` asking to simplify the outline, other aborts a `RuntimeError` with the message. The cornerflat layout's
forked skeleton computation now raises these again in the parent instead of a generic `RuntimeError`.

The 3000-vertex outline is simplified to 1216 skeleton vertices (1 reflex) in 1.9 s. `round_svg1000r_a0.60_n8k3` takes
4.5 s instead of 115 s (layout and footprint, without the checker) and passes, with trace width 2.6117 instead of 2.6098
mm and 0.58 % instead of 0.65 % uncovered, no overshoot. No other case of the main or round corpus is simplified.

In a first version of this fix the spiral only had the simplified outline's vertices, and the limit was 500 000. That
coarsened the angle reference wherever nearly collinear vertices were removed: a 24-gon with 12 edges per side and 0.1
µm jitter (288 vertices, 133 reflex, simplified to 89) went from trace width 2.7781 to 2.7376 mm and from 0.81 % to 2.29
% uncovered (60 % annular width, 8 turns, 3 twists); now 2.7783 mm and 0.80 %, in 1 s instead of 8 s. The old limit
also rejected clean outlines that lay out in minutes (a 520-point star: 56 s; a 300-tooth gear: 101 s).

### D31. Angle reference quadratic in the number of vertices

**Defect.** `Skeletonator.set_angle_reference` (not in the original, which has no fixed angle reference and lays out a
1000-vertex blob in 1.9 s) evaluates every edge at every distinct node time of all tracks, O(n²) `track_position` calls
on smooth outlines, where every event time is distinct. It ran three times per coil: in `Skeletonator.__init__` (for the
whole depth, the most expensive), in `OffsetShape.__post_init__` and from `set_fold_limit`, also when nothing was cut.
On smooth outlines all tracks run to the center, so the tracks themselves hold O(n²) nodes (1.1 million for 2500
vertices), and building them, `set_fold_limit`'s scan of all track pairs and the coordinate hash of every `SkeletonNode`
lookup were quadratic too.

**Symptom.** `round_dense2500_a0.30_n5k1` (2500 vertices): 10.9 s for layout and footprint, 48 s under the profiler, of
it 34.7 s in `set_angle_reference` (6.3 million `track_position` calls) and 5.4 s in `set_fold_limit`. Smooth blobs (8
turns, 3 twists, 60 % annular width) with 2500 and 5000 vertices take 10.9 s and 38.3 s.

**Fix.** The shortest length of edge i over the same sample depths is computed from its own two tracks only: once they
meet (continue on the same nodes) the two vertices coincide at every greater depth, so the length is exactly 0; before
that, between consecutive node times of the two tracks the edge vector is affine in the depth, so the length is convex
and its minimum over the sample depths there is at a sample next to the continuous minimum, which is evaluated with the
same `track_position` calls (`_min_edge_lengths`; the old version is kept as `_min_edge_lengths_bruteforce`).
Neighboring tracks meet soon (summed over all edges, the parts before the meeting point visit each skeleton edge about
twice), so this is close to linear. The result is cached by (tracks, depth), and `set_fold_limit` keeps the tracks (and
the angles) when nothing is cut and skips the protrusion search when the skeleton has no constant-time groups. Tracks
copy the rest of an earlier track at the first shared node, and nodes hash by identity (one object per distinct node).
On all 93 corpus outlines (main and round) at the annular width, at the full depth, with and without the protrusion cut,
the edge lengths are bit for bit those of the brute force version (2.9 s instead of 57 s in total), and the trace widths
of the main corpus are unchanged. On simplified outlines (D30) they agree within 2e-17 of the circumference: an edge
between two vertices on the same chord keeps its length while both move straight inwards, so its samples differ only
by rounding. `round_dense2500_a0.30_n5k1` takes 3.7 s (3.1 s of it the skeleton itself), the 2500-
and 5000-vertex blobs 3.7 s and 8.0 s (about 6 s of it the skeleton).

### D32. Clearance violation at the thin inner tip of an ellipse (checker, already fixed)

`round_ellipse3to1_a0.90_n5k1` (60 × 20 mm ellipse, 512 vertices, 90 % annular width) was reported with a clearance
deficit of 0.0275 mm at (12.45, −1.82). The flagged pieces are the innermost turn on each layer running along the bottom
of the thin inner contour (y = −1.785 at x = 12.59), around its right tip and back along the top (y = +1.778): 3.56 mm
apart, 0.045 turns apart in winding angle, 14.54 mm apart along the conductor. The checker the report was made with
(`8ab123c`) also counted copper more than s_far = 4 × (w + c) = 14.36 mm apart along the conductor as different turns,
so this fold of one turn became a clearance violation. The generator agrees that it is one turn: the spacing measurement
leaves it out (0.045 < 0.5 turns), and the fold warning (D28) reports exactly this spot ("Near (12.445, -1.820) the
copper of one turn comes within 0.122 mm of itself"). Since `33a665a` the checker decides by winding angle alone; it
counts the 856 close pairs as self overlaps (no self short), and the case passes. No change to the generator; a test
pins the classification and the warning.

---

## Vias

### D-VIAS-1. Inner vias placed on top of each other, shorting the arms (warned only)

**Defect.** The automatic via offset ((via diameter − trace width)/2, at most the collapse depth minus the annular
width) moves the inner vias inwards along the skeleton. Where the inner contour narrows (a sliver, or near the
collapse depth, where it degenerates to a segment or a point), several edges have zero length at the via depth, so
different fold angles project to the same point. The vias of different arms then coincide or overlap, which shorts the
arms. `PlanarInductor` only warned ("Overlapping vias") and emitted the layout.

**Symptom.** `round_ellipse20to1_a0.90_n16k5` (80 × 4 mm ellipse, 1024 vertices, annular width 1.8 of 2.0 mm, 5
arms): via offset 0.2 mm = the full collapse depth, all five inner vias at (0, 0); checker: "via at (0.000, 0.000) has
10 track connections", connectivity, winding. `round_ellipse10to1_a0.90_n16k5`: two vias at (−7.389, 0), the others
0.16 mm apart. `round_ellipse10to1_a0.60_n21k8` (8 arms): two vias 0.623 mm apart (via 0.6 mm), a via-via clearance
deficit of 0.127 mm. The original code has the same defect: it cannot lay out the two 90 % ellipses (`math domain
error`), but lays out `round_ellipse10to1_a0.60_n21k8` with two inner vias 0.62 mm apart at (−17.907, ±0.310), warned
only ("Overlapping vias in inner via ring"); a circle 20/1 mm, 16 turns, 5 twists puts its 5 inner vias (0.68 mm,
clipped to the trace) on a 0.5 mm ring, 0.59 mm apart, with the same warning.

**Fix.** With an automatic via offset, when the vias are closer than via diameter + clearance, the offset is chosen in
[0, offset] (33 samples, then bisection): the largest offset at which the vias clear each other and the neighboring
turns by the clearance, or else the one with the largest smallest gap (via to via, or via to turn)
(`PlanarInductor._via_offset_for_spacing`). If the vias still overlap (center distance below the via diameter), the
request is rejected with an `OverlappingViasError` (a `ValueError`) naming the two vias, their distance and what to
reduce; a remaining clearance deficit between vias is warned, as before. The cornerflat and jog layouts catch the error
while they try layout candidates and raise it only if the chosen candidate has it. Both 90 % ellipses are now rejected:
on the innermost turn the two vias on opposite sides of the sliver are 0.261 and 0.391 mm apart, so no placement fits.
`round_ellipse10to1_a0.60_n21k8` gets offset 0.244 instead of 0.289 mm: vias 0.714 mm apart (deficit 0.036 mm),
0.105 mm from the neighboring turn (warned) instead of 0.150 mm. The circle is rejected. Cornerflat and jog reject the
same two ellipses. Jog's other layout candidates keep the vias apart, but put a via 0.103 mm (20:1) and 0.035 mm (10:1)
into a neighboring turn, which shorts as well: when the preferred candidate had overlapping vias, a candidate whose via
overlaps a neighboring turn is rejected with the same error (`reject_shorting_fallback`, in jog and cornerflat).

### D-VIAS-2. A via touching the copper of its own turn (checker exemption)

**Defect.** The checker skipped every contact between a via and copper of its own conductor closer than s_near + via
radius along the path (s_near = π/2·(w + c)), to allow the conductor's arrival into the via. With wide traces that is
10 to 18 mm, so a turn that leaves its via and comes back to touch it from another side within that distance (which
shorts that part of the turn) passed. The generator did not warn either (`via_track_clearance` skips the half
revolution next to the via's own connection).

**Symptom.** Triangle at 96 % of the inscribed radius, 4 turns, 1 twist (trace and via 3.76 mm): followed from the inner
via at (0, 0.8), the arm runs out to a corner of the small triangular inner contour at (3.464, −2.0), 4.45 mm from the
via center (0.55 mm more than via radius + w/2 + c, so clear of it), and comes back past the via: its center line passes
3.33 mm from the via center, 0.43 mm into the via's copper, 7.4 mm along the path; checker: pass (except conformance).
Not in the corpus. In a sweep of 388 nearby inputs (12 outlines at 80-96 % of the inscribed radius × 6 turn/twist
combinations, 28 circles) the same happens in 7 kicoil layouts (triangles, `rstar0` at 96 %), 11 cornerflat and 3 jog
ones. The original code cannot lay out any of them (`math domain error`: it fails on every polygon at 80-96 % and
every circle with a 2-8 mm hole and 2-5 turns tried), so whether it has the defect cannot be tested.

**Not a defect: the arrival.** The wide innermost turns of e.g. `rstar0_a0.90_n3k1`, `pentagon_a0.90_n3k1`, cornerflat
`rconvex0_a0.90_n3k1` and `circle30x6_n2k1` curve tightly into their via, and copper 7 to 11 mm back along the path
(0.18 to 0.42 turns around the center) overlaps the via by up to 2.9 mm. Followed from the via, the distance from the via
center to the center line only grows there (within 0.07 mm): that copper never leaves the via, it is one piece of copper
with it, and the via shorts nothing that the track's own copper does not already connect. A first version of this fix
flagged these by winding angle (at least 0.18 turns from the via). That verdict was set by where the 0.18-turn cut fell,
measured around shapely's `representative_point` of a tiny inner contour: it changed with the outline's orientation
(`star5` at 80 %, 5 turns, 2 twists: self short at 0-27° and 72-90°, none at 36-63°), alternated along an annular width
sweep, and the generator (which measured the angle in skeleton parameter) missed some of them (unwarned self shorts).

**Fix.** Checker (`own_via_returns` in `check_layout`): within s_near + radius of a via along the path, followed away
from the via on both sides, the deficit of a point at distance d from the via center is min(r + w/2 + c − d, X + c,
M − d), with M the largest d and X the largest d − (r + w/2 + c) between the via and the point. It is a self short when
the deficit reaches the clearance, i.e. the copper touches the via after its center line has been at least
r + w/2 + c away (its copper cleared the via). It uses no winding center, and is exact per segment (d is convex along a
segment, the deficit concave), so it depends neither on the orientation nor on how the track is cut into segments.
Generator: `PlanarInductor.via_own_turn_clearance` applies the same rule to the arm center lines (trimmed at the via as
`render_footprint` does), with margins: copper counts once the center line has been r + w/2 + c/2 away and come back by
c/2, or when it is more than s_near + r − c along the arm, and `__post_init__` warns "Via at (x, y) overlaps the copper
of its own turn by … mm, … mm away from it along the conductor" when it is closer than the clearance;
`test_corpus_case` accepts this warning for a self short. The generator does not try to avoid it (the via sits at the
arm end); a smaller annular width, more turns or a narrower trace help.

Corpus (997 cases): no kicoil case changes status from this rule. Cornerflat: 7 cases gain a self short, all
warned: `star5_a0.60_n7k3` (and `_cw`), `sector180_a0.90_n5k3` and `concave_crescent_a0.9_n8k3` passed before;
`ellipse3to2_a0.90_n5k3`, `d_shape_a0.90_n5k3`, `rconvex0_a0.90_n9k4` and `rconvex2_a0.90_n5k3` failed only
conformance. There an arm with a flattened corner hooks out of its via's reach and back; the copper overlap is 0.000 to
0.28 mm (the crescent's contact is exactly at zero gap, so its verdict sits on the threshold). In the sweep every one
of the 7/11/3 self shorts of this rule is warned; the generator warns 51/56/44 of the 388 inputs, so it errs on the
side of warning.
The verdict and deficit of `triangle_a0.96_n4k1` and `rstar0_a0.96_n4k1` (0.579 and 0.332 mm) are the same at every
orientation from 0° to 90° in 9° steps; `star5` and `rstar0` with 2 twists and the pentagon at 80 % pass at all of
them. The other unwarned self shorts of the sweep are track-to-track contacts ("copper touches itself … turns further
on"), the same on `next`, not via related.

### D-VIAS-3. Arm runs into a sharp tip and back to its via (backtrack)

**Defect.** An arm whose fold angle lands on a sharp tip of the inner contour (the sliver of a slender ellipse) ends at
the tip, but its via has to sit back along the tip's spine: there the neighboring turn's sides are only (w + c)/2 from
the spine and converge at about 6°, so the via clearance grows by only 0.11 mm per mm back from the tip. The automatic
offset search moves the via inwards, which moves the tip vertex 8 times as fast, and the straight connection from the
tip runs back over the arm's own copper for 1 to 5 mm (a `backtrack`, same net).

**Symptom.** `round_ellipse10to1_a0.60_n8k3` (60 × 6 mm, via 0.6 mm, trace 0.30 mm): arm end (23.879, 0), via
(22.520, 0), connection 1.36 mm back (cos −0.989). Along the spine from the tip, the via's gap to the neighboring turn is
−0.000 mm at the tip, −0.034 mm 0.25 mm beyond it, and reaches the 0.15 mm clearance only 1.36 mm back, so the via
cannot be put at or after the arm end. Also `round_ellipse10to1_a0.60_n6_1layer`, `round_ellipse20to1_a0.30_n5k1` and
one of two tips of three more 20:1 cases, in all layouts. The original code has the same backtrack at (23.879, 0), via
at (22.661, 0).

**Fix.** The via placement stays. `render_footprint` ends an inner arm where it comes closest to its via when the
connection from the arm end would run back along it (more than 154° to the arm's last piece; `_trim_arm_at_via`, both
layers): the arm stops at the via instead of running into the tip and back; only the very tip of the innermost turn
(between via and tip) is no longer covered. The three cases above now pass, in kicoil, cornerflat and jog (they share
`render_footprint`); no other status changes. 16 more cases with sharp tips (the other slender ellipses, shark, heart,
crescent) lose 0.02 to 18 mm of such doubled-back conductor, with the uncovered fraction changed by at most 0.0006. The
other backtracks of the 20:1 ellipse are turns reversing at the sharp tips of deeper offsets, not via connections, and
stay known failures (`corpus_round.KNOWN_FAILURES['slender']`).

---

## Folds, merges and wraps of one turn

### D-FOLDS-1. Merged copper at hairpins of one turn not warned (fold rule gap)

**Defect.** `PlanarInductor` warned about a turn coming back to itself only for pieces closer than trace width plus
clearance that are more than π·d + pitch, or more than 4·(w + c), apart along the conductor (D28). Where a turn runs
into a sharp tip of the outline and back (a hairpin), the centerlines of its two sides converge at the tip's angle α:
the copper merges over w/sin(α/2) of conductor, but each pair of pieces is only d/sin(α/2) apart along it. For tips of
about 29–39° neither criterion holds anywhere. The spacing measurement also only compares pieces up to 4 pitches long
and measures between their ends, so it cannot see a merge along one long centerline segment at all.

**Symptom.** `concave_crescent_a0.6_n5k1` (w = 1.642 mm): at each horn tip the copper of one turn merges (0.86 mm overlap
at (21.6, −17.5), 3.9·(w + c) of conductor), without a message. An isosceles triangle with a 15° apex (50 mm, 13 turns,
4 twists, annular width 0.72 of the split depth) merges over 6.8·(w + c) at the apex, a self merge (D-FOLDS-2), and the
pieces of the spacing measurement show no pair closer than w at all: no warning.

**Fix.** `measure_same_turn_contacts` measures merges the way the checker does: the arms' centerlines, with their
connections to the vias, sampled at w/4 (at most (w + c)/8), each sample paired with the ends of the stretch of the
other piece's centerline that its copper touches (centerline distance w); pieces of one turn (less than 0.5 turns apart
in winding angle around the checker's center, see D-FOLDS-3) at least π/2·(w + c) apart along the conductor, and vias
against the tracks of their own arm (the via's copper as such). The longest bypassed stretch of conductor,
`max_merge_bypass`, is at most 0.2·(w + c) below the checker's `max_self_touch_bypass` (D-FOLDS-4), and never above it,
on all corpus cases that merge over 3·(w + c) or more. `_warn_same_turn_contacts` warns ("folds onto itself") from `MERGE_WARN_BYPASS` = 5·(w + c) on, one (w + c)
below the checker's limit, and logs local merges from 3·(w + c) on (tips sharper than about 39°, e.g. the crescent).
On the 125 cases of the corpus with merges or wraps, kicoil warns on 28, 22 of them failing `self merge` and 5 passing
(crescent a0.9 n5k1/n13k4 at 5.3/5.6, shark and sharksvg a0.6 n13k4 at 5.8, `narrow_taper_w8.0_n7k3` at 5.0); every
case the checker fails for a self merge is warned, with all four implementations (kicoil 22, cornerflat 19, optspan 17,
jog 16; passing cases warned: 5, 5, 6, 3). A warning from 3·(w + c) on (the first version of this fix) would warn on 48 passing
kicoil cases. The fold rule of D28 is unchanged. Avoiding the merge was
measured and not done: narrowing the trace cannot remove a merge at a V tip (w/sin(α/2) shrinks with w; removing the
crescent's would take the trace from 1.642 to 1.169 mm for the whole coil); cutting the turn short of the tip would need a
corner cut in the skeleton like D28's protrusion cut, which also leaves the tip uncovered.

**Original code:** has no fold warning at all; it lays out the crescent with other defects (connectivity, crossings,
clearance) and the same unwarned merge at the horns.

### D-FOLDS-2. Checker: merged copper of one turn never fails (self merge)

**Defect.** `geomcheck` counts same-turn copper contacts (deficit ≥ clearance) less than `SELF_SHORT_SEP` = 0.18 turns
apart as self touches and reports the bypassed conductor length (`max_self_touch_bypass`), but never fails them. A hairpin
whose copper merges over the whole arm of a C shorts that stretch of the conductor ("connectivity end to end").

**Symptom.** `concave_cshape_a0.9_n5k1` and `concave_uround_a0.9_n5k1` pass with merged copper bypassing 11.5 and
13.8·(w + c) of the innermost turn.

**Fix.** New failure kind `self merge`: a self touch (copper touching or overlapping, the same condition as a self short)
whose pieces are at least `SELF_MERGE_BYPASS` = 6·(w + c) apart along the conductor (`Report.self_merges`), measured
along the whole contact (D-FOLDS-4). Contacts within the copper of one via or pad do not count, nor do the two pieces of
one track drawn as overlapping pieces. The threshold is geometric: at a tip of angle α the two sides merge over
w/sin(α/2), so 6·(w + c) is the merge of a tip sharper than about 19°, or of a hairpin into an arm; the merged copper
then shorts six pitches of conductor or more. Measured along the whole contact, the corpus has no gap there: over the
full corpus, tips merge over up to 5.93 (kicoil, passing: shark a0.6 n13k4), 6.02 (kicoil: shark a0.3 n8k3, the
inner via's copper touching the arm that runs past it into the tip), 6.31 (kicoil: crescent a0.9 n8k3) and 6.30
(cornerflat: shark a0.6 n13k4); hairpins into arms start at 6.10 (the heart's cusp spike), then the slot 7.8, the comb
8.1–8.9, the C 11.5–11.7, the U 10.0–13.8 and the slivers of slender ellipses 6.9–31.
(The first version of this fix claimed a gap between 5.7 and 6.1 from closest points of segment pairs; that measure
depended on the segmentation.) `test_layout.test_corpus_case` treats it like the other warned kinds (xfail when the
generator warned, D-FOLDS-1); the heart's known issue lists it. Full corpus (997 cases):

| | self merges | of these passing before | warned |
|---|---|---|---|
| kicoil | 0 → 22 | 6: `concave_crescent_a0.9_n8k3`, `concave_cshape_a0.9_n5k1`, `concave_shark_a0.3_n8k3`, `concave_sharksvg_a0.3_n8k3`, `concave_uround_a0.9_n5k1`, `round_ellipse10to1_a0.90_n5k1` | 22 |
| cornerflat | 0 → 19 | 4: `concave_cshape_a0.9_n5k1`, `concave_shark_a0.6_n13k4`, `concave_sharksvg_a0.6_n13k4`, `concave_uround_a0.9_n5k1` | 19 |
| optspan (125 cases with merges or wraps) | 0 → 17 | | 17 |
| jog (the same 125 cases) | 0 → 16 | | 16 |

The others already failed (backtracks at the heart's cusp and the slivers of slender ellipses, conformance of the comb
and the slot).

### D-FOLDS-3. Unwarned self short where the innermost turn wraps around a small hole

**Defect.** The spacing measurement only pairs pieces at least 0.5 turns apart (in the spiral's parameter angle), and
the fold rule needs pieces more than π·d apart along the conductor. A turn that wraps around a hole smaller than the
trace comes back to itself 0.2–0.5 turns further on, only about π/2·d along the conductor: neither rule sees it, while
the checker reports copper touching itself at least 0.18 turns further on as a self short.

**Symptom.** `concave_starround_a0.9_n5k1` (10.5 mm annulus in a star with 13 mm inscribed radius, w = 3.644 mm): self
short on F.Cu at (−1.864, 2.566), copper touching itself 0.21 turns further on, no warning; the same with cornerflat,
optspan and jog. `round_blob2_a0.90_n5k1` (w = 6.368 mm, 0.3–0.4 turns). Both were xfailed by name. The sector 90° of
the corpus with 2 or 3 turns at 93–96 % of the maximal annular width: self shorts 0.24–0.42 turns long, no warning.

**Fix.** `measure_same_turn_contacts` (D-FOLDS-1) also finds the closest approach of pieces of one turn at least
`WRAP_SEPARATION` = 0.18 and less than 0.5 turns apart in winding angle (`min_wrap_spacing`), and
`_warn_same_turn_contacts` warns when their copper touches. The winding angle is measured around the point the checker
uses, the shape's `winding_center`: the interior point (GEOS's rule as in D-FOLDS-5, `interior_point`) of the outline offset inwards by
1.02 times the annular width, which the straight skeleton gives exactly up to the depth where the offset splits (beyond
it, from a grid of the points that deep, `_deep_interior_point`). It agrees with the checker's center to 1e-10 mm except
on outlines with many tiny reflex corners (0.8 mm on `round_noisy_l`, whose skeleton is computed for a simplified
outline). The spiral's parameter angle cannot be used: on noisy outlines it stands still over runs of short edges and
then jumps 0.19 turns within 2.6 mm. The first version of this fix used the deepest skeleton node as center, which is
an arbitrary end of a ridge for many shapes (the sector's self short was 0.11 turns long around it), and also compared
pieces one turn apart, so that its result was the ordinary turn spacing and a trace width given within the rounding of
the pitch (`circle30x6_n5k1` with 4.590 mm) was warned as a wrap; and it warned at clearance level. Since the checker
measures contacts along their whole length (D-FOLDS-4), the corners of an innermost turn close to the center that touch
themselves 0.18–0.46 turns further on count as self shorts, too; the generator finds them the same way (with a margin of
one sampling step on the π/2·(w + c) of one bend). On the 125 cases with merges or wraps every self short is warned
(kicoil 18 of 18, cornerflat 13 of 13, optspan 22 of 22, jog 19 of 19). Wrap warnings without a checker self short:
kicoil 5, cornerflat 9, optspan 2, jog 1, all a0.90 n3k1 cases whose innermost turn touches itself at a corner just
within the margin (and cornerflat's failing `round_ellipse20to1_a0.90_n16k5`). The
by-name xfails are removed. Avoiding the short by narrowing the trace was tried and not kept: −50 % trace width for the
star, −38 % for blob2.

**Original code:** rejects `concave_starround_a0.9_n5k1` and `round_blob2_a0.90_n5k1` (math domain error) and has no
fold warnings.

### D-FOLDS-4. Checker: same-turn contacts measured at one pair of closest points per segment pair

**Defect.** For two segments of the same turn, `check_layout` used only their closest points: the deficit, the winding
angle between them and the path distance (bypassed conductor) all came from that one pair; vias and pads against a
track likewise. The closest points of the two long legs of a V lie at its tip, path distance 0, so the merge along the
legs was invisible or underestimated, and contacts closer than π/2·(w + c) along the conductor are skipped.

**Symptom.** The same copper cut into shorter collinear pieces gives other results: `concave_crescent_a0.9_n8k3` 5.60 →
6.2·(w + c) (pass → self merge), `concave_shark_a0.3_n8k3` 3.03 / 5.04 / 6.00·(w + c) depending on the cut, a 13° V with
one segment per leg no contact at all. A corner of the innermost turn close to the center, whose copper merges over
1.6–1.8·(w + c) at 0.18–0.41 turns (the same as the wraps of D-FOLDS-3), was a self short or not depending on the
segmentation: `trapezoid_a0.90_n3k1` and the other a0.90 n3k1 cases below.

**Fix.** `same_turn_contacts` samples both center lines at a quarter of the narrower width and pairs each sample with
points of the other segment: its closest point, the two ends of the stretch whose copper its copper touches (the
farthest contacts along the conductor), and the points π/2·(w + c) along the conductor and 0.18 turns in winding angle
away from it (where the deficit is largest among the pairs that count). Deficit, self short and self touch come from
those pairs; the end of the longest contact is located by bisection to 1/256 of the step (`farthest_contact` does the
same for vias and pads). A V hairpin now gives w/sin(α/2) to 1 % with 1 to 64 segments per leg, real layouts the same bypass within
0.05·(w + c) when cut into 0.5 mm pieces. Full corpus: kicoil's self shorts 4 → 18 (new: the a0.90 n3k1 cases
`trapezoid`, `triangle`, `pentagon`, `hexagon`, `octagon`, `star6_shallow`, `sector90`, `rconvex0/1/3`, `rstar0/1/2`, all
failing conformance already, and `round_ellipse20to1_a0.90_n16k5`); cornerflat's 8 → 14. No case changes status from
this alone, and no trace width changes. The checker takes 2.0 s instead of 1.7 s on the slowest corpus case. Not in the original code (no checker).

### D-FOLDS-5. Checker: the coil's center decided by rounding errors on symmetric holes

**Defect.** The checker takes the coil's center as shapely's `representative_point` of the inset outline (GEOS: the
middle of the widest stretch of a horizontal line through the middle of the extent, moved between vertex heights). On
symmetric outlines two of these choices are ties: a vertex at the middle height (the line moves up or down by rounding)
and two equally wide stretches (e.g. the legs of an arch-shaped hole).

**Symptom.** `octagon_a0.90_n3k1`: center (0, +0.58) where an exact computation of the same inset gives (0, −0.58);
the sector 90° at 95 % annular width: (−2.86, 0.18) against (+2.86, 0.18). Same-turn contacts are classified by the
winding angle around it (0.42 turns around one, 0.11 around the other).

**Fix.** `_interior_point` follows GEOS but counts a vertex within 1e-9 of the extent from the middle as below it, and
takes the first of stretches equally wide to 1e-9; the generator's `interior_point` makes the same choices. The center
moves in 164 of the 997 cases (symmetric outlines; up to 4.9 mm in `octagon_a0.30_*`); in both full corpus runs the only
changes of status or failure kinds are the self merges and self shorts of D-FOLDS-2 and -4. Not in the original code (no
checker).
