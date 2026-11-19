// Placement of library symbols on a schematic sheet: which units/body styles are drawn, the
// library → sheet transform, and the sheet positions of pins (shared by rendering and netlists).
//
// Library symbols use y-up coordinates. KiCad's symbol orientation matrix is "mirror ∘ rotation"
// applied to y-down library coordinates; positive angles rotate counter-clockwise on screen.

import { apply, IDENTITY, multiply, rotate, scale, translate } from '../geom.js';

export const FLIP_Y = scale(1, -1);

/** Orientation part of a symbol's transform (without translation), for y-down library coordinates. */
export function orientation(sym) {
  const mirror = sym.mirror === 'x' ? scale(1, -1) : sym.mirror === 'y' ? scale(-1, 1) : IDENTITY;
  return multiply(mirror, rotate(sym.at.rot));
}

/** Full library (y-up) → sheet transform of a placed symbol. */
export function symbolTransform(sym) {
  return multiply(translate(sym.at.x, sym.at.y), multiply(orientation(sym), FLIP_Y));
}

/** Find the library definition a placed symbol refers to. */
export function findDef(schematic, sym) {
  const name = sym.libName ?? sym.libId;
  return schematic.libSymbols.find(d => d.name === name) ?? schematic.libSymbols.find(d => d.name === sym.libId);
}

/** Units/body styles of a definition that are drawn for this placed symbol. */
export function drawnUnits(def, sym) {
  return def.units.filter(u => (u.unit === 0 || u.unit === sym.unit) && (u.bodyStyle === 0 || u.bodyStyle === sym.bodyStyle));
}

/** Pins of a placed symbol in sheet coordinates: tip (connection point) and body end. */
export function placedPins(def, sym) {
  const m = symbolTransform(sym);
  const out = [];
  for (const u of drawnUnits(def, sym)) {
    for (const p of u.pins) {
      const a = (p.at.rot * Math.PI) / 180;
      const [tx, ty] = apply(m, p.at.x, p.at.y);
      const [ex, ey] = apply(m, p.at.x + p.length * Math.cos(a), p.at.y + p.length * Math.sin(a));
      out.push({ pin: p, number: p.number.text, name: p.name.text, etype: p.etype, tip: { x: tx, y: ty }, end: { x: ex, y: ey } });
    }
  }
  return out;
}

/** Reference designator of a placed symbol: the Reference field, else the first instance's. */
export function referenceOf(sym) {
  return sym.properties.find(p => p.name === 'Reference')?.value ?? sym.instances[0]?.reference ?? '?';
}

export function fieldValue(item, name) {
  return item.properties?.find(p => p.name === name)?.value;
}
