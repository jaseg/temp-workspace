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
| `geometry.py` | The flat pattern (`build_pattern`: outline, typed folds, faces), the folding map (`FoldedBox`), the 3D mesh (`build_model3d`) and the cross-section view data. |
| `svg.py` | Serializes a `Pattern` to SVG (layers, dash styles, labels, embedded config) and reads the config back (`extract_config`). |
| `dimensions.py` | Preview-only dimension annotations for all three views, measured on the same geometry. |
| `payload.py` | Payload clearance, per-field maximize, and *Fit box to payload*. |
| `scad.py` | OpenSCAD model of the interior: the payload space and the end spaces. |
| `presets.py` | Board sizes for the payload dropdown. |
| `api.py` | The JSON API apart from its transport: request config parsing (`ApiError` carries the status and body of a refusal), `render` (SVG, model, section, info, dimensions and payload summary in one response), the payload actions and the defaults. The Flask server and the in-browser build (`artifact/pb_api.py`) both route to it. |
| `server.py` | Flask app bound to 127.0.0.1, serving the UI and `/api/*`. |
| `persistence.py`, `cli.py` | Settings file (`./yanartas-pillowbox.json`), and the `serve` / `generate` commands. |

**Frontend** (`static/`): plain ES modules and custom elements, with no build step.

- `app.js` builds the form from the field specs, debounces renders and saves, and wires the
  views together, including linked highlighting between fields and dimensions.
- `pb-param` is one form field.
- `pb-preview2d` shows the SVG with pan and zoom.
- `pb-preview3d` uses vendored three.js r160.
- `pb-section` draws the cross-section.
- `panzoom.js` is the 2D views' shared wheel, drag and pinch handling.
- `dims2d.js` draws 2D dimensions at a constant on-screen text size.

The browser never computes geometry: an edit posts the config, and the views redraw from
the response.

**Caching:** `solve_body` is `lru_cache`d on their (hashable) inputs.
One render touches the same body many times, so this keeps a render under about 100 ms.

## 3. Test suite architecture

`pytest` with about 490 tests, run in parallel with pytest-xdist (about 10 s), plus
`ruff` for linting. `tests/conftest.py` overrides
`Config.defaults()` to 0.4 mm material, which most expected values assume; the UI default
is 0.2 mm. `tests/helpers.py` parses SVG paths back into `Line`/`Arc` segments and has
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
| `test_payload.py` | Clearance against a brute-force distance to a fine mesh, tightness of maximize, and *Fit box* against a brute-force grid search. |
| `test_scad.py` | The OpenSCAD spaces against the interior and the end walls. |
| `test_server.py`, `test_cli.py` | API contracts, settings fallback, CLI flags. |
| `test_artifact_api.py` | The in-browser API answers every route like the Flask server. |

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
- **Views.** The 3D and section views show the model turned half a turn about its length,
  back panel (lids) up; the model frame itself keeps the front panel at +Z.
- **Interior.** The interior, payload clearance and fit are unchanged: they are bounded by
  the inner walls, centred on the box.

### 4.5 FPC cutout

`level_cut` finds, by bisection on the level, the horizontal cut that removes exactly
`width` from the top of a rising-then-falling edge. It sits around the edge's highest
point, which is slightly off-centre because the edge is not symmetric. The cut flattens the
inner flap's free edge.

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
