// Small accessors over the generic s-expression tree (see ../sexpr.js).
// Every accessor that consumes a child list marks it `used`, so unread tokens can be reported.

/** The head atom of a list, e.g. 'pin' for (pin ...). */
export function tag(n) {
  return Array.isArray(n) && typeof n[0] === 'string' ? n[0] : undefined;
}

/** First child list with the given head, marked as used. */
export function child(n, name) {
  if (!n) return undefined;
  for (let i = 1; i < n.length; i++) {
    const c = n[i];
    if (Array.isArray(c) && c[0] === name) {
      c.used = true;
      return c;
    }
  }
  return undefined;
}

/** All child lists with the given head (or any of several heads), marked as used. */
export function children(n, ...names) {
  const out = [];
  if (!n) return out;
  for (let i = 1; i < n.length; i++) {
    const c = n[i];
    if (Array.isArray(c) && names.includes(c[0])) {
      c.used = true;
      out.push(c);
    }
  }
  return out;
}

/** Mark children as deliberately ignored. */
export function ignore(n, ...names) {
  children(n, ...names);
}

/** Text of an atom or quoted string. */
export function text(v) {
  return typeof v === 'string' ? v : v?.str;
}

/** Text at position i of a list (default: the first argument). */
export function str(n, i = 1) {
  return n ? text(n[i]) : undefined;
}

/** Number at position i of a list; undefined if absent. */
export function num(n, i = 1, fallback = undefined) {
  const v = n ? text(n[i]) : undefined;
  return v === undefined ? fallback : Number(v);
}

/** Number from a named child, e.g. numOf(n, 'width') for (width 0.1). */
export function numOf(n, name, fallback = undefined) {
  return num(child(n, name), 1, fallback);
}

/** Text from a named child, e.g. strOf(n, 'layer') for (layer "F.Cu"). */
export function strOf(n, name) {
  return str(child(n, name));
}

/**
 * Boolean flag that KiCad writes in several ways over the versions:
 * bare atom `hide`, `(hide)`, `(hide yes)` or `(hide no)`.
 */
export function flag(n, name, fallback = false) {
  if (!n) return fallback;
  for (let i = 1; i < n.length; i++) {
    const c = n[i];
    if (c === name) return true;
    if (Array.isArray(c) && c[0] === name) {
      c.used = true;
      return c.length < 2 || c[1] === 'yes' || c[1] === 'true';
    }
  }
  return fallback;
}

/** True if a bare atom is present among the list's arguments, e.g. `locked` in (footprint "x" locked ...). */
export function hasAtom(n, name) {
  return Array.isArray(n) && n.includes(name);
}

/** Point from (xy x y), (at x y [angle]), (start x y) and similar. */
export function xy(n) {
  return n ? { x: num(n, 1, 0), y: num(n, 2, 0) } : undefined;
}

/** Read a child list with `fn`, isolating failures: on error the element is dropped and recorded. */
export function tryRead(n, fn, ctx) {
  try {
    return fn(n, ctx);
  } catch (e) {
    ctx.errors.push({ tag: tag(n), pos: n.pos, message: e.message });
    return null;
  }
}

/** Read all children with the given head(s) through tryRead, dropping failures. */
export function readAll(n, names, fn, ctx) {
  const list = Array.isArray(names) ? names : [names];
  return children(n, ...list).map(c => tryRead(c, fn, ctx)).filter(v => v != null);
}

/**
 * Collect tag paths of list nodes that no reader consumed, below a consumed node.
 * Returns a Map path → count, e.g. 'kicad_sch/symbol/foo' → 3.
 */
export function unhandled(root) {
  const out = new Map();
  const walk = (n, path) => {
    for (let i = 1; i < n.length; i++) {
      const c = n[i];
      if (!Array.isArray(c)) continue;
      const p = `${path}/${tag(c) ?? '()'}`;
      if (c.used) walk(c, p);
      else out.set(p, (out.get(p) ?? 0) + 1);
    }
  };
  walk(root, tag(root));
  return out;
}
