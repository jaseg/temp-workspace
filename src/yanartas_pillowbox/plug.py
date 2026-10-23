"""The cable's plug end: which signal each contact carries, and the copper just behind the
contacts (a row of GND vias, the back mesh's vias in two staggered rows, then the traces'
fan-out from their places along the cable onto the contacts).

Both the cable's outline (``fpc``) and its copper (``pcb``) are laid out from this. Where the
cable is narrower than the plug (``fpc_cable_inset``), the cable keeps the plug's width back
past the vias and the fan-out, then narrows at 45 degrees to its own width just where the
fan-out starts: every trace jogs out at 45 degrees at most, so none leaves the cable. The
traces then always neck down to their places along the cable in its first corner (``pcb``),
so that those, and so the fan-out, follow from the configuration alone.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from shapely.geometry import LineString

from yanartas_pillowbox.config import Config

Point = tuple[float, float]

VIA_SIZE, VIA_DRILL = 0.45, 0.2
# The plug's contacts, this share of the pin pitch wide: 0.35 mm at 0.5 mm, as Hirose's
# FH12 (and the like) want an FPC's conductors (their exposed length, 3.5 mm or more, and
# the stiffener behind them, 4.5 mm or more: ``fpc_plug_length``)
CONTACT = 0.7
FRONT, BACK = "F.Cu", "B.Cu"


class PcbError(ValueError):
    """The layout cannot be made for this configuration."""


def pinout(pins: int, traces: int, group: int | None = None) -> list[str | None]:
    """Each pin's signal, from pin 1: "GND" or "M<i>" (mesh end i, from 1); the pins the
    mesh leaves over GND too; ``traces``: the mesh's nets on each side; ``group``: the
    traces between two GND pins (one partition's, its ends nested: 1s 2s … 2r 1r; default:
    a side's)."""
    ends = 4 * traces  # two ends per loop, two sides
    size = 2 * (group or traces)
    out: list[str | None] = ["GND"]
    for i in range(ends):
        out.append(f"M{i + 1}")
        if (i + 1) % size == 0:
            out.append("GND")
    if len(out) > pins:
        raise PcbError(f"the plug needs at least {len(out)} pins for the mesh's ends")
    return out + ["GND"] * (pins - len(out))


def config_pinout(cfg: Config) -> list[str | None]:
    """The configuration's pinout: a GND pin after each partition's ends (the curve's;
    KiMesh, a side's)."""
    n = cfg.mesh_nets
    each = int(cfg.mesh_traces) if cfg.mesh_algorithm == "sfc" else n
    return pinout(int(cfg.fpc_pins), n, each)


def k_pin(cfg: Config, j: int) -> float:
    """Pin j's place across the plug, from its middle (pin 1 on the cable's left, walking
    from the edge to the tip)."""
    return ((int(cfg.fpc_pins) + 1) / 2 - j) * cfg.fpc_pitch


def sides(cfg: Config) -> dict[str, list[int]]:
    """Each layer's mesh ends' pins, in order: the front mesh's the first half."""
    pins = config_pinout(cfg)
    mesh_pins = {s: j + 1 for j, s in enumerate(pins) if s and s.startswith("M")}
    per_side = 2 * cfg.mesh_nets
    return {
        FRONT: [mesh_pins[f"M{i + 1}"] for i in range(per_side)],
        BACK: [mesh_pins[f"M{per_side + i + 1}"] for i in range(per_side)],
    }


def fan(starts: Sequence[float], ends: Sequence[float], pitch: float) -> list[list[Point]]:
    """Traces moving sideways from offsets ``starts`` to ``ends`` (both in the same order),
    each by one 45 degree jog, staggered so that neighbours stay ``pitch`` apart (centre to
    centre). In local coordinates (u along, from 0, v across): each trace's points from
    ``(0, start)`` to ``(length, end)``, all ending at the same ``length``."""
    n = len(starts)
    delay = [0.0] * n

    def trace(i: int, length: float | None = None) -> list[Point]:
        a, b, u = starts[i], ends[i], delay[i]
        pts = [(0.0, a), (u, a), (u + abs(b - a), b)]
        if length is not None:
            pts.append((length, b))
        return pts

    for _ in range(64 * n):
        moved = False
        for i in range(n - 1):
            ta, tb = LineString(trace(i, 1e3)), LineString(trace(i + 1, 1e3))
            if ta.distance(tb) >= pitch - 1e-9:
                continue
            # Whoever moves towards the other waits for the other to get out of the way.
            gap_start, gap_end = abs(starts[i] - starts[i + 1]), abs(ends[i] - ends[i + 1])
            towards_a = (ends[i + 1] - starts[i + 1]) * (starts[i] - starts[i + 1]) > 0
            j = i + 1 if towards_a or gap_end < gap_start else i
            delay[j] += 0.02
            moved = True
        if not moved:
            break
    else:  # pragma: no cover - the fan always settles for ordered offsets
        raise PcbError("could not fan the traces out")
    length = max(delay[i] + abs(ends[i] - starts[i]) for i in range(n)) + pitch
    return [dedupe(trace(i, length)) for i in range(n)]


def dedupe(pts: list[Point]) -> list[Point]:
    out: list[Point] = []
    for p in pts:
        if not out or math.dist(out[-1], p) > 1e-9:
            out.append(p)
    return out


def plug_width(cfg: Config) -> float:
    """The plug's width: the contacts' span plus the edge margin on both sides."""
    return (cfg.fpc_pins - 1) * cfg.fpc_pitch + 2 * cfg.fpc_edge_margin


def cable_width(cfg: Config) -> float:
    """The cable's width away from the plug: the plug's less the inset on both sides."""
    return plug_width(cfg) - 2 * cfg.fpc_cable_inset


@dataclass(frozen=True)
class PlugEnd:
    """The copper behind the contacts, by how far back from the cable's tip (``s``) and
    across it from its centreline (``k``, to its left)."""

    pitch: float  # the traces' along the cable (necked down: the plug's pitch, if less)
    space: float  # ... the space between them
    along: dict[str, list[float]]  # each layer's traces' places across the cable, in order
    fans: dict[str, list[list[Point]]]  # each layer's fan-out (``fan``'s local points)
    row_gnd: float  # the GND vias' row
    rows: tuple[float, float]  # the back mesh's vias' two rows
    fan_start: float  # where the fan-out starts: the traces at their places from there on
    full: float  # the cable as wide as the plug up to here, then narrowing to fan_start


def plug_end(cfg: Config, ks: dict[str, list[float]] | None = None) -> PlugEnd:
    """The plug end's copper. ``ks``: each layer's traces' places along the cable as they
    come from the junction (``pcb``: their exits centred on their pins); none, or with the
    cable inset: necked down to the plug's pitch (the mesh's, if less), each layer's block
    centred on its pins but kept off the stitching vias' lanes along the cable's edges
    where it is wide enough. Raises ``PcbError``."""
    w, clearance = cfg.mesh_trace_width, cfg.mesh_trace_space
    inset = cfg.fpc_cable_inset
    necked = ks is None or inset > 0
    pitch = min(w + clearance, cfg.fpc_pitch) if necked else w + clearance
    space = pitch - w
    width = cable_width(cfg)
    along: dict[str, list[float]] = {}
    for layer, side_pins in sides(cfg).items():
        if not necked:
            along[layer] = list(ks[layer])  # type: ignore[index]
            continue
        centre = sum(k_pin(cfg, j) for j in side_pins) / len(side_pins)
        m = len(side_pins)
        clear = width / 2 - 2 * space - VIA_SIZE - cfg.mesh_edge_clearance / 2 - w / 2
        half = (m - 1) / 2 * pitch
        if half <= clear:
            centre = min(max(centre, -clear + half), clear - half)
        along[layer] = [centre + ((m - 1) / 2 - i) * pitch for i in range(m)]
        if max(abs(k) for k in along[layer]) + w / 2 + space > width / 2:
            raise PcbError("the cable is too narrow for the mesh's traces at its pitch")
    plug = cfg.fpc_plug_length
    row_gnd = plug + 0.2 + VIA_SIZE / 2
    rows = (row_gnd + VIA_SIZE + space, row_gnd + 2 * (VIA_SIZE + space))
    fans = {
        layer: fan(along[layer], [k_pin(cfg, j) for j in side_pins], pitch)
        for layer, side_pins in sides(cfg).items()
    }
    rows_end = rows[1] + VIA_SIZE / 2 + space
    fan_start = rows_end + max(f[0][-1][0] for f in fans.values())
    # (inset: as wide as the plug past the vias' rows, narrowing at 45 degrees from there
    # at the earliest; the fan-out starts where the narrowing does)
    fan_start = max(fan_start, rows_end + inset) if inset > 0 else fan_start
    return PlugEnd(pitch, space, along, fans, row_gnd, rows, fan_start, fan_start - inset)
