"""Pillow box configuration: defaults, validation, (de)serialization and schema versioning.

The configuration is a flat, frozen dataclass. All lengths are in millimetres.
``Config.from_dict`` is the single entry point for untrusted input (API requests, imported
SVG metadata, the persisted settings file, ``--set`` overrides); it either returns a fully
validated ``Config`` or raises ``ConfigError`` carrying one message per offending field.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, fields, replace
from typing import Any, Literal

from yanartas_pillowbox import crosssection

# Bumped whenever the meaning of saved settings changes; documents of any other version are
# rejected (no migrations).
SCHEMA_VERSION = 5

STROKE_WIDTH = 0.1  # mm, written to every line of the SVG

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

FieldKind = Literal["float", "bool", "str", "color", "choice"]


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
    # Show the field only when another field has a given value: (field, value).
    depends_on: tuple[str, Any] | None = None
    max_length: int | None = None
    # Not shown in the web UI (still settable via config files, imports and --set).
    hidden: bool = False
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
        if self.depends_on is not None:
            out["dependsOn"] = {"field": self.depends_on[0], "value": self.depends_on[1]}
        if self.max_length is not None:
            out["maxLength"] = self.max_length
        if self.hidden:
            out["hidden"] = True
        if self.action is not None:
            out["action"] = dict(zip(("id", "label", "title"), self.action, strict=True))
        return out


FIELD_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "width",
        "Box width",
        "float",
        "Body",
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
        "Body",
        "mm",
        10,
        2000,
        0.5,
        help="Interior length along the middle of the box, between the end walls (the "
        "shortest length between the curves). The straight edges are longer by the height "
        "plus three times the thickness.",
    ),
    FieldSpec(
        "height",
        "Box height",
        "float",
        "Body",
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
        "payload_margin",
        "Payload margin",
        "float",
        "Payload",
        "mm",
        0,
        100,
        0.25,
        help="Minimum clearance: the true distance from any point of the payload to the "
        "nearest point of the box surface.",
    ),
    FieldSpec("glue_tab_width", "Glue-tab width", "float", "Glue tab", "mm", 3, 100, 0.5),
    FieldSpec(
        "glue_tab_taper",
        "Glue-tab end taper",
        "float",
        "Glue tab",
        "mm",
        0,
        1000,
        0.5,
        help="How far each end of the glue tab is cut back along the length.",
    ),
    FieldSpec(
        "interior_walls",
        "Interior walls",
        "bool",
        "Interior walls",
        help="Extend each inner end flap into a bridge along the front panel and a second "
        "end wall, standing inside the doubled end wall. The box length stays the space "
        "between the end walls; the payload has to fit between the interior walls.",
    ),
    FieldSpec(
        "interior_wall_offset",
        "Interior wall offset",
        "float",
        "Interior walls",
        "mm",
        0,
        500,
        0.5,
        help="Clear gap between the inside of the doubled end wall and the outside of the "
        "interior wall.",
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
        "end: the one at the bottom.",
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
        "thickness",
        "Material thickness",
        "float",
        "Material",
        "mm",
        0,
        5,
        0.05,
        help="Width, height and length are interior dimensions; the pattern adds the material "
        "around them. The front panel's flaps close on the outside, flush with the body; "
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

    width: float = 55.0
    length: float = 120.0
    height: float = 20.0
    # Rectangular payload, inscribed centred in the closed box (preview only, not exported).
    payload_width: float = 30.0
    payload_depth: float = 95.0
    payload_height: float = 13.0
    payload_margin: float = 1.0
    glue_tab_width: float = 12.0
    glue_tab_taper: float = 9.0
    interior_walls: bool = True
    interior_wall_offset: float = 10.0
    fpc_cutout: str = "none"
    fpc_cutout_width: float = 15.0
    thickness: float = 0.2
    print_side: str = "outside"

    # ----------------------------------------------------------------- derived values
    @property
    def body(self) -> crosssection.Body:
        """Mid-surface geometry of the closed body around the interior (cached)."""
        return crosssection.solve_body(self.width, self.height, self.length, self.thickness)

    @property
    def edge_length(self) -> float:
        """Length of the straight body edges, corner to corner."""
        return crosssection.edge_length(self.length, self.height, self.thickness)

    @property
    def circumference(self) -> float:
        """Flat width of both body panels: the closed cross-section's mid-surface perimeter."""
        return self.body.circumference

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
    if spec.kind == "float":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("must be a number")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("must be a finite number")
        return value
    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise ValueError("must be true or false")
        return value
    if spec.kind == "color":
        if not isinstance(value, str) or not HEX_COLOR_RE.match(value.strip()):
            raise ValueError("must be a color like #FF0000")
        return value.strip().upper()
    if spec.kind == "choice":
        allowed = [c[0] for c in spec.choices]
        if value not in allowed:
            raise ValueError(f"must be one of {', '.join(allowed)}")
        return value
    if not isinstance(value, str):
        raise ValueError("must be text")
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
    if spec.kind == "bool":
        lowered = raw.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
        raise ConfigError({name: "must be true or false"})
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
        if spec.max_length is not None and len(value) > spec.max_length:  # pragma: no cover
            errors[spec.name] = f"must be at most {spec.max_length} characters"

    def add(name: str, msg: str) -> None:
        errors.setdefault(name, msg)

    if not errors.keys() & {"width", "height", "thickness"}:
        # The closed box needs |f'| <= 1 along the folds, i.e. the fold arcs may turn at most
        # 45 degrees at the corners (sagitta < 0.207 W). Keep a margin so the panels still
        # meet at a real fold: sagitta <= MAX_SAGITTA_RATIO * W for both panels, which bounds
        # the height for a given width (see crosssection.max_height).
        try:
            _ = cfg.body
        except ValueError:
            max_height = crosssection.max_height(cfg.width, cfg.thickness)
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

    # Checks below need the flat panel widths, which only exist for a valid body.
    body = None if errors.keys() & {"width", "height", "thickness"} else cfg.body

    if body is not None and "glue_tab_width" not in errors:
        panel = body.front.width
        if cfg.glue_tab_width >= panel:
            add(
                "glue_tab_width",
                f"must be narrower than the front panel ({_fmt(panel)} mm) since it is glued "
                "onto it",
            )

    walls = None
    if body is not None and cfg.interior_walls and "interior_wall_offset" not in errors:
        from yanartas_pillowbox.geometry import wall_layout  # geometry imports this module

        room = cfg.length - 2 * (cfg.interior_wall_offset + cfg.thickness)
        if "length" not in errors and room <= 0:
            add(
                "interior_wall_offset",
                f"leaves no room between the interior walls (at most "
                f"{_fmt(cfg.length / 2 - cfg.thickness)} mm for this length)",
            )
        try:
            walls = wall_layout(cfg)
        except ValueError:
            add("interior_walls", "the box is too low for interior walls")

    if body is not None and cfg.fpc_cutout != "none" and "fpc_cutout_width" not in errors:
        if walls is not None:  # the notches go through the bridge's folds
            limit, what = walls.ub - walls.ua - 1, "the interior walls' width"
            full = walls.ub - walls.ua
        else:
            limit, what, full = body.back.width - 1, "the inner flaps' width", body.back.width
        if cfg.fpc_cutout_width > limit:
            add(
                "fpc_cutout_width",
                f"must be at most {_fmt(limit)} mm ({what}, {_fmt(full)} mm, minus 1 mm)",
            )

    if "glue_tab_taper" not in errors and not errors.keys() & {"length", "height", "thickness"}:
        max_taper = cfg.edge_length / 2 - 1
        if cfg.glue_tab_taper > max_taper:
            add(
                "glue_tab_taper",
                f"must be at most {_fmt(max_taper)} mm (half the straight edge, "
                f"{_fmt(cfg.edge_length)} mm, minus 1 mm)",
            )

    return errors


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def field_specs_json() -> list[dict[str, Any]]:
    return [s.to_json() for s in FIELD_SPECS]
