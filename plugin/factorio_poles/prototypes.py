"""Electric pole prototypes.

All numbers here are transcribed from Factorio's ``base/prototypes/entity/entities.lua``
(``type = "electric-pole"``) so that texture packs laid out like the game's
``base/graphics/entity`` directory drop in unchanged.

Units
-----
Everything is stored in *tiles* (one Factorio map tile).  Factorio specifies offsets
either with ``util.by_pixel(x, y)`` (32 px per tile) or ``util.by_pixel_hr(x, y)``
(64 px per tile, the resolution of the high-res sprites); :func:`px` and :func:`hr`
convert those.  Screen/schematic coordinates have +y pointing *down*, the same as
both Factorio and KiCad, so a negative y offset is "up" (i.e. height above ground).
"""

from __future__ import annotations

from dataclasses import dataclass

Vec = tuple[float, float]


def px(x: float, y: float) -> Vec:
    """``util.by_pixel``: 32 pixels per tile."""
    return (x / 32.0, y / 32.0)


def hr(x: float, y: float) -> Vec:
    """``util.by_pixel_hr``: 64 pixels per tile."""
    return (x / 64.0, y / 64.0)


@dataclass(frozen=True)
class SpriteSheet:
    """One ``pictures.layers[]`` entry: ``frames`` same-sized frames side by side."""

    filename: str  # relative to the texture root, e.g. "small-electric-pole/small-electric-pole.png"
    width: int  # frame width in pixels
    height: int  # frame height in pixels
    frames: int  # direction_count; frames are laid out left to right
    shift: Vec  # offset of the frame centre from the entity position, tiles
    scale: float  # sprite scale; 0.5 means 64 sprite pixels per tile

    @property
    def sheet_size(self) -> tuple[int, int]:
        return (self.width * self.frames, self.height)

    @property
    def tiles_per_pixel(self) -> float:
        return self.scale / 32.0

    def frame_box(self, frame: int) -> tuple[int, int, int, int]:
        """Pixel box (left, top, right, bottom) of ``frame`` within the sheet."""
        return (frame * self.width, 0, (frame + 1) * self.width, self.height)

    def frame_rect_tiles(self) -> tuple[float, float, float, float]:
        """Frame extent relative to the entity position: (left, top, right, bottom), tiles."""
        w = self.width * self.tiles_per_pixel
        h = self.height * self.tiles_per_pixel
        return (self.shift[0] - w / 2, self.shift[1] - h / 2, self.shift[0] + w / 2, self.shift[1] + h / 2)


@dataclass(frozen=True)
class WirePoints:
    copper: Vec
    red: Vec
    green: Vec


@dataclass(frozen=True)
class ConnectionPoints:
    """``connection_points[]`` entry for one direction frame."""

    wire: WirePoints
    shadow: WirePoints


@dataclass(frozen=True)
class PoleType:
    name: str  # Factorio prototype name, also the texture directory name
    title: str
    symbol_name: str  # name of the KiCad library symbol
    maximum_wire_distance: float  # tiles
    supply_area_distance: float  # tiles
    selection_box: tuple[Vec, Vec]
    picture: SpriteSheet
    shadow: SpriteSheet
    connection_points: tuple[ConnectionPoints, ConnectionPoints, ConnectionPoints, ConnectionPoints]

    @property
    def frames(self) -> int:
        return self.picture.frames


def _cp(wire: tuple[Vec, Vec, Vec], shadow: tuple[Vec, Vec, Vec]) -> ConnectionPoints:
    """Build connection points from (copper, red, green) triples."""
    return ConnectionPoints(wire=WirePoints(*wire), shadow=WirePoints(*shadow))


def _sheets(name: str, pic: tuple[int, int, Vec], shadow: tuple[int, int, Vec]) -> dict[str, SpriteSheet]:
    """``pictures.layers``: the pole itself and its shadow, both 4 frames at scale 0.5."""
    return {
        "picture": SpriteSheet(f"{name}/{name}.png", pic[0], pic[1], 4, pic[2], 0.5),
        "shadow": SpriteSheet(f"{name}/{name}-shadow.png", shadow[0], shadow[1], 4, shadow[2], 0.5),
    }


SMALL = PoleType(
    "small-electric-pole",
    "Small electric pole",
    "Small_Electric_Pole",
    maximum_wire_distance=7.5,
    supply_area_distance=2.5,
    selection_box=((-0.4, -0.4), (0.4, 0.4)),
    **_sheets("small-electric-pole", (72, 220, px(1.5, -42.5)), (256, 52, px(51, 3))),
    connection_points=(
        _cp((px(0.0, -82.5), px(13.0, -81.0), px(-12.5, -81.0)), (px(98.5, 2.5), px(111.0, 4.5), px(85.5, 4.0))),
        _cp((px(1.5, -81.0), px(12.0, -76.0), px(-6.0, -89.5)), (px(99.5, 4.0), px(110.0, 9.0), px(92.5, -4.0))),
        _cp((px(2.5, -79.5), px(4.0, -71.0), px(5.0, -89.5)), (px(100.5, 5.5), px(102.5, 14.5), px(103.5, -3.5))),
        _cp((px(0.5, -86.5), px(-10.5, -81.5), px(8.0, -93.5)), (px(98.5, -1.5), px(88.0, 3.5), px(106.0, -9.0))),
    ),
)

MEDIUM = PoleType(
    "medium-electric-pole",
    "Medium electric pole",
    "Medium_Electric_Pole",
    maximum_wire_distance=9.0,
    supply_area_distance=3.5,
    selection_box=((-0.5, -0.5), (0.5, 0.5)),
    **_sheets("medium-electric-pole", (84, 252, px(3.5, -44)), (280, 64, px(56.5, -1))),
    connection_points=(
        _cp((hr(15, -199), hr(43, -179), hr(-15, -185)), (hr(229, -13), hr(246, -2), hr(201, -2))),
        _cp((hr(15, -199), hr(27, -167), hr(-9, -200)), (hr(229, -13), hr(230, 10), hr(196, -23))),
        _cp((hr(15, -199), hr(5, -166), hr(13, -206)), (hr(229, -13), hr(208, 12), hr(217, -30))),
        _cp((hr(15, -199), hr(-12, -175), hr(36, -199)), (hr(229, -13), hr(195, 1), hr(238, -23))),
    ),
)

BIG = PoleType(
    "big-electric-pole",
    "Big electric pole",
    "Big_Electric_Pole",
    maximum_wire_distance=32.0,
    supply_area_distance=2.0,
    selection_box=((-1.0, -1.0), (1.0, 1.0)),
    **_sheets("big-electric-pole", (148, 312, px(0, -51)), (374, 94, px(60, 0))),
    connection_points=(
        _cp((hr(0, -246), hr(58, -211), hr(-58, -211)), (hr(245, -34), hr(301, 0), hr(206, 0))),
        _cp((hr(34, -235), hr(41, -183), hr(-40, -240)), (hr(279, -24), hr(284, 28), hr(204, -31))),
        _cp((hr(47, -212), hr(1, -170), hr(1, -251)), (hr(292, 0), hr(244, 41), hr(244, -41))),
        _cp((hr(33, -188), hr(-41, -182.5), hr(41, -239)), (hr(277, 23), hr(204, 30), hr(286, -29))),
    ),
)

POLE_TYPES: tuple[PoleType, ...] = (SMALL, MEDIUM, BIG)
BY_NAME: dict[str, PoleType] = {p.name: p for p in POLE_TYPES}
BY_SYMBOL: dict[str, PoleType] = {p.symbol_name: p for p in POLE_TYPES}

#: Name of the hidden symbol field that marks a symbol as a power pole.  Its value is the
#: prototype name (e.g. ``small-electric-pole``).
POLE_FIELD = "Factorio_Pole"

#: Factorio limits each pole to this many copper wire connections.
MAX_COPPER_CONNECTIONS = 5


def wire_reach(a: PoleType, b: PoleType) -> float:
    """Two poles can be wired if they are within reach of *both* of them."""
    return min(a.maximum_wire_distance, b.maximum_wire_distance)
