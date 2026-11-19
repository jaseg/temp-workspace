// Geometric comparison of wiring (schematic wires, board tracks). Collinear touching segments are
// merged first, so splitting or joining a wire without changing its shape is not a change.

const R = v => Math.round(v * 1e4) / 1e4;

/** Canonical maximal segments of a list of {a, b, key, group} (group: e.g. layer + width). */
function maximal(segs) {
  const lines = new Map();
  for (const s of segs) {
    let { a, b } = s;
    if (a.x > b.x || (a.x === b.x && a.y > b.y)) [a, b] = [b, a];
    const dx = b.x - a.x, dy = b.y - a.y;
    const len = Math.hypot(dx, dy);
    if (len < 1e-9) continue;
    const ux = dx / len, uy = dy / len;
    const offset = R(a.x * uy - a.y * ux); // distance of the line from the origin
    const line = `${s.group ?? ''}|${R(ux)},${R(uy)}|${offset}`;
    const t0 = a.x * ux + a.y * uy;
    if (!lines.has(line)) lines.set(line, []);
    lines.get(line).push({ t0: R(t0), t1: R(t0 + len), key: s.key });
  }
  const out = [];
  for (const [line, spans] of lines) {
    spans.sort((x, y) => x.t0 - y.t0);
    let cur = null;
    for (const s of spans) {
      if (cur && s.t0 <= cur.t1 + 1e-4) {
        cur.t1 = Math.max(cur.t1, s.t1);
        cur.keys.push(s.key);
      } else {
        if (cur) out.push(cur);
        cur = { line, t0: s.t0, t1: s.t1, keys: [s.key] };
      }
    }
    if (cur) out.push(cur);
  }
  return out;
}

/** Item keys (per version) of wiring whose geometry differs between the versions. */
export function changedWiring(oldSegs, newSegs) {
  const A = maximal(oldSegs), B = maximal(newSegs);
  const id = s => `${s.line}|${R(s.t0)}|${R(s.t1)}`;
  const inA = new Set(A.map(id)), inB = new Set(B.map(id));
  const keys = (list, other) => new Set(list.filter(s => !other.has(id(s))).flatMap(s => s.keys));
  return { old: keys(A, inB), new: keys(B, inA) };
}
