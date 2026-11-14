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

Every entry was checked by an independent reviewer against the original code (reproduction where practical) and
corrected where it overstated or misdescribed something. Where a corpus case is given as the symptom, it fails with the
original code and passes the corresponding check with the fixed code. Entries marked *latent* have no visible symptom
in the corpus. Three bugs in the first version of the fixes were found the same way and are described with the fix they
belong to (D2, D3, D10). The remaining 17 rejections are annular widths beyond the straight-skeleton collapse depth
(stars, L/U shapes, the neck) and one circle whose pitch is smaller than the requested clearance.

---

## Spiral geometry (`skeletonator.py`)

### D1. Vertices on a turn boundary are emitted twice, so the spiral folds back on itself

**Defect.** `do_spiral` emits each spiral turn separately. A turn keeps an edge unless it lies wholly outside `[t_start, t_end]`, and the bounds are checked with `isclose` (`tp2 < t_start`, l. 289, and `tp1 > t_end`, l. 291). For each kept edge it emits the edge's *end* vertex. When a vertex angle coincides with a turn boundary, the edge that starts exactly at `t_end` is still accepted, and its end vertex, which belongs to the next turn, is emitted. This happens on every turn for regular polygons, and approximately for rectangles. If the boundary is not a whole number (e.g. 6.5, which is hexagon vertex 3), the next turn also keeps the edge ending at `t_start`. It emits the boundary vertex and then that vertex again, so the track runs A→B→A→B: three copies of one segment, nearly coincident for rectangles, where the next turn recomputes the vertex angles at a different radius (D2). At a whole-number boundary the per-turn angle list starts at `floor(t_start)`, so the result is one vertex emitted twice in a row, a zero-length segment.

**Symptom.** Branches in the conductor graph, and a winding error of whole turns because the checker counts every copy of the folded segment. Example: `hexagon_a0.30_n13k1` has 6 fold-backs in its 13→6.5 arm, giving 12 branches and a winding error of +2.0 turns (6 × 2 extra passes × 1/6 turn). For regular polygons the vertex angles do not depend on size, so a size tweak does not help (all `sweep_hexagon_*` cases keep their branches). Whether a boundary lands on a vertex depends on the turns and twists.

**Fix.** `do_spiral` is rewritten on top of a new `Skeletonator.spiral(t1, t2, d1, d2)`. It emits the start point, then every vertex instance with `t1 <= angle < t2` exactly once in angle order (`iter_vertex_angles`), then the end point. Consecutive identical points are dropped.

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

### D8. Arc approximation eats into the clearance

**Defect.** For circles, `arc_approximate` replaces the spiral with circular arcs. Its default tolerance is 0.02 mm, which is 13 % of the default 0.15 mm clearance, and it is checked only at the input points (64 per turn), not between them. The trace width does not allow for this error. Nearly all of the loss comes from the tolerance itself: on the symptom case, sampling at 256 points per turn with the 0.02 mm tolerance changes nothing. There are also two latent bugs that the corpus never reaches. First, for fewer than 5 points the function emits an arc and then falls through to the general case (missing `return`, l. 78–79). That gives a duplicate arc, or a `ValueError` when an out-of-tolerance 4-point run is split into a 2-point piece. Second, collinear points divide by zero.

**Symptom.** `circle50x25_n11k5`: 12 % of the clearance missing (0.018 mm). With the original code and only the tolerance capped, this drops to 0.9 %.

**Fix.** The effective tolerance is capped at clearance / 40. Arcs are fitted to at least 256 points per turn. The early return is added (runs of 3–4 points are still emitted unchecked as a single arc). Collinear point runs are split instead of dividing by zero. The case now loses 0.09 % of the clearance.

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
violations; found in review and fixed by the splitting.

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

**Fix.** Uses the footprint's zones, lines, arcs (as `TrackArc`) and through-hole pads. **Not fully resolved:**
gerbonara's `Board.empty_board()` cannot serialize even an empty board (`MappingError` on `legacy_footprints`), so the
kicad-pcb export still fails inside gerbonara.

### D23. Keepout zone outline closes on a duplicate point

**Defect.** For polygon shapes, `OffsetShape.offset_exterior` (geometry.py l. 199–200) returns the raw generator of `do_spiral(0, 1, ...)` (one full revolution). That revolution ends on its start point, and D1's turn-boundary double emission repeats that point once more. The keepout polygon therefore ends with two extra copies of its first vertex, which are two zero-length edges (a hexagon gives 8 points instead of 6). The generator also yields `(point, r_ref)` pairs, not points. `render_footprint` (l. 628) unpacks each pair as `x, y`, which works only because gerbonara's `XYCoord` takes the coordinates from a tuple `x` and ignores `y`. `CircleShape` is not affected.

**Fix.** `offset_exterior` unwraps the pairs to plain points and drops the closing point (`[:-1]`). The other copy is no longer emitted since D1's rewrite of `do_spiral`. The outline now has exactly one point per vertex (6 for a hexagon, 4 for a rectangle).
