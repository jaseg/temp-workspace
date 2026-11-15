# Defects of the layout and how they are fixed

Found by laying out a corpus of about 1000 shapes and parameters (`tests/corpus*.py`) and checking the resulting copper
with an independent geometric checker (`tests/geomcheck.py`, see `tests/README.md`). Line numbers refer to
`7fe1f45` (v0.11.1); where upstream `main` (373f65c) changed the code since, that is noted. Every entry is covered by a
test in `tests/` (named in parentheses where it is not obvious).

| full corpus (1008 cases) | 7fe1f45 (v0.11.1) | main (373f65c) | this branch |
|---|---|---|---|
| pass | 50 | 18 | 513 |
| crashes / rejected requests | 18 / 198 | 18 / 198 | 0 / 35 (all infeasible) |
| connectivity broken | 370 | 722 | 0 |
| crossings between turns | 154 | 677 | 0 |
| wrong number of turns | 23 | 721 | 0 |
| backtracks | 329 | 562 | 7 |
| track clearance deficit > 5 % | 718 | 771 | 1 |
| via clearance deficit > 5 % | 565 | 725 | 2 |

Most remaining failures are *conformance*: the linear spiral does not reach into convex corners of deep annuli and
narrow tips of the outline (uncovered area), which is a property of the layout, not a defect.

## Spiral geometry (`skeletonator.py`)

**D1. Vertices on a turn boundary are emitted twice.** `do_spiral` kept an edge unless it lay wholly outside the
turn and emitted its end vertex, so a vertex exactly on a turn boundary (every turn of a regular polygon) was emitted by
two turns: the track ran A→B→A→B, with branches and a winding error of whole turns (`hexagon_a0.30_n13k1`). *Fix:*
`Skeletonator.spiral(t1, t2, d1, d2)` emits the start point, every vertex with `t1 <= angle < t2` once, and the end
point (`iter_vertex_angles`); non-finite arguments are a `ValueError`.

**D2. Vertex angles are recomputed for every turn and arm.** The angle of a vertex came from the outline's edge lengths
at the current turn's radius, so the same vertex had a different angle on each turn and arm: neighboring turns were
not one pitch apart and twisted arms drifted into each other. Upstream's "angle reference radius misalignment" fix
(167c041) interpolates the reference radius per turn, but still recomputes the angles per turn. *Fix:* the angle of
every vertex is fixed once per shape (`set_angle_reference`): each edge gets a span proportional to its *shortest*
length over the depths the spiral uses, which bounds the spiral's slope relative to every edge. Edges that collapse get
a span of 0, so that the vertices of a collapsing group share an angle and a turn runs along them at constant depth
(`_locate` resolves ties to the first vertex). Angles are quantized to 2⁻⁴⁰ revolutions so that `turn + angle` is exact
(`ellipse3to2_a0.90_n9k4`). The shortest lengths are computed from each edge's own two tracks until they meet
(`_min_edge_lengths`), linear instead of quadratic in the number of vertices (2500 vertices: 35 s → 0.3 s).

**D3. The usable depth is the depth of the *last* split event.** `min(n1.time, self.radius)` (l. 180) compares with the
full radius, not with the running minimum, so the depth limit was whichever split CGAL printed last. *Fix:* the limit
(`max_depth`, also `min_radius`) is the minimum over all split events, detected on groups of nodes joined by
constant-time edges (a neck between two reflex corners pinches off at such an edge, `neck`).

**D4. Coincident skeleton nodes taken for split events.** CGAL emits clusters of coincident nodes at degenerate events;
nodes with the same coordinates became self-loops and looked divergent, so convex rounded rectangles were rejected far
below their depth (`roundrect_a0.90_n9k4`: limit 5.35 instead of 12.5). Tracks also relied on CGAL's edge order.
*Fix:* nodes within 3e-7 × the outline's extent are merged, self-loops dropped, and tracks step to the neighbor with
strictly greater time. Tolerances scale with the extent, not the distance from the origin.

**D5. Debug file written on every call.** `compute_skeleton` wrote `/tmp/debug.txt` (fails on Windows and with
concurrent runs). *Fix:* removed.

**D6. `do_spiral`'s default end radius is a depth (latent).** *Fix:* `do_spiral` is replaced by `spiral`, which takes
depths.

**D24. Polygon vertices matched to skeleton nodes by rounded coordinates.** skeleton.wasm prints 12 significant digits,
the lookup rounded to 6 decimals: `KeyError` near rounding boundaries (3 of 1000 random 64-gons). *Fix:* nearest
contour node within a tolerance.

**D26. Clockwise polygons crash**, and the orientation test looked at one extreme vertex, fooled by a repeated start
point. *Fix:* `clean_polygon` normalizes every outline (orientation by `shapely.is_ccw`, duplicates removed, vertex 0
kept).

**D28. Turns fold onto themselves in narrow protrusions.** Where two parallel edges of a protrusion collapse inside the
annulus (the stem of a T, a finger, a keyhole's tab) the turns just above the collapse depth run into a sliver and back
(clearance deficits up to 18 × the clearance). *Fix:* `set_fold_limit` (half the pitch): turns that would run into a
sliver narrower than one pitch cut across the protrusion's mouth; nested and bent protrusions are cut at every mouth.
A fold around a notch narrower than the pitch (a slot) cannot be cut without leaving the outline; the checker reports
it (self merge).

**D31. Angle reference quadratic in the number of vertices.** See D2.

**D43. Sharp reflex cusps make every turn run into a zero-width spike.** The mitered offset of a reflex corner that
turns by φ runs 1/cos(φ/2) times as fast as the outline; at the cusp of a heart (173°, factor 16) every turn runs into
a spike far inside the shape and back, and the spike hits the bottom of the heart at 1.6 mm, the split depth, although
the inscribed radius is 11.5 mm. Upstream has the same. *Fix:* round joints at reflex corners sharper than 120°
(`ROUND_JOINT_MIN_TURN`; up to that the miter stays, as for the keepout zone): the outline is cut there by an arc of
0.01 mm (`round_reflex_joints`, shapely's difference with a polygonal disk), whose mitered offsets are arcs around the
corner. See `docs/outlines.md` for why this is done in the input polygon and why only sharp corners get it. Heart:
split depth 1.6 → 10.1 mm, no backtracks or overshoot at the cusp.

## Trace sizing and vias (`geometry.py`, `PlanarInductor`)

**D7. Trace width from a circle formula.** `spiral_pitch · cos(alpha)` with alpha computed as for a circle ignores
that on polygons neighboring turns come closest at convex corners (`square40_a0.30_n8k3`: 24–37 % of the clearance
missing at every corner). *Fix:* the arms' center lines are computed first and the smallest distance between different
turns is measured (`min_turn_spacing`: shapely STRtree and distances on pieces of at most 0.025 revolutions; pieces of
one arm less than half a revolution apart are the same turn). Trace width or clearance come from that. A request whose
measured spacing leaves no trace width is rejected with the location and the likely cause.

**D8. Arc approximation eats into the clearance.** The 0.02 mm arc tolerance is 13 % of the default clearance, and
`arc_approximate` fell through after the short-run case (missing `return`) and divided by zero for collinear points.
*Fix:* arc tolerance and polyline chord error at most clearance/80 (two neighboring turns lose at most clearance/40),
arcs fitted to 256 points per turn; explicit settings that have to be tightened are logged (`effective_render_options`;
CLI and GUI default to automatic).

**D9. Via ring overlap check crashes** (`math domain error`, 57 corpus cases) when a via is wider than the inner ring,
and only checked one ring with a circle formula. *Fix:* via positions from the shape's projection, all pairs checked
(`via_ring_spacing`).

**D10. Vias wider than the trace collide with tilted neighboring turns.** *Fix:* the via-to-track distance is measured
(`via_track_clearance`, skipping the half turn that leads into the via) and the automatic via offset grows until the
vias clear, bounded by the collapse depth (circles: the center).

**D11. NameError instead of an error when the clearance exceeds the pitch**, and negative trace widths. *Fix:* correct
names, `ValueError` when the result would be ≤ 0.

**D12. Single-layer mode reset twists after computing the angles.** Fixed upstream (89b0829) by removing the reset:
single-layer coils with several twists are laid out as such. They are valid (tests/test_layout.py,
test_single_layer_with_several_twists), but often leave more of the outline uncovered than one twist did: over the base
shapes at 60 % depth with 5/2 and 7/3 turns/twists, 38 of 66 layouts pass the 5 % coverage limit against 63 with the
reset. The corpus has no such cases.

**D13. Track length and resistance for one sector instead of one arm.** *Fix:* measured on a whole arm.

**D14. Dangling stubs at the terminal pads.** Lines to the unused outer via position were drawn. *Fix:* the pads sit at
the ends of the arms, no stubs; zero-length connections are not emitted.

**D15, D16. `twists = 0` and `turns = 0` crash** (`ZeroDivisionError`). *Fix:* checked first.

**D17. Annular widths ≤ 0, or equal to the collapse depth, accepted.** *Fix:* rejected.

**D29. Error messages when trace width and clearance are both given**: 2-decimal rounding, "reduce clearance" where the
trace width is the problem, no hint about the measured spacing. *Fix:* 3 decimals, the parameter to change, the
measured spacing and where.

**D33. Inner vias on top of each other.** Where the inner contour narrows, the automatic via offset puts the vias of
several arms on one point, shorting them (warned only). *Fix:* the offset is reduced to where the vias clear each other
and the neighboring turns (`_via_offset_for_spacing`); vias that still overlap are an `OverlappingViasError`.

**D35. Arm runs into a sharp tip and back to its via.** At the sharp tip of a sliver-shaped inner contour the via sits
back along the tip's spine and the connection ran back over the arm (backtrack). *Fix:* the arm ends where it comes
closest to its via (`_trim_arm_at_via`).

## Shapes, SVG import, CLI and export

**D18. Shape `slug`/`desc` format strings broken** (missing `f`, nonexistent `self.radius`). *Fix:* fixed.

**D19. SVG import computes a wrong bounding box** (`min_y = max(x…)`), so the recentering test was wrong. *Fix:*
shapely bounds and centroid.

**D20. Stray debug print** in `RegularPolygonShape`. *Fix:* removed.

**D21. `kicoil trapezoid` crashes** (`TrapezoidShape` not imported). *Fix:* imported.

**D22. `--format kicad-pcb` crashes** (undefined names), and gerbonara's `TrackSegment.from_footprint_line` writes
layer "False", the empty legacy footprint list does not serialize and the SMD pads were dropped. *Fix:*
`footprint_to_board` builds segments and arcs with keywords and puts the pads in a footprint of their own.

**D23. Keepout outline closes on a duplicate point.** *Fix:* see D25.

**D25. Keepout outline extrapolated from the skeleton**: self-intersecting at notches, unbounded miter spikes at sharp
tips. *Fix:* shapely's mitered buffer, miters cut at twice the margin.

**D27. Circles rendered without arcs lose clearance** (64 chords per turn). *Fix:* see D8.

**D41. SVG import reads one path dialect of the first path** (`M x y L x y … Z` only, no H/V, relative commands,
curves, shapes, transforms or units; a hidden or tiny first path is taken). *Fix:* `svg_import` parses with
svgelements (all path syntax, shapes, transforms, `<use>`, units, hidden elements and `<defs>` skipped), flattens
curves within `arc_tolerance` (0.01 mm), joins open subpaths whose ends meet (KiCad exports) and takes the largest
closed contour, with a warning about the others.

**D42. Start vertex of a reversed SVG path depends on a repeated start point.** *Fix:* see D26; SVGShape no longer
reorients the outline itself.

## GUI

**D45. Long layouts freeze the GUI.** The layout ran on the Tk main thread on every parameter change; the straight
skeleton of a complex outline takes seconds to minutes, during which the window does not respond. *Fix:* the layout
runs in a worker process (`worker.LayoutWorker`): a parameter change restarts it, *Cancel* stops it, and saving uses the
finished result.

## Checker conventions (no generator change)

**D32, D34, D37, D39, D40, D44.** Rules of the checker found while reviewing failures: copper of one turn is told apart
from neighboring turns by winding angle, not by path length (D32); a via touched by copper of its own turn that has
left it is a short, the conductor's own arrival is not (D34); merged copper of one turn bypassing 6·(w + c) or more is a
failure (`self merge`, D37); same-turn contacts are measured along the whole contact (D39); the coil's center does not
depend on rounding on symmetric holes (D40); the intended inner contour is the Euclidean (round) offset, the envelope
admits miters up to a factor of 2 (D44). See `tests/README.md`.

## Not handled by the generator

**D30, D36, D38.** Outlines with thousands of reflex vertices (noisy traced or exported curves) make the straight
skeleton slow and memory hungry (D30): simplify them before the import (`docs/outlines.md`); the GUI can cancel a long
layout, and a skeleton that runs out of memory is a `ValueError`. Merged hairpins of one turn (D36) and wraps of a wide
trace around a hole smaller than itself (D38) are reported by the checker (`self merge`, `self short`).
