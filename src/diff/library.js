// Changes between two versions of a symbol library (.kicad_sym). Each change names the library
// entry (`entry`) it belongs to, so the viewer can switch to that symbol.

import { fieldKey, libSymbolKey, pinKey } from '../kicad/keys.js';
import { canon, change, match, propertyChanges, q, same } from './util.js';

function pinsOf(def) {
  return def.units.flatMap(u => u.pins.map(p => ({ ...p, unit: u.unit, bodyStyle: u.bodyStyle })));
}

function symbolChanges(a, b, out) {
  const key = libSymbolKey(b.name);
  const keyA = libSymbolKey(a.name);
  const at = (c, entry = b.name) => out.push(Object.assign(c, { entry }));
  const pins = match(pinsOf(a), pinsOf(b), [p => `${p.unit}|${p.bodyStyle}|${p.number.text}`, p => `${p.unit}|${p.number.text}`]);
  for (const p of pins.removed) at(change('electrical', 'removed', b.name, `${b.name} pin ${p.number.text} (${p.name.text}) removed`, { old: [pinKey(keyA, p.number.text)] }));
  for (const p of pins.added) at(change('electrical', 'added', b.name, `${b.name} pin ${p.number.text} (${p.name.text}) added`, { new: [pinKey(key, p.number.text)] }));
  for (const [pa, pb] of pins.pairs) {
    const f = { old: [pinKey(keyA, pa.number.text)], new: [pinKey(key, pb.number.text)] };
    const sub = `${b.name} pin ${pb.number.text}`;
    if (pa.etype !== pb.etype) at(change('electrical', 'modified', sub, `${sub} type ${pa.etype} → ${pb.etype}`, f));
    if (pa.name.text !== pb.name.text) at(change('metadata', 'modified', sub, `${sub} name ${q(pa.name.text)} → ${q(pb.name.text)}`, f));
    if (!same(pa.at, pb.at) || pa.length !== pb.length) at(change('layout', 'modified', sub, `${sub} moved`, f));
    if (pa.style !== pb.style || pa.hide !== pb.hide || !same(pa.alternates, pb.alternates)) at(change('metadata', 'modified', sub, `${sub} style or alternates changed`, { minor: true, ...f }));
  }
  const graphics = d => canon(d.units.map(u => [u.unit, u.bodyStyle, u.shapes, u.texts, u.textBoxes]));
  if (graphics(a) !== graphics(b)) at(change('layout', 'modified', b.name, `${b.name} graphics changed`, { old: [keyA], new: [key] }));
  const props = propertyChanges(a.properties, b.properties).filter(p => p.op !== 'style');
  if (props.length) {
    at(change('metadata', 'modified', b.name, props.length === 1 ? `${b.name} ${props[0].text}` : `${b.name}: ${props.length} fields changed`, {
      details: props.length > 1 ? props.map(p => p.text) : [], old: props.map(p => fieldKey(keyA, p.name)), new: props.map(p => fieldKey(key, p.name)),
    }));
  }
  const flags = ['extends', 'power', 'pinNames', 'pinNumbers', 'inBom', 'onBoard', 'excludeFromSim', 'inPosFiles', 'settings', 'extra'].filter(k => !same(a[k], b[k]));
  if (flags.length) at(change('metadata', 'modified', b.name, `${b.name} options changed (${flags.join(', ')})`, { minor: true, old: [keyA], new: [key] }));
}

export function diffSymbolLib(a, b) {
  const out = [];
  const { pairs, removed, added } = match(a.symbols, b.symbols, [d => d.name]);
  for (const d of removed) out.push(Object.assign(change('metadata', 'removed', d.name, `Symbol ${d.name} removed`, { old: [libSymbolKey(d.name)] }), { entry: d.name }));
  for (const d of added) out.push(Object.assign(change('metadata', 'added', d.name, `Symbol ${d.name} added`, { new: [libSymbolKey(d.name)] }), { entry: d.name }));
  for (const [da, db] of pairs) if (!same(da, db)) symbolChanges(da, db, out);
  return out;
}
