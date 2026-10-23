# yanartas-pillowbox: architecture and geometry

> **Snapshot, not maintained.** This document describes the code as of October 2026 and
> is not kept up to date as the code changes. Where it disagrees with the code, the code
> wins. Parameter-level details are in the README.

## 1. What the app does

`yanartas-pillowbox` generates laser-cuttable SVG patterns for pillow boxes: a two-panel
shell with lens-shaped end flaps folded along curved creases. The input is the box's
interior size and the material thickness. A local web UI shows the flat pattern, a folded
3D model and the shell's cross-section, with dimensions, a payload volume and board
presets. The same SVG can be generated from the command line.

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
| `crosssection.py` | Pure math for the closed shell: one panel's cross-section (`CrossSection`), the panel width solver, and `Shell`, the material model around the interior (section 4.3). |
| `mesh.py` | What the mesh layouts share: the `Mesh` result, `MeshError`, the side bits, `straighten`, a nearest-point `Grid`, and the metrics: `spacing` (the space between traces along them), `density`, `holes` (what is farther from copper than it should be) and `skew` (neighbouring traces as a differential pair). Needs numpy. |
| `kimesh.py` | The security mesh generator, a port of KiMesh: tiles, the randomized depth-first walk over the cells inside a mask, and joining each net's segments into one path. Needs shapely. |
| `sfc.py` | The second mesh layout: a closed space-filling curve after Bedel et al. (2022), the folding pattern's panels filled one by one and joined across the folds as seldom as possible, relaxed to an even spacing, the traces offset from it, then settled by the Rust core (`yanartas_mesh`). Needs shapely and numpy. |
| `rand.py` | The layouts' randomness, deterministic from the seed and cryptographically secure: the seed text distilled into a 256-bit key (SHAKE-256), each consumer a key of its own derived under a label (`layer/<name>`, `kimesh`, `partition`, `sfc`, `sfc/relax`, `sfc/graph/<n>`: domain separation, no two draw on one stream), `Rand` a SHAKE-256 stream in counter mode (uniform floats, unbiased integers, shuffles; its state checkpointable). The Rust core draws from ChaCha20 (`graph::Rng`, RFC 8439's block function) under a key derived here. |
| `progress.py` | How far a long layout has got: the layouts report phases and steps, the CLI and the web UI show them. |
| `checkpoint.py` | The layout's steps timed, and (with `YANARTAS_CHECKPOINT` set) their inputs and results written as gzipped JSON, any one step then run again alone (`resume`). |
| `pcb.py` | The flex-PCB layout (mask, both meshes, the cable's traces, fan-out, vias and plug contacts, GND zone) and its export through gerbonara (KiCad board and project, Gerber, SVG). Imported on demand: its dependencies are heavy (the in-browser build loads them on the first PCB request). |
| `plug.py` | The cable's plug end, shared by `fpc` and `pcb`: the pinout, the vias' rows behind the contacts and the traces' fan-out (`plug_end`), how far back the cable stays as wide as the plug. |
| `fpc.py` | The FPC cable's layout: it leaves the front panel's free edge (x = 0) where set (`entry_range`: by default as near the end it turns away from as the inner flap allows), as wide as the meshes' exits need (`junction_width`), and turns up or down along it; the meander (laid out in a frame of its own, turned into the pattern's), its outline and plug, the corners' flat folds, and `unfold` (where a point lies once the corners are folded). |
| `geometry.py` | The flat pattern (`build_pattern`: outline, typed folds, faces), the folding map (`FoldedBox`), the 3D mesh (`build_model3d`) and the cross-section view data. |
| `svg.py` | Serializes a `Pattern` to SVG (layers, dash styles, labels, embedded config) and reads the config back (`extract_config`). |
| `dimensions.py` | Preview-only dimension annotations for all three views, measured on the same geometry. |
| `payload.py` | Payload clearance, per-field maximize, and *Fit box to payload*. |
| `scad.py` | OpenSCAD model of the interior: the payload space and the end spaces. |
| `presets.py` | Board sizes for the payload dropdown. |
| `api.py` | The JSON API apart from its transport: request config parsing (`ApiError` carries the status and reply of a refusal), `render` (SVG, model, section, info, dimensions and payload summary in one response), the payload actions and the defaults. The Flask server and the in-browser build (`artifact/pb_api.py`) both route to it. |
| `server.py` | Flask app bound to 127.0.0.1, serving the UI and `/api/*`. |
| `persistence.py`, `cli.py` | Settings file (`./yanartas-pillowbox.json`), and the `serve` / `generate` / `pcb` commands. |

**Frontend** (`static/`): plain ES modules and custom elements, with no build step.

- `app.js` builds the form from the field specs (collapsible groups, the payload's first),
  debounces renders and saves, and wires the views together, including linked highlighting
  between fields and dimensions. It runs the mesh's layout on *Generate mesh* (polling its
  progress into a bar and a log; *Cancel* posts `/api/pcb/cancel`, which in the browser
  build restarts the worker), keeps the result with the config it was made for (a different
  design: out of date, the views' note says none is generated), and opens a dialog when a
  layout fails.
- `panels.js`: the dividers (the stats panel's sized in px from the right), maximizing a
  view within the previews' area (the settings stay), and the settings' collapse.
- `scalebar.js`: the 2D views' scale bars (a round length in mm, kept about 110 px long).
- `pb-param` is one form field.
- `pb-preview2d` shows the SVG with pan and zoom.
- `pb-preview3d` uses vendored three.js r160.
- `pb-section` draws the cross-section.
- `panzoom.js` is the 2D views' shared wheel, drag and pinch input.
- `dims2d.js` draws 2D dimensions at a constant on-screen text size.
- `meshtex.js` draws the PCB layout's copper into a canvas: the 2D view shows it as one
  image under the lines (and the visible part again at screen resolution when zoomed in),
  the 3D view as textures, F.Cu on the outside and B.Cu on the inside (UVs from the faces'
  flat coordinates). The ~100k trace segments are never DOM or scene objects.

The browser never computes geometry: an edit posts the config, and the views redraw from
the response.

**Caching:** `solve_shell` is `lru_cache`d on their (hashable) inputs.
One render touches the same shell many times, so this keeps a render under about 100 ms.

## 3. Test suite architecture

`pytest` with about 730 tests, run in parallel with pytest-xdist (a couple of minutes), plus
`ruff` for linting. The tests use the same defaults as the UI: a box fitting the Raspberry
Pi Model B + HAT preset in 0.2 mm material, with the FPC cable on. Tests about other parts
of the geometry switch the cable off where it does not fit or would get in the way.
`tests/helpers.py` parses SVG paths back into `Line`/`Arc` segments and has
polygon utilities: exact loop area, self-intersection, point in polygon. `tests/conftest.py`
has `even`, the check every small mesh layout must pass: its copper's density near the
nominal everywhere (`mesh.density`: mean 85–95 %, spread under 3 %, no dip under 70 %),
no hole (`mesh.holes`: under 1 % of the area farther than two thirds of a pitch from a
trace, no spot over 0.15 mm²) and the space between traces mostly within −5 / +20 % of
the nominal, never much less (`mesh.spacing`).

The tests deliberately check properties against independent computations, not snapshot
outputs.

| File | What it pins down |
|---|---|
| `test_config.py` | Validation messages, limits, the width solve (interior corner to corner), interior height and flap offsets. |
| `test_geometry.py` | Outline continuity and absence of self-intersections, fold placement, fold directions from both sides, thickness offsets, FPC cutouts, the end wall gap. |
| `test_model3d.py` | That the 3D model *is* the pattern folded: faces tile the pattern, each mesh triangle is isometric to its flat triangle, faces stay attached along every fold, no hidden creases inside a face, flap edges meet the intended surfaces, the glue tab lies at distance `t` on the outside of the front panel, and the section matches the mesh. |
| `test_svg.py` | SVG conventions (layers, dashes, a single closed cut path, attributes only), round-trip of the embedded config, parsed paths reproducing the geometry, labels. |
| `test_dimensions.py` | Every dimension measures its parameter and its points lie on, or a stated allowance off, the exported geometry. |
| `test_fpc.py` | The FPC cable: one simple outline, a folded straight strip of the set length, corner creases that lay each run back along the one before and end on the cut, where it leaves the front panel's free edge, its clearances, the sharp plug and the rounded other corners, turning down mirroring turning up, the pattern growing only beside the edge, the folded route (on the back panel, the layer over it, onto the front panel; isometric, inside the box), the cross-section, the default pins, and validation. |
| `test_payload.py` | Clearance against a brute-force distance to a fine mesh, tightness of maximize, and *Fit box* against a brute-force grid search. |
| `test_scad.py` | The OpenSCAD spaces against the interior and the end walls. |
| `test_mesh.py` | The shared metrics: spacing of parallel traces and across islands (not past the edge), skew of detours, holes (none between traces at the pitch, one where a trace is missing), the pairs matched. |
| `test_sfc.py` | The space-filling-curve layout on small areas: ends at the exit at the pitch, traces simple, in the area and apart, each zone border crossed twice, spacing rarely below the nominal and few islands (settled), density, coverage and uniformity (`even`), repeatable seeds; a pocket off a lane filled by the pair beside it (both its traces, `even` there too), and left bare without filling holes (the checks see it). |
| `test_kimesh.py` | The KiMesh generator: each net one path whose ends leave the exit side at the pitch, every cell reached and inside the mask, nets apart, tiles opening on their key's sides, repeatable seeds. |
| `test_rand.py` | The keyed streams: the same seed the same stream, another another; text and a number apart; each label's key distinct (lengths framed); draws in range and unbiased; a checkpoint keeps a stream's place. |
| `test_partition.py` | Partitions of a mesh's area: of equal area, together the whole of it, disjoint, each of a piece and holding its port and its strip (a port wide, no two neighbours as long); cells never across a fold, pinned seeds kept; the seed repeats the split, another differs; necks found (where the area itself is wide) and widened, no partition torn further; the mesh over partitions laid out at once (each partition's traces out through its port at the pitch, in it, apart, matched in length, `even`). |
| `test_pcb.py` | The PCB layout: the pinout, both meshes, their exit cells at the junction, contacts carrying it, every mesh net one chain from contact to contact, a DRC of the copper, edge and fold clearances, multi-row cables, errors, the exports (re-read with gerbonara), the CLI and the API routes; the electrical check (`verify`, also against an open and a short put in) and the fail-safe, the metrics, the curve layout's wiring (a layer's partitions, of equal area, laid out at once, their traces the layer's; a layer whose curves leave a region out tried again with its seed salted, strict but the last). A full-size curve layout is marked `slow` (left out by default: `pytest -m slow`). |
| `test_two_piece.py` | Two identical pieces: the shell (the second panel the first turned, the interior as asked), the config's lengths, one closed outline without crossings, folds on it and off it, the faces a piece has, every fold a mountain fold, the walls a gap and a thickness apart at both ends, each glue tab a thickness outside the other piece, both pieces (and cables) in the model and the section, the cable clear of both inner flaps, the dimensions, payload, OpenSCAD and labels, a KiMesh layout over a piece; strips ordered to keep their ends off a fold. |
| `test_server.py`, `test_cli.py` | API contracts, settings fallback, CLI flags. |
| `test_artifact_api.py` | The in-browser API answers every route like the Flask server; the PCB files' zip travels base64-encoded; the build ships every package module a shipped one imports. |

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

### 4.3 Material thickness (`crosssection.Shell`)

Inputs are **interior** dimensions, and the mid-surface lies `t/2` outside the interior.

- **Stacked end walls.** A flap's wall stands at its own panel's crease. For the outer
  flap to lie *outside* the inner one, the front fold bows in by `height/2` and the back
  fold by `height/2 + t`. The front panel therefore comes out about `t` flatter: this
  follows from the stacking, it is not a modelling choice. With the model centred on the
  interior (`z_shift = t/2`), the panels' inner surfaces sit at `±height/2`.
- **Flap reach.** Outer flaps reach the back panel's **outer** surface (flush with the
  shell); inner flaps stop at the front panel's **inner** surface.
- **Cut edges.** Cut edges are not arcs. `Shell.front_cuts` and `Shell.back_cuts` sample the
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
  `solve_shell` finds the front panel's closed width by fixed-point iteration (the
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
  the front panel's overhangs, with their own curved folds continuing the panel's. At the
  straight fold the overhang's end is the inner flap's cut edge itself: that stretch is a slit
  (`Pattern.slits`, a cut with material on both sides), written as its own open path. The outer
  flap is a lens between the continued front fold and the lid's fold. `max_lid_offset`
  limits the offset so the continued arc turns at most `MAX_SPREAD_SLOPE`.
- **Lid glue tabs.** Each lid's straight sides (at `x = -spread` and `Wf + spread`, from
  the crease's ends to the free edge) are glue folds carrying square tabs `g` wide
  (`lid-tab-{end}-{side}` faces, kind `tab`). Over the inner flap, `_lid_tab_right` butts
  the tab up against the flap's cut edge where that rises above the crease's end; the
  piece that leaves beside the overhang is cut out (`Pattern.scraps`, a closed loop of slits).
  In 3D a tab is a flat panel on the overhang's tangent plane at the lid's side.
- **Glue tab taper.** `glue_tab_taper` cuts the shell's glue tab back only as far as keeps
  it, glued from the back panel's end on, off the front panel's fold arc: square where the
  gap leaves room, at most 45°.
- **Views.** The 3D and section views show the model turned half a turn about its length,
  back panel (lids) up; the model frame itself keeps the front panel at +Z.
- **Interior.** The interior, payload clearance and fit are unchanged: they are bounded by
  the inner walls, centred on the box.

### 4.4a Two pieces (`pieces = "two"`)

The box made of two identical pieces, the second turned over (point inversion about the
box's middle: X, Y and Z reversed; its print side inward), each one panel with an outer flap
at its top end and an inner flap at its bottom end, the FPC cable on its free edge and a glue
tab beyond its glue fold (`geometry._build_piece`).

- **Shell.** `crosssection.solve_two_piece`: one `CrossSection` for both panels (fold
  sagitta `(height + t)/2`), `back_point(u) = -front_point(u)` (both `u` from the free
  edge), both chords on `Z = 0` (`Shell.z_shift` 0). Each seam is the one-piece glued edge:
  the free edge rests inside the other panel, whose glue fold lies `t / sin α` beyond; the
  interior corner from the same mitre. The width is solved for the interior as before.
- **Lengths.** `Config.front_length` is the piece's straight edge,
  `edge_length + end_wall_gap`; `Config.inner_offset` (`end_wall_gap + t`; one piece: the gap)
  is how far the inner flap's panel's ends stand in from the outer flap's at an end. With
  both folds bowing in alike, the outer wall's extra thickness comes from there.
  `FoldedBox.cy` is the box's middle in pattern y (`(front_length + inner_offset) / 2`).
- **Flaps.** The outer flap's cut is `Shell.front_cuts` (to the other panel's outer surface),
  the inner flap's `Shell.back_cuts` (to its inner surface; the same in the piece's own `u`,
  by symmetry), with a short cut step where it does not start on the chord. The lid end
  (`_lid_end`) is the one-piece one made the same on both sides; `lid_layout`'s depth follows
  the other piece's inner wall, continued along its tangent past its free edge (which stops
  short of this one's glue fold).
- **Glue tab.** From `inner_offset` (where the other piece's free edge begins) to the
  piece's inner end, tapered off the other's inner flap fold at the top
  (`glue_tab_taper(cfg, 0)`), off its outer flap fold `inner_offset` on at the bottom.
- **3D model.** `FoldedBox.map` maps the piece on top; `build_model3d` adds the other piece's
  parts, lines, cut edges and cable turned (`FoldedBox.other`), tagged `piece` 1 and 2
  (`cables` holds both cables). Turned over, the second piece's triangles keep their
  winding, so the viewer shows its B.Cu outside, as made. The section adds the other glue
  tab (`glue_tabs`) and cable.
- **FPC.** `fpc.entry_range` takes the other piece's inner flap at the top and this one's at
  the bottom; the rows may run down to the piece's corner. Near that corner the inner flap's
  fold closes in on the junction; `partition.strips` orders the exits' strips to keep their
  ends off it.
- **Elsewhere.** Dimensions (`_piece_dimensions`), payload wall clearance and the OpenSCAD
  interior (the other end turned) use `inner_offset`/`cy`; the SVG labels name the body panel and, in the middle of each end's flap, the wall it makes (outer, inner).

### 4.5 FPC cutout and cable

`level_cut` finds, by bisection on the level, the horizontal cut that removes exactly
`width` from the top of a rising-then-falling edge. It sits around the edge's highest
point, which is slightly off-centre because the edge is not symmetric. The cut flattens the
inner flap's free edge.

The FPC cable is independent of it: it leaves the front panel's free straight edge where
`fpc_entry_offset` puts it, measured from the lowest (turning up; turning down, the highest)
it can go: folded in, its stub and first corner square lie on the back panel's inside up to
the square's far side deep, where the inner flap's wall stands `e + z(u)` in from the back
panel's end (`z` the back fold's sagitta at that depth, from where the front panel's edge
rests); the cable keeps the clearance from it past half its thickness (`entry_range`). Past
the wall fold the cable runs on across the front panel's inside (round onto the back panel,
if that long) at the junction's place along the box, where the walls stand in further: at
every X it reaches, the wall over it (the panel's fold there, by X), most towards the
panels' middle, so the cable keeps the clearance from the deepest; the plug's ears count
where they stick out further than the junction. The plug end (`plug.py`, shared with
`pcb`): the pinout, the GND and via rows behind the contacts and the traces' fan-out, from
the configuration alone (an inset cable's traces always neck down in its first corner), so
that the outline keeps the plug's width past them and narrows at 45 degrees just where the
fan-out starts (`CableLayout.plug_full`, `plug_end`; the 3D model's strip likewise). Its junction is as wide as the meshes' exits
need (`exit_width`), if wider than the cable: the stub widens on the side away from the first
turn up to the first corner's far side (a rectangle there), whose crease is still the
cable's square's diagonal, so the rows fold back as before. `fpc.meander` lays it out in a frame of its own (the junction level, the stub up, the
first turn to the right); `fpc.layout` turns that into the pattern (out of the edge is -x,
the first turn up or down along it; down mirrors, so the outline is reversed). In the box
(`FoldedCable`), the front panel's free edge rests against the inside of the back panel by
the glue fold (the glue tab lies outside, 4.3), a thickness off its mid-surface: the stub
follows the back panel's inside (its mid-surface offset `t`), the layer folded back over it
`2t`, and from the wall fold (where that layer crosses the front panel's offset `t`, at
`r = -t`) the strip follows the front panel's inside, round the straight fold onto the back
panel's. These are polylines by arc length (`_Run`), so the strip, ruled along the box, is
an exact isometry: the panels curve along it, not across it.

### 4.6 PCB layout

- **Mask.** The foil (`Polygon` of the outline, arcs within 5 µm, less the slits as 0.1 mm
  slots and the scraps) shrunk by the edge clearance, less the cable: the outline segments
  no face owns, closed along the front panel's free edge (x = 0), plus a band beyond the
  junction so that the mask's edge there is the junction line itself. The F.Cu exit cell
  sits against it, open towards the cable (-x); the B.Cu mesh's grid is offset by half a
  cell in x and y (its exit cell half a cell in, on the row of its grid nearest its pins),
  so the two layers' bare edge strips differ. Each exit cell is `2 N` trace pitches wide,
  `N` the side's nets (`Config.mesh_nets`: the curve's `mesh_partitions × mesh_traces`,
  KiMesh's `mesh_traces`); for the curve it is a row of *ports*, one per partition, each
  a square a pair of trace lanes wide (`2 mesh_traces` pitches).
- **Partitions** (`partition.py`, the curve only). Each side's area (less the leads' strip
  to the ports) is split into `mesh_partitions` parts of equal area, each with its own
  traces through its own port; all are laid out in one pass (`sfc.generate(partitions=,
  stems=)`): one graph over every partition's pieces (a partition's borders kept as a
  fold: no curve crosses one, each curve keeps half a spacing off it, so two partitions'
  curves run a spacing apart, as two runs of one curve do), a curve per partition, its
  own stem and exit, relaxed and offset into lanes each on its own, all traces settled
  together (each partition's piece of a panel its own zone; lengths matched within a
  partition: `settle`'s `groups`). The layer's mesh is theirs together (`Mesh.groups`:
  how many traces each; pair skew only within one).
  1. *Strips:* from each port, straight on in, a strip as wide (a pair of trace lanes),
     side by side with the next port's (nothing between them); the middle ones longest, no
     two neighbours as long (1 port, then 1.5 ports longer a step), so each strip's end
     and a stretch of its side face the open area. Where a fold closes in on the ports, the
     first order (rising to the longest and falling off) that leaves the square in front of
     every strip's end within one panel: else a strip run up beside the fold ends too near
     it for its curve to open there. The stem's rails run along it (its
     traces at the pitch, held as laid in settling) and the curve opens at its end. (A
     strip made curve area instead, a corridor a spacing wide, left the stem a small cycle
     of its own that no merge joins.) Beside a longer strip, a curve's opening has no room
     to spare: relaxation puts the curve on its rail's line for a spacing (less and less
     over the next half; `CurveParams::hold`, only the rails beside a longer strip, as
     elsewhere it turns as it would), its lanes there are laid at the pitch, and from a
     spacing on the area is kept a quarter pitch further off the strip.
  2. *Cells:* Voronoi cells 2.5 ports across, Lloyd-relaxed, each zone (panel) on its own,
     so none straddles a fold; a cell pinned in front of each strip's end, a box over the
     end all its own (wider, it left narrow pockets beside the strip no curve fills). Two
     cells are neighbours only through a wall at least a port long: no partition narrows
     below a curve's run in and back out.
  3. *Grown from the strips' ends:* each cell to the strip its cheapest path starts from,
     each start weighted (an additively weighted Voronoi diagram over the cell graph; a
     step across a fold 4 times dearer, every step's cost varied by a smooth random field
     and noise from the seed, so the two layers' borders differ), the weights set for equal
     areas: each partition the tree of its start's paths, so of a piece.
  4. *Refined:* borders smoothed (a cell to the partition holding most of its border, a
     neighbour across a fold counting a quarter: borders keep to folds), areas evened out
     between neighbours, the most uneven pair first (a cell at a time, to within about
     1 %), no partition ever torn (a cell is given up only if its neighbours in the
     partition stay joined). (The weights of step 3 rarely even the areas out by
     themselves: the strips' ends lie together, so a small change of weight hands a whole
     lobe of the area, behind a cell or two near the ends, from one partition to another;
     the evening out here does most of it.)
  5. *Necks widened* (`_Necks`, `_widened`): a partition (as a whole, and its piece of each
     panel) narrower than 2 ports somewhere between two wide parts of it (each 3 cells or
     more), where the area itself is wide, is a *neck*: its curve runs in there and back
     out with no room to turn, the graph's cycles beyond join the rest at a few cells if
     at all, and leave the part beyond bare. Tested as an erosion by a port, at points (each
     cell's centre and three along each wall): a point is clear when no border (the
     outline, or a wall between two partitions; for a panel's piece, or two panels) lies
     within a port of it. The walls near each point are found once, so a test is a look at
     their cells' partitions. Where a partition's wide parts are several, it takes the
     cells on the cheapest way between its two largest (its own free) and the neighbours'
     cells across the borders that keep that way narrow, each one only if its partition
     can spare it (stays of a piece, and round the cell, within 3 steps, comes apart into
     no more wide groups); then the areas are evened out again under the same guard.
     Finally cells past a passage that a partition's piece of a panel comes apart at when
     shrunk by half a spacing (no curve would reach them) go to the neighbour beside them
     most. Each partition is its cells, its strip and its port. The cells, walls and
     points are set up once (`_Cells`), and steps 3 to 5 tried up to 6 times, the first
     split with no neck and even (within 3 %) kept, else the best (no neck first, unless
     less even than that).
  6. *Unreached pieces handed on* (`sfc._reassigned`): a partition's piece its curve
     still does not reach (a piece of the back panel hanging off a sliver of the front
     one too thin for a run in and back out: the cells' walls were wide enough, the
     piece across them not) goes to the partition whose curve reaches the piece beside
     it, across the longest border a curve can cross, and so on from there; the curves
     are then found again. The partitions' areas come out less even, the box covered.
     A small region still left out (a lid's glue tab: one cell, beside the lid's narrow
     band whose run keeps to the far end of their border) is merged into the reached
     region of its own partition beside it (`sfc._merged`), and the curves found again:
     its curve then crosses the fold between them inside the merged region.
  7. *Tried again, salted* (`pcb._partitioned`): a layer whose curves still leave a region
     out (any region the core reached only in part counts) is split and laid out afresh,
     right after the curves' graph (before relaxation, the costly rest), its seed salted:
     `mesh_seed` and "-1", "-2", ... (`RETRIES`, 8; each layer on its own); so is one no
     split of which came out even (`partition.Uneven`), or whose curves' graph the core
     could not build (`sfc.Unbuilt`). The last try is kept as it is, its unreached regions
     counted (`Mesh.unreached`). In a survey of 400 seeds of a five-partition, two-piece
     layout (800 layers, at double pitch), 5 layers took a second try, none more, and none
     was left with a region out.
  The graph is built afresh (up to `ATTEMPTS` times, the best kept) when a cycle ends up
  joined to no exit's curve; across a border it joins as long as cycles there are apart.
  A join keeps off the border's ends (by `min(2 spacings, length / 6)`): a cycle edge along
  the border that runs into those margins (a small region's one cell has one from end to
  end) is first split where they begin, an edge a tenth of a spacing past them counts as
  clear, and a last pass takes edges anywhere near the border as long as both joins cross
  it clear of its ends.
  Seeds that the Lloyd steps bring near an exit's pinned seed are left out each step (a
  seed in a corner beside an opening otherwise comes back each time, its cell's wall
  across the opening).
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
  6. *Exit:* a seed pinned in the opening keeps cell walls off it; the stretch of the domain's
     edge between the stem's two ends becomes a fixed edge of the graph, standing for the
     stem (two rails, a spacing apart, straight through the exit cell), so the cycle takes
     it and leaves the opening outward.
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
     exactly the pitch on the stem's rails). Spreading skews: two neighbouring traces on
     one side differ in length by the pitch times the curve's turning, so a wider pitch in
     a bend adds to or takes from their skew with the bend's sense, and over hundreds of
     U-turns it adds up (to 16–19 mm on the default box). So, walking the curve from the
     exit, the traces spread on the straight wherever there is room but in a bend only
     where that pays back the skew run up so far (eased in and out over a few vertices).
     Loops and backward runs an offset makes inside a tight bend are cut out; the traces are
     cut where the stem leaves through the exit.
  9. *Settling* (`_settle`, not in the reference): the traces, offsets of one curve, leave
     every gap between two runs as wide as the runs are apart, and the holes where runs
     meet. So each trace is then moved on its own, by steps (`SETTLE`), towards the middle
     between the nearest copper on either side of it (nothing within three pitches: a hole,
     moved into; the area's edge and the zones' borders standing for copper at twice their
     distance; where the traces cross a border, at the curve's joins, they stay as laid). Smoothness
     counts for little: a trace may kink into a hole's corner (only jitter is smoothed, by
     a Taubin step); but in a bend tighter than 1.5 pitches nothing moves along its axis
     into it, so a U-turn's innermost trace keeps its tip and closes up its sides. A U-turn's
     tip (bends about as tight as a ribbon's) goes on out along its axis instead of to
     the middle of the room before it, up to a pitch from the copper in front: the outermost
     trace first, the ones inside after it, so the U grows longer into a gap rather than
     its traces spreading apart (each trace gains about as much: little skew). Filling
     holes lengthens the outermost traces (only they face holes), so length is steered:
     by each trace's length run from the exit at its place along the curve (a place kept
     per vertex as laid, against the traces' lengths as laid), a trace behind a neighbour
     has its bends about a pitch across grown into what room there is (spurs,
     squiggles), one in the lead has the bumps it pushes towards that neighbour straightened,
     giving the room up to it (well in the lead, its spurs into holes too: skew before
     coverage). It is steered only where the lead is still being built up (over about 15
     mm of curve it gains on the neighbour the way it leads): steered all along after a
     lead, a long trace took it back many times over and swung. Over a whole board that
     still leaves 10-25 mm, so the settled traces are then matched: walking along the
     curve, wherever a trace runs more than 15 pitches longer than the shortest, that much is
     marked to come out of it there, and a few steps straighten its bends there (its
     squiggles and spurs) by that much (`_match`; the band above how far leads swing to
     and fro through the bends, or every swing is cut). Only ever shortening, it costs
     little coverage (on the default box: skew 21 → 10 mm at most, length and islands as
     before). Neighbours are matched in pairs only (`mesh.matching`: 1-2, 3-4, ..., an odd
     ribbon's middle three together; `settle`'s `groups`, each pair's own, and the
     ribbon's width, the density's blur and the U-turn tips, a pair's): steered across the
     whole ribbon, a hole at a tight corner too small for the ribbon's U-turn stayed open,
     while a pair's fits (on the default box the holes' area more than halved, the pairs
     of a ribbon then a few cm apart in length). With more traces the holes where a ribbon's bends meet grow (the ribbon
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
     (annealing), or the layout churns and the steering goes round in circles. Every move keeps
     a pitch (+1 %) from other copper, measured to segments, and from the trace itself
     where it faces itself across (or is much further along it than away: a spur's
     pinched sides); none crosses. Only vertices near ones that moved are
     looked at again. Neighbours come from GEOS STRtrees (shapely; in the browser too, from
     Pyodide's build): one of the vertices per step for the centring, one of the segments
     per step for the clearance (distances to segments exactly; a vertex taken back is
     looked for as far again as it moved).
  10. *Holes* (`SETTLE_HOLE*`, in `settle.rs`): settled as above, a pair's outer trace
     grows into a hole alone and its partner never follows: centring sees the room
     inside the outer trace's U-turn as its own, and the annealing ends long before the
     partner would get in (with the steps raised globally: 160 fill a 1.5 × 3 mm pocket
     with both traces, at several times the cost, and the rest of the layout churns). So
     after settling, holes are found on a grid half a pitch apart (inside the area, a pitch
     off its edge: places more than a pitch from any trace, joined; kept if one is more than
     `SETTLE_HOLE` pitches from it), and each is filled on its own, in a box
     `SETTLE_HOLE_MARGIN` pitches wider. The traces nearest the hole's places, and their
     pairs, are cut out of it (their runs in the box; all others there held as laid, as
     obstacles), and: (1) each pair is settled as one trace along its middle at twice the
     pitch (`SETTLE_HOLE_STEPS` steps, the density blurred as for `SETTLE_HOLE_RIBBON`
     traces): its U-turn into the hole is the pair's two, one inside the other; (2) its
     traces are offset half a pitch either side of it again (mitred at corners), spliced
     into their runs where in the box; (3) all the moved runs are settled at the pitch for
     a quarter of the steps, each trace's own room across counting as its partner's too
     (`SETTLE_SHARE`: the outer trace's U-turn stays open for the inner's), without length
     steering; (4) whatever is still a little too near is pushed straight away from it.
     The result is kept only if every moved run keeps a pitch (−1 %) from all other copper
     (the held runs as they are: settling resamples what it is given, a U-turn's tip cut a
     little; and every vertex against every segment, either moved)
     and crosses none (and from itself, but where it turns: a U-turn as tight as laid is
     half a pitch across); else the hole stays as it was. Each hole costs a few hundred
     vertices' work (the length matching after takes up the skew it adds).
  The default box takes about 2 min per layer to lay, and about 20 min more to settle
  (see Later).
- **Check** (`verify`, run at the end of every `layout`): the tracks' points joined along
  each track and through the vias (union-find on µm-rounded points; only the points other
  copper meets are nodes: a track's ends and any point of it another's end or a via lands
  on): every mesh net one piece, ending on exactly its two contact pads; per layer, every
  pair of copper pieces of different nets (track segments, vias, pads; shapely `STRtree`
  `dwithin`, segments against segments only as near as two can touch, vias and pads
  against all as near as each can) at least their half widths apart (the default box: 15
  s; looked up as near as a via can reach for every segment, 80 s). The tests add a DRC of their own (different nets at least the trace
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
  sample matched to the nearest point of its neighbour a little further along than the last match
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
  out both exit corners and the partitions first, then lays both out together
  (`progress.side_by_side`, a stage per side:
  threads, as the heavy parts release the GIL; each with its own copy of the mask, since
  shapely crashes when two threads prepare one geometry; one after the other in the
  browser), their progress merged (the share done: their mean).
- **Progress** (`progress.py`): the layouts report their phases and steps (graph, relax,
  lanes, settle, fill, match; the stage: the mesh's layer) with figures (vertices, moved,
  clearances measured, the traces' length differences) and the whole layout's share done.
  The CLI shows a bar redrawn in place on a terminal (each phase's last figures kept above
  it), otherwise a status line per step. The web UI polls `GET /api/progress` while a PCB
  layout runs (the latest event: the server keeps it; in the browser build the worker posts
  each to the page, and `pyshim.js` answers the poll) and shows a bar and the phase in the
  top bar. The lengths' differences are shown only once matching: settling's swing wide.
- **Timing and checkpoints** (`checkpoint.py`): the layout's steps (`partition`; per
  layer `graph`, `relax`, `lanes`, `settle`, `fill`, `finish`, `output`; `verify`,
  `layout` in all) are timed (`checkpoint.report()`: seconds per step and layer; the
  layers run side by side, so theirs add up to more than the wall-clock time). With
  `YANARTAS_CHECKPOINT=<dir>` each step's arguments and result are also written there,
  gzipped JSON (arrays exactly, as base64 of their bytes; geometries as WKB), numbered in
  order; a run (a layout, a mesh, a step called alone) first clears what the run before it
  left there. `checkpoint.resume(<…in.json.gz>)` runs that step alone again, as it ran
  (writing and clearing nothing).
  Settling is three calls of the Rust core for this (its `phases`: settling, the holes,
  smoothing and matching; `base` the traces as first laid, for their lengths), so a fix
  to filling holes is tried in seconds on a whole board's layer.
  `scripts/crop_checkpoint.py` cuts a window out of a settling phase's checkpoint (each
  trace's runs in it traces of their own, a pair's runs side by side) for a smaller case
  of the same spot. On the default box (4 cores, per layer, the two at once): settling
  250 s, smoothing and matching 68 s, relaxation 13 s, graph 3–6 s, filling holes 3 s,
  output 1.5 s; then `verify` 18 s; the layout 385 s in all.
- **Later.** The rest of the curve layout in Rust; an alignment field (the reference's
  needles) to lay the curve along the edges; a hard skew limit in settling
  (dropped: it cost coverage; steering and matching keep the skew within 10 mm instead):
  reconsider it.
- **Smooth redraw** (`arcs::refine_all`, both shapes): the settled vertices are a
  pitch's third or so apart, and the polyline turns at each, so it looks rough.
  Each trace is redrawn as the C¹ cubic Hermite curve through its vertices (tangents along
  the neighbours' chord, scaled to the segment), subdivided so no step turns more than
  half of `MAX_TURN` (10°). The curve bulges out of the polyline a little, so where that
  costs room it is not taken: a segment stays straight wherever a point of its curve would
  have less room (to another trace, half of how much further than the pitch; to the
  area's edge or a zone's border, e.g. a fold, how much further than half a pitch) than
  the less of its two ends and zero, and so does the other trace's segment it would crowd
  (repeated until nothing changes, at most 6 times). Towards the trace's own copper (round
  a hairpin's tip, the other leg) it may come nearer by the polyline's own error there:
  the trace only comes nearer itself. `TURN_GIVE` allows a share of the
  pitch more (0: no clearance lost; about 5 % of the vertices keep their sharper turn).
  Straight segments (`smooth_traces`) are that curve simplified greedily: the longest
  chord within `SIMPLIFY` of it whose dense steps each stay within `MAX_TURN / 4` of the
  chord's own heading, so two chords turn at most `MAX_TURN` from one another.
- **Lines and arcs** (`mesh_shape = arcs`, `arcs::fit_all`): the same smooth curve
  redrawn greedily, the longest piece from each vertex that a line or an arc through the
  run's two ends follows. The arc is the one of those (one per sagitta) nearest the run at
  its worst, found by a golden-section search over the sagitta. The tolerance is per
  vertex: the error the polyline itself makes there (its chords' sagitta, `L·θ/8`, plus
  10 % for rounding), at least `ARCS` scaled to the pitch; and where the trace has room,
  up to `ARCS_ROOM` pitches: half of how much further than the pitch the nearest copper
  beside it is (another trace, or its own more than 1.8 pitches along it, as round a
  U-turn: half a turn a pitch across is π/2 pitches long, so nearer along, round a
  hairpin's tip, it is the same bend, which may then be drawn in arcs; and its own within
  4 pitches along, the hairpin's other leg, a quarter pitch nearer still), and all of how much further than half a pitch the area's edge is. So the
  traces keep as far apart as before, in far fewer pieces, about 90 % of their length
  arcs.
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
