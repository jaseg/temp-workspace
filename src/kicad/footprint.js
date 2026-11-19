// Footprints (.kicad_mod, and footprints placed on a board), plus the board-style graphics,
// text, pads and zones they share with .kicad_pcb.

import { at, effects, fill, property, pts, rest, settings, stroke, uuid } from './common.js';
import { child, children, flag, hasAtom, num, numOf, readAll, str, strOf, text, xy } from './read.js';

/** Layer list from (layers "F.Cu" "B.Cu") or a single (layer "F.Cu" [knockout]). */
export function layersOf(n) {
  const many = child(n, 'layers');
  if (many) return many.slice(1).map(text);
  const one = child(n, 'layer');
  return one ? [str(one)] : [];
}

/** Net name of an item: (net "GND") since 10.0, or legacy (net 3 "GND") / (net 3) resolved via ctx.nets. */
export function netOf(n, ctx) {
  const c = child(n, 'net');
  if (!c) return undefined;
  if (c.length > 2) return str(c, 2);
  const v = str(c, 1);
  return ctx.nets?.get(v) ?? v;
}

/** gr_*, fp_* and pad primitive graphics. The type is the part after the prefix: line, rect, circle, arc, poly, curve, bbox, vector. */
export function readGraphic(n, ctx) {
  const type = n[0].replace(/^(gr|fp)_/, '');
  const s = stroke(n);
  const g = {
    type,
    layer: strOf(n, 'layer'),
    layers: child(n, 'layers') ? layersOf(n) : undefined,
    width: s.width, strokeType: s.type,
    fill: fill(n).type,
    locked: flag(n, 'locked') || hasAtom(n, 'locked'),
    net: netOf(n, ctx),
    uuid: uuid(n),
  };
  switch (type) {
    case 'line': case 'rect': case 'bbox': case 'vector':
      Object.assign(g, { start: xy(child(n, 'start')), end: xy(child(n, 'end')), radius: numOf(n, 'radius') });
      break;
    case 'circle':
      Object.assign(g, { center: xy(child(n, 'center')), end: xy(child(n, 'end')) });
      break;
    case 'arc':
      Object.assign(g, { start: xy(child(n, 'start')), mid: xy(child(n, 'mid')), end: xy(child(n, 'end')) });
      break;
    case 'poly': case 'curve':
      g.pts = pts(n);
      break;
    default:
      throw new Error(`unknown graphic ${n[0]}`);
  }
  g.settings = settings(n, 'solder_mask_margin', 'start_shape', 'end_shape');
  g.extra = rest(n);
  return g;
}

export const GRAPHICS = ['line', 'rect', 'circle', 'arc', 'poly', 'curve'];

/** gr_text, fp_text (legacy "reference"/"value"/"user" kinds) and board properties drawn as text. */
export function readBoardText(n) {
  const isFp = n[0] === 'fp_text';
  const layer = child(n, 'layer');
  return {
    type: 'text',
    kind: isFp ? str(n, 1) : 'user',
    text: str(n, isFp ? 2 : 1),
    at: at(child(n, 'at')),
    layer: str(layer),
    knockout: !!layer?.includes('knockout') || flag(n, 'knockout'),
    hide: flag(n, 'hide') || hasAtom(n, 'hide') || flag(child(n, 'effects'), 'hide'),
    unlocked: flag(n, 'unlocked'),
    locked: flag(n, 'locked') || hasAtom(n, 'locked'),
    effects: effects(n),
    uuid: uuid(n),
    extra: rest(n),
  };
}

/** gr_text_box / fp_text_box: rectangle (start/end) or rotated (pts), with optional border. */
export function readBoardTextBox(n) {
  const s = stroke(n);
  return {
    type: 'text_box',
    text: str(n),
    start: xy(child(n, 'start')), end: xy(child(n, 'end')), pts: pts(n), angle: numOf(n, 'angle', 0),
    layer: strOf(n, 'layer'),
    border: flag(n, 'border'), width: s.width, strokeType: s.type,
    knockout: flag(n, 'knockout'),
    margins: child(n, 'margins')?.slice(1).map(Number),
    effects: effects(n),
    uuid: uuid(n),
    extra: rest(n),
  };
}

function readDrill(n) {
  if (!n) return undefined;
  const oval = n[1] === 'oval';
  const w = num(n, oval ? 2 : 1, 0);
  return { oval, w, h: oval ? num(n, 3, w) : w, offset: xy(child(n, 'offset')) };
}

/** (pad "1" smd roundrect (at ..) (size ..) (drill ..) (layers ..) (net ..) ...) */
export function readPad(n, ctx) {
  const size = child(n, 'size');
  const delta = child(n, 'rect_delta');
  const chamfer = child(n, 'chamfer');
  const primitives = child(n, 'primitives');
  return {
    number: str(n, 1),
    kind: str(n, 2),
    shape: str(n, 3),
    at: at(child(n, 'at')),
    size: { w: num(size, 1, 0), h: num(size, 2, 0) },
    drill: readDrill(child(n, 'drill')),
    layers: layersOf(n),
    net: netOf(n, ctx),
    pinFunction: strOf(n, 'pinfunction'),
    pinType: strOf(n, 'pintype'),
    roundrectRatio: numOf(n, 'roundrect_rratio', 0.25),
    chamferRatio: numOf(n, 'chamfer_ratio', 0),
    chamfer: chamfer ? chamfer.slice(1).map(text) : [],
    rectDelta: delta ? { x: num(delta, 1, 0), y: num(delta, 2, 0) } : undefined,
    primitives: primitives ? readAll(primitives, ['gr_line', 'gr_rect', 'gr_circle', 'gr_arc', 'gr_poly', 'gr_curve', 'gr_bbox', 'gr_vector'], readGraphic, ctx) : [],
    locked: hasAtom(n, 'locked') || flag(n, 'locked'),
    uuid: uuid(n),
    settings: settings(n, 'options', 'padstack', 'die_length', 'die_delay', 'solder_mask_margin', 'solder_paste_margin',
      'solder_paste_margin_ratio', 'clearance', 'zone_connect', 'thermal_bridge_width', 'thermal_bridge_angle', 'thermal_gap',
      'thermal_width', 'teardrops', 'tenting', 'remove_unused_layers', 'keep_end_layers', 'zone_layer_connections',
      'sim_electrical_type', 'front_post_machining', 'back_post_machining', 'backdrill', 'tertiary_drill', 'property'),
    extra: rest(n),
  };
}

/** (zone ...): outline polygon, per-layer filled polygons and keepout/fill settings. */
export function readZone(n, ctx) {
  const keepout = child(n, 'keepout');
  return {
    type: 'zone',
    name: strOf(n, 'name'),
    net: netOf(n, ctx) ?? strOf(n, 'net_name'),
    layers: layersOf(n),
    priority: numOf(n, 'priority', 0),
    keepout: keepout ? Object.fromEntries(children(keepout, 'tracks', 'vias', 'pads', 'copperpour', 'footprints').map(k => [k[0], str(k)])) : undefined,
    outline: children(n, 'polygon').map(pts),
    filled: children(n, 'filled_polygon').map(f => ({ layer: strOf(f, 'layer'), island: !!child(f, 'island'), pts: pts(f) })),
    locked: flag(n, 'locked') || hasAtom(n, 'locked'),
    uuid: uuid(n),
    settings: settings(n, 'net_name', 'hatch', 'connect_pads', 'min_thickness', 'filled_areas_thickness', 'fill', 'placement', 'attr', 'property', 'fill_segments'),
    extra: rest(n),
  };
}

/** (dimension ...): drawn as its leader/feature lines plus its text. */
export function readDimension(n, ctx) {
  const t = child(n, 'gr_text');
  return {
    type: 'dimension',
    kind: strOf(n, 'type'),
    layer: strOf(n, 'layer'),
    pts: pts(n),
    height: numOf(n, 'height', 0),
    text: t ? readBoardText(t) : undefined,
    uuid: uuid(n),
    settings: settings(n, 'format', 'style', 'orientation', 'leader_length', 'locked'),
    extra: rest(n),
  };
}

/** Footprint placement: legacy (at x y rot) or 10.99 (transform (translate x y) (rotate r) (scale sx sy)). */
function placement(n) {
  const t = child(n, 'transform');
  if (t) {
    const tr = child(t, 'translate');
    const sc = child(t, 'scale');
    return { x: num(tr, 1, 0), y: num(tr, 2, 0), rot: numOf(t, 'rotate', 0), scale: { x: num(sc, 1, 1), y: num(sc, 2, 1) } };
  }
  return { ...at(child(n, 'at')), scale: { x: 1, y: 1 } };
}

/** Item angles inside footprints are stored absolute in the file; make them relative to the footprint. */
function localize(item, rot) {
  if (item?.at && rot) item.at.rot -= rot;
  return item;
}

export function readFootprint(n, ctx) {
  const pos = placement(n);
  const attr = child(n, 'attr');
  const fpProperty = (p, c) => localize({ ...property(p, c), type: 'property' }, pos.rot);
  const graphics = readAll(n, GRAPHICS.map(g => 'fp_' + g), readGraphic, ctx);
  return {
    type: 'footprint',
    name: str(n),
    layer: str(children(n, 'layer')[0]), // hand-edited files may repeat (layer)
    at: pos,
    locked: hasAtom(n, 'locked') || flag(n, 'locked'),
    placed: hasAtom(n, 'placed'),
    descr: strOf(n, 'descr'),
    tags: strOf(n, 'tags'),
    path: strOf(n, 'path'),
    sheetName: strOf(n, 'sheetname'),
    sheetFile: strOf(n, 'sheetfile'),
    attributes: attr ? attr.slice(1).filter(a => !Array.isArray(a)).map(text) : [],
    properties: readAll(n, 'property', fpProperty, ctx),
    texts: readAll(n, 'fp_text', (t, c) => localize(readBoardText(t, c), pos.rot), ctx),
    textBoxes: readAll(n, 'fp_text_box', readBoardTextBox, ctx),
    graphics,
    pads: readAll(n, 'pad', (p, c) => localize(readPad(p, c), pos.rot), ctx),
    zones: readAll(n, 'zone', readZone, ctx),
    dimensions: readAll(n, 'dimension', readDimension, ctx),
    uuid: uuid(n),
    settings: settings(n, 'model', 'clearance', 'solder_mask_margin', 'solder_paste_margin', 'solder_paste_margin_ratio',
      'solder_paste_ratio', 'zone_connect', 'thermal_width', 'thermal_gap', 'net_tie_pad_groups', 'jumper_pad_groups',
      'duplicate_pad_numbers_are_jumpers', 'component_classes', 'units', 'variant', 'custom_property', 'constraint',
      'embedded_fonts', 'embedded_files', 'group', 'point', 'table', 'height', 'private_layers', 'autoplace_cost90',
      'autoplace_cost180', 'tedit', 'image', 'barcode', 'version', 'generator', 'generator_version'),
    extra: rest(n),
  };
}
