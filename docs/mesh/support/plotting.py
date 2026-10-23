"""The notebook's plots: one look for each kind of element, the same in every plot."""

from __future__ import annotations

import numpy as np
import shapely
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, PathPatch
from matplotlib.path import Path as MplPath

# (the partitions' colours: as in the partition notebook)
PALETTE = ["#4E79A7", "#F28E2B", "#59A14F", "#B07AA1", "#76B7B2", "#EDC948", "#9C755F", "#BAB0AC"]
CHANGED = "#D62728"  # what a step changed
CURVE = "#222222"  # the space-filling curve
GRAPH = "#B5B5B5"  # graph edges (cell walls)
FOLD = "#666666"  # folds between panels
STEM = "#8C564B"  # the stems' rails
TRACE = ["#1F77B4", "#FF7F0E", "#2CA02C", "#9467BD", "#17BECF", "#BCBD22", "#E377C2", "#7F7F7F"]


def fill(ax, g, **kw):
    """A (multi)polygon, holes included."""
    for p in shapely.get_parts(g):
        if p.geom_type != "Polygon" or p.is_empty:
            continue
        verts, codes = [], []
        for r in (p.exterior, *p.interiors):
            xy = np.asarray(r.coords)
            verts += xy.tolist()
            codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(xy) - 2) + [MplPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MplPath(verts, codes), **kw))


def rings(ax, rs, **kw):
    """A polygon given as rings of points."""
    fill(ax, shapely.Polygon(rs[0], rs[1:]), **kw)


def lines(ax, segs, **kw):
    """Segments [(a, b), ...] in one go."""
    if len(segs):
        ax.add_collection(LineCollection(np.asarray(segs, float), **kw))


def line(ax, p, **kw):
    p = np.asarray(p, float).reshape(-1, 2)
    ax.plot(p[:, 0], p[:, 1], **kw)


def base(ax, mask, zones, title=None, folds=True):
    """The area's outline and its folds (the zones' borders inside it)."""
    fill(ax, mask, facecolor="none", edgecolor="black", lw=1.2, zorder=6)
    if folds:
        outline = mask.boundary.buffer(1e-6)
        for z in zones:
            inner = z.boundary.intersection(mask).difference(outline)
            for seg in shapely.get_parts(inner):
                if seg.length > 1e-6 and seg.geom_type in ("LineString", "LinearRing"):
                    line(ax, seg.coords, ls="--", color=FOLD, lw=1.0, zorder=6)
    ax.set_aspect("equal")
    ax.autoscale_view()
    if title:
        ax.set_title(title, fontsize=10)


def legend(ax, items, loc="upper right", outside=False):
    """items: (kind, colour, label); kind: patch, edge, line, dash, dot, hollow."""
    hs = []
    for kind, color, label in items:
        if kind == "patch":
            hs.append(Patch(facecolor=color, edgecolor="none", label=label))
        elif kind == "edge":
            hs.append(Patch(facecolor="none", edgecolor=color, lw=1.8, label=label))
        elif kind == "line":
            hs.append(Line2D([], [], color=color, lw=1.5, label=label))
        elif kind == "dash":
            hs.append(Line2D([], [], color=color, lw=1.2, ls="--", label=label))
        elif kind == "dot":
            hs.append(Line2D([], [], color=color, marker="o", ls="none", ms=4, label=label))
        elif kind == "hollow":
            hs.append(
                Line2D([], [], color=color, marker="o", mfc="none", ls="none", ms=5, label=label)
            )
    if outside:
        ax.legend(handles=hs, fontsize=7, loc="center left", bbox_to_anchor=(1.02, 0.5))
    else:
        ax.legend(handles=hs, fontsize=7, loc=loc, framealpha=0.9)


BASE = [("line", "black", "area outline"), ("dash", FOLD, "fold")]


def zoom(ax, centre, half):
    ax.set_xlim(centre[0] - half, centre[0] + half)
    ax.set_ylim(centre[1] - half, centre[1] + half)
