# Defects found in the original code and how they were fixed

Baseline: upstream commit `7fe1f45` ("Update kicad addon metadata description", v0.11.1). Line numbers refer to that
commit. Corpus numbers come from `tests/run_corpus.py --kind full` (588 cases), evaluated with the checker in
`tests/geomcheck.py`. See `tests/README.md` for what the checks mean.

| | original | fixed |
|---|---|---|
| connectivity broken | 258 | 0 |
| crossings between turns | 63 | 0 |
| wrong number of turns (winding) | 217 | 0 |
| track clearance deficit > 5 % | 454 | 1 (infeasible request, warned) |
| via clearance deficit > 5 % | 408 | 1 (same case) |
| crashes / rejected requests | 1 / 85 | 0 / 25 |

---

## Spiral geometry (`skeletonator.py`)

### D1. Vertices on a turn boundary are emitted twice, so the spiral folds back on itself

**Defect.** `do_spiral` emits each spiral turn separately. A turn keeps an edge if its *start* angle `tp1` is not
beyond the turn's end (`if tp1 > t_end and not isclose(...)`, l. 291), and then emits the edge's *end* vertex. When a
vertex angle coincides with a turn boundary, which happens on every turn for symmetric shapes (regular polygons,
rectangles) and for arms that start on a vertex, the edge that starts exactly at `t_end` is still accepted. Its end
vertex, which belongs to the next turn, is emitted. The next turn then emits the boundary vertex and that vertex again.
The track runs A→B→A→B, three copies of one segment.

**Symptom.** Branches in the conductor graph and a winding error of whole turns, e.g. `hexagon_a0.30_n13k1`: 12
branches, winding off by +2.0 turns. This is the "a small tweak fixes it" behavior: a slightly different size moves the
vertex off the boundary and the duplicate disappears.

**Fix.** `do_spiral` is rewritten on top of a new `Skeletonator.spiral(t1, t2, d1, d2)`. It emits the start point, then
every vertex instance with `t1 <= angle < t2` exactly once in angle order (`iter_vertex_angles`), then the end point.
Consecutive identical points are dropped.

### D2. Vertex angles are recomputed for every turn and every arm

**Defect.** The angle coordinate of a vertex (which sets the spiral's depth there) comes from the outline's edge
lengths at a reference radius `r_ref`. `do_spiral` recomputes it for each turn, at that turn's inner radius
(l. 268–269). `project_point` does the same for the via and pad positions at whatever `r_ref` it is given. Edges grow
or shrink as the outline is offset, so the same vertex gets a different angle on each turn and on each arm. Neighboring
turns are then not one pitch apart at a vertex but `pitch · (1 + Δangle)`, and arms of twisted coils drift into each
other.

**Symptom.** Clearance violations and crossings on shapes whose edge-length proportions change with depth (stars,
sectors, random polygons, chamfered rectangles), worse for more twists.

**Fix.** The angle of every vertex is fixed once per shape (`Skeletonator.set_angle_reference`, called with the
annular width). Each edge gets an angle span proportional to its *shortest* length over the depth range the spiral
uses. This bounds the slope of the spiral relative to every edge at every depth. Edges that collapse before the inner
turn get a span of zero, so several vertices can share one angle. A spiral arm traverses such a group at constant
depth. `_locate` resolves the tie to the first vertex of the group for arm ends, vias and pads alike, and
`snap_angle` removes floating point noise from computed arm angles. Without these two, arms ending at a collapsed tip
cut across it (seen on `ellipse3to1_a0.60_n5k1`). `r_ref` is still accepted by the API but ignored.

### D3. The usable depth is the depth of the *last* split event, not the first

**Defect.** In `Skeletonator.__init__` (l. 178–180), the depth limit is updated with
`self.min_radius = min(n1.time, self.radius)` for every "divergent" node. That compares against the full radius, not
against the running minimum, so the result is the time of whichever divergent node comes last in CGAL's output.

**Symptom.** Annular widths beyond the first split event are accepted (projection then runs into a dead end), or valid
widths are rejected, depending on output order.

**Fix.** The limit is the minimum over all split events (`max_depth`, also exposed as `min_radius` for compatibility).

### D4. Coincident skeleton nodes are taken for split events, and arc direction relies on CGAL's output order

**Defect.** Vertex tracks follow `arc_map[n1] = n2` built from the order in which the C++ wrapper writes each edge
(l. 181). That order is `he->vertex()` / `he->opposite()->vertex()` of the halfedge with the larger id, not inward in
time. A node that appears as the source of two edges is treated as a split ("divergent"). At degenerate events (several
wavefront vertices meeting at one point, e.g. the center of regular polygons, or rounded corners) CGAL emits clusters of
coincident nodes joined by zero-length edges. These look divergent even in convex polygons.

**Symptom.** Convex shapes rejected far below their real depth. `roundrect_a0.90_n9k4`: "Annular width (11.25) is too
large. Must be less than 5.35", although the shape is convex and 12.5 deep.

**Fix.** Coincident nodes (same position and time within a tolerance) are merged. The skeleton is used as an undirected
graph, and tracks always step to the neighbor with strictly greater time. A node with more than one way up is a real
split. Tracks end where the outline collapses. Depths past the end of a track are clamped, not extrapolated
(`track_position`).

### D5. Debug file written on every call

**Defect.** `compute_skeleton` writes its input to `/tmp/debug.txt` (l. 135). On every shape construction, on every
platform (fails on Windows without `/tmp`, races between processes).

**Fix.** Removed.

---

## Trace sizing and vias (`geometry.py`, `PlanarInductor`)

### D6. Trace width is sized from a circle formula that does not hold for polygons

**Defect.** The distance between neighboring turns is estimated as `spiral_pitch · cos(alpha)` (l. 402–407), with the
spiral's inclination `alpha` computed as if the shape were a circle. For polygon shapes, `inner_radius` /
`outer_radius` are skeleton depths, not geometric radii, so `alpha` is meaningless. Even for circles, averaging alpha
between the two innermost turns underestimates the inclination of the innermost one. Above all, on polygons two
neighboring turns come closest at convex corners. The turn leaving a corner runs at a slope `s` relative to the edge,
so the next turn's corner point is only about `p · (1 − s · cot(θ/2))` away. That depends on the corner angle, the
number of twists and the depth, and the formula ignores it. The trace width `projected_pitch − clearance` therefore
regularly leaves less than the requested clearance.

**Symptom.** Track clearance violations in 454 of 588 cases. `square40_a0.30_n8k3` is short by 37 % of the clearance
next to every corner.

**Fix.** `PlanarInductor` computes the center lines of all arms first (`spiral_center_lines`) and measures the actual
smallest distance between different turns on each layer (`measure_turn_spacing` → `min_turn_spacing`, grid-accelerated
segment distances). Pieces of the same arm count as different turns only when they are at least half a revolution
apart, judged on sub-segments of ≤ 0.05 revolutions. Trace width (or clearance, if the width is given) is derived from
that measurement. As a result traces are narrower where the geometry forces it (median (w+c)/pitch 0.93 instead of
0.99), but the requested clearance holds. A trace width ≤ 0 is now a clear `ValueError` (see D10).

### D7. Arc approximation eats into the clearance

**Defect.** For circles, the spiral is replaced by circular arcs (`arc_approximate`) with a default tolerance of
0.02 mm (13 % of the default 0.15 mm clearance), checked only at the 64 input points per turn, not between them. This
error was not accounted for in the trace width. In addition, for fewer than 5 points the function emits an arc and then
falls through to the general case (missing `return`, l. 78–79), emitting overlapping duplicate arcs. Collinear points
divide by zero.

**Symptom.** `circle50x25_n11k5`: 12 % of the clearance missing.

**Fix.** The effective tolerance is capped at clearance / 40, arcs are fitted to at least 256 points per turn, the
early return is added, and collinear point runs are split instead of dividing by zero.

### D8. Via ring overlap check crashes on polygon shapes

**Defect.** The check for overlapping vias uses the circle formula `2·asin((d_via + clearance)/2 / r_ring)`
(l. 467, 470), with `r_ring` derived from skeleton depths for polygons. For deep annuli the argument exceeds 1.

**Symptom.** `ValueError: math domain error`. 57 corpus cases rejected for this reason alone, e.g. every 90 % depth
case of convex polygons.

**Fix.** The via positions are computed (`via_positions`) and their smallest center distance compared with via
diameter plus clearance (`via_ring_spacing`). A warning is emitted with the actual numbers.

### D9. Vias wider than the trace collide with tilted neighboring turns

**Defect.** When the via is wider than the trace, the via offset `(d_via − w)/2` aligns the via's edge with the trace's
edge in the radial direction only. Next to a neighboring turn that runs at an angle (many twists), the via's sides come
closer than the clearance. The original code did not check via-to-track distances at all.

**Symptom.** Via clearance violations in 408 cases (most are D6 as well). After fixing D6, `triangle_a0.60_n21k8`
still had all 8 inner vias 13 % short.

**Fix.** `via_track_clearance` measures the distance from every via to every arm segment except the part of an arm
within half a turn of where it enters that via. With an automatic via offset, the offset grows until the vias clear.
It stops if that would push inner vias past the collapse depth (`OffsetShape.max_via_offset`) or make vias overlap each
other. With a user-given offset, or when no offset works, a warning names the via and the gap.

### D10. NameError instead of an error message when the clearance exceeds the pitch

**Defect.** The message for "clearance larger than the projected spiral pitch" references undefined names
`clearance` and `projected_spiral_pitch` (l. 434). If the message had worked, the code would have gone on to compute a
negative trace width, since the branch only warns.

**Symptom.** `circle20x18_n16k5`: `NameError: name 'clearance' is not defined`.

**Fix.** Correct names, and both "auto width" and "auto clearance" branches raise `ValueError` when the result would be
≤ 0.

### D11. Single-layer mode ignores the twists reset when computing angles

**Defect.** For `layers == 1`, twists are forced to 1 (l. 409–411), but only after `sector_angle = 2π / twists`
(l. 393) and `sweeping_angle` have been computed with the old value.

**Symptom.** A single-layer coil requested with twists > 1 gets a fraction of the requested turns.

**Fix.** The validation and reset run before the angles are computed.

### D12. Track length and resistance computed for one sector instead of one arm

**Defect.** `compute_spiral(a1=0, a2=self.sector_angle)` (l. 496) measures one sector (1/twists of a revolution). That
is then multiplied by twists and layers, as if it were a full arm (which spans `sweeping_angle`, i.e. turns / layers /
twists revolutions).

**Symptom.** Reported track length and resistance too low by a factor of turns/layers.

**Fix.** Uses `sweeping_angle`.

### D13. Dangling stubs at the terminal pads

**Defect.** At `i == 0`, the outer "via" position is not used for a via (the pads go there instead), but the two
connecting lines from the arm ends to that position are still drawn (l. 607–608). With a via offset > 0, they stick out
of the coil as dead-end copper.

**Symptom.** 62 cases with stubs, e.g. `circle20x18_n5k3`.

**Fix.** No connecting lines for `i == 0`. Pad 1 sits on the start of the first layer-0 arm, pad 2 on the end of the
last layer-1 arm (the same point as before, now taken from the actual arm ends). Zero-length connection lines are no
longer emitted either.

### D14. Twists of 0 accepted

**Defect.** `if self.twists < 0` (l. 416) allows `twists = 0`, which divides by zero in `2π / twists`. The message also
names the wrong parameter.

**Fix.** `twists < 1` is rejected with a message naming twists.

---

## Shapes, CLI and export

### D15. `slug` and `desc` broken for polygon shapes

**Defect.** `CircleShape.slug` and `OffsetShape.slug` lack the `f` prefix (l. 123, 172), so footprint names contain
literal `{self.outer_diameter:.2f}`. `OffsetShape.desc` (l. 177) references `self.radius`, which does not exist. Any
polygon shape that does not override `desc` fails in `render_footprint` with `AttributeError`.

**Fix.** f-strings, and `desc` / `slug` use the annular width.

### D16. SVG import computes a wrong bounding box

**Defect.** `SVGShape` computes `min_y = max(x…)` and `max_x = min(y…)` (l. 350–351). The decision whether to recenter
the polygon on its centroid is therefore based on a nonsense box.

**Fix.** Correct min/max of x and y.

### D17. Stray debug print

**Defect.** `RegularPolygonShape.__post_init__` prints its polygon (l. 315).

**Fix.** Removed.

### D18. `kicoil trapezoid` crashes

**Defect.** `cli.py` uses `TrapezoidShape` (l. 283) without importing it.

**Fix.** Imported.

### D19. `--format kicad-pcb` crashes

**Defect.** `kicad.footprint_to_board` references undefined `zones`, `lines` and `pads` (l. 46–48) and ignores arcs.

**Fix.** Uses the footprint's zones, lines, arcs (as `TrackArc`) and through-hole pads. **Not fully resolved:**
gerbonara's `Board.empty_board()` cannot serialize even an empty board (`MappingError` on `legacy_footprints`), so the
kicad-pcb export still fails inside gerbonara.

### D20. Keepout zone outline closes on a duplicate point

**Defect.** `offset_exterior` returns the output of a full-revolution spiral, which ends on its start point, so the
keepout polygon has a duplicated vertex.

**Fix.** The closing point is dropped.
