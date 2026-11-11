"""Plugin settings.

Defaults can be overridden per project with a ``factorio-poles.json`` next to the
``.kicad_pro`` file, e.g.::

    {
        "tile_mm": 2.54,
        "textures": ["~/factorio/data/base/graphics/entity"],
        "connection_mode": "mesh"
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

SETTINGS_FILE = "factorio-poles.json"


@dataclass(frozen=True)
class Settings:
    #: Size of one Factorio tile on the schematic.  2.54 mm (100 mil) keeps every pole on
    #: the default grid and makes a small pole about as tall as a resistor is long.
    tile_mm: float = 2.54
    #: Extra texture roots, searched before a Factorio installation and the bundled art.
    #: Relative paths are relative to the project directory.
    textures: tuple[str, ...] = ()
    #: Look for textures in a local Factorio installation.
    use_factorio_install: bool = True
    #: Draw the pole shadows and wire shadows.
    shadows: bool = True
    #: Direction shadows fall in, degrees clockwise from "to the right" on the sheet:
    #: -45 = up-right, i.e. away from the viewer; 45 = down-right, towards the viewer.
    #: null keeps the game's direction (almost straight to the right).
    shadow_angle: float | None = -45.0
    #: Opacity of pole and wire shadows (Factorio itself uses about 0.5).
    shadow_opacity: float = 0.2
    #: "tree" (fewest wires) or "mesh" (every pole in reach, up to max_connections).
    connection_mode: str = "tree"
    #: Copper wire connections per pole (Factorio: 5).
    max_connections: int = 5
    #: Extra wire length as a fraction of the span; sets how far wires droop.
    wire_slack: float = 0.015
    wire_width_mm: float = 0.2
    wire_color: tuple[float, float, float, float] = (0.80, 0.42, 0.18, 1.0)
    #: Draw each stranded pole's wire reach when a net falls apart into several islands.
    mark_islands: bool = True
    island_color: tuple[float, float, float, float] = (0.85, 0.15, 0.10, 1.0)
    #: Seconds between checks in live mode.
    poll_interval: float = 0.5
    #: Seconds between full checks of the drawing in live mode (catches undo, deletions).
    verify_interval: float = 3.0
    #: Where the settings came from, for messages.
    source: str = field(default="defaults", compare=False)

    @property
    def tile_nm(self) -> float:
        return self.tile_mm * 1e6

    def validate(self) -> Settings:
        if self.tile_mm <= 0:
            raise ValueError("tile_mm must be positive")
        if self.connection_mode not in ("tree", "mesh"):
            raise ValueError('connection_mode must be "tree" or "mesh"')
        if self.max_connections < 1:
            raise ValueError("max_connections must be at least 1")
        if not 0 <= self.shadow_opacity <= 1:
            raise ValueError("shadow_opacity must be between 0 and 1")
        if not 0 <= self.wire_slack <= 0.5:
            raise ValueError("wire_slack must be between 0 and 0.5")
        return self


def load(project_dir: str | Path | None) -> Settings:
    """Settings for a project, with ``factorio-poles.json`` applied if present."""
    base = Settings()
    if not project_dir:
        return base
    path = Path(project_dir) / SETTINGS_FILE
    if not path.is_file():
        return base
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    known = {f.name: f for f in fields(Settings) if f.name != "source"}
    updates = {}
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"{path}: unknown setting {key!r} (known: {', '.join(sorted(known))})")
        if isinstance(value, list):
            value = tuple(value)
        if key == "textures":
            value = tuple(str((Path(project_dir) / Path(p).expanduser()).resolve()) for p in value)
        updates[key] = value
    return replace(base, **updates, source=str(path)).validate()
