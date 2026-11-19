// Readers for structures shared by all KiCad file types.

import { print } from '../sexpr.js';
import { child, children, flag, num, numOf, str, strOf, tag, text, xy } from './read.js';

/** (at x y [angle]) → {x, y, rot}. */
export function at(n) {
  return n ? { x: num(n, 1, 0), y: num(n, 2, 0), rot: num(n, 3, 0) } : { x: 0, y: 0, rot: 0 };
}

/** (uuid "...") or legacy (tstamp ...). Internal identity only; never shown to users. */
export function uuid(n) {
  return strOf(n, 'uuid') ?? strOf(n, 'tstamp');
}

/** (color r g b a) → [r, g, b, a] with r/g/b in 0..255 and a in 0..1; undefined if absent or all-zero (= default). */
export function color(n) {
  const c = child(n, 'color');
  if (!c) return undefined;
  const rgba = [num(c, 1, 0), num(c, 2, 0), num(c, 3, 0), num(c, 4, 1)];
  return rgba.every(v => v === 0) ? undefined : rgba;
}

/**
 * (pts (xy x y) ... (arc (start ..) (mid ..) (end ..))) → list of points.
 * Arc entries are kept as {arc: {start, mid, end}} so polygons with arcs can be rendered exactly.
 */
export function pts(n) {
  const p = child(n, 'pts');
  if (!p) return [];
  return children(p, 'xy', 'arc').map(c =>
    c[0] === 'xy' ? xy(c) : { arc: { start: xy(child(c, 'start')), mid: xy(child(c, 'mid')), end: xy(child(c, 'end')) } });
}

/** (stroke (width w) (type t) (color ...)) → {width, type, color}; also legacy (width w). */
export function stroke(n) {
  const s = child(n, 'stroke');
  if (!s) return { width: numOf(n, 'width', 0), type: 'default' };
  return { width: numOf(s, 'width', 0), type: strOf(s, 'type') ?? 'default', color: color(s) };
}

/** (fill (type none|outline|background|color|hatch...) (color ...)), or board-style (fill yes|solid|none). */
export function fill(n) {
  const f = child(n, 'fill');
  if (!f) return { type: 'none' };
  if (f.length > 1 && !Array.isArray(f[1])) {
    const v = text(f[1]);
    return { type: v === 'yes' || v === 'solid' ? 'solid' : v === 'no' ? 'none' : v };
  }
  return { type: strOf(f, 'type') ?? 'none', color: color(f) };
}

/** (effects (font (face ..) (size h w) (thickness t) bold italic (color ..)) (justify ..) (hide yes) (href ..)). */
export function effects(n) {
  const e = child(n, 'effects');
  if (!e) return { size: { w: 1.27, h: 1.27 }, justify: {}, hide: false };
  const font = child(e, 'font');
  const size = child(font, 'size');
  const just = child(e, 'justify');
  const words = just ? just.slice(1).map(text) : [];
  return {
    face: strOf(font, 'face'),
    size: { h: num(size, 1, 1.27), w: num(size, 2, 1.27) },
    thickness: numOf(font, 'thickness'),
    bold: flag(font, 'bold'),
    italic: flag(font, 'italic'),
    lineSpacing: numOf(font, 'line_spacing'),
    color: color(font),
    justify: {
      h: words.includes('left') ? 'left' : words.includes('right') ? 'right' : 'center',
      v: words.includes('top') ? 'top' : words.includes('bottom') ? 'bottom' : 'center',
      mirror: words.includes('mirror'),
    },
    hide: flag(e, 'hide'),
    href: strOf(e, 'href'),
  };
}

/** (property "Name" "Value" (at ..) (hide yes) (show_name yes) (effects ..) ...) as used by schematics and boards. */
export function property(n) {
  return {
    name: str(n, 1),
    value: str(n, 2),
    at: at(child(n, 'at')),
    hide: flag(n, 'hide') || hasHideInEffects(n),
    showName: flag(n, 'show_name'),
    doNotAutoplace: flag(n, 'do_not_autoplace'),
    layer: strOf(n, 'layer'),
    unlocked: flag(n, 'unlocked'),
    private: n.includes('private'),
    effects: effects(n),
    uuid: uuid(n),
  };
}

function hasHideInEffects(n) {
  const e = child(n, 'effects');
  return !!e && flag(e, 'hide');
}

/** (title_block (title ..) (date ..) (rev ..) (company ..) (comment 1 "..")) → plain object. */
export function titleBlock(n) {
  const t = child(n, 'title_block');
  if (!t) return undefined;
  const out = { title: strOf(t, 'title'), date: strOf(t, 'date'), rev: strOf(t, 'rev'), company: strOf(t, 'company'), comments: {} };
  for (const c of children(t, 'comment')) out.comments[str(c, 1)] = str(c, 2);
  return out;
}

/** (paper "A4" [portrait]) or (paper "User" w h). */
export function paper(n) {
  const p = child(n, 'paper');
  if (!p) return undefined;
  return { size: str(p, 1), width: num(p, 2), height: num(p, 3), portrait: p.includes('portrait') };
}

/**
 * Settings we keep only as canonical text, so changes still show up as metadata diffs.
 * Marks the children used. Returns {tag: text} (repeated tags are joined).
 */
export function settings(n, ...names) {
  const out = {};
  for (const c of children(n, ...names)) markUsed(c), add(out, tag(c), print(c));
  return out;
}

/**
 * Unread child lists, as canonical text. These are NOT marked used (they show up in the unhandled
 * report), but are kept so that a change to an unsupported element still shows up in the diff.
 */
export function rest(n) {
  const out = {};
  for (let i = 1; i < n.length; i++) {
    const c = n[i];
    if (Array.isArray(c) && !c.used) add(out, tag(c) ?? '()', print(c));
  }
  return out;
}

function add(out, key, value) {
  out[key] = key in out ? out[key] + '\n' + value : value;
}

function markUsed(n) {
  n.used = true;
  for (const c of n) if (Array.isArray(c)) markUsed(c);
}

/** Mark a whole subtree as consumed (for data we read wholesale, e.g. embedded files). */
export { markUsed };
