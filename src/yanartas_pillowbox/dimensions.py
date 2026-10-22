"""Dimension annotations for the preview views, one per input parameter they illustrate.

Pure functions (no Flask, no SVG). Every dimension names the config field it shows
(``param``, or None for derived values), the points it measures (``points``, which lie on the
actual geometry), and the measured ``value``. Views only decide how to draw them; the
values themselves always come from the same geometry as the pattern and the 3D model.

Kinds:

* ``horizontal`` / ``vertical`` (2D): ``points`` = two measured points; ``value`` is their
  x / y distance; the dimension line is drawn at ``at`` (y for horizontal, x for vertical).
* ``path`` (2D): ``points`` = polyline along the measured curve (its length is ``value``);
  drawn parallel to it, ``offset`` to the left of the direction of travel.
* ``aligned3d`` (3D): ``points`` = two measured points; ``line`` is the polyline to draw,
  ``extensions`` the extension lines and ``label_at`` the label anchor (all precomputed).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from yanartas_pillowbox.config import Config
from yanartas_pillowbox.crosssection import curve_samples
from yanartas_pillowbox.geometry import FoldedBox, Pattern, Point, Point3, lid_layout
from yanartas_pillowbox.svg import MARGIN

Coords = tuple[float, ...]


@dataclass(frozen=True)
class Dimension:
    param: str | None
    label: str
    kind: str
    points: tuple[Coords, ...]
    value: float
    at: float | None = None
    offset: float | None = None
    line: tuple[Coords, ...] = ()
    extensions: tuple[tuple[Coords, Coords], ...] = ()
    label_at: Coords | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "param": self.param,
            "label": self.label,
            "kind": self.kind,
            "value": self.value,
            "points": [_r(p) for p in self.points],
        }
        if self.at is not None:
            out["at"] = round(self.at, 6)
        if self.offset is not None:
            out["offset"] = round(self.offset, 6)
        if self.line:
            out["line"] = [_r(p) for p in self.line]
        if self.extensions:
            out["extensions"] = [[_r(a), _r(b)] for a, b in self.extensions]
        if self.label_at is not None:
            out["labelAt"] = _r(self.label_at)
        return out


def _r(p: Coords) -> list[float]:
    return [round(c, 6) for c in p]


def fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def polyline_length(pts: list[Coords]) -> float:
    return sum(math.dist(a, b) for a, b in itertools.pairwise(pts))


# ------------------------------------------------------------------------- 2D pattern
def pattern_dimensions(cfg: Config, pattern: Pattern, offset: Point) -> list[Dimension]:
    """Dimensions for the flat pattern, in SVG user units (flat coordinates + ``offset``).

    Width, length and height are interior dimensions: where they are measured inside the
    material, the measured points sit off the drawn lines by the material allowance."""
    if cfg.two_piece:
        return _piece_dimensions(cfg, pattern, offset)
    shell = cfg.shell
    wf, wb = shell.front.width, shell.back.width
    edge, g, t = cfg.edge_length, cfg.glue_tab_width, cfg.thickness
    taper = pattern.info["glue_tab_taper"]
    e, front_edge, s_f = cfg.end_wall_gap, cfg.front_length, shell.front.sagitta
    dx, dy = offset
    x0, y0, x1, y1 = pattern.bbox
    # Outer dimension lines sit outside the sheet (pattern + margin), so they never cover it.
    gap = MARGIN + max(4.0, 0.04 * max(x1 - x0, y1 - y0))

    def p(x: float, y: float) -> Coords:
        return (x + dx, y + dy)

    # Interior length along the back panel's midline, between the inner end walls (its
    # flaps): their inner surfaces stand t/2 inside the back panel's curved folds.
    s_b = shell.back.sagitta
    ya, yb = e + s_b + t / 2, e + edge - s_b - t / 2
    # Interior height across a back panel (inner) flap: from t/2 inside the fold (the back
    # panel's inner surface) to the cut edge (the front panel's inner surface). Taken on the
    # bottom flap if an FPC cutout cuts only the top one down; with both cut down, measured
    # to where the edge would be without the cut.
    xh = wf + wb / 2
    cut = {end for end in ("front", "back") if cfg.fpc_cutout in (end, "both")}
    reach = shell.back_cuts[len(shell.back_cuts) // 2][1] if len(cut) == 2 else None
    if cut == {"front"}:
        y_cut = pattern.face("back-bottom-flap").y_range(xh)[1]
        y_fold = e + edge - shell.back.sagitta + t / 2
    else:
        y_cut = e - reach if reach is not None else pattern.face("back-top-flap").y_range(xh)[0]
        y_fold = e + shell.back.sagitta - t / 2
    # End wall gap, on the front panel's midline at the bottom end: from the outer wall's
    # inner surface (t/2 inside the front's curved fold) to the inner wall's outer surface.
    yg = (front_edge - s_f - t / 2, front_edge - e - s_f - t / 2)
    dims = [
        # The two panels, flat, are the closed cross-section's full circumference (computed
        # from the box width, height and thickness; not an input).
        Dimension(
            "circumference",
            f"circumference {fmt(wf + wb)}",
            "horizontal",
            (p(0, e + edge), p(wf + wb, e + edge)),
            wf + wb,
            at=y1 + dy + gap,
        ),
        Dimension(
            "length",
            f"length {fmt(cfg.length)}",
            "vertical",
            (p(xh, ya), p(xh, yb)),
            yb - ya,
            at=wf + wb * 0.3 + dx,  # beside the midline, clear of the exported labels
        ),
        Dimension(
            "height",
            f"height {fmt(cfg.height)}",
            "vertical",
            (p(xh, y_fold), p(xh, y_cut)),
            abs(y_fold - y_cut),
            at=wf + wb * 0.8 + dx,  # beside the middle, clear of the exported labels
        ),
        # Glue tab: width and taper both dimensioned at the tab's bottom end.
        Dimension(
            "glue_tab_width",
            f"tab {fmt(g)}",
            "horizontal",
            (p(wf + wb, e + edge), p(wf + wb + g, e + edge - taper)),
            g,
            at=y1 + dy + gap,
        ),
    ]
    if taper > 0.005:
        dims.append(
            Dimension(
                None,  # (derived: only as much as the curved folds need)
                f"taper {fmt(taper)}",
                "vertical",
                (p(wf + wb, e + edge), p(wf + wb + g, e + edge - taper)),
                taper,
                at=x1 + dx + gap,
            )
        )
    if e > 0:
        dims.append(
            Dimension(
                "end_wall_gap",
                f"gap {fmt(e)}",
                "vertical",
                (p(wf / 2, yg[0]), p(wf / 2, yg[1])),
                yg[0] - yg[1],
                at=wf * 0.3 + dx,  # beside the midline, clear of the exported labels
                # (from the drawn fold's and inner wall's apexes, t/2 outside the surfaces)
                extensions=(
                    (p(wf / 2, yg[0] + t / 2), p(wf * 0.3, yg[0])),
                    (p(wf / 2, yg[1] - t / 2), p(wf * 0.3, yg[1])),
                ),
            )
        )
    lid = lid_layout(cfg)
    if lid is not None and cfg.lid_overlap > 0:
        # Lid overlap, on the top lid at the middle: from its free edge back to where the
        # inner end wall's outer surface lies under it.
        y_edge = pattern.face("front-top-lid").y_range(wf / 2)[0]
        dims.append(
            Dimension(
                "lid_overlap",
                f"overlap {fmt(cfg.lid_overlap)}",
                "vertical",
                (p(wf / 2, y_edge), p(wf / 2, y_edge + cfg.lid_overlap)),
                cfg.lid_overlap,
                at=wf * 0.3 + dx,
                # (from the lid's edge and the drawn inner wall under it, t/2 outside its
                # outer surface)
                extensions=(
                    (p(wf / 2, y_edge), p(wf * 0.3, y_edge)),
                    (
                        p(wf / 2, y_edge + cfg.lid_overlap - t / 2),
                        p(wf * 0.3, y_edge + cfg.lid_overlap),
                    ),
                ),
            )
        )
    return dims


def _piece_dimensions(cfg: Config, pattern: Pattern, offset: Point) -> list[Dimension]:
    """``pattern_dimensions`` for one of two pieces (``geometry._build_piece``)."""
    shell = cfg.shell
    w, s, t, g = shell.front.width, shell.front.sagitta, cfg.thickness, cfg.glue_tab_width
    lp, e, d = cfg.front_length, cfg.end_wall_gap, cfg.inner_offset
    taper = pattern.info["glue_tab_taper"]
    dx, dy = offset
    x0, y0, x1, y1 = pattern.bbox
    gap = MARGIN + max(4.0, 0.04 * max(x1 - x0, y1 - y0))

    def p(x: float, y: float) -> Coords:
        return (x + dx, y + dy)

    xm = w / 2
    # Interior length on the midline: from the other piece's inner wall at the top (its
    # ends ``d`` on) to this one's at the bottom, t/2 inside their folds.
    ya, yb = d + s + t / 2, lp - s - t / 2
    # Interior height across the inner flap: from this panel's inner surface (t/2 inside
    # its fold) to the cut edge (the other's inner surface; without an FPC cutout's cut).
    y_fold = lp - s + t / 2
    y_cut = lp + shell.back_cuts[len(shell.back_cuts) // 2][1]
    dims = [
        Dimension(
            "circumference",
            f"panel {fmt(w)} (circumference {fmt(2 * w)})",
            "horizontal",
            (p(0, lp), p(w, lp)),
            w,
            at=y1 + dy + gap,
        ),
        Dimension(
            "length",
            f"length {fmt(cfg.length)}",
            "vertical",
            (p(w * 0.7, ya), p(w * 0.7, yb)),
            yb - ya,
            at=w * 0.7 + dx,
        ),
        Dimension(
            "height",
            f"height {fmt(cfg.height)}",
            "vertical",
            (p(xm, y_fold), p(xm, y_cut)),
            y_cut - y_fold,
            at=w * 0.8 + dx,
        ),
        # Glue tab: width and taper both at the tab's top end.
        Dimension(
            "glue_tab_width",
            f"tab {fmt(g)}",
            "horizontal",
            (p(w, d), p(w + g, d + taper)),
            g,
            at=y0 + dy - gap,
        ),
    ]
    if taper > 0.005:
        dims.append(
            Dimension(
                None,
                f"taper {fmt(taper)}",
                "vertical",
                (p(w, d), p(w + g, d + taper)),
                taper,
                at=x1 + dx + gap,
            )
        )
    if e > 0:
        # At the top, on the midline: from the outer wall's inner surface to the inner wall's
        # outer surface (the other piece's, its ends ``d`` on).
        dims.append(
            Dimension(
                "end_wall_gap",
                f"gap {fmt(e)}",
                "vertical",
                (p(w * 0.3, s + t / 2), p(w * 0.3, d + s - t / 2)),
                d - t,
                at=w * 0.3 + dx,
                # (from the drawn fold's and inner wall's apexes, t/2 outside the surfaces)
                extensions=(
                    (p(w / 2, s), p(w * 0.3, s + t / 2)),
                    (p(w / 2, d + s), p(w * 0.3, d + s - t / 2)),
                ),
            )
        )
    lid = lid_layout(cfg)
    if lid is not None and cfg.lid_overlap > 0:
        y_edge = pattern.face("front-top-lid").y_range(xm)[0]
        dims.append(
            Dimension(
                "lid_overlap",
                f"overlap {fmt(cfg.lid_overlap)}",
                "vertical",
                (p(xm, y_edge), p(xm, y_edge + cfg.lid_overlap)),
                cfg.lid_overlap,
                at=w * 0.3 + dx,
                # (from the lid's edge and the drawn inner wall under it, t/2 outside its
                # outer surface)
                extensions=(
                    (p(xm, y_edge), p(w * 0.3, y_edge)),
                    (p(xm, y_edge + cfg.lid_overlap - t / 2), p(w * 0.3, y_edge + cfg.lid_overlap)),
                ),
            )
        )
    return dims


def landing_outlines(cfg: Config, pattern: Pattern, offset: Point) -> list[dict[str, Any]]:
    """Where each inner end wall stands, once folded, seen on the front panel: its flap's
    cut edge, which rests against the front panel's inside, carried onto the front panel's
    flat coordinates (+ ``offset``) at the same place along the box. One arc per end, the
    end wall gap inside the outer flap's fold, as ``outline`` entries (open, dashed) for the
    dimensions layer. Two pieces: the other piece's inner flap, at this one's outer flap
    end."""
    box = FoldedBox(cfg)
    shell = box.shell
    sec = shell.front
    dx, dy = offset
    lid = lid_layout(cfg)
    sp = 0.0 if lid is None else lid.spread

    def flat_x(x3: float) -> float:
        """The front panel's flat x where it stands at X = x3 (its section continued over
        the overhangs)."""
        lo, hi = -sp - sec.width, sec.width * 2 + sp
        for _ in range(80):
            mid = (lo + hi) / 2
            try:
                beyond = shell.front_x + sec.x_ext(mid) > x3
            except ValueError:  # (past 45 degrees: beyond the box either way)
                beyond = mid > sec.width / 2
            lo, hi = (lo, mid) if beyond else (mid, hi)
        return (lo + hi) / 2

    # (inner flap face, its cut edge (away from its fold on the back panel), the end, whose)
    if cfg.two_piece:
        ends = [("back-bottom-flap", "upper", "top", True)]
    else:
        ends = [
            ("back-top-flap", "lower", "top", False),
            ("back-bottom-flap", "upper", "bottom", False),
        ]
    k, length = box.lid_level, box.length
    out = []
    for inner, edge, end, other in ends:
        # Where it stands along the box (Y, unflipped; the same at a given X all down the
        # wall), carried onto the front panel (its flat y that distance along the box) and
        # onto the lid closing over it (folded back at the lid's level: the overlap's end).
        # (On the front panel, the overhangs beside it too: by the glued edge the inner wall
        # reaches a little past the front panel's free edge, off the sheet there.)
        panel = ["front-panel", f"front-{end}-left", f"front-{end}-right"]
        targets = [(panel, lambda y: y, f"inner end wall, folded, at the {end} end")]
        if lid is not None and any(f.name == f"front-{end}-lid" for f in pattern.faces):
            fold = (lambda y: k - y) if end == "top" else (lambda y: 2 * length - k - y)
            targets.append(([f"front-{end}-lid"], fold, f"inner end wall, under the {end} lid"))
        for names, flat_y, label in targets:
            body = [pattern.face(n) for n in names]
            pts = _clipped(
                getattr(pattern.face(inner), edge),
                lambda p, inner=inner, other=other, flat_y=flat_y: _carried(
                    box, inner, other, p, flat_x, flat_y
                ),
                lambda q, body=body: any(
                    f.x0 <= q[0] <= f.x1 and _within(f.y_range(q[0]), q[1]) for f in body
                ),
            )
            out.append(
                {
                    "param": None,
                    "kind": "outline",
                    "label": label,
                    "value": 0.0,
                    "points": [_r((x + dx, y + dy)) for x, y in pts],
                }
            )
    return out


def _carried(
    box: FoldedBox,
    face: str,
    other: bool,
    p: Point,
    flat_x: Callable[[float], float],
    flat_y: Callable[[float], float],
) -> Point:
    """Flat point p of an inner flap, folded (two pieces: the other piece's), in the flat
    coordinates ``flat_x`` of its X and ``flat_y`` of its distance along the box."""
    q = box.map(face, p)
    if other:
        q = box.other(q)
    return (flat_x(q[0]), flat_y(box.cy - q[1]))


def _clipped(
    segments: Sequence[Any], at: Callable[[Point], Point], on: Callable[[Point], bool]
) -> list[Point]:
    """The chain of segments carried by ``at``, sampled every half millimetre or so: its
    longest run that ``on`` holds along (from and to where it comes on and goes off)."""
    runs: list[list[Point]] = [[]]
    for seg in segments:
        n = max(2, math.ceil(seg.length / 0.5))

        def q(u: float, seg: Any = seg) -> Point:
            return at(seg.point_at(u))

        for i in range(n + 1):
            p = q(i / n)
            pts = runs[-1]
            if on(p):
                if not pts and i > 0:  # (from where it comes on)
                    lo, hi = (i - 1) / n, i / n
                    for _ in range(40):
                        mid = (lo + hi) / 2
                        lo, hi = (lo, mid) if on(q(mid)) else (mid, hi)
                    pts.append(q(hi))
                pts.append(p)
            elif pts and i > 0 and on(q((i - 1) / n)):  # (to where it goes off)
                lo, hi = (i - 1) / n, i / n
                for _ in range(40):
                    mid = (lo + hi) / 2
                    lo, hi = (mid, hi) if on(q(mid)) else (lo, mid)
                pts.append(q(lo))
                runs.append([])
    pts = max(runs, key=len)
    return [p for k, p in enumerate(pts) if k == 0 or p != pts[k - 1]]


def _within(span: tuple[float, float], v: float, tol: float = 1e-6) -> bool:
    return span[0] - tol <= v <= span[1] + tol


# ------------------------------------------------------------------------- cross-section
def section_dimensions(cfg: Config, section: dict[str, Any]) -> list[Dimension]:
    """Dimensions for the shell cross-section, in its (X, Z) frame (Z up). Width and height
    are measured on the interior (the material's inner surfaces)."""
    front, inner = section["front"], section["inner"]
    x0, z0, x1, z1 = section["bbox"]
    gap = 0.12 * max(x1 - x0, z1 - z0)
    return [
        Dimension(
            "height",
            f"height {fmt(cfg.height)}",
            "vertical",
            (tuple(inner["back_apex"]), tuple(inner["front_apex"])),
            inner["front_apex"][1] - inner["back_apex"][1],
            at=x1 + gap,
        ),
        Dimension(
            "width",
            f"width {fmt(cfg.width)}",
            "horizontal",
            (tuple(inner["glue"]), tuple(inner["fold"])),
            inner["fold"][0] - inner["glue"][0],
            at=z0 - gap,
        ),
        # Part of the (computed) circumference: the front panel's arc.
        Dimension(
            "circumference",
            f"front panel {fmt(cfg.shell.front.width)}",
            "path",
            tuple(tuple(q) for q in front),
            polyline_length(front),
            offset=gap * 0.55,
        ),
    ]


# ------------------------------------------------------------------------- 3D model
def model_dimensions(cfg: Config) -> list[Dimension]:
    """Dimensions for the 3D preview, in the model frame (X across, Y length, Z height),
    measured on the interior."""
    box = FoldedBox(cfg)
    shell = box.shell
    wf, length, s_f, t = shell.front.width, cfg.front_length, shell.front.sagitta, cfg.thickness
    e = cfg.end_wall_gap
    x0, x1 = shell.inner_glue[0], shell.inner_fold[0]
    gap = 0.12 * max(length, x1 - x0)

    def add(a: Point3, v: Coords, k: float = 1.0) -> Coords:
        return tuple(a[i] + v[i] * k for i in range(3))

    def offset_dim(
        param: str, label: str, a: Point3, b: Point3, off: Coords, ext: float, at: float
    ) -> Dimension:
        """a to b, its line drawn ``off`` away, extension lines ``ext`` times as far, the
        label a further ``at`` times ``off`` out."""
        la, lb = add(a, off), add(b, off)
        return Dimension(
            param,
            label,
            "aligned3d",
            (a, b),
            math.dist(a, b),
            line=(la, lb),
            extensions=((a, add(a, off, ext)), (b, add(b, off, ext))),
            label_at=tuple((la[i] + lb[i]) / 2 + off[i] * at for i in range(3)),
        )

    dims: list[Dimension] = []

    # Length: along the back panel's midline (the ridge on the side the view shows up), between
    # the inner end walls' inner surfaces, t/2 inside the back panel's curved folds; drawn
    # beyond the back panel (-Z).
    wb, s_b = shell.back.width, shell.back.sagitta
    if cfg.two_piece:  # (the other piece's midline: this one's, turned)
        a = box.other(box.map("front-panel", (wf / 2, cfg.inner_offset + s_f + t / 2)))
        b = box.other(box.map("front-panel", (wf / 2, length - s_f - t / 2)))
    else:
        a = box.map("back-panel", (wf + wb / 2, e + s_b + t / 2))
        b = box.map("back-panel", (wf + wb / 2, length - e - s_b - t / 2))
    off = (0.0, 0.0, -gap * 0.6)
    dims.append(offset_dim("length", f"length {fmt(cfg.length)}", a, b, off, 1.15, 0.5))
    lid = lid_layout(cfg)
    if e > 0 and lid is not None:
        # End wall gap, in line with the length at the far end (-Y), on the centreline under
        # the lid: from the inner wall's outer surface to the outer wall's inner surface.
        z = shell.z_shift + lid.level - s_f + t / 2  # the lid's inner surface there
        # (two pieces: at the near end, under the lid of the piece on top)
        k = 1.0 if cfg.two_piece else -1.0
        a = (0.0, k * (cfg.length / 2 + t), z)
        b = (0.0, k * (cfg.length / 2 + t + e), z)
        dims.append(offset_dim("end_wall_gap", f"gap {fmt(e)}", a, b, off, 1.15, 0.5))
    if lid is not None and cfg.lid_overlap > 0:
        # Lid overlap, on the near end's lid (+Y): from where the inner wall's outer surface
        # lies under it to its free edge; drawn further out than the length.
        depth = next(d for x, d in lid.depth if x >= wf / 2)
        x_mid = next(x for x, _ in lid.depth if x >= wf / 2)
        a = box.map("front-top-lid", (x_mid, lid.level - depth + cfg.lid_overlap))
        b = box.map("front-top-lid", (x_mid, lid.level - depth))
        off2 = tuple(c * 1.6 for c in off)
        label = f"overlap {fmt(cfg.lid_overlap)}"
        dims.append(offset_dim("lid_overlap", label, a, b, off2, 1.1, 0.3))

    if lid is not None and cfg.lid_offset > 0:
        # Lid offset, where the lid comes closest to the back panel, over the overlap at the
        # near end: from where the lid's mid-surface would rest (a thickness outside the back
        # panel's) up to where it floats; drawn beside, outward across the box.
        zs, front = shell.z_shift, shell.front
        n = curve_samples(wf)
        us = [wf * i / n for i in range(n + 1)]

        def float_at(u: float) -> float:
            x3 = shell.front_point(u)[0]
            return shell.surface_z("back", t, x3) - (zs + lid.level - front.z(u))

        u = min(us, key=float_at)
        x3 = shell.front_point(u)[0]
        y_int = cfg.inner_offset + (zs - shell.surface_z("back", 0.0, x3)) + cfg.lid_overlap / 2
        y3 = box.cy - y_int
        a = (x3, y3, shell.surface_z("back", t, x3))
        b = (x3, y3, zs + lid.level - front.z(u))
        side = (math.copysign(gap * 0.35, x3 or 1.0), 0.0, 0.0)
        label = f"lid offset {fmt(cfg.lid_offset)}"
        dims.append(offset_dim("lid_offset", label, a, b, side, 1.15, 0.9))

    # Height: between the panels' inner surfaces on the centreline, at the interior's end,
    # drawn beyond the end of the box.
    y_end = cfg.length / 2
    a, b = (0.0, y_end, -cfg.height / 2), (0.0, y_end, cfg.height / 2)
    y_line = box.cy + gap * 0.6
    la, lb = (0.0, y_line, a[2]), (0.0, y_line, b[2])
    dims.append(
        Dimension(
            "height",
            f"height {fmt(cfg.height)}",
            "aligned3d",
            (a, b),
            math.dist(a, b),
            line=(la, lb),
            extensions=((a, (0.0, y_line + gap * 0.1, a[2])), (b, (0.0, y_line + gap * 0.1, b[2]))),
            label_at=(0.0, y_line + gap * 0.45, 0.0),
        )
    )

    # Width: across the interior from inner corner to inner corner, at the near end of the
    # back panel (where the corners end).
    z = (shell.inner_glue[1] + shell.inner_fold[1]) / 2
    y_w = -(cfg.length if cfg.two_piece else cfg.edge_length) / 2
    a, b = (x0, y_w, z), (x1, y_w, z)
    y_line = -box.cy - gap * 0.6
    la, lb = (a[0], y_line, 0.0), (b[0], y_line, 0.0)
    dims.append(
        Dimension(
            "width",
            f"width {fmt(cfg.width)}",
            "aligned3d",
            (a, b),
            math.dist(a, b),
            line=(la, lb),
            extensions=((a, add(la, (0.0, -gap * 0.1, 0.0))), (b, add(lb, (0.0, -gap * 0.1, 0.0)))),
            label_at=(0.0, y_line - gap * 0.35, 0.0),
        )
    )
    return dims


def to_json(dims: list[Dimension]) -> list[dict[str, Any]]:
    return [d.to_json() for d in dims]
