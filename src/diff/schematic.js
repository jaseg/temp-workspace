// Changes between two versions of a schematic sheet.

import { fieldKey, itemKey, sheetPinKey } from '../kicad/keys.js';
import { referenceOf } from '../kicad/place.js';
import { schematicNetlist } from './netlist-sch.js';
import { connectivityChanges, reroutes } from './connectivity.js';
import { changedWiring } from './wires.js';
import { canon, change, changedKeys, describeMove, fmtPoint, match, propertyChanges, q, same } from './util.js';

const FLAGS = { dnp: 'DNP', inBom: 'in BOM', onBoard: 'on board', excludeFromSim: 'excluded from simulation', inPosFiles: 'in position files' };
const yesNo = v => (v ? 'yes' : 'no');

function indexed(model, type) {
  return model.items.map((it, i) => ({ it, key: itemKey(it, i) })).filter(e => (Array.isArray(type) ? type.includes(e.it.type) : e.it.type === type));
}

const byUuid = e => e.it.uuid;

function symbolChanges(a, b, out) {
  const ref = e => referenceOf(e.it);
  const { pairs, removed, added } = match(indexed(a, 'symbol'), indexed(b, 'symbol'), [
    byUuid,
    e => (/\?$/.test(ref(e)) ? undefined : `${ref(e)}|${e.it.unit}`),
    e => `${e.it.libId}|${fmtPoint(e.it.at)}`,
  ]);
  for (const e of removed) out.push(change('electrical', 'removed', ref(e), `${ref(e)} removed (${e.it.libId})`, { old: [e.key] }));
  for (const e of added) out.push(change('electrical', 'added', ref(e), `${ref(e)} added (${e.it.libId})`, { new: [e.key] }));
  for (const [ea, eb] of pairs) {
    const sa = ea.it, sb = eb.it;
    const r = ref(eb);
    const move = describeMove(sa.at, sb.at) + (sa.mirror !== sb.mirror ? `${sa.at.x === sb.at.x && sa.at.y === sb.at.y ? '' : ', '}mirror ${sa.mirror ?? 'none'} → ${sb.mirror ?? 'none'}` : '');
    if (move) out.push(change('layout', 'modified', r, `${r} ${move}`, { minor: true, old: [ea.key], new: [eb.key] }));
    const meta = [];
    const focusOld = [], focusNew = [];
    if (ref(ea) !== r) meta.push(`Reference ${q(ref(ea))} → ${q(r)}`);
    if (sa.libId !== sb.libId) meta.push(`Symbol ${sa.libId} → ${sb.libId}`);
    if (sa.unit !== sb.unit) meta.push(`Unit ${sa.unit} → ${sb.unit}`);
    if (sa.bodyStyle !== sb.bodyStyle) meta.push(`Body style ${sa.bodyStyle} → ${sb.bodyStyle}`);
    for (const [k, label] of Object.entries(FLAGS)) if (sa[k] !== sb[k]) meta.push(`${label}: ${yesNo(sa[k])} → ${yesNo(sb[k])}`);
    let restyled = false;
    for (const p of propertyChanges(sa.properties, sb.properties)) {
      if (p.name === 'Reference' && p.op === 'value') continue;
      if (p.op === 'style') restyled = true;
      else {
        meta.push(p.text);
        focusOld.push(fieldKey(ea.key, p.name));
        focusNew.push(fieldKey(eb.key, p.name));
      }
    }
    for (const p of propertyChanges(sa.customProperties, sb.customProperties)) if (p.op !== 'style') meta.push(p.text);
    const alt = pins => Object.fromEntries(pins.filter(p => p.alternate).map(p => [p.number, p.alternate]));
    for (const n of changedKeys(alt(sa.pins), alt(sb.pins))) meta.push(`Pin ${n} alternate function ${q(alt(sa.pins)[n])} → ${q(alt(sb.pins)[n])}`);
    if (!same(sa.extra, sb.extra) || !same(sa.settings, sb.settings)) meta.push('Other attributes changed');
    if (meta.length) {
      out.push(change('metadata', 'modified', r, meta.length === 1 ? `${r} ${meta[0]}` : `${r}: ${meta.length} attributes changed`, {
        details: meta.length > 1 ? meta : [], old: focusOld.length ? focusOld : [ea.key], new: focusNew.length ? focusNew : [eb.key],
      }));
    }
    if (restyled && !move) out.push(change('layout', 'modified', r, `${r} fields moved or restyled`, { minor: true, old: [ea.key], new: [eb.key] }));
  }
}

const LABEL_TYPES = ['label', 'global_label', 'hierarchical_label', 'directive_label', 'netclass_flag'];
const LABEL_NAMES = { label: 'Label', global_label: 'Global label', hierarchical_label: 'Hierarchical label', directive_label: 'Directive label', netclass_flag: 'Net class flag' };

function labelChanges(a, b, out) {
  const { pairs, removed, added } = match(indexed(a, LABEL_TYPES), indexed(b, LABEL_TYPES), [byUuid, e => `${e.it.type}|${e.it.text}|${fmtPoint(e.it.at)}`]);
  const name = e => `${LABEL_NAMES[e.it.type]} ${e.it.text}`;
  for (const e of removed) out.push(change('electrical', 'removed', name(e), `${name(e)} removed`, { old: [e.key] }));
  for (const e of added) out.push(change('electrical', 'added', name(e), `${name(e)} added`, { new: [e.key] }));
  for (const [ea, eb] of pairs) {
    const la = ea.it, lb = eb.it;
    if (la.text !== lb.text || la.type !== lb.type) {
      out.push(change('electrical', 'modified', name(eb), `${name(ea)} renamed to ${lb.text}`, { old: [ea.key], new: [eb.key] }));
    }
    const move = describeMove(la.at, lb.at);
    if (move) out.push(change('layout', 'modified', name(eb), `${name(eb)} ${move}`, { minor: true, old: [ea.key], new: [eb.key] }));
    if (la.shape !== lb.shape) out.push(change('metadata', 'modified', name(eb), `${name(eb)} shape ${la.shape} → ${lb.shape}`, { old: [ea.key], new: [eb.key] }));
    const props = propertyChanges(la.properties, lb.properties).filter(p => p.op !== 'style');
    if (props.length) out.push(change('metadata', 'modified', name(eb), `${name(eb)}: ${props.map(p => p.text).join('; ')}`, { old: [ea.key], new: [eb.key] }));
  }
}

function sheetChanges(a, b, out) {
  const sheetName = e => e.it.properties.find(p => /^Sheet ?name$/i.test(p.name))?.value ?? 'sheet';
  const { pairs, removed, added } = match(indexed(a, 'sheet'), indexed(b, 'sheet'), [byUuid, sheetName]);
  for (const e of removed) out.push(change('electrical', 'removed', `sheet ${sheetName(e)}`, `Sheet ${sheetName(e)} removed`, { old: [e.key] }));
  for (const e of added) out.push(change('electrical', 'added', `sheet ${sheetName(e)}`, `Sheet ${sheetName(e)} added`, { new: [e.key] }));
  for (const [ea, eb] of pairs) {
    const s = `sheet ${sheetName(eb)}`;
    const geo = describeMove(ea.it.at, eb.it.at) || (same(ea.it.size, eb.it.size) ? '' : 'resized');
    if (geo) out.push(change('layout', 'modified', s, `Sheet ${sheetName(eb)} ${geo}`, { minor: true, old: [ea.key], new: [eb.key] }));
    const props = propertyChanges(ea.it.properties, eb.it.properties).filter(p => p.op !== 'style');
    if (props.length) out.push(change('metadata', 'modified', s, `Sheet ${sheetName(eb)}: ${props.map(p => p.text).join('; ')}`, { old: [ea.key], new: [eb.key] }));
    const pins = match(ea.it.pins, eb.it.pins, [p => p.uuid, p => p.name]);
    for (const p of pins.removed) out.push(change('electrical', 'removed', s, `Sheet pin ${p.name} removed from sheet ${sheetName(eb)}`, { old: [sheetPinKey(ea.key, p.name)] }));
    for (const p of pins.added) out.push(change('electrical', 'added', s, `Sheet pin ${p.name} added to sheet ${sheetName(eb)}`, { new: [sheetPinKey(eb.key, p.name)] }));
    for (const [pa, pb] of pins.pairs) {
      if (pa.name !== pb.name || pa.shape !== pb.shape) out.push(change('electrical', 'modified', s, `Sheet pin ${pa.name} → ${pb.name} (${pb.shape})`, { old: [sheetPinKey(ea.key, pa.name)], new: [sheetPinKey(eb.key, pb.name)] }));
      else if (describeMove(pa.at, pb.at)) out.push(change('layout', 'modified', s, `Sheet pin ${pb.name} moved`, { minor: true, old: [sheetPinKey(ea.key, pa.name)], new: [sheetPinKey(eb.key, pb.name)] }));
    }
  }
}

/** Junctions and no-connect flags, matched by position. */
function markerChanges(a, b, out) {
  for (const [type, label, kind] of [['junction', 'Junction', 'electrical'], ['no_connect', 'No-connect flag', 'metadata']]) {
    const { removed, added } = match(indexed(a, type), indexed(b, type), [e => fmtPoint(e.it.at)]);
    for (const e of removed) out.push(change(kind, 'removed', label, `${label} at ${fmtPoint(e.it.at)} removed`, { old: [e.key] }));
    for (const e of added) out.push(change(kind, 'added', label, `${label} at ${fmtPoint(e.it.at)} added`, { new: [e.key] }));
  }
}

const OTHER = ['text', 'text_box', 'table', 'polyline', 'bezier', 'rectangle', 'circle', 'arc', 'ellipse', 'ellipse_arc', 'image', 'rule_area', 'bus', 'bus_entry', 'group'];
const OTHER_NAMES = { text: 'Text', text_box: 'Text box', table: 'Table', image: 'Image', rule_area: 'Rule area', bus: 'Bus', bus_entry: 'Bus entry', group: 'Group' };

/** Text and graphics: geometry changes are minor layout changes, text content changes are metadata. */
function otherChanges(a, b, out) {
  const { pairs, removed, added } = match(indexed(a, OTHER), indexed(b, OTHER), [byUuid, e => canon(e.it)]);
  const name = e => `${OTHER_NAMES[e.it.type] ?? 'Graphic'}${e.it.text ? ` ${q(e.it.text)}` : ''}`;
  const kindOf = e => (e.it.type === 'bus' || e.it.type === 'bus_entry' ? 'electrical' : 'layout');
  for (const e of removed) out.push(change(kindOf(e), 'removed', name(e), `${name(e)} removed`, { minor: kindOf(e) === 'layout', old: [e.key] }));
  for (const e of added) out.push(change(kindOf(e), 'added', name(e), `${name(e)} added`, { minor: kindOf(e) === 'layout', new: [e.key] }));
  for (const [ea, eb] of pairs) {
    if (same(ea.it, eb.it)) continue;
    if (ea.it.text !== eb.it.text) out.push(change('metadata', 'modified', name(eb), `${OTHER_NAMES[eb.it.type] ?? 'Text'} changed: ${q(ea.it.text)} → ${q(eb.it.text)}`, { old: [ea.key], new: [eb.key] }));
    else out.push(change('layout', 'modified', name(eb), `${name(eb)} ${describeMove(ea.it.at ?? {}, eb.it.at ?? {}) || 'changed'}`, { minor: true, old: [ea.key], new: [eb.key] }));
  }
}

function libraryChanges(a, b, out) {
  const { pairs } = match(a.libSymbols, b.libSymbols, [d => d.name]);
  for (const [da, db] of pairs) {
    if (same(da, db)) continue;
    const parts = [];
    const pins = d => canon(d.units.map(u => u.pins.map(p => [p.number.text, p.name.text, p.etype, p.at, p.length, p.hide])));
    if (pins(da) !== pins(db)) parts.push('pins');
    if (canon(da.units.map(u => [u.shapes, u.texts])) !== canon(db.units.map(u => [u.shapes, u.texts]))) parts.push('graphics');
    if (!same(da.properties, db.properties)) parts.push('default fields');
    if (!parts.length) parts.push('attributes');
    out.push(change('layout', 'modified', db.name, `Symbol ${db.name}: ${parts.join(', ')} changed`, { details: ['Affects every use of this symbol on the sheet'] }));
  }
}

function sheetSettingsChanges(a, b, out) {
  const meta = [];
  for (const k of changedKeys(a.titleBlock ?? {}, b.titleBlock ?? {})) meta.push(`Title block ${k} changed`);
  if (!same(a.paper, b.paper)) meta.push(`Paper ${a.paper?.size ?? '?'} → ${b.paper?.size ?? '?'}`);
  for (const k of changedKeys(a.settings, b.settings)) meta.push(`${k.replace(/_/g, ' ')} changed`);
  for (const k of changedKeys(a.extra, b.extra)) meta.push(`Unsupported element ${k} changed`);
  if (meta.length) out.push(change('metadata', 'modified', 'sheet', meta.length === 1 ? meta[0] : `${meta.length} sheet settings changed`, { minor: true, details: meta.length > 1 ? meta : [] }));
}

export function diffSchematic(a, b) {
  const out = [];
  const segs = model => indexed(model, 'wire').flatMap(({ it, key }) => it.pts.slice(1).map((p, i) => ({ a: it.pts[i], b: p, key })));
  const wires = changedWiring(segs(a), segs(b));
  const na = schematicNetlist(a), nb = schematicNetlist(b);
  const pinLabel = id => {
    const p = nb.pins.get(id) ?? na.pins.get(id);
    return p.name && p.name !== '~' && p.name !== p.number ? `${p.ref} pin ${p.number} (${p.name})` : `${p.ref} pin ${p.number}`;
  };
  const electrical = connectivityChanges(na, nb, { changedWires: wires, pinLabel });
  out.push(...electrical);

  // Wiring changes not explained by connectivity changes: reroutes.
  const explained = new Set(electrical.flatMap(c => [...c.old, ...c.new]));
  const left = { old: new Set([...wires.old].filter(k => !explained.has(k))), new: new Set([...wires.new].filter(k => !explained.has(k))) };
  for (const [net, keys] of reroutes(left, k => na.wireNet.get(k), k => nb.wireNet.get(k))) {
    const summary = net ? `Wiring of net ${net} rerouted` : 'Unconnected wiring changed';
    out.push(change('layout', 'modified', net ? `net ${net}` : 'wiring', summary, { minor: true, old: keys.old, new: keys.new, net }));
  }

  symbolChanges(a, b, out);
  labelChanges(a, b, out);
  sheetChanges(a, b, out);
  markerChanges(a, b, out);
  otherChanges(a, b, out);
  libraryChanges(a, b, out);
  sheetSettingsChanges(a, b, out);
  return out;
}


