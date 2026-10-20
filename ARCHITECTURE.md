# yanartas-pillowbox: architecture and geometry

> **Snapshot, not maintained.** This document describes the code as of October 2026 and
> is not kept up to date as the code changes. Where it disagrees with the code, the code
> wins. Parameter-level details are in the README.

## 1. What the app does

`yanartas-pillowbox` generates laser-cuttable SVG patterns for pillow boxes: a two-panel
body with lens-shaped end flaps folded along curved creases. The input is the box's
interior size and the material thickness. A local web UI shows the flat pattern, a folded
3D model and the body's cross-section, with dimensions, a payload volume and board
presets. The same SVG can be generated headless from the CLI.

## 2. Application architecture

All geometry lives in pure Python modules with no Flask or SVG imports. The web layer and
the browser only display what Python computes.

```
config ──► crosssection ──► geometry ──► svg ──► (download / CLI output)
  │             │              │  ├──────► scad ───────┐
  │             │              │  └──────► dimensions ─┤
  │             │              └─────────► payload ────┤
  └── persistence                                      ▼
                                                      api ──► server (Flask, /api/*)
                                                       │  └─► artifact/pb_api (Pyodide)
                                                       ▼
                                        static/js (UI components)
```

| Module | Role |
|---|---|
| `config.py` | `Config`, a frozen dataclass and the single validated input. It also holds `FieldSpec` metadata that drives the UI form, `from_dict` (the only entry point for untrusted data), cross-field validation, and the schema version (other versions are rejected). |
| `crosssection.py` | Pure math for the closed body: one panel's cross-section (`CrossSection`), the panel width solver, and `Body`, the material model around the interior (section 4.3). |
| `mesh.py` | What the mesh layouts share: the `Mesh` result, `MeshError`, the side bits, `straighten`, a nearest-point `Grid`, and the metrics: `spacing` (the space between traces along them) and `skew` (neighbouring traces as a differential pair). Needs numpy. |
| `kimesh.py` | The security mesh generator, a port of KiMesh: tiles, the randomized depth-first walk over the cells inside a mask, and joining each net's segments into one path. Needs shapely. |
| `sfc.py` | The second mesh layout: a closed space-filling curve after Bedel et al. (2022), the folding pattern's panels filled one by one and joined across the folds as seldom as possible, relaxed to an even spacing, the traces offset from it, then settled by the Rust core (`yanartas_mesh`). Needs shapely and numpy. |
| `progress.py` | How far a long layout has got: the layouts report phases and steps, the CLI and the web UI show them. |
| `pcb.py` | The flex-PCB layout (mask, both meshes, the cable's traces, fan-out, vias and plug contacts, GND zone) and its export through gerbonara (KiCad board and project, Gerber, SVG). Imported on demand: its dependencies are heavy (the in-browser build loads them on the first PCB request). |
| `fpc.py` | The FPC cable's layout at the top end of the pattern: the level cut it leaves the inner flap by, the meander, its outline and plug, the corners' flat folds, and `unfold` (where a point lies once the corners are folded). |
| `geometry.py` | The flat pattern (`build_pattern`: outline, typed folds, faces), the folding map (`FoldedBox`), the 3D mesh (`build_model3d`) and the cross-section view data. |
| `svg.py` | Serializes a `Pattern` to SVG (layers, dash styles, labels, embedded config) and reads the config back (`extract_config`). |
| `dimensions.py` | Preview-only dimension annotations for all three views, measured on the same geometry. |
| `payload.py` | Payload clearance, per-field maximize, and *Fit box to payload*. |
| `scad.py` | OpenSCAD model of the interior: the payload space and the end spaces. |
| `presets.py` | Board sizes for the payload dropdown. |
| `api.py` | The JSON API apart from its transport: request config parsing (`ApiError` carries the status and body of a refusal), `render` (SVG, model, section, info, dimensions and payload summary in one response), the payload actions and the defaults. The Flask server and the in-browser build (`artifact/pb_api.py`) both route to it. |
| `server.py` | Flask app bound to 127.0.0.1, serving the UI and `/api/*`. |
| `persistence.py`, `cli.py` | Settings file (`./yanartas-pillowbox.json`), and the `serve` / `generate` / `pcb` commands. |

**Frontend** (`static/`): plain ES modules and custom elements, with no build step.

- `app.js` builds the form from the field specs, debounces renders and saves, and wires the
  views together, including linked highlighting between fields and dimensions.
- `pb-param` is one form field.
- `pb-preview2d` shows the SVG with pan and zoom.
- `pb-preview3d` uses vendored three.js r160.
- `pb-section` draws the cross-section.
- `panzoom.js` is the 2D views' shared wheel, drag and pinch handling.
- `dims2d.js` draws 2D dimensions at a constant on-screen text size.
- `meshtex.js` draws the PCB layout's copper into a canvas: the 2D view shows it as one
  image under the lines (and the visible part again at screen resolution when zoomed in),
  the 3D view as textures, F.Cu on the outside and B.Cu on the inside (UVs from the faces'
  flat coordinates). The ~100k trace segments are never DOM or scene objects.

The browser never computes geometry: an edit posts the config, and the views redraw from
the response.

**Caching:** `solve_body` is `lru_cache`d on their (hashable) inputs.
One render touches the same body many times, so this keeps a render under about 100 ms.

## 3. Test suite architecture

`pytest` with about 560 tests, run in parallel with pytest-xdist (a couple of minutes), plus
`ruff` for linting. The tests use the same defaults as the UI: a box fitting the Raspberry
Pi Model B + HAT preset in 0.2 mm material, with the FPC cable on. Tests about other parts
of the geometry switch the cable off where it does not fit or would get in the way.
`tests/helpers.py` parses SVG paths back into `Line`/`Arc` segments and has
polygon utilities: exact loop area, self-intersection, point in polygon.

The tests deliberately check properties against independent computations, not snapshot
outputs.

| File | What it pins down |
|---|---|
| `test_config.py` | Validation messages, limits, the width solve (interior corner to corner), interior height and flap offsets. |
| `test_geometry.py` | Outline continuity and absence of self-intersections, fold placement, fold directions from both sides, thickness offsets, FPC cutouts, the end wall gap. |
| `test_model3d.py` | That the 3D model *is* the pattern folded: faces tile the pattern, each mesh triangle is isometric to its flat triangle, faces stay attached along every fold, no hidden creases inside a face, flap edges meet the intended surfaces, the glue tab lies at distance `t`, and the section matches the mesh. |
| `test_svg.py` | SVG conventions (layers, dashes, a single closed cut path, attributes only), round-trip of the embedded config, parsed paths reproducing the geometry, labels. |
| `test_dimensions.py` | Every dimension measures its parameter and its points lie on, or a stated allowance off, the exported geometry. |
| `test_fpc.py` | The FPC cable: one simple outline, a folded straight strip of the set length, corner creases that lay each run back along the one before and end on the cut, the level cut it leaves the flap by, its clearances, the sharp plug and the rounded other corners, mirroring to the back end, the default fitting the pattern, and validation. |
| `test_payload.py` | Clearance against a brute-force distance to a fine mesh, tightness of maximize, and *Fit box* against a brute-force grid search. |
| `test_scad.py` | The OpenSCAD spaces against the interior and the end walls. |
| `test_mesh.py` | The shared metrics: spacing of parallel traces and across islands (not past the edge), skew of detours. |
| `test_sfc.py` | The space-filling-curve layout on small areas: ends at the exit at the pitch, traces simple, in the area and apart, each zone border crossed twice, spacing rarely below the nominal and few islands (settled), repeatable seeds, holes. |
| `test_kimesh.py` | The KiMesh generator: each net one path whose ends leave the exit side at the pitch, every cell reached and inside the mask, nets apart, tiles opening on their key's sides, repeatable seeds. |
| `test_pcb.py` | The PCB layout: the pinout, both meshes, contacts carrying it, every mesh net one chain from contact to contact, a DRC of the copper, edge and fold clearances, multi-row cables, errors, the exports (re-read with gerbonara), the CLI and the API routes; the electrical check (`verify`, also against an open and a short put in) and the fail-safe, the metrics, the curve layout's wiring. A full-size curve layout is marked `slow` (left out by default: `pytest -m slow`). |
| `test_server.py`, `test_cli.py` | API contracts, settings fallback, CLI flags. |
| `test_artifact_api.py` | The in-browser API answers every route like the Flask server; the PCB files' zip travels base64-encoded. |

Configs are parametrized across representative shapes (default, steepest arc, shallow,
thick material, very large, zero thickness), so invariants are tested away from the
defaults too.

## 4. Box geometry

### 4.1 Flat pattern

Flat coordinates are in mm, with x to the right and y down, as in SVG. From left to right:

- **Front panel**, width `Wf`. It carries the **outer** flaps.
- **Back panel**, width `Wb`. It carries the **inner** flaps.
- **Glue tab**, width `g`.

The straight edges run from `y = 0` to `y = L`, where `L = length + height + 3t` (the front
panel's are longer by the end wall gap, see 4.4). Each end
of a panel has a **flap** between two curves through the panel's corners:

- the **curved fold**, a circular arc bowing *into* the panel by its sagitta `s`;
- the **cut edge**, bowing *out* of the panel.

The pattern's top end is the box's "front end", and the bottom end its "back end".

### 4.2 Closed box: the folding model

The model folds the material's **mid-surface** isometrically. Every 3D face is an exact
image of its flat face, and this is what `test_model3d` verifies.

- **Panels.** Each panel bends into a cylinder whose rulings run along the length. If the
  fold arc sits at distance `f(u)` from its chord at chord position `u`, the panel's
  cross-section, parametrized by arc length `u`, is given height `Z(u) = f(u)`, so
  `X'(u) = sqrt(1 − f'(u)²)`. With this choice every curved crease `(X(u), f(u), f(u))`
  lies in a **plane at 45°**.
- **Flaps.** Folding a flat sheet along a *planar* crease mirrors the material beyond it
  across that plane. Each flap therefore becomes a cylindrical **end wall** with vertical
  rulings, whose plan view is the curve `Y = f(X)` (`FoldedBox.map` is exactly this
  reflection).
- **Consequence.** The ends are concave in plan view, and no midline crease is needed on
  the flaps. This requires `|f'| ≤ 1` (the arc turns at most 45° at the corners); the
  config allows `s ≤ 0.2·W`.

**Cross-section solve.** With `u − W/2 = R sin ψ`, the closed width is `2R·E(ψmax)` where
`E(ψ) = ∫ sqrt(cos 2t) dt`, evaluated with Gauss–Legendre quadrature. The shape depends
only on `r = s/W`, so the panel width for a given closed width and sagitta is a 1D
bisection on `c(r)/r` (`crosssection.panel_width`). `CrossSection.x(u)` uses a Simpson
table for fast repeated evaluation.

### 4.3 Material thickness (`crosssection.Body`)

Inputs are **interior** dimensions, and the mid-surface lies `t/2` outside the interior.

- **Stacked end walls.** A flap's wall stands at its own panel's crease. For the outer
  flap to lie *outside* the inner one, the front fold bows in by `height/2` and the back
  fold by `height/2 + t`. The front panel therefore comes out about `t` flatter: this
  follows from the stacking, it is not a modelling choice. With the model centred on the
  interior (`z_shift = t/2`), the panels' inner surfaces sit at `±height/2`.
- **Flap reach.** Outer flaps reach the back panel's **outer** surface (flush with the
  body); inner flaps stop at the front panel's **inner** surface.
- **Cut edges.** Cut edges are not arcs. `Body.front_cuts` and `Body.back_cuts` sample the
  target surface. `surface_z(panel, offset, X)` finds the panel point at that `X` on the
  surface offset along the normal, by bisection on `u` with tangent extension beyond the
  panel ends. Inner cuts are clipped at the chord, with the exact chord-leaving point
  inserted. The pattern uses these samples as fine polylines when `t > 0`, and as exact
  arcs at `t = 0`.
- **Glue tab.** The tab lies on the **outside** of the front panel. The back panel's glue
  fold sits `t / sin α` beyond the front panel's free edge, where α is the panel's angle
  there. The tab leaves along the tangent for `t·cot α`, then follows the front profile
  offset by `t`. It is parametrized by the offset curve's true arc length,
  `s = u + t·(α − asin f'(u))`, solved by Newton iteration, which keeps it isometric.
- **Width solve.** The interior width runs between the **mitred inner corners**: the
  intersections of the panels' inner-surface tangent lines at each side fold.
  `solve_body` finds the front panel's closed width by fixed-point iteration (the
  derivative is about 1), then centres the interior on `X = 0`.

### 4.4 End wall gap

Each end has an outer wall (front flap) and an inner wall (back flap), each standing at its
own panel's crease. To spread them apart (`)_)___(_(` instead of `))___((`), the front panel
is `2e` longer than the back panel (`e = end_wall_gap`): in flat coordinates the front panel
spans `0..Lf` and the back panel and glue tab `e..e + L`, with `Lf = L + 2e`
(`cfg.front_length`, `cfg.edge_length`). `FoldedBox.map` shifts the back flaps' crease
planes by `e` accordingly; everything stays an exact isometric folding.

- **Cut.** The front panel's edge at the straight fold is cut over `0..e` and
  `L + e..Lf`, continuing the outer flaps' cut step down to the back panel's corners.
- **Gap.** On the centreline the walls' mid-surfaces are `e + t` apart, a clear gap of `e`.
  Towards the sides the outer wall curves away a little more.
- **Lid.** The back panel ends at the inner wall, so each outer flap carries a lid over the
  gap (`geometry.lid_layout`). Its fold lies in the plane `y_int + (Z - zs) = level` (45°),
  so it is the front fold arc mirrored (`y = level - f(x)`), and the lid lies on the
  cylinder `Z = zs + level - f(x)`, ruled along the box: the front profile turned over.
  At rest, `level` is the highest that keeps the lid's mid-surface at least `t` outside the
  back panel's everywhere; `lid_offset` lowers it further, so the lid floats that far off
  the back panel where closest. Its free edge runs `e - t/2 + lid_overlap` beyond the back
  panel's crease, in folded depth.
- **Widened ends.** The two folds meet where `f(x) = level / 2`: over the gap, the front
  panel's fold arc and cross-section run on past both edges (`CrossSection.x_ext/z_ext`,
  the arc continued, valid below 45°) by `spread` on each side. In the pattern these are
  the front panel's wings, with their own curved folds continuing the panel's. At the
  straight fold the wing's end is the inner flap's cut edge itself: that stretch is a slit
  (`Pattern.slits`, a cut with material on both sides), written as its own open path. The outer
  flap is a lens between the continued front fold and the lid's fold. `max_lid_offset`
  limits the offset so the continued arc turns at most `MAX_SPREAD_SLOPE`.
- **Lid glue tabs.** Each lid's straight sides (at `x = -spread` and `Wf + spread`, from
  the crease's ends to the free edge) are glue folds carrying square tabs `g` wide
  (`lid-tab-{end}-{side}` faces, kind `tab`). Over the inner flap, `_lid_tab_right` butts
  the tab up against the flap's cut edge where that rises above the crease's end; the
  piece that leaves beside the wing is cut out (`Pattern.scraps`, a closed loop of slits).
  In 3D a tab is a flat panel on the wing's tangent plane at the lid's side.
- **Glue tab taper.** `glue_tab_taper` cuts the body's glue tab back only as far as keeps
  it, glued from the back panel's end on, off the front panel's fold arc: square where the
  gap leaves room, at most 45°.
- **Views.** The 3D and section views show the model turned half a turn about its length,
  back panel (lids) up; the model frame itself keeps the front panel at +Z.
- **Interior.** The interior, payload clearance and fit are unchanged: they are bounded by
  the inner walls, centred on the box.

### 4.5 FPC cutout

`level_cut` finds, by bisection on the level, the horizontal cut that removes exactly
`width` from the top of a rising-then-falling edge. It sits around the edge's highest
point, which is slightly off-centre because the edge is not symmetric. The cut flattens the
inner flap's free edge.

### 4.6 PCB layout

- **Mask.** The foil (`Polygon` of the outline, arcs within 5 µm, less the slits as 0.1 mm
  slots and the scraps) shrunk by the edge clearance, less the cable: the outline segments
  no face owns, closed and cut off level at the junction, plus a band beyond the junction
  so that the mask's edge there is the junction line itself. The F.Cu exit cell sits against
  it; the B.Cu mesh's grid is offset by half a cell in x and y (its exit cell half a cell in,
  on the column of its grid nearest its pins), so the two layers' bare edge strips differ.
- **Mesh.** `kimesh.generate` aligns the grid on the exit cell. Cells inside the mask are
  found in one vectorized `shapely.contains`; the walk is KiMesh's (iterative, with its
  "keep going straight" bias for `randomness < 1`); tiles are KiMesh's look-up table with
  its rotations done on tuples. Each net's segments are chained end to end into one path
  (two loose ends, at the exit side) and collinear points dropped.
- **Cable traces** are the cable's centreline offset sideways (mitred at the square
  corners, as `fpc.outline`), so they stay parallel round every turn. `fan` jogs each
  layer's traces from the mesh's pitch to the pins' places at 45°, delaying jogs until
  neighbours keep their pitch. The back layer's vias alternate between two rows.
- **Space-filling curve** (`sfc.generate`). Steps, and where they differ from the
  reference code (github.com/mfx-inria/controllable-space-filling-curve):
  1. *Segments:* the area cut into the zones' (panels') pieces, each shrunk by half a
     spacing (its *domain*).
  2. *Graph:* seeds on a jittered triangular grid, Lloyd iterations to a centroidal Voronoi
     tessellation (shapely), cells clipped to the domain, holes split off. The reference
     builds a Voronoi diagram of short segments ("needles") along a direction field and
     optimizes it with L-BFGS, so that cell edges, and so the curve, can follow the field;
     with no field set, points suffice. (A boundary-alignment field is a possible extension.)
  3. *2-factor:* Edmonds' blossom algorithm (degree-two chains contracted) for a perfect
     matching; the edges left out cover every vertex with cycles.
  4. *Refinement:* a vertex at each cell's centre, joined to the corners it sees, threaded
     into one cycle edge of its cell (a bipartite matching here, "steal and freeze" there);
     cycles joined by split-and-reconnect, then doubled edges (checked not to cross).
  5. *Zoning:* the reference counts zone-border crossings in a stochastic optimizer (flip,
     transpose, cross, zigzag moves). Here each zone's cycle is complete first and the
     zones are joined along a spanning tree (longest borders first), one
     split-and-reconnect across each border, the joins checked against the curve: two
     crossings per join, the minimum. No orientation objective, so the optimizer is not
     ported.
  6. *Exit:* a seed pinned in the mouth keeps cell walls off it; the stretch of the domain's
     edge between the tongue's two ends becomes a fixed edge of the graph, standing for the
     tongue (two legs, a spacing apart, straight through the exit cell), so the cycle takes
     it and leaves the mouth outward.
  7. *Geometry:* the reference minimizes the segment-CVT energy plus a Laplacian and a
     length term with L-BFGS. Here: per-zone discrete CVT steps (each vertex to the
     centroid of the sample points nearest it in its zone), Taubin smoothing, bends tighter
     than the traces can follow smoothed, a length controller (shrink or inflate) towards
     area / spacing. The reference's curve is a zero-width line (a printed bead fills small
     voids); here each run carries a ribbon of all the traces, so a run spaced wider than
     the ribbon leaves an island of up to a ribbon's width. So, unlike the reference, the
     seeds are denser (the cycle comes out sparse), and two passes follow at a finer step:
     growth (as by differential growth: runs nearer than a little over the ribbon's width
     repel each other, bends bulge into the room left, pushes smoothed over a ribbon's
     width; each step only where the step before pushed, until the length stalls), then a
     repair pass pushing apart runs nearer than the least spacing (+4 %) and runs nearer
     than half that to the area's edge or a fold (but at the joins). Tight bends are
     rounded with Taubin's smoothing about them (a Laplacian step pulls a U-turn's tip
     back, shortening the curve and opening an island in front of it), the Laplacian only
     for those still too tight after ten steps (U-turns sit right at the limit: half the
     ribbon). The vertices are kept and only split or merged locally (resampling every
     step shrinks a curve). Every step is undone where it would make the curve cross
     itself.
  8. *Traces:* offsets of the curve (made smooth and fine by a Catmull-Rom spline), at a
     pitch per side of the measured distance to the next run (or twice that to the edge)
     over the number of traces, smoothed along the curve (a running minimum, then a running
     mean over ±10 vertices), capped inside bends, never below the trace pitch (+2 %;
     exactly the pitch on the tongue's legs). Spreading skews: two neighbouring traces on
     one side differ in length by the pitch times the curve's turning, so a wider pitch in
     a bend adds to or takes from their skew with the bend's sense, and over hundreds of
     U-turns it adds up (to 16–19 mm on the default box). So, walking the curve from the
     exit, the traces spread on the straight wherever there is room but in a bend only
     where that pays back the skew run up so far (eased in and out over a few vertices).
     Loops and backward runs an offset makes inside a tight bend are cut out; the traces are
     cut where the tongue leaves through the exit.
  9. *Settling* (`_settle`, not in the reference): the traces, offsets of one curve, leave
     every gap between two runs as wide as the runs are apart, and the holes where runs
     meet. So each trace is then moved on its own, by steps (`SETTLE`), towards the middle
     between the nearest copper on either side of it (nothing within three pitches: a hole,
     moved into; the area's edge and the zones' borders standing for copper at twice their
     distance; where the traces cross a border, at the curve's joins, they stay as laid). Smoothness
     counts for little: a trace may kink into a hole's corner (only jitter is smoothed, by
     a Taubin step); but in a bend tighter than 1.5 pitches nothing moves along its axis
     into it, so a U-turn's innermost trace keeps its tip and closes up its legs. A U-turn's
     tip (bends about as tight as a ribbon's) goes on out along its axis instead of to
     the middle of the room before it, up to a pitch from the copper ahead: the outermost
     trace first, the ones inside after it, so the U grows longer into a gap rather than
     its traces spreading apart (each trace gains about as much: little skew). Filling
     holes lengthens the outermost traces (only they face holes), so length is steered:
     by each trace's length run from the exit at its place along the curve (a place kept
     per vertex as laid, against the traces' lengths as laid), a trace behind a neighbour
     has its bends about a pitch across grown into what room there is (fingers,
     squiggles), one ahead has the bumps it pushes towards that neighbour straightened,
     giving the room up to it (well ahead, its fingers into holes too: skew before
     coverage). It is steered only where the lead is still being built up (over about 15
     mm of curve it gains on the neighbour the way it leads): steered all along after a
     lead, a long trace took it back many times over and swung. Over a whole board that
     still leaves 10-25 mm, so the settled traces are then matched: walking along the
     curve, wherever a trace runs more than 15 pitches ahead of the shortest, that much is
     marked to come out of it there, and a few steps straighten its bends there (its
     squiggles and fingers) by that much (`_match`; the band above how far leads swing to
     and fro through the bends, or every swing is cut). Only ever shortening, it costs
     little coverage (on the default box: skew 21 → 10 mm at most, length and islands as
     before). With more traces the holes where a ribbon's bends meet grow (the ribbon
     is as wide as its traces), past what centring fills: there a hole fills only as a
     wave, the trace facing it first and each one behind it a step later. So every vertex
     is also moved down the slope of the traces' density (`density.rs`: their length per
     area times the pitch, on a grid, blurred over half a pitch per trace, over the area
     blurred alike so its edge is no hole; `SETTLE_FILL`): every trace near a hole sees
     its slope at once and the ribbon moves into it as a whole, each trace gaining about
     as much. The steps and the U-turn tips' lean also grow with the traces past four
     (`SCALE`). On a 75 × 90 mm crop, 8 traces: the density's spread 4.4 → 1.3 % (as
     4 traces), the area under 70 % of nominal 0.55 → 0.01 %, skew ≤ 13.6 → 4.4 mm; 12
     traces: thin area 5.4 → 0.3 %. All moves die down over the steps
     (annealing), or the layout churns and the steering chases its tail. Every move keeps
     a pitch (+1 %) from other copper, measured to segments, and from the trace itself
     where it faces itself across (or is much further along it than away: a finger's
     pinched legs); none crosses. Only vertices near ones that moved are
     looked at again. Neighbours come from GEOS STRtrees (shapely; in the browser too, from
     Pyodide's build): one of the vertices per step for the centring, one of the segments
     per step for the clearance (distances to segments exactly; a vertex taken back is
     looked for as far again as it moved).
  The default box takes about 2 min per layer to lay, and about 20 min more to settle
  (see Later).
- **Check** (`verify`, run at the end of every `layout`): the tracks' points joined along
  each track and through the vias (union-find on µm-rounded points): every mesh net one
  piece, ending on exactly its two contact pads; per layer, every pair of copper pieces of
  different nets (track segments, vias, pads; shapely `STRtree` `dwithin`) at least their
  half widths apart. The tests add a DRC of their own (different nets at least the trace
  space apart), all copper on the foil, vias off the cable's folds.
- **Metrics.** `mesh.spacing` (from `mesh.gaps`, the per-sample profile): each trace
  sampled every pitch; on either side the nearest copper within 1.5 pitches in a cone
  about the normal (not the same trace within 2.5 pitches along it), refined to the exact
  distance to its segments, and near the nominal space or below to the trace's own
  segments (the chords between samples cut a bend's corner by up to 0.025 mm); where
  nothing is that near, the first copper straight across, out to three times as many
  pitches as there are traces (further: the area's edge, not counted), so islands count.
  Lengths below the nominal space, below it by 5 %, within −5 %…+20 %, above, above twice
  it, and the least and largest space. `mesh.skew`: one trace sampled every 0.5 mm, each
  sample matched to the nearest point of its neighbour a little ahead of the last match
  (monotone); the largest difference of the lengths run to the matched points, and the
  difference of the totals.
- **Rust.** The curve layout runs in Rust (`rust/`, see its README; AGPL-3.0-or-later):
  the graph (step 2 to 5: Lloyd's Voronoi cells as boxes cut by the bisectors with the
  seeds near, clipped by the domain with `geo`'s boolean operations only where its edge is
  near; Edmonds' matching; centres, threaded only into a cycle edge they face, between its
  ends, or the detour folds back; merges, doubled edges, joins), the relaxation and growth
  (6, 7), the lanes, settling and length matching (9). Natively the PyO3 extension
  `yanartas_mesh` (a dependency, built from `rust/python`; on all cores), in the browser
  its WebAssembly build, which the web worker loads (`artifact/build.py` builds it, with
  SIMD). `sfc.py` keeps what needs shapely on whole regions (the regions, the segments'
  domains, the borders between regions, the edge's points, the exit's cut) and the
  constants, passed in by name. The default box lays out in about 2 min a side natively,
  nearly all of it settling.
- **Both sides at once.** The front and back meshes are independent: `pcb.layout` works
  out both exit corners first, then lays both out together (`progress.side_by_side`:
  threads, as the heavy parts release the GIL; each with its own copy of the mask, since
  shapely crashes when two threads prepare one geometry; one after the other in the
  browser), their progress merged (the share done: their mean).
- **Progress** (`progress.py`): the layouts report their phases and steps (graph, relax,
  lanes, settle, match; the stage: the mesh's layer) with figures (vertices, moved,
  clearances measured, the traces' length differences) and the whole layout's share done.
  The CLI shows a bar redrawn in place on a terminal (each phase's last figures kept above
  it), otherwise a status line per step. The web UI polls `GET /api/progress` while a PCB
  layout runs (the latest event: the server keeps it; in the browser build the worker posts
  each to the page, and `pyshim.js` answers the poll) and shows a bar and the phase in the
  header. The lengths' differences are shown only once matching: settling's swing wide.
- **Later.** The rest of the curve layout in Rust; an alignment field (the reference's
  needles) to lay the curve along the edges; a hard skew limit in settling
  (dropped: it cost coverage; steering and matching keep the skew within 10 mm instead):
  reconsider it; a
  switch to draw the traces as circular arcs (now
  polylines, simplified within 2 µm).
- **Export.** One gerbonara KiCad `Board` is the source of all files; gerbonara's own board
  renderer fails on footprints, so `render_stack` draws the tracks, vias, graphics and
  footprint into the layer stack itself.

## 5. Other algorithms

- **Fold direction.** Classified numerically on the folded model: at a fold's midpoint,
  does the face on one side bend away from the other face's print-side normal (mountain)
  or towards it (valley)? `print_side = inside` flips the normal.
- **Payload clearance.** This is the true 3D distance to the material's inner surface. For
  a payload inside the box, the distance to the surface equals the minimum distance to the
  *unbounded* cylinders: panels with rulings along Y, end walls with rulings along Z. A
  nearest point that is off the real surface lies outside the box. Each distance is
  therefore 2D, from a centred rectangle to a curve, minus `t/2`. It is computed by
  dense sampling plus golden-section refinement. The end walls use the back panel's crease
  curve (the inner walls).
- **Fit box to payload.** The search runs on a fast approximation: the interior is treated
  as a zero-thickness box of the interior size, so the shape is scale-invariant in
  `r = s/W`, and a closed-form "scale needed" is computed per profile sample. A 1D grid
  plus golden-section search over `r` minimizes an approximate pattern area. The height is
  then rounded and the width solved *exactly* by bisection with the real clearance. If the
  end walls still need room, the length grows in one exact step: the end-wall clearance
  grows by half the length change. The area is flat near its optimum, so the
  approximation costs next to nothing; tests compare against a brute-force search.
- **Dimensions.** They are computed in Python with measured points on the real geometry,
  or at a documented allowance off it for interior measures. They are drawn as overlays at
  the UI's text size and never exported.
- **SVG.** The output has one closed cut path (plus the slits, open). Folds are grouped into
  mountain and valley layers, every line is black at 0.1 mm, and labels go in their own
  layer. The full config is embedded as JSON in `<metadata>` for re-import.
