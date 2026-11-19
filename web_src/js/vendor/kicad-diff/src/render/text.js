// Text layout following KiCad's conventions: the text size is the cap height, the anchor is
// justified horizontally (left/center/right) and vertically (top/center/bottom), lines are spaced
// by LINE_SPACING × height, and text is rotated counter-clockwise about its anchor.
//
// Two ways to draw: stroked with KiCad's Newstroke font (PCB silkscreen), or with a native browser
// font (everything else). Both share the layout below; only the glyph widths differ.

import { GLYPHS } from '../font/newstroke.js';

export const LINE_SPACING = 1.62;
const UNIT = 1 / 21; // Newstroke grid unit relative to the glyph height
const ITALIC_TILT = 1 / 8;
// Native monospace fonts: cap height ≈ 0.73 em, advance ≈ 0.6 em.
export const NATIVE_EM = 1 / 0.73;

const glyphCache = new Map();

/** Decoded Newstroke glyph: {advance, strokes: [[{x, y}]]} in units of the text height, y up = negative. */
function glyph(cp) {
  let g = glyphCache.get(cp);
  if (g) return g;
  const s = GLYPHS[cp] ?? GLYPHS[0x3f]; // '?' for missing glyphs
  const left = s.charCodeAt(0) - 82;
  const right = s.charCodeAt(1) - 82;
  const strokes = [];
  let cur = null;
  for (let i = 2; i < s.length; i += 2) {
    if (s[i] === ' ' && s[i + 1] === 'R') {
      cur = null;
      continue;
    }
    if (!cur) strokes.push((cur = []));
    cur.push({ x: (s.charCodeAt(i) - 82 - left) * UNIT, y: (s.charCodeAt(i + 1) - 82 - 10) * UNIT });
  }
  g = { advance: (right - left) * UNIT, strokes };
  glyphCache.set(cp, g);
  return g;
}

// KiCad escapes characters that are special in net names, e.g. "VPP{slash}MCLR".
const ESCAPES = { slash: '/', backslash: '\\', colon: ':', comma: ',', dblquote: '"', quote: "'", lt: '<', gt: '>', tab: '\t', return: '\n', space: ' ', brace: '{' };

/**
 * Strip KiCad text markup: ~{overbar}, _{subscript}, ^{superscript}, and escapes like {slash}.
 * Returns plain text plus overbar character ranges.
 */
export function plain(str) {
  str = str.replace(/\{(slash|backslash|colon|comma|dblquote|quote|lt|gt|tab|return|space|brace)\}/g, (_, k) => ESCAPES[k]);
  let text = '';
  const overbars = [];
  const re = /([~_^])\{([^}]*)\}/g;
  let last = 0;
  for (let m; (m = re.exec(str));) {
    text += str.slice(last, m.index);
    if (m[1] === '~') overbars.push([text.length, text.length + m[2].length]);
    text += m[2];
    last = re.lastIndex;
  }
  return { text: text + str.slice(last), overbars };
}

/** Width of one line of text in the stroke font, in model units. */
export function strokeWidth(line, w) {
  let width = 0;
  for (const ch of line) width += glyph(ch.codePointAt(0)).advance;
  return width * w;
}

/**
 * Lay out text: returns the lines with their left x and baseline y in text-local coordinates
 * (anchor at the origin, before rotation), and the local bounding box.
 * `measure(line)` gives a line's width; defaults to the stroke font.
 */
export function layout(t, measure = line => strokeWidth(line, t.w)) {
  const lines = plain(t.str).text.split('\n');
  const pitch = t.h * LINE_SPACING;
  const blockHeight = t.h + (lines.length - 1) * pitch;
  const firstBaseline = t.vj === 'top' ? t.h : t.vj === 'bottom' ? -(lines.length - 1) * pitch : t.h - blockHeight / 2;
  let x0 = Infinity, x1 = -Infinity;
  const out = lines.map((str, i) => {
    const width = measure(str);
    const x = t.hj === 'left' ? 0 : t.hj === 'right' ? -width : -width / 2;
    x0 = Math.min(x0, x);
    x1 = Math.max(x1, x + width);
    return { str, x, y: firstBaseline + i * pitch, width };
  });
  return { lines: out, box: { x0, y0: firstBaseline - t.h, x1, y1: firstBaseline + (lines.length - 1) * pitch + t.h * 0.25 } };
}

/** Map text-local coordinates to model coordinates (mirror, then rotate about the anchor). */
export function toModel(t, x, y) {
  const a = (t.rot * Math.PI) / 180;
  const c = Math.cos(a), s = Math.sin(a);
  const lx = t.mirror ? -x : x;
  return { x: t.x + lx * c + y * s, y: t.y - lx * s + y * c };
}

/** Corners of the text's bounding box in model coordinates. */
export function textCorners(t, measure) {
  const { box } = layout(t, measure);
  return [[box.x0, box.y0], [box.x1, box.y0], [box.x1, box.y1], [box.x0, box.y1]].map(([x, y]) => toModel(t, x, y));
}

/** Stroked text as polylines in model coordinates (for silkscreen and PDF). */
export function strokeText(t) {
  const out = [];
  const { lines } = layout(t);
  const { overbars } = plain(t.str);
  let offset = 0;
  for (const line of lines) {
    let x = line.x;
    const chars = [...line.str];
    chars.forEach((ch, i) => {
      const g = glyph(ch.codePointAt(0));
      for (const s of g.strokes) {
        out.push(s.map(p => {
          const gy = p.y * t.h;
          return toModel(t, x + p.x * t.w - (t.italic ? gy * ITALIC_TILT : 0), line.y + gy);
        }));
      }
      const pos = offset + i;
      if (overbars.some(([a, b]) => pos >= a && pos < b)) {
        const y = line.y - t.h * 1.25;
        out.push([toModel(t, x, y), toModel(t, x + g.advance * t.w, y)]);
      }
      x += g.advance * t.w;
    });
    offset += chars.length + 1;
  }
  return out;
}
