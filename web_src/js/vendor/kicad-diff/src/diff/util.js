// Helpers shared by the diff engines: matching elements between versions, comparing them, and
// building change records.

/**
 * Pair up elements of two versions. `keys` are functions tried in order (e.g. by UUID, then by
 * reference designator); each returns a string key or undefined. Elements with equal keys are
 * paired in order of appearance (so duplicates, e.g. stacked identical pads, still pair up).
 * @returns {{pairs: [object, object][], removed: object[], added: object[]}}
 */
export function match(olds, news, keys) {
  let a = olds.map((v, i) => ({ v, i }));
  let b = news.map((v, i) => ({ v, i }));
  const pairs = [];
  for (const key of keys) {
    const index = list => {
      const m = new Map();
      for (const e of list) {
        const k = key(e.v);
        if (k === undefined) continue;
        if (!m.has(k)) m.set(k, []);
        m.get(k).push(e);
      }
      return m;
    };
    const ia = index(a);
    const ib = index(b);
    const used = new Set();
    for (const [k, la] of ia) {
      const lb = ib.get(k) ?? [];
      for (let i = 0; i < Math.min(la.length, lb.length); i++) {
        pairs.push([la[i], lb[i]]);
        used.add(la[i]).add(lb[i]);
      }
    }
    a = a.filter(e => !used.has(e));
    b = b.filter(e => !used.has(e));
  }
  pairs.sort((x, y) => x[1].i - y[1].i);
  return { pairs: pairs.map(([x, y]) => [x.v, y.v]), removed: a.map(e => e.v), added: b.map(e => e.v) };
}

/** Structural equality, ignoring internal identity (uuid) and source positions. */
export function same(a, b) {
  return canon(a) === canon(b);
}

export function canon(v) {
  return JSON.stringify(normalize(v));
}

/** Copy with sorted object keys, rounded numbers and no identity/source fields. */
function normalize(v) {
  if (typeof v === 'number') return Math.round(v * 1e4) / 1e4;
  if (Array.isArray(v)) return v.map(normalize);
  if (!v || typeof v !== 'object') return v;
  const out = {};
  for (const k of Object.keys(v).sort()) if (k !== 'uuid' && k !== 'pos' && k !== 'used' && v[k] !== undefined) out[k] = normalize(v[k]);
  return out;
}

/** Order-insensitive structural equality of two lists. */
export function sameItems(a, b) {
  const sorted = list => (list ?? []).map(canon).sort().join('\n');
  return sorted(a) === sorted(b);
}

/** Keys of two plain objects whose values differ (shallow, structural). */
export function changedKeys(a, b, ignore = []) {
  const keys = new Set([...Object.keys(a ?? {}), ...Object.keys(b ?? {})]);
  return [...keys].filter(k => !ignore.includes(k) && !same(a?.[k], b?.[k]));
}

/** Format a length in mm for messages. */
export function mm(v) {
  return `${Math.round(v * 1000) / 1000}`;
}

export function fmtPoint(p) {
  return `(${mm(p.x)}, ${mm(p.y)})`;
}

/** Describe a move/rotation between two placements {x, y, rot}. Empty string if unchanged. */
export function describeMove(a, b) {
  const parts = [];
  const dx = b.x - a.x, dy = b.y - a.y;
  const signed = v => (Math.abs(v) < 1e-9 ? '0' : `${v > 0 ? '+' : ''}${mm(v)}`);
  if (Math.hypot(dx, dy) > 1e-6) parts.push(`moved by (${signed(dx)}, ${signed(dy)}) mm`);
  const dr = ((((b.rot ?? 0) - (a.rot ?? 0)) % 360) + 360) % 360;
  if (dr > 1e-6) parts.push(`rotated ${Math.round((dr > 180 ? dr - 360 : dr) * 100) / 100}°`);
  return parts.join(', ');
}

/** Short quoted value for messages. */
export function q(v) {
  if (v === undefined || v === null || v === '') return '(empty)';
  const s = String(v);
  return `“${s.length > 60 ? s.slice(0, 57) + '…' : s}”`;
}

let nextId = 0;

/** Create a change record. `old`/`new` are scene item keys to highlight in each version. */
export function change(kind, op, subject, summary, { minor = false, details = [], old = [], new: nu = [], net } = {}) {
  return { id: ++nextId, kind, op, minor, subject, summary, details, old, new: nu, net };
}

/** Summarise field-level differences of two property lists [{name, value}]. */
export function propertyChanges(a, b) {
  const out = [];
  const byName = list => new Map(list.map(p => [p.name, p]));
  const A = byName(a), B = byName(b);
  for (const [name, p] of B) {
    const o = A.get(name);
    if (!o) out.push({ name, op: 'added', text: `${name} added: ${q(p.value)}` });
    else if (o.value !== p.value) out.push({ name, op: 'value', text: `${name}: ${q(o.value)} → ${q(p.value)}` });
    else if (!same({ ...o, value: 0 }, { ...p, value: 0 })) out.push({ name, op: 'style', text: `${name} field moved or restyled` });
  }
  for (const [name, o] of A) if (!B.has(name)) out.push({ name, op: 'removed', text: `${name} removed (was ${q(o.value)})` });
  return out;
}
