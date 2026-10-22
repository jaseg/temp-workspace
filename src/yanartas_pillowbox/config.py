"""Pillow box configuration: defaults, validation, (de)serialization and schema versioning.

The configuration is a flat, frozen dataclass. All lengths are in millimetres.
``Config.from_dict`` is the single entry point for untrusted input (API requests, imported
SVG metadata, the persisted settings file, ``--set`` overrides); it either returns a fully
validated ``Config`` or raises ``ConfigError`` carrying one message per offending field.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace
from typing import Any, Literal

from yanartas_pillowbox import crosssection

# Bumped whenever the meaning of saved settings changes; documents of any other version are
# rejected (no migrations).
SCHEMA_VERSION = 12

STROKE_WIDTH = 0.1  # mm, written to every line of the SVG

FieldKind = Literal["float", "choice", "text"]


class ConfigError(ValueError):
    """Raised when a configuration is invalid. ``errors`` maps field names to messages."""

    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = dict(errors)
        super().__init__("; ".join(f"{k}: {v}" for k, v in self.errors.items()))


class SchemaVersionError(ValueError):
    """Raised when a document carries a missing or unsupported schema version."""


@dataclass(frozen=True)
class FieldSpec:
    """UI/validation metadata for one configuration field."""

    name: str
    label: str
    kind: FieldKind
    group: str
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    choices: tuple[tuple[str, str], ...] = ()
    help: str = ""
    # Per-field UI action button: (action id, button label, tooltip).
    action: tuple[str, str, str] | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "kind": self.kind,
            "group": self.group,
            "unit": self.unit,
            "help": self.help,
        }
        if self.minimum is not None:
            out["min"] = self.minimum
        if self.maximum is not None:
            out["max"] = self.maximum
        if self.step is not None:
            out["step"] = self.step
        if self.choices:
            out["choices"] = [{"value": v, "label": lbl} for v, lbl in self.choices]
        if self.action is not None:
            out["action"] = dict(zip(("id", "label", "title"), self.action, strict=True))
        return out


FIELD_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "pieces",
        "Pieces",
        "choice",
        "Shell",
        choices=(("one", "One piece"), ("two", "Two identical pieces")),
        help="One piece: the front and back panels in one, joined by a straight fold, with "
        "outer flaps on the front panel and inner flaps on the back one. Two identical "
        "pieces: each one panel with an outer flap at its top end and an inner flap at its "
        "bottom end, the FPC cable on its free edge and a glue tab on the other. The second "
        "piece, turned over (its print side inward: its folds go the other way), closes the "
        "box from below: each glue tab onto the other piece's free edge, each outer flap over "
        "the other's inner flap. The end wall gap is at each outer flap only; plug in both "
        "pieces' cables.",
    ),
    FieldSpec(
        "width",
        "Box width",
        "float",
        "Shell",
        "mm",
        10,
        1000,
        0.5,
        help="Interior width of the closed box's cross-section, from fold to fold (inside "
        "the material). The flat panel widths are derived from it, the height and the "
        "thickness.",
    ),
    FieldSpec(
        "length",
        "Box length",
        "float",
        "Shell",
        "mm",
        10,
        2000,
        0.5,
        help="Interior length along the middle of the box, between the inner end walls (the "
        "shortest length between the curves). The back panel's straight edges are longer by "
        "the height plus three times the thickness, the front panel's by twice the end wall "
        "gap more.",
    ),
    FieldSpec(
        "end_wall_gap",
        "End wall gap",
        "float",
        "Shell",
        "mm",
        0,
        500,
        0.5,
        help="Clear gap, in the middle of the box, between each outer end wall (the front "
        "panel's flap) and the inner end wall inside it (the back panel's flap). The front "
        "panel runs on past the inner walls to the outer walls, and a lid on each outer flap "
        "covers the gap. 0 stacks the walls on each other (no lid).",
    ),
    FieldSpec(
        "lid_overlap",
        "Lid overlap",
        "float",
        "Shell",
        "mm",
        0,
        200,
        0.5,
        help="How far each lid (folded over from the outer end wall's top edge, covering the "
        "end wall gap) runs on over the outside of the back panel, past the inner end wall. "
        "Only with an end wall gap.",
    ),
    FieldSpec(
        "lid_offset",
        "Lid offset",
        "float",
        "Shell",
        "mm",
        0,
        100,
        0.25,
        help="How far the lids float above the back panel where they come closest. The box's "
        "ends (the gaps, outer walls and lids) grow by as much in height, and wider to match: "
        "there the front panel's cross-section runs on past the side folds. Only with an end "
        "wall gap.",
    ),
    FieldSpec(
        "height",
        "Box height",
        "float",
        "Shell",
        "mm",
        0.5,
        640,
        0.5,
        help="Interior height of the closed box at maximum bulge. The curved folds bow into "
        "the panels by about half of this.",
    ),
    *(
        FieldSpec(
            f"payload_{axis}",
            f"Payload {axis}",
            "float",
            "Payload",
            "mm",
            0,
            2000,
            0.5,
            help=help_text,
            action=("maximize", "Max", f"Largest payload {axis} that fits the current box"),
        )
        for axis, help_text in (
            ("width", "Across the box (along the box width)."),
            ("depth", "Along the box length."),
            ("height", "Along the box height. Set any payload dimension to 0 to hide it."),
        )
    ),
    FieldSpec(
        "payload_clearance",
        "Payload clearance",
        "float",
        "Payload",
        "mm",
        0,
        100,
        0.25,
        help="The minimum true distance from any point of the payload to the "
        "nearest point of the box surface.",
    ),
    FieldSpec(
        "glue_tab_width",
        "Glue-tab width",
        "float",
        "Glue tab",
        "mm",
        3,
        100,
        0.5,
        help="Width of the glue tab, and of the lids' glue tabs (with an end wall gap). Their "
        "ends are cut back only as far as needed to stay off the curved folds, at most at 45 "
        "degrees.",
    ),
    FieldSpec(
        "fpc_cutout",
        "FPC cutout",
        "choice",
        "FPC cutout",
        choices=(
            ("none", "None"),
            ("front", "Front end"),
            ("back", "Back end"),
            ("both", "Both ends"),
        ),
        help="Cuts the top of the inner flaps' curved edge off level, leaving a slot between "
        "flap and box for a flat cable. Front end: the flap at the top of the pattern; back "
        "end: the one at the bottom. Two pieces: any of them cuts the piece's inner flap "
        "(both pieces').",
    ),
    FieldSpec(
        "fpc_cutout_width",
        "FPC cutout width",
        "float",
        "FPC cutout",
        "mm",
        0,
        1000,
        0.5,
        help="Width of the flat section, around the top of the inner flap's edge (within "
        "about a millimetre of its centre).",
    ),
    FieldSpec(
        "fpc_cable",
        "FPC cable",
        "choice",
        "FPC cable",
        choices=(
            ("none", "None"),
            ("up", "Up (towards the front end)"),
            ("down", "Down (towards the back end)"),
        ),
        help="A flat cable of the flex PCB, leaving the front panel's free straight edge (the "
        "glued edge) outward, turning up or down along it and meandering in rows beside it. "
        "Every corner folds flat along its diagonal, so the cable becomes one straight strip. "
        "Up: towards the top of the pattern (the box's front end); down: towards the bottom. "
        "Where it leaves the edge: see Cable entry.",
    ),
    FieldSpec(
        "fpc_entry_offset",
        "Cable entry",
        "float",
        "FPC cable",
        "mm",
        0,
        2000,
        0.5,
        help="Where the cable leaves the free edge: how far from the lowest it can go (cable "
        "turning up; the highest, turning down). Folded into the box, the cable's first "
        "corner lies on the back panel beside the edge, and must stay clear of the inner "
        "flap at that end: 0 puts it as near as that allows.",
    ),
    FieldSpec(
        "fpc_cable_length",
        "Cable length",
        "float",
        "FPC cable",
        "mm",
        10,
        2000,
        1,
        help="From the front panel's edge to the plug's tip, once every corner is folded "
        "flat. Rows that do not fit beside the edge make the pattern wider.",
    ),
    FieldSpec(
        "fpc_pins",
        "Pin count",
        "float",
        "FPC cable",
        "",
        2,
        200,
        1,
        help="Contacts of the FPC connector.",
    ),
    FieldSpec(
        "fpc_pitch",
        "Pin pitch",
        "float",
        "FPC cable",
        "mm",
        0.1,
        2.54,
        0.05,
    ),
    FieldSpec(
        "fpc_edge_margin",
        "Plug edge margin",
        "float",
        "FPC cable",
        "mm",
        0,
        10,
        0.05,
        help="From the outermost contacts' centres to the plug's edges. The plug is (pins - 1) "
        "x pitch + 2 x this wide (standard: one pitch, (pins + 1) x pitch overall).",
    ),
    FieldSpec(
        "fpc_plug_length",
        "Plug length",
        "float",
        "FPC cable",
        "mm",
        1,
        50,
        0.25,
        help="Length of the plug at the cable's end: the part that goes into the connector "
        "(the contacts and the stiffener behind them).",
    ),
    FieldSpec(
        "fpc_cable_inset",
        "Cable inset",
        "float",
        "FPC cable",
        "mm",
        0,
        10,
        0.05,
        help="How much narrower than the plug the rest of the cable is on each side (0: the "
        "same width). The plug's ears then stick out beside the cable.",
    ),
    FieldSpec(
        "fpc_corner_radius",
        "Cable corner radius",
        "float",
        "FPC cable",
        "mm",
        0,
        10,
        0.1,
        help="Rounds every corner of the cable's outline, and where it meets the front panel. "
        "Smaller where the outline leaves no room (e.g. at the ends of the slots between "
        "rows: at most half the clearance).",
    ),
    FieldSpec(
        "fpc_cable_gap",
        "Cable clearance",
        "float",
        "FPC cable",
        "mm",
        0.1,
        20,
        0.1,
        help="Cut-to-cut distance between the cable's rows, and between the cable and the "
        "rest of the pattern.",
    ),
    FieldSpec(
        "mesh_trace_width",
        "Mesh trace width",
        "float",
        "PCB mesh",
        "mm",
        0.05,
        2,
        0.01,
        help="Width of the security mesh's traces (both copper layers, and on the cable).",
    ),
    FieldSpec(
        "mesh_trace_space",
        "Mesh trace space (minimum)",
        "float",
        "PCB mesh",
        "mm",
        0.05,
        2,
        0.01,
        help="Least copper-to-copper space between the mesh's traces: the layout never goes "
        "below it, and the design rules check it. Settled, the traces spread into the room "
        "left over, so the average space comes out larger: about 20 % with the space-filling "
        "curve, 5 % with the KiMesh grid (see Average space under the mesh's figures).",
    ),
    FieldSpec(
        "mesh_traces",
        "Traces per partition",
        "float",
        "PCB mesh",
        "",
        1,
        16,
        1,
        help="Mesh traces (loops, two ends each) on each side of the foil: for the "
        "space-filling curve, in each partition (see Mesh partitions); for KiMesh, in all. "
        "Their ends leave through the FPC cable. The exit cell is twice as many trace pitches "
        "wide as a side has traces.",
    ),
    FieldSpec(
        "mesh_partitions",
        "Mesh partitions",
        "float",
        "PCB mesh",
        "",
        1,
        16,
        1,
        help="Space-filling curve: the mesh's area on each side is split into this many "
        "partitions of equal area, each with Mesh traces traces of its own from the "
        "connector. KiMesh ignores it.",
    ),
    FieldSpec(
        "mesh_edge_clearance",
        "Mesh edge clearance",
        "float",
        "PCB mesh",
        "mm",
        0,
        10,
        0.05,
        help="Distance the mesh keeps from the foil's cut edges and slits.",
    ),
    FieldSpec(
        "mesh_seed",
        "Mesh seed",
        "text",
        "PCB mesh",
        help="Seed of the mesh's random walk, any text: the same seed gives the same mesh.",
        action=("randomize", "\u2684", "Randomize: a new random seed"),
    ),
    FieldSpec(
        "mesh_algorithm",
        "Mesh layout",
        "choice",
        "PCB mesh",
        choices=(
            ("kimesh", "KiMesh grid"),
            ("sfc", "Space-filling curve (slow)"),
        ),
        help="How the mesh is laid out. KiMesh: tiles on a square grid of cells, walked by "
        "a random spanning tree; fast, but whole cells only, so strips along the edges stay "
        "bare. Space-filling curve (after Bedel et al., 2022): one closed curve through "
        "each panel, the panels joined across the folds as seldom as can be, the traces "
        "offset from it and spread to share its spacing; follows the edges and folds, "
        "but takes a minute or more per layer.",
    ),
    FieldSpec(
        "mesh_shape",
        "Mesh traces",
        "choice",
        "PCB mesh",
        choices=(
            ("lines", "Straight segments"),
            ("arcs", "Lines and arcs"),
        ),
        help="Space-filling curve: how its traces are drawn. Straight segments: the "
        "smooth curve through each trace's vertices, no two segments turning more than 10° "
        "(but where that would bring copper closer). Lines and arcs: that curve redrawn in "
        "straight lines and circular arcs (KiCad track arcs) within the polyline's own error "
        "(up to 3 % of the pitch where it has room to the copper beside it), for far fewer, "
        "smoother pieces.",
    ),
    FieldSpec(
        "mesh_back_offset",
        "Back mesh offset",
        "choice",
        "PCB mesh",
        choices=(
            ("cell", "Half a cell"),
            ("cell_trace", "Half a cell plus a trace width"),
        ),
        help="KiMesh: how far the back (B.Cu) mesh's grid is offset from the front one's, "
        "in x and y: half a cell, so that the two layers leave different strips bare along "
        "the edges; "
        "plus a trace width, so that its traces also lie over the front traces' gaps.",
    ),
    FieldSpec(
        "thickness",
        "Material thickness",
        "float",
        "Material",
        "mm",
        0,
        5,
        0.05,
        help="Width, height and length are interior dimensions; the pattern adds the material "
        "around them. The front panel's flaps close on the outside, flush with the shell; "
        "the back panel's flaps are shortened to fit inside.",
    ),
    FieldSpec(
        "print_side",
        "Print side",
        "choice",
        "Material",
        choices=(("outside", "Outside of the box"), ("inside", "Inside of the box")),
        help="Which side of the material the fold indicators are drawn for (e.g. the side "
        "the laser scores). Only switches the fold lines between mountain (dash-dot) and "
        "valley (dashed); the pattern itself is the same either way.",
    ),
)

SPECS_BY_NAME: dict[str, FieldSpec] = {s.name: s for s in FIELD_SPECS}


@dataclass(frozen=True)
class Config:
    """A complete, validated pillow box configuration. Lengths in mm."""

    # The defaults fit the "Raspberry Pi Model B + HAT" payload preset with its clearance.
    width: float = 107.0
    length: float = 101.0
    height: float = 48.5
    pieces: str = "one"
    end_wall_gap: float = 10.0
    lid_overlap: float = 5.0
    lid_offset: float = 2.0
    # Rectangular payload, inscribed centred in the closed box (preview only, not exported).
    payload_width: float = 56.0
    payload_depth: float = 85.0
    payload_height: float = 22.0
    payload_clearance: float = 8.0
    glue_tab_width: float = 12.0
    fpc_cutout: str = "none"
    fpc_cutout_width: float = 15.0
    fpc_cable: str = "up"
    fpc_entry_offset: float = 0.0  # (0: the lowest it can go, the cable turning up)
    fpc_cable_length: float = 55.0  # (one row, beside the default pattern's free edge)
    fpc_pins: float = 61.0  # (the default curve mesh's ends and GND pins take 55)
    fpc_pitch: float = 0.5
    fpc_edge_margin: float = 0.5
    fpc_plug_length: float = 4.0
    fpc_cable_inset: float = 0.0
    fpc_corner_radius: float = 1.0
    fpc_cable_gap: float = 1.0
    mesh_trace_width: float = 0.15
    mesh_trace_space: float = 0.15
    mesh_traces: float = 4.0
    mesh_partitions: float = 3.0
    mesh_edge_clearance: float = 0.5
    mesh_seed: str = "0"
    mesh_algorithm: str = "kimesh"
    mesh_shape: str = "lines"
    mesh_back_offset: str = "cell"
    thickness: float = 0.2
    print_side: str = "outside"

    # ----------------------------------------------------------------- derived values
    @property
    def seed(self) -> bytes:
        """``mesh_seed`` distilled into the layout's 256-bit random key (``rand.key_of``)."""
        from yanartas_pillowbox import rand

        return rand.key_of(self.mesh_seed)

    @property
    def two_piece(self) -> bool:
        return self.pieces == "two"

    @property
    def shell(self) -> crosssection.Shell:
        """Mid-surface geometry of the closed shell around the interior (cached)."""
        solve = crosssection.solve_two_piece if self.two_piece else crosssection.solve_shell
        return solve(self.width, self.height, self.length, self.thickness)

    @property
    def edge_length(self) -> float:
        """Length of the back panel's straight edges (and the glue tab's), corner to corner."""
        return crosssection.edge_length(self.length, self.height, self.thickness)

    @property
    def front_length(self) -> float:
        """Length of the front panel's straight edges, corner to corner: the box overall. The
        front panel runs on by the end wall gap at each end. Two pieces: each piece's
        panel's, one end wall gap longer (at its outer flap)."""
        return self.edge_length + (1 if self.two_piece else 2) * self.end_wall_gap

    @property
    def inner_offset(self) -> float:
        """How far the inner flap's panel's ends stand in from the outer flap's at each end
        (corner line to corner line): the end wall gap; two pieces, a thickness more (their
        folds bow in alike, so the outer wall's thickness comes from the panel's length)."""
        return self.end_wall_gap + (self.thickness if self.two_piece else 0.0)

    @property
    def mesh_nets(self) -> int:
        """The mesh's nets (loops) on each copper layer: the space-filling curve's traces in
        all its partitions; KiMesh's traces."""
        traces = int(self.mesh_traces)
        return traces * int(self.mesh_partitions) if self.mesh_algorithm == "sfc" else traces

    # -------------------------------------------------------------- (de)serialization
    def to_dict(self) -> dict[str, Any]:
        """JSON-ready dict including the schema ``version``."""
        out: dict[str, Any] = {"version": SCHEMA_VERSION}
        for f in fields(self):
            out[f.name] = getattr(self, f.name)
        return out

    @classmethod
    def defaults(cls) -> Config:
        return cls()

    @classmethod
    def from_dict(cls, data: Any, *, require_version: bool = False) -> Config:
        """Build and validate a config from untrusted data.

        Missing fields take their defaults; unknown keys are ignored. If ``version`` is
        present (or required) it must be ``SCHEMA_VERSION``.
        """
        if not isinstance(data, dict):
            raise ConfigError({"_": "configuration must be a JSON object"})
        check_version(data, required=require_version)

        defaults = cls.defaults()
        values: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for spec in FIELD_SPECS:
            if spec.name not in data:
                continue
            try:
                values[spec.name] = _coerce(spec, data[spec.name])
            except ValueError as exc:
                errors[spec.name] = str(exc)

        cfg = replace(defaults, **values)
        for name, msg in validate(cfg).items():
            errors.setdefault(name, msg)
        if errors:
            raise ConfigError(errors)
        return cfg

    def with_values(self, **changes: Any) -> Config:
        """Return a validated copy with ``changes`` applied."""
        return Config.from_dict({**self.to_dict(), **changes})


def check_version(data: dict[str, Any], *, required: bool) -> None:
    if "version" not in data:
        if required:
            raise SchemaVersionError("configuration has no schema version")
        return
    version = data["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise SchemaVersionError(f"invalid schema version {version!r}")
    if version != SCHEMA_VERSION:
        raise SchemaVersionError(
            f"configuration uses schema version {version}; "
            f"this version of yanartas-pillowbox supports version {SCHEMA_VERSION}"
        )


def _coerce(spec: FieldSpec, value: Any) -> Any:
    if spec.kind == "text":
        if not isinstance(value, str):
            raise ValueError("must be text")
        return value
    if spec.kind == "float":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("must be a number")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("must be a finite number")
        return value
    allowed = [c[0] for c in spec.choices]
    if value not in allowed:
        raise ValueError(f"must be one of {', '.join(allowed)}")
    return value


def parse_cli_value(name: str, raw: str) -> Any:
    """Parse a ``--set key=value`` string into the field's native type."""
    spec = SPECS_BY_NAME.get(name)
    if spec is None:
        raise ConfigError({name: f"unknown parameter (known: {', '.join(SPECS_BY_NAME)})"})
    if spec.kind == "float":
        try:
            return float(raw)
        except ValueError:
            raise ConfigError({name: "must be a number"}) from None
    return raw


def validate(cfg: Config) -> dict[str, str]:
    """Range and cross-field checks. Returns ``{field: message}`` (empty when valid)."""
    errors: dict[str, str] = {}

    for spec in FIELD_SPECS:
        value = getattr(cfg, spec.name)
        if spec.kind == "float":
            if spec.minimum is not None and value < spec.minimum:
                errors[spec.name] = f"must be at least {_fmt(spec.minimum)} {spec.unit}".strip()
            elif spec.maximum is not None and value > spec.maximum:
                errors[spec.name] = f"must be at most {_fmt(spec.maximum)} {spec.unit}".strip()

    def add(name: str, msg: str) -> None:
        errors.setdefault(name, msg)

    if not errors.keys() & {"width", "height", "thickness"}:
        # The closed box needs |f'| <= 1 along the folds, i.e. the fold arcs may turn at most
        # 45 degrees at the corners (sagitta < 0.207 W). Keep a margin so the panels still
        # meet at a real fold: sagitta <= MAX_SAGITTA_RATIO * W for both panels, which bounds
        # the height for a given width (see crosssection.max_height).
        try:
            _ = cfg.shell
        except ValueError:
            max_height = crosssection.max_height(cfg.width, cfg.thickness, cfg.two_piece)
            add(
                "height",
                f"must be at most {_fmt(max_height - 0.005)} mm for a {_fmt(cfg.width)} mm "
                "wide box (steeper flap arcs cannot close)",
            )
    if "thickness" not in errors and "height" not in errors and cfg.height - cfg.thickness < 0.5:
        add(
            "thickness",
            "too thick for this height: the inner flaps need half of (height - thickness) "
            "to be at least 0.25 mm",
        )

    # Checks below need the flat panel widths, which only exist for a valid shell.
    shell = None if errors.keys() & {"width", "height", "thickness"} else cfg.shell

    if shell is not None and "glue_tab_width" not in errors:
        panel = shell.front.width
        if cfg.glue_tab_width >= panel:
            add(
                "glue_tab_width",
                f"must be narrower than the front panel ({_fmt(panel)} mm) since it is glued "
                "onto it",
            )

    if (
        shell is not None
        and cfg.end_wall_gap > 0
        and not errors.keys() & {"end_wall_gap", "lid_offset"}
    ):
        # (geometry imports this module)
        from yanartas_pillowbox.geometry import max_lid_offset, min_lid_width

        limit = max_lid_offset(shell)
        if limit < 0:
            add(
                "end_wall_gap",
                "this box's cross-section is too steep at the sides for the lids (set the "
                "gap to 0, or make the box flatter)",
            )
        elif cfg.lid_offset > limit:
            wide = min_lid_width(cfg)
            hint = f"; a box at least {_fmt(wide)} mm wide allows it" if wide is not None else ""
            add(
                "lid_offset",
                f"must be at most {_fmt(math.floor(limit * 100) / 100)} mm for this box (the "
                f"widened ends would have to turn past 45 degrees at the sides){hint}",
            )

    if shell is not None and cfg.fpc_cutout != "none" and "fpc_cutout_width" not in errors:
        limit = shell.back.width - 1
        if cfg.fpc_cutout_width > limit:
            add(
                "fpc_cutout_width",
                f"must be at most {_fmt(limit)} mm (the inner flaps' width, "
                f"{_fmt(shell.back.width)} mm, minus 1 mm)",
            )

    fpc_fields = {
        "fpc_cable",
        "fpc_entry_offset",
        "fpc_cable_length",
        "fpc_pins",
        "fpc_pitch",
        "fpc_edge_margin",
        "fpc_plug_length",
        "fpc_cable_inset",
        "fpc_corner_radius",
        "fpc_cable_gap",
    }
    if cfg.fpc_cable != "none" and "fpc_pins" not in errors and cfg.fpc_pins != int(cfg.fpc_pins):
        add("fpc_pins", "must be a whole number")
    for name in ("mesh_traces", "mesh_partitions"):
        if name not in errors and getattr(cfg, name) != int(getattr(cfg, name)):
            add(name, "must be a whole number")
    if shell is not None and cfg.fpc_cable != "none" and not errors.keys() & fpc_fields:
        from yanartas_pillowbox import fpc  # (fpc imports this module)

        width = fpc.cable_width(cfg)
        edge = cfg.edge_length - 1  # (between the end sections, beside the back panel)
        if width <= 0:
            add("fpc_cable_inset", "leaves no cable: must be less than half the plug's width")
        elif width > edge:
            add(
                "fpc_pins",
                f"the cable ({_fmt(width)} mm) must be at most {_fmt(edge)} mm wide (the front "
                "panel's free edge beside the back panel, minus 1 mm)",
            )
        elif "end_wall_gap" not in errors and "lid_offset" not in errors:
            try:
                fpc.layout(cfg)
            except fpc.CableError as exc:
                add(exc.field, str(exc))

    return errors


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def field_specs_json() -> list[dict[str, Any]]:
    return [s.to_json() for s in FIELD_SPECS]
