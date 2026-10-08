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

SCHEMA_VERSION = 1

# Largest fold sagitta, as a fraction of the box width, that can still close (see geometry).
MAX_SAGITTA_RATIO = 0.2

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
        return out


ARC_MODES = (("depth", "From box depth"), ("sagitta", "Arc sagitta directly"))

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
        help="Width of one body panel (across the curved flap).",
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
        help="Length of the straight body edge, corner to corner.",
    ),
    FieldSpec(
        "arc_mode",
        "Arc geometry",
        "choice",
        "Curved flaps",
        choices=ARC_MODES,
        help="Derive the flap arc from the target depth, or set its sagitta directly.",
    ),
    FieldSpec(
        "depth",
        "Box depth",
        "float",
        "Curved flaps",
        "mm",
        0.5,
        640,
        0.5,
        help="Total thickness of the closed box at maximum bulge.",
        depends_on=("arc_mode", "depth"),
    ),
    FieldSpec(
        "sagitta",
        "Arc sagitta",
        "float",
        "Curved flaps",
        "mm",
        0.25,
        320,
        0.25,
        help="How far the curved fold bows into the panel (arc height over its chord).",
        depends_on=("arc_mode", "sagitta"),
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
        "thickness",
        "Material thickness",
        "float",
        "Material",
        "mm",
        0,
        5,
        0.05,
        help="Curved folds are offset by half of this so the flaps clear each other.",
    ),
    FieldSpec(
        "stroke_width",
        "Stroke width",
        "float",
        "Material",
        "mm",
        0.001,
        2,
        0.01,
        help="Hairline stroke width written to every line.",
    ),
    FieldSpec("color_cut", "Cut outline", "color", "Line colors"),
    FieldSpec("color_fold_straight", "Straight folds", "color", "Line colors"),
    FieldSpec("color_fold_curved", "Curved flap folds", "color", "Line colors"),
    FieldSpec("color_fold_glue", "Glue-tab fold", "color", "Line colors"),
    FieldSpec("thumb_notch", "Thumb notch on flaps", "bool", "Extras"),
    FieldSpec(
        "thumb_notch_radius",
        "Thumb-notch radius",
        "float",
        "Extras",
        "mm",
        1,
        100,
        0.5,
        depends_on=("thumb_notch", True),
    ),
    FieldSpec(
        "label",
        "Text label",
        "bool",
        "Extras",
        help="Engraved text on the front panel, in its own layer and color.",
    ),
    FieldSpec(
        "label_text", "Label text", "str", "Extras", depends_on=("label", True), max_length=64
    ),
    FieldSpec(
        "label_size", "Label size", "float", "Extras", "mm", 1, 100, 0.5, depends_on=("label", True)
    ),
    FieldSpec("color_label", "Label color", "color", "Extras", depends_on=("label", True)),
)

SPECS_BY_NAME: dict[str, FieldSpec] = {s.name: s for s in FIELD_SPECS}


@dataclass(frozen=True)
class Config:
    """A complete, validated pillow box configuration. Lengths in mm."""

    width: float = 60.0
    length: float = 120.0
    arc_mode: str = "depth"
    depth: float = 20.0
    sagitta: float = 10.0
    glue_tab_width: float = 12.0
    glue_tab_taper: float = 9.0
    thickness: float = 0.4
    stroke_width: float = 0.1
    color_cut: str = "#FF0000"
    color_fold_straight: str = "#0000FF"
    color_fold_curved: str = "#00A000"
    color_fold_glue: str = "#FF00FF"
    thumb_notch: bool = False
    thumb_notch_radius: float = 8.0
    label: bool = False
    label_text: str = "yanartas"
    label_size: float = 6.0
    color_label: str = "#000000"

    # ----------------------------------------------------------------- derived values
    @property
    def fold_sagitta(self) -> float:
        """Sagitta of the curved fold (how far it bows into the panel)."""
        return self.depth / 2 if self.arc_mode == "depth" else self.sagitta

    @property
    def cut_sagitta(self) -> float:
        """Sagitta of the flap's cut edge; smaller than the fold by half the thickness."""
        return self.fold_sagitta - self.thickness / 2

    @property
    def box_depth(self) -> float:
        return 2 * self.fold_sagitta

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
        present (or required) it must equal ``SCHEMA_VERSION``.
        """
        if not isinstance(data, dict):
            raise ConfigError({"_": "configuration must be a JSON object"})
        check_version(data, required=require_version)

        defaults = cls()
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
        if spec.max_length is not None and len(value) > spec.max_length:
            errors[spec.name] = f"must be at most {spec.max_length} characters"

    def add(name: str, msg: str) -> None:
        errors.setdefault(name, msg)

    arc_field = "depth" if cfg.arc_mode == "depth" else "sagitta"
    if arc_field not in errors and "width" not in errors:
        # The closed box needs |f'| <= 1 along the fold, i.e. the fold arc may turn at most
        # 45 degrees at the corners (sagitta < 0.207 W). Keep a margin so the panels still
        # meet at a real fold: sagitta <= MAX_SAGITTA_RATIO * W.
        max_sag = MAX_SAGITTA_RATIO * cfg.width
        if cfg.fold_sagitta > max_sag:
            limit = 2 * max_sag if arc_field == "depth" else max_sag
            add(
                arc_field,
                f"must be at most {_fmt(limit)} mm for a {_fmt(cfg.width)} mm wide box "
                "(steeper flap arcs cannot close)",
            )
    if "thickness" not in errors and arc_field not in errors and cfg.cut_sagitta < 0.25:
        add(
            "thickness",
            "too thick for this arc: half the thickness must stay 0.25 mm "
            f"below the fold sagitta ({_fmt(cfg.fold_sagitta)} mm)",
        )

    if "length" not in errors and arc_field not in errors:
        # The curved folds at both ends bow into the panel; they must not meet in the middle.
        min_length = 2 * cfg.fold_sagitta + 1
        if cfg.length < min_length:
            add(
                "length",
                f"must be at least {_fmt(min_length)} mm for this arc "
                "(the curved folds at both ends would cross)",
            )

    if "glue_tab_width" not in errors and "width" not in errors and cfg.glue_tab_width >= cfg.width:
        add("glue_tab_width", "must be narrower than the box width (it is glued inside)")

    if "glue_tab_taper" not in errors and "length" not in errors:
        max_taper = cfg.length / 2 - 1
        if cfg.glue_tab_taper > max_taper:
            add(
                "glue_tab_taper",
                f"must be at most {_fmt(max_taper)} mm (half the box length minus 1 mm)",
            )

    if (
        cfg.thumb_notch
        and "thumb_notch_radius" not in errors
        and not (errors.keys() & {"width", arc_field, "thickness"})
    ):
        # The notch is centred on the flap's cut apex and must stay clear of the fold.
        flap_height = cfg.cut_sagitta + cfg.fold_sagitta
        max_r = min(flap_height - 1.0, cfg.width / 3)
        if cfg.thumb_notch_radius > max_r:
            if max_r < 1:
                add("thumb_notch_radius", "the flaps are too small for a thumb notch")
            else:
                add("thumb_notch_radius", f"must be at most {_fmt(max_r)} mm for this flap")

    if cfg.label and "label_text" not in errors and not cfg.label_text.strip():
        add("label_text", "enter some text or disable the label")

    return errors


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def field_specs_json() -> list[dict[str, Any]]:
    return [s.to_json() for s in FIELD_SPECS]
