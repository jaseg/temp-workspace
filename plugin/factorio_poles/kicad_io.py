"""Read poles from, and write power lines to, a schematic open in KiCad (IPC API).

Every item the plugin draws is locked and carries a custom property ``factorio_poles``
whose value is ``<key>|<sig>``:

* ``key`` names what the item is (``pole:<uuid>``, ``wire:<uuid>:<uuid>``, ...)
* ``sig`` is a digest of what it should look like

so a later run only touches items whose poles actually moved or changed.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from kipy.common_types import Circle, Color, CustomProperty, Polygon
from kipy.geometry import PolygonWithHoles, PolyLine, PolyLineNode, Vector2
from kipy.proto.common.commands import editor_commands_pb2
from kipy.proto.common.types import base_types_pb2
from kipy.proto.common.types.enums_pb2 import StrokeLineStyle
from kipy.schematic import Schematic
from kipy.schematic_types import SchematicGraphicShape, SchematicImage, SchematicSymbolInstance, unwrap
from kipy.util.proto import pack_any

from .config import Settings
from .network import Pole
from .plan import IU_NM, CircleSpec, ImageSpec, Plan, PolylineSpec, Spec, make_plan
from .prototypes import BY_NAME, BY_SYMBOL, POLE_FIELD, PoleType
from .textures import TexturePack

PROP = "factorio_poles"


class SyncError(Exception):
    pass


# ---------------------------------------------------------------------------
# Low-level item helpers.  kicad-python's Schematic.create_items/update_items unpack the
# reply twice (kicad-python 0.9.0.dev, KiCad 10.99); talk to the API directly instead.


def _check(response, field_name: str, what: str) -> list:
    if response.status != base_types_pb2.ItemRequestStatus.IRS_OK:
        raise SyncError(f"failed to {what} items: {response.status}")
    out, failures = [], []
    for result in getattr(response, field_name):
        if result.status.code != editor_commands_pb2.ItemStatusCode.ISC_OK:
            failures.append(result.status.error_message or editor_commands_pb2.ItemStatusCode.Name(result.status.code))
        else:
            out.append(unwrap(result.item))
    if failures:
        raise SyncError(f"failed to {what} items: " + "; ".join(failures))
    return out


def create_items(sch: Schematic, items: Sequence) -> list:
    if not items:
        return []
    cmd = editor_commands_pb2.CreateItems()
    cmd.header.document.CopyFrom(sch.document)
    cmd.items.extend(pack_any(i.proto) for i in items)
    return _check(sch.client.send(cmd, editor_commands_pb2.CreateItemsResponse), "created_items", "create")


def update_items(sch: Schematic, items: Sequence) -> list:
    if not items:
        return []
    cmd = editor_commands_pb2.UpdateItems()
    cmd.header.document.CopyFrom(sch.document)
    cmd.items.extend(pack_any(i.proto) for i in items)
    return _check(sch.client.send(cmd, editor_commands_pb2.UpdateItemsResponse), "updated_items", "update")


# ---------------------------------------------------------------------------
# Reading


def pole_type_of(sym: SchematicSymbolInstance) -> PoleType | None:
    """Poles are recognised by their hidden ``Factorio_Pole`` field, falling back to the
    library symbol name (in case the field was deleted from an instance)."""
    for f in list(sym.user_fields) + list(sym.definition.fields):
        if f.name == POLE_FIELD:
            t = BY_NAME.get(f.text.value.strip())
            if t is not None:
                return t
    return BY_SYMBOL.get(sym.proto.lib_id.entry_name) or BY_SYMBOL.get(sym.definition.id.name)


def read_poles(sch: Schematic, settings: Settings) -> list[Pole]:
    poles = []
    for sym in sch.get_symbols():
        t = pole_type_of(sym)
        if t is None:
            continue
        pos = sym.position
        poles.append(
            Pole(
                id=sym.id.value,
                net=sym.value.strip(),
                type=t,
                position=(pos.x / settings.tile_nm, pos.y / settings.tile_nm),
            )
        )
    return poles


def _tag(item) -> tuple[str, str] | None:
    for p in item.custom_properties:
        if p.key == PROP:
            key, _, sig = p.value.partition("|")
            return key, sig
    return None


def generated_items(sch: Schematic) -> dict[str, list[tuple[object, str]]]:
    """Generated items on this sheet, by key (normally one item per key)."""
    out: dict[str, list[tuple[object, str]]] = {}
    for item in sch.get_items():
        if not isinstance(item, (SchematicImage, SchematicGraphicShape)):
            continue
        tag = _tag(item)
        if tag is not None:
            out.setdefault(tag[0], []).append((item, tag[1]))
    return out


# ---------------------------------------------------------------------------
# Building


def _color(c: tuple[float, float, float, float]) -> Color:
    col = Color()
    col.red, col.green, col.blue, col.alpha = c
    return col


def _prop(spec: Spec) -> CustomProperty:
    p = CustomProperty()
    p.key = PROP
    p.value = f"{spec.key}|{spec.sig}"
    return p


def build(spec: Spec):
    if isinstance(spec, ImageSpec):
        img = SchematicImage()
        img.position = Vector2.from_xy(*spec.position)
        img.image_data = spec.png
        img.image_scale = spec.scale
        img.proto.opacity = 1.0  # not wrapped by kicad-python yet; 0 would be invisible
        img.locked = True
        img.custom_properties = [_prop(spec)]
        return img
    if isinstance(spec, PolylineSpec):
        line = PolyLine()
        for x, y in spec.points:
            line.append(PolyLineNode.from_point(Vector2.from_xy(x, y)))
        outline = PolygonWithHoles()
        outline.outline = line
        # Newer kicad-python closes assigned outlines by default; a wire is an open polyline.
        outline.proto.outline.closed = False
        geom = Polygon()
        geom.polygons.append(outline)
        _stroke(geom, spec.width, spec.color, spec.dashed)
        return _shape(geom, spec)
    if isinstance(spec, CircleSpec):
        geom = Circle.from_center_radius(Vector2.from_xy(*spec.center), spec.radius)
        _stroke(geom, spec.width, spec.color, spec.dashed)
        return _shape(geom, spec)
    raise TypeError(spec)


def _stroke(geom, width: int, color, dashed: bool) -> None:
    stroke = geom.attributes.stroke
    stroke.width = width
    stroke.color = _color(color)
    stroke.style = StrokeLineStyle.SLS_DASH if dashed else StrokeLineStyle.SLS_SOLID


def _shape(geom, spec: Spec) -> SchematicGraphicShape:
    shape = SchematicGraphicShape()
    shape.shape = geom
    shape.locked = True
    shape.custom_properties = [_prop(spec)]
    return shape


# ---------------------------------------------------------------------------
# Syncing


@dataclass
class SheetResult:
    sheet: str
    poles: int = 0
    created: int = 0
    updated: int = 0
    removed: int = 0
    plan: Plan | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated or self.removed)


def diff(desired: Sequence[Spec], existing: dict[str, list[tuple[object, str]]]):
    """Split into (to_create, to_update, to_remove)."""
    want = {s.key: s for s in desired}
    create: list[Spec] = []
    update: list[object] = []
    remove: list[object] = []
    for key, entries in existing.items():
        spec = want.get(key)
        keep = None
        for item, sig in entries:
            if keep is None and spec is not None and sig == spec.sig:
                keep = item
            else:
                remove.append(item)
        if spec is not None and keep is None:
            create.append(spec)
        elif spec is not None and isinstance(spec, ImageSpec):
            pos = keep.position
            if abs(pos.x - spec.position[0]) > IU_NM or abs(pos.y - spec.position[1]) > IU_NM:
                keep.position = Vector2.from_xy(*spec.position)
                update.append(keep)
    create.extend(s for k, s in want.items() if k not in existing)
    return create, update, remove


def sync_sheet(
    sch: Schematic, settings: Settings, pack: TexturePack | None, label: str = "", clear: bool = False
) -> SheetResult:
    res = SheetResult(sheet=label)
    if clear:
        poles: list[Pole] = []
        desired: list[Spec] = []
    else:
        poles = read_poles(sch, settings)
        plan = make_plan(poles, settings, pack)
        res.plan = plan
        res.warnings.extend(plan.warnings)
        desired = plan.items
    res.poles = len(poles)
    create, update, remove = diff(desired, generated_items(sch))
    if not (create or update or remove):
        return res
    commit = sch.begin_commit()
    try:
        if remove:
            sch.remove_items(remove)
        update_items(sch, update)
        create_items(sch, [build(s) for s in create])
    except Exception:
        sch.drop_commit(commit)
        raise
    sch.push_commit(commit, "Clear power lines" if clear else "Update power lines")
    res.created, res.updated, res.removed = len(create), len(update), len(remove)
    return res


def unique_sheets(sch: Schematic) -> list[tuple[str, Schematic]]:
    """One bound Schematic per sheet *file* (repeated sheets share their drawing)."""
    out = []
    seen: set[str] = set()
    for sheet in sch.get_hierarchy():
        key = sheet.filename or sheet.path.proto.path_human_readable
        if key in seen:
            continue
        seen.add(key)
        out.append((sheet.path.proto.path_human_readable or "/", sch.for_sheet(sheet)))
    return out


def sync(sch: Schematic, settings: Settings, pack: TexturePack | None, clear: bool = False) -> list[SheetResult]:
    return [sync_sheet(s, settings, pack, label, clear) for label, s in unique_sheets(sch)]


def fingerprint(sch: Schematic, settings: Settings) -> tuple:
    """Cheap summary of everything that affects the drawing, for live mode."""
    out = []
    for _, s in unique_sheets(sch):
        out.append(tuple(sorted((p.id, p.net, p.type.name, p.position) for p in read_poles(s, settings))))
    return tuple(out)


def describe(results: Iterable[SheetResult]) -> str:
    lines = []
    for r in results:
        line = f"{r.sheet}: {r.poles} poles"
        if r.plan is not None:
            line += f", {len(r.plan.wires)} wires"
        line += f" (+{r.created} ~{r.updated} -{r.removed})"
        lines.append(line)
        lines.extend(f"  warning: {w}" for w in r.warnings)
    return "\n".join(lines)
