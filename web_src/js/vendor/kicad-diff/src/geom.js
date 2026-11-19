// 2D geometry helpers. KiCad coordinates are millimetres with y pointing down; positive
// angles (degrees) rotate counter-clockwise on screen.

const RAD = Math.PI / 180;

/** Affine transform [a, b, c, d, e, f]: x' = a x + c y + e, y' = b x + d y + f. */
export const IDENTITY = [1, 0, 0, 1, 0, 0];

export function multiply(m, n) {
  return [
    m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1],
    m[0] * n[2] + m[2] * n[3], m[1] * n[2] + m[3] * n[3],
    m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5],
  ];
}

export function translate(x, y) {
  return [1, 0, 0, 1, x, y];
}

/** Rotation by `deg` degrees, counter-clockwise on screen (y down). */
export function rotate(deg) {
  const c = Math.cos(deg * RAD);
  const s = Math.sin(deg * RAD);
  return [c, -s, s, c, 0, 0];
}

export function scale(sx, sy = sx) {
  return [sx, 0, 0, sy, 0, 0];
}

export function apply(m, x, y) {
  return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
}

/** Length scale factor of a transform (for stroke widths and text sizes). */
export function scaleOf(m) {
  return Math.sqrt(Math.abs(m[0] * m[3] - m[1] * m[2]));
}

export function isMirrored(m) {
  return m[0] * m[3] - m[1] * m[2] < 0;
}

/** On-screen rotation angle (degrees) that a transform applies to text. */
export function angleOf(m) {
  return -Math.atan2(m[1], m[0]) / RAD;
}

/** Circle through three points → {cx, cy, r}, or null if collinear. */
export function circleFrom3(a, b, c) {
  const d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y));
  if (Math.abs(d) < 1e-12) return null;
  const a2 = a.x * a.x + a.y * a.y;
  const b2 = b.x * b.x + b.y * b.y;
  const c2 = c.x * c.x + c.y * c.y;
  const cx = (a2 * (b.y - c.y) + b2 * (c.y - a.y) + c2 * (a.y - b.y)) / d;
  const cy = (a2 * (c.x - b.x) + b2 * (a.x - c.x) + c2 * (b.x - a.x)) / d;
  return { cx, cy, r: Math.hypot(a.x - cx, a.y - cy) };
}

/** Number of segments needed to approximate an arc of `sweep` radians with max deviation `tol`. */
export function arcSegments(r, sweep, tol = 0.005) {
  if (r <= tol) return 1;
  const step = 2 * Math.acos(1 - tol / r);
  return Math.min(256, Math.max(2, Math.ceil(Math.abs(sweep) / step)));
}

/** Points along the arc start → mid → end (falls back to a straight line if degenerate). */
export function arcPoints(start, mid, end, tol) {
  const c = circleFrom3(start, mid, end);
  if (!c) return [start, end];
  const a0 = Math.atan2(start.y - c.cy, start.x - c.cx);
  const am = Math.atan2(mid.y - c.cy, mid.x - c.cx);
  let a1 = Math.atan2(end.y - c.cy, end.x - c.cx);
  // Choose the sweep direction that passes through mid.
  const norm = a => ((a % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
  let sweep = norm(a1 - a0);
  if (norm(am - a0) > sweep) sweep -= 2 * Math.PI;
  const n = arcSegments(c.r, sweep, tol);
  const out = [];
  for (let i = 0; i <= n; i++) {
    const a = a0 + (sweep * i) / n;
    out.push({ x: c.cx + c.r * Math.cos(a), y: c.cy + c.r * Math.sin(a) });
  }
  out[0] = start;
  out[n] = end;
  return out;
}

/** Points of a full circle (closed: first point repeated at the end). */
export function circlePoints(cx, cy, r, tol) {
  const n = arcSegments(r, 2 * Math.PI, tol);
  const out = [];
  for (let i = 0; i <= n; i++) {
    const a = (2 * Math.PI * i) / n;
    out.push({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });
  }
  return out;
}

/** Cubic Bézier through 4 control points, flattened. */
export function bezierPoints(p0, p1, p2, p3, n = 24) {
  const out = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const u = 1 - t;
    const a = u * u * u, b = 3 * u * u * t, c = 3 * u * t * t, d = t * t * t;
    out.push({ x: a * p0.x + b * p1.x + c * p2.x + d * p3.x, y: a * p0.y + b * p1.y + c * p2.y + d * p3.y });
  }
  return out;
}

/** Expand polyline points that contain {arc: {start, mid, end}} entries (board polygons) into plain points. */
export function flattenPts(pts, tol) {
  const out = [];
  for (const p of pts) {
    if (p.arc) out.push(...arcPoints(p.arc.start, p.arc.mid, p.arc.end, tol));
    else out.push(p);
  }
  return out;
}

export function emptyBox() {
  return { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
}

export function extendBox(box, x, y, pad = 0) {
  if (x - pad < box.x0) box.x0 = x - pad;
  if (y - pad < box.y0) box.y0 = y - pad;
  if (x + pad > box.x1) box.x1 = x + pad;
  if (y + pad > box.y1) box.y1 = y + pad;
  return box;
}

export function unionBox(a, b) {
  return { x0: Math.min(a.x0, b.x0), y0: Math.min(a.y0, b.y0), x1: Math.max(a.x1, b.x1), y1: Math.max(a.y1, b.y1) };
}

export function isEmptyBox(b) {
  return !(b.x1 >= b.x0 && b.y1 >= b.y0);
}

export function boxContains(b, x, y) {
  return x >= b.x0 && x <= b.x1 && y >= b.y0 && y <= b.y1;
}

export function padBox(b, d) {
  return { x0: b.x0 - d, y0: b.y0 - d, x1: b.x1 + d, y1: b.y1 + d };
}

/** Distance from point (px, py) to segment (ax, ay)-(bx, by). */
export function segmentDistance(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
  return Math.hypot(px - ax - t * dx, py - ay - t * dy);
}
