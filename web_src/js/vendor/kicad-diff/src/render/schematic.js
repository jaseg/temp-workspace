// Schematic (.kicad_sch) and symbol library (.kicad_sym) rendering into a scene.
// Scene layers are named after KiCad's schematic colour-theme keys (see theme/themes.js).

import { apply, arcPoints, bezierPoints, circlePoints, emptyBox, extendBox, multiply, rotate, translate } from '../geom.js';
import { drawnUnits, FLIP_Y, findDef, orientation, placedPins, referenceOf, symbolTransform } from '../kicad/place.js';
import { layout, toModel } from './text.js';
import { fieldKey, itemKey, libSymbolKey, pinKey, sheetPinKey } from '../kicad/keys.js';

const MIL = 0.0254;
const LINE = 6 * MIL;
const BUS = 12 * MIL;
const JUNCTION = 36 * MIL;
const NOCONNECT = 48 * MIL;
const PIN_TEXT_MARGIN = 4 * MIL;
const TEXT_OFFSET_RATIO = 0.15;
const LABEL_RATIO = 0.375;
const PIN_DECO = 25 * MIL;

const width = w => (w > 0 ? w : LINE);

/** Text record for scene.text(). */
function rec(str, at, e, extra = {}) {
  return {
    str, at, h: e.size.h, w: e.size.w, thickness: e.thickness ?? e.size.h / (e.bold ? 5 : 8),
    bold: e.bold, italic: e.italic, hj: e.justify.h, vj: e.justify.v, ...extra,
  };
}

/** Schematic text is always drawn readable: horizontal, or vertical reading bottom-to-top. */
function readable(r) {
  const rot = ((Math.round(r.at.rot) % 360) + 360) % 360;
  if (rot !== 180 && rot !== 270) return r;
  const flip = { left: 'right', right: 'left', center: 'center' };
  const flipV = { top: 'bottom', bottom: 'top', center: 'center' };
  return { ...r, at: { ...r.at, rot: rot - 180 }, hj: flip[r.hj], vj: flipV[r.vj] };
}

// Shapes ---------------------------------------------------------------------------------------

function shapeOutline(s) {
  switch (s.type) {
    case 'polyline': return { pts: s.pts, closed: false };
    case 'bezier': return { pts: s.pts.length === 4 ? bezierPoints(...s.pts) : s.pts, closed: false };
    case 'rectangle': return { pts: [s.start, { x: s.end.x, y: s.start.y }, s.end, { x: s.start.x, y: s.end.y }], closed: true };
    case 'circle': return { pts: circlePoints(s.center.x, s.center.y, s.radius), closed: true };
    case 'arc': return { pts: arcPoints(s.start, s.mid, s.end), closed: false };
    case 'ellipse': case 'ellipse_arc': {
      const a0 = s.type === 'ellipse' ? 0 : (s.startAngle ?? 0), a1 = s.type === 'ellipse' ? 360 : (s.endAngle ?? 360);
      const pts = [];
      for (let i = 0; i <= 64; i++) {
        const a = ((a0 + ((a1 - a0) * i) / 64) * Math.PI) / 180;
        const [x, y] = apply(rotate(s.rot), s.major * Math.cos(a), s.minor * Math.sin(a));
        pts.push({ x: s.center.x + x, y: s.center.y + y });
      }
      return { pts, closed: s.type === 'ellipse' };
    }
  }
  return { pts: [], closed: false };
}

/** Graphic shape on `layer`, with fills: outline → `layer`, background → `fillLayer`. */
function shape(scene, s, layer, fillLayer) {
  const { pts, closed } = shapeOutline(s);
  if (s.fill.type === 'outline') scene.polygon(layer, pts);
  else if (s.fill.type !== 'none') scene.polygon(fillLayer, pts);
  scene.polyline(layer, pts, width(s.stroke.width), closed && s.type !== 'circle');
}

// Symbols --------------------------------------------------------------------------------------

/**
 * Field of a placed symbol. KiCad stores the field position in the symbol's unrotated frame; it is
 * shown at symbol.at + T·(pos − symbol.at), centred on its transformed bounding box, and kept
 * horizontal or vertical.
 */
function symbolField(scene, sym, f, layer, text) {
  const T = orientation(sym);
  const r = rec(text, f.at, f.effects);
  const corners = cornersOf(r);
  const box = emptyBox();
  for (const p of corners) {
    const [x, y] = apply(T, p.x - sym.at.x, p.y - sym.at.y);
    extendBox(box, x + sym.at.x, y + sym.at.y);
  }
  const swapped = Math.abs(T[1]) > 0.5;
  const rot = (f.at.rot % 180 === 0) !== swapped ? 0 : 90;
  scene.text(layer, { ...r, at: { x: (box.x0 + box.x1) / 2, y: (box.y0 + box.y1) / 2, rot }, hj: 'center', vj: 'center' });
}

function cornersOf(r) {
  const t = { ...r, x: r.at.x, y: r.at.y, rot: r.at.rot };
  const { box } = layout(t);
  return [[box.x0, box.y0], [box.x1, box.y0], [box.x1, box.y1], [box.x0, box.y1]].map(([x, y]) => toModel(t, x, y));
}

function fieldLayer(name, sheet = false) {
  if (sheet) return name === 'Sheetname' || name === 'Sheet name' ? 'sheet_name' : name === 'Sheetfile' || name === 'Sheet file' ? 'sheet_filename' : 'sheet_fields';
  return name === 'Reference' ? 'reference' : name === 'Value' ? 'value' : 'fields';
}

function fieldText(f, sheet) {
  if (sheet && (f.name === 'Sheetfile' || f.name === 'Sheet file')) return `File: ${f.value}`;
  if (sheet && (f.name === 'Sheetname' || f.name === 'Sheet name')) return `Sheet: ${f.value}`;
  return f.showName ? `${f.name}: ${f.value}` : f.value;
}

const isEmptyName = (s, version) => !s || (s === '~' && !(version >= 20250318));

/** Pin line, decoration, name and number, in sheet coordinates. */
function pin(scene, p, def, version) {
  const { tip, end } = p;
  const len = Math.hypot(end.x - tip.x, end.y - tip.y) || 1;
  const d = { x: (end.x - tip.x) / len, y: (end.y - tip.y) / len };
  const style = p.pin.style;
  // Line, shortened for an inversion bubble.
  const inverted = style === 'inverted' || style === 'inverted_clock';
  const lineEnd = inverted ? { x: end.x - d.x * 2 * PIN_DECO * 0.6, y: end.y - d.y * 2 * PIN_DECO * 0.6 } : end;
  scene.segment('pin', tip, lineEnd, LINE);
  const r = PIN_DECO * 0.6;
  if (inverted) scene.polyline('pin', circlePoints(end.x - d.x * r, end.y - d.y * r, r), LINE);
  const n = { x: -d.y, y: d.x };
  if (style === 'clock' || style === 'inverted_clock' || style === 'edge_clock_high') {
    const c = PIN_DECO;
    scene.polyline('pin', [{ x: end.x + n.x * c, y: end.y + n.y * c }, { x: end.x + d.x * c, y: end.y + d.y * c }, { x: end.x - n.x * c, y: end.y - n.y * c }], LINE);
  }
  // Active-low flags: a small wedge on the outside of the pin line, next to the body.
  const c = 2 * PIN_DECO;
  const flagBase = { x: end.x - d.x * c, y: end.y - d.y * c };
  const flagTop = { x: flagBase.x + n.x * c / 2, y: flagBase.y + n.y * c / 2 };
  if (style === 'input_low' || style === 'clock_low' || style === 'edge_clock_high') scene.polyline('pin', [flagBase, flagTop, end], LINE);
  if (style === 'output_low') scene.segment('pin', flagTop, end, LINE);
  if (style === 'non_logic') {
    const c = PIN_DECO;
    scene.segment('pin', { x: tip.x - c, y: tip.y - c }, { x: tip.x + c, y: tip.y + c }, LINE);
    scene.segment('pin', { x: tip.x + c, y: tip.y - c }, { x: tip.x - c, y: tip.y + c }, LINE);
  }

  const vertical = Math.abs(d.y) > Math.abs(d.x);
  const rot = vertical ? 90 : 0;
  const mid = { x: (tip.x + end.x) / 2, y: (tip.y + end.y) / 2 };
  // "Above" the pin line in the text's own frame is screen-up for horizontal pins, screen-left for vertical ones.
  const above = vertical ? { x: -1, y: 0 } : { x: 0, y: -1 };
  const off = PIN_TEXT_MARGIN + LINE / 2;
  const name = p.pin.name;
  const number = p.pin.number;
  const showName = !def.pinNames.hide && !isEmptyName(name.text, version);
  const showNumber = !def.pinNumbers.hide && !isEmptyName(number.text, version);
  if (def.pinNames.offset > 0) {
    if (showName) {
      const at = { x: end.x + d.x * def.pinNames.offset, y: end.y + d.y * def.pinNames.offset, rot };
      const forward = vertical ? d.y < 0 : d.x > 0;
      scene.text('pin_name', rec(name.text, at, name.effects, { hj: forward ? 'left' : 'right', vj: 'center' }));
    }
    if (showNumber) scene.text('pin_number', rec(number.text, { x: mid.x + above.x * off, y: mid.y + above.y * off, rot }, number.effects, { hj: 'center', vj: 'bottom' }));
  } else {
    if (showName) scene.text('pin_name', rec(name.text, { x: mid.x + above.x * off, y: mid.y + above.y * off, rot }, name.effects, { hj: 'center', vj: 'bottom' }));
    if (showNumber) scene.text('pin_number', rec(number.text, { x: mid.x - above.x * off, y: mid.y - above.y * off, rot }, number.effects, { hj: 'center', vj: 'top' }));
  }
}

/** Body graphics and texts of a symbol's drawn units, through transform `m` (library → sheet). */
function symbolBody(scene, def, sym, m) {
  scene.withTransform(m, () => {
    for (const u of drawnUnits(def, sym)) {
      for (const s of u.shapes) shape(scene, s, 'component_outline', 'component_body');
    }
  });
  for (const u of drawnUnits(def, sym)) {
    for (const t of u.texts) {
      if (t.effects.hide) continue;
      const [x, y] = apply(m, t.at.x, t.at.y);
      symbolField(scene, { ...sym, at: { x: sym.at.x, y: sym.at.y, rot: sym.at.rot } }, { ...t, at: { x, y, rot: t.at.rot } }, 'component_outline', t.text);
    }
  }
}

function placedSymbol(scene, sch, sym, key, version) {
  const def = findDef(sch, sym);
  const ref = referenceOf(sym);
  const value = sym.properties.find(p => p.name === 'Value')?.value;
  scene.beginItem(key, { kind: 'symbol', ref, value, libId: sym.libId });
  if (def) symbolBody(scene, def, sym, symbolTransform(sym));
  if (sym.dnp) {
    const b = scene.items[scene.items.length - 1].bbox;
    if (b.x1 > b.x0) {
      scene.segment('dnp_marker', { x: b.x0, y: b.y0 }, { x: b.x1, y: b.y1 }, 3 * LINE);
      scene.segment('dnp_marker', { x: b.x1, y: b.y0 }, { x: b.x0, y: b.y1 }, 3 * LINE);
    }
  }
  scene.endItem();
  if (def) {
    for (const p of placedPins(def, sym)) {
      if (p.pin.hide) continue;
      scene.beginItem(pinKey(key, p.number), { kind: 'pin', ref, pin: p.number, pinName: p.name, parent: key });
      pin(scene, p, def, version);
      scene.endItem();
    }
  }
  sym.properties.forEach(f => {
    if (f.hide || !f.value) return;
    scene.beginItem(fieldKey(key, f.name), { kind: 'field', ref, field: f.name, parent: key });
    symbolField(scene, sym, f, fieldLayer(f.name), fieldText(f));
    scene.endItem();
  });
}

// Labels ---------------------------------------------------------------------------------------

/** Unit direction a label's body extends in, from its rotation. */
function labelDir(rot) {
  const r = ((Math.round(rot) % 360) + 360) % 360;
  return r === 0 ? { x: 1, y: 0 } : r === 90 ? { x: 0, y: -1 } : r === 180 ? { x: -1, y: 0 } : { x: 0, y: 1 };
}

function label(scene, l) {
  const e = l.effects;
  const h = e.size.h;
  const layer = { label: 'label_local', global_label: 'label_global', hierarchical_label: 'label_hier' }[l.type] ?? 'netclass_flag';
  const dir = labelDir(l.at.rot);
  const vertical = dir.x === 0;
  const textRot = vertical ? 90 : 0;
  // "forward" along the reading direction of the text
  const forward = vertical ? dir.y < 0 : dir.x > 0;
  const hj = forward ? 'left' : 'right';
  const thick = e.thickness ?? h / 8;

  if (l.type === 'label') {
    const off = h * TEXT_OFFSET_RATIO + thick;
    const at = vertical ? { x: l.at.x - off, y: l.at.y, rot: 90 } : { x: l.at.x, y: l.at.y - off, rot: 0 };
    return scene.text(layer, rec(l.text, at, e, { hj, vj: 'bottom' }));
  }

  if (l.type === 'global_label' || l.type === 'hierarchical_label') {
    const margin = h * LABEL_RATIO;
    const half = h / 2 + margin;
    const textLen = layout(rec(l.text, { x: 0, y: 0, rot: 0 }, e)).box;
    const tw = textLen.x1 - textLen.x0;
    let outline;
    let textStart;
    if (l.type === 'hierarchical_label') {
      const s = h;
      outline = hierShape(l.shape, s);
      textStart = s + margin;
    } else {
      const arrowIn = l.shape === 'input' || l.shape === 'bidirectional' || l.shape === 'tri_state';
      const arrowOut = l.shape === 'output' || l.shape === 'bidirectional' || l.shape === 'tri_state';
      const a = half;
      const len = tw + 2 * margin + (arrowIn ? a : 0) + (arrowOut ? a : 0);
      outline = [
        { x: 0, y: 0 }, { x: arrowIn ? a : 0, y: -half }, { x: len - (arrowOut ? a : 0), y: -half },
        { x: len, y: 0 }, { x: len - (arrowOut ? a : 0), y: half }, { x: arrowIn ? a : 0, y: half },
      ];
      if (!arrowIn) outline[0] = { x: 0, y: -half }, outline.splice(5, 0, { x: 0, y: half });
      textStart = (arrowIn ? a : 0) + margin;
    }
    // Local frame: x along `dir`, y perpendicular (screen-down for horizontal labels).
    const frame = multiply(translate(l.at.x, l.at.y), rotate(vertical ? (dir.y < 0 ? 90 : 270) : dir.x > 0 ? 0 : 180));
    scene.withTransform(frame, () => scene.polyline(layer, outline, thick, true));
    const at = { x: l.at.x + dir.x * textStart, y: l.at.y + dir.y * textStart, rot: textRot };
    return scene.text(layer, rec(l.text, at, e, { hj, vj: 'center' }));
  }

  // netclass_flag / directive_label: a stem of `length`, a small symbol and the fields.
  const len = l.length ?? 2.54;
  const tipEnd = { x: l.at.x + dir.x * len, y: l.at.y + dir.y * len };
  scene.segment(layer, l.at, tipEnd, thick);
  const r = h / 2;
  const c = { x: tipEnd.x + dir.x * r, y: tipEnd.y + dir.y * r };
  if (l.shape === 'dot') scene.disc(layer, c, r / 2);
  else if (l.shape === 'diamond') scene.polyline(layer, [{ x: tipEnd.x, y: tipEnd.y }, { x: c.x + dir.y * r, y: c.y + dir.x * r }, { x: c.x + dir.x * r, y: c.y + dir.y * r }, { x: c.x - dir.y * r, y: c.y - dir.x * r }], thick, true);
  else if (l.shape === 'rectangle') scene.polyline(layer, [{ x: c.x - r, y: c.y - r }, { x: c.x + r, y: c.y - r }, { x: c.x + r, y: c.y + r }, { x: c.x - r, y: c.y + r }], thick, true);
  else scene.polyline(layer, circlePoints(c.x, c.y, r), thick);
  for (const f of l.properties) {
    if (!f.hide && f.value) scene.text(layer, readable(rec(fieldText(f), f.at, f.effects)));
  }
}

/** Hierarchical label/sheet pin glyph of size s, pointing along +x from the connection point. */
function hierShape(kind, s) {
  const h = s / 2;
  switch (kind) {
    case 'input': return [{ x: 0, y: -h }, { x: h, y: -h }, { x: s, y: 0 }, { x: h, y: h }, { x: 0, y: h }];
    case 'output': return [{ x: 0, y: 0 }, { x: h, y: -h }, { x: s, y: -h }, { x: s, y: h }, { x: h, y: h }];
    case 'bidirectional': case 'tri_state': return [{ x: 0, y: 0 }, { x: h, y: -h }, { x: s, y: 0 }, { x: h, y: h }];
    default: return [{ x: 0, y: -h }, { x: s, y: -h }, { x: s, y: h }, { x: 0, y: h }];
  }
}

// Other items ----------------------------------------------------------------------------------

function sheet(scene, s, key) {
  const { x, y } = s.at;
  const { w, h } = s.size;
  const box = [{ x, y }, { x: x + w, y }, { x: x + w, y: y + h }, { x, y: y + h }];
  scene.beginItem(key, { kind: 'sheet', name: s.properties.find(p => /^Sheet ?name$/i.test(p.name))?.value });
  if (s.fill.color) scene.polygon('sheet_background', box);
  scene.polyline('sheet', box, width(s.stroke.width), true);
  for (const f of s.properties) if (!f.hide && f.value) scene.text(fieldLayer(f.name, true), readable(rec(fieldText(f, true), f.at, f.effects)));
  scene.endItem();
  for (const p of s.pins) {
    scene.beginItem(sheetPinKey(key, p.name), { kind: 'sheet_pin', name: p.name, parent: key });
    const side = p.at.rot === 0 ? 'right' : p.at.rot === 180 ? 'left' : p.at.rot === 90 ? 'top' : 'bottom';
    // Glyph points into the sheet; text sits inside the sheet.
    const inward = { right: 180, left: 0, top: 270, bottom: 90 }[side];
    const sz = p.effects.size.h;
    scene.withTransform(multiply(translate(p.at.x, p.at.y), rotate(inward)), () => scene.polyline('sheet_label', hierShape(p.shape, sz), LINE, true));
    const d = labelDir(inward);
    const at = { x: p.at.x + d.x * sz * 1.4, y: p.at.y + d.y * sz * 1.4, rot: d.x === 0 ? 90 : 0 };
    const forward = d.x === 0 ? d.y < 0 : d.x > 0;
    scene.text('sheet_label', rec(p.name, at, p.effects, { hj: forward ? 'left' : 'right', vj: 'center' }));
    scene.endItem();
  }
}

function textBox(scene, t, layer) {
  const { x, y } = t.at;
  const { w, h } = t.size;
  const box = [{ x, y }, { x: x + w, y }, { x: x + w, y: y + h }, { x, y: y + h }];
  if (t.fill.type !== 'none') scene.polygon('note_background', box);
  if (t.stroke.width >= 0 && t.stroke.type !== 'none') scene.polyline(layer, box, width(t.stroke.width), true);
  const [ml, mt, mr, mb] = t.margins ?? [1, 1, 1, 1];
  const e = t.effects;
  const ax = e.justify.h === 'left' ? x + ml : e.justify.h === 'right' ? x + w - mr : x + w / 2;
  const ay = e.justify.v === 'top' ? y + mt : e.justify.v === 'bottom' ? y + h - mb : y + h / 2;
  scene.text(layer, rec(t.text, { x: ax, y: ay, rot: 0 }, e));
}

/** Render a schematic sheet. */
export function renderSchematic(scene, sch) {
  const version = sch.version;
  sch.items.forEach((it, i) => scene.safely(() => schematicItem(scene, sch, it, i, version), it.type));
  return scene;
}

function schematicItem(scene, sch, it, i, version) {
  const key = itemKey(it, i);
  switch (it.type) {
    case 'symbol':
      return placedSymbol(scene, sch, it, key, version);
    case 'sheet':
      return sheet(scene, it, key);
  }
  scene.beginItem(key, { kind: it.type, text: it.text });
  switch (it.type) {
    case 'wire': case 'bus':
      scene.polyline(it.type, it.pts, it.stroke.width > 0 ? it.stroke.width : it.type === 'bus' ? BUS : LINE);
      break;
    case 'bus_entry':
      scene.segment('bus_entry', it.at, { x: it.at.x + it.size.w, y: it.at.y + it.size.h }, width(it.stroke.width));
      break;
    case 'junction':
      scene.disc('junction', it.at, (it.diameter || JUNCTION) / 2);
      break;
    case 'no_connect': {
      const s = NOCONNECT / 2;
      scene.segment('no_connect', { x: it.at.x - s, y: it.at.y - s }, { x: it.at.x + s, y: it.at.y + s }, LINE);
      scene.segment('no_connect', { x: it.at.x + s, y: it.at.y - s }, { x: it.at.x - s, y: it.at.y + s }, LINE);
      break;
    }
    case 'label': case 'global_label': case 'hierarchical_label': case 'directive_label': case 'netclass_flag':
      label(scene, it);
      break;
    case 'text':
      if (!it.effects.hide) scene.text('notes', readable(rec(it.text, it.at, it.effects)));
      break;
    case 'text_box':
      textBox(scene, it, 'notes');
      break;
    case 'table':
      for (const c of it.cells) textBox(scene, { ...c, stroke: { width: LINE, type: 'solid' } }, 'notes');
      break;
    case 'rule_area':
      for (const s of it.shapes) shape(scene, s, 'rule_area', 'rule_area');
      break;
    case 'polyline': case 'bezier': case 'rectangle': case 'circle': case 'arc': case 'ellipse': case 'ellipse_arc':
      shape(scene, it, 'notes', 'note_background');
      break;
  }
  scene.endItem();
}

/** Render one symbol of a library (or a schematic's lib_symbols) at the origin, unit 1. */
export function renderLibSymbol(scene, def, { unit = 1, bodyStyle = 1, version } = {}) {
  const sym = { at: { x: 0, y: 0, rot: 0 }, unit, bodyStyle, properties: def.properties };
  const key = libSymbolKey(def.name);
  scene.beginItem(key, { kind: 'symbol', ref: def.name });
  symbolBody(scene, def, sym, FLIP_Y);
  scene.endItem();
  for (const p of placedPins(def, sym)) {
    if (p.pin.hide) continue;
    scene.beginItem(pinKey(key, p.number), { kind: 'pin', ref: def.name, pin: p.number, pinName: p.name, parent: key });
    pin(scene, p, def, version);
    scene.endItem();
  }
  def.properties.forEach(f => {
    if (f.hide || !f.value) return;
    scene.beginItem(fieldKey(key, f.name), { kind: 'field', ref: def.name, field: f.name, parent: key });
    // Library field positions are y-up like the rest of the library.
    symbolField(scene, sym, { ...f, at: { ...f.at, y: -f.at.y } }, fieldLayer(f.name), fieldText(f));
    scene.endItem();
  });
  return scene;
}
