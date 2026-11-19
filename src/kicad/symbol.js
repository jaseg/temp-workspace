// Library symbols (.kicad_sym and a schematic's lib_symbols) and schematic-style graphic shapes.

import { at, effects, fill, property, pts, rest, settings, stroke, uuid } from './common.js';
import { child, children, flag, num, numOf, readAll, str, strOf, text, xy } from './read.js';

/** Line end decoration of 10.99 schematic/symbol lines: (start_shape arrow (length l) (width w)). */
function lineEnd(n, name) {
  const e = child(n, name);
  return e && { shape: str(e), length: numOf(e, 'length'), width: numOf(e, 'width'), stroke: child(e, 'stroke') && stroke(e) };
}

/** Graphic shape shared by schematics and symbol bodies. */
export function readShape(n) {
  const base = { type: n[0], stroke: stroke(n), fill: fill(n), uuid: uuid(n), locked: flag(n, 'locked') };
  switch (n[0]) {
    case 'polyline':
    case 'bezier':
      return { ...base, pts: pts(n), startShape: lineEnd(n, 'start_shape'), endShape: lineEnd(n, 'end_shape') };
    case 'rectangle':
      return { ...base, start: xy(child(n, 'start')), end: xy(child(n, 'end')), radius: numOf(n, 'radius') };
    case 'circle':
      return { ...base, center: xy(child(n, 'center')), radius: numOf(n, 'radius', 0) };
    case 'arc':
      return {
        ...base, start: xy(child(n, 'start')), mid: xy(child(n, 'mid')), end: xy(child(n, 'end')),
        startShape: lineEnd(n, 'start_shape'), endShape: lineEnd(n, 'end_shape'),
      };
    case 'ellipse':
    case 'ellipse_arc':
      return {
        ...base, center: xy(child(n, 'center')), major: numOf(n, 'major_radius', 0), minor: numOf(n, 'minor_radius', 0),
        rot: numOf(n, 'rotation', 0), startAngle: numOf(n, 'start_angle'), endAngle: numOf(n, 'end_angle'),
      };
  }
  throw new Error(`unknown shape ${n[0]}`);
}

export const SHAPES = ['polyline', 'bezier', 'rectangle', 'circle', 'arc', 'ellipse', 'ellipse_arc'];

/** (text "..." (at ..) (effects ..)) */
export function readText(n) {
  return { type: 'text', text: str(n), at: at(child(n, 'at')), effects: effects(n), uuid: uuid(n), excludeFromSim: flag(n, 'exclude_from_sim') };
}

/** (text_box "..." (at x y rot) (size w h) (margins ..) (stroke ..) (fill ..) (effects ..)); legacy uses (start)/(end). */
export function readTextBox(n) {
  const a = at(child(n, 'at'));
  const size = child(n, 'size');
  const start = child(n, 'start');
  const end = child(n, 'end');
  return {
    type: 'text_box', text: str(n),
    at: start ? { ...xy(start), rot: 0 } : a,
    size: size ? { w: num(size, 1, 0), h: num(size, 2, 0) } : start && end ? { w: num(end, 1) - num(start, 1), h: num(end, 2) - num(start, 2) } : { w: 0, h: 0 },
    margins: child(n, 'margins')?.slice(1).map(Number),
    stroke: stroke(n), fill: fill(n), effects: effects(n), uuid: uuid(n),
    excludeFromSim: flag(n, 'exclude_from_sim'),
  };
}

function readPinText(n) {
  return n ? { text: str(n), effects: effects(n) } : { text: '', effects: effects(undefined) };
}

/** (pin etype style (at x y rot) (length l) (hide yes) (name ..) (number ..) (alternate name etype style)) */
export function readPin(n, ctx) {
  return {
    etype: str(n, 1),
    style: str(n, 2),
    at: at(child(n, 'at')),
    length: numOf(n, 'length', 2.54),
    hide: flag(n, 'hide'),
    name: readPinText(child(n, 'name')),
    number: readPinText(child(n, 'number')),
    alternates: children(n, 'alternate').map(a => ({ name: str(a, 1), etype: str(a, 2), style: str(a, 3) })),
    properties: readAll(n, 'custom_property', property, ctx),
    extra: rest(n),
  };
}

/** One unit/body-style section: (symbol "Name_U_S" (unit_name "..") shapes... pins... texts...) */
function readUnit(n, ctx) {
  const m = /_(\d+)_(\d+)$/.exec(str(n));
  return {
    unit: m ? Number(m[1]) : 0,
    bodyStyle: m ? Number(m[2]) : 0,
    unitName: strOf(n, 'unit_name'),
    shapes: readAll(n, SHAPES, readShape, ctx),
    texts: readAll(n, 'text', readText, ctx),
    textBoxes: readAll(n, 'text_box', readTextBox, ctx),
    pins: readAll(n, 'pin', readPin, ctx),
    extra: rest(n),
  };
}

/** A library symbol definition. */
export function readSymbolDef(n, ctx) {
  const power = child(n, 'power');
  const pinNames = child(n, 'pin_names');
  const pinNumbers = child(n, 'pin_numbers');
  return {
    name: str(n),
    extends: strOf(n, 'extends'),
    power: power ? (text(power[1]) ?? 'global') : null,
    pinNames: { offset: numOf(pinNames, 'offset', 0.508), hide: flag(pinNames, 'hide') || !!pinNames?.includes('hide') },
    pinNumbers: { hide: flag(pinNumbers, 'hide') || !!pinNumbers?.includes('hide') },
    inBom: flag(n, 'in_bom', true),
    onBoard: flag(n, 'on_board', true),
    excludeFromSim: flag(n, 'exclude_from_sim'),
    inPosFiles: flag(n, 'in_pos_files', true),
    properties: readAll(n, 'property', property, ctx),
    units: readAll(n, 'symbol', readUnit, ctx),
    settings: settings(n, 'body_styles', 'associated_footprints', 'duplicate_pin_numbers_are_jumpers', 'jumper_pin_groups', 'pin_maps', 'embedded_fonts', 'embedded_files'),
    extra: rest(n),
  };
}

/** Resolve (extends "Parent"): derived symbols take the parent's graphics and inherit missing properties. */
export function resolveExtends(defs) {
  const byName = new Map(defs.map(d => [d.name, d]));
  for (const d of defs) {
    const parent = d.extends && byName.get(d.extends);
    if (!parent) continue;
    d.units = parent.units;
    const own = new Set(d.properties.map(p => p.name));
    d.properties = [...d.properties, ...parent.properties.filter(p => !own.has(p.name))];
  }
  return defs;
}

/** .kicad_sym file → {type: 'symbol_lib', symbols: [...]} */
export function readSymbolLib(root, ctx) {
  return {
    type: 'symbol_lib',
    symbols: resolveExtends(readAll(root, 'symbol', readSymbolDef, ctx)),
    extra: rest(root),
  };
}

