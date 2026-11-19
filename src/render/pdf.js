// PDF export: vector pages drawn from the same scenes the viewer shows, using pdf-lib for the
// document structure and raw content streams for the drawing (fast for millions of segments).
//
// Annotations become real PDF annotations (Ink, Square, Circle, FreeText) with appearance streams,
// so PDF tools can show and edit them; the annotations JSON is attached to the document.

import { layout } from './text.js';

const PAGE = { w: 1190.55, h: 841.89 }; // A3 landscape, in points
const MARGIN = 28;

const num = v => (Math.round(v * 1000) / 1000).toString();
const rgbOp = (c, op) => `${num(c[0])} ${num(c[1])} ${num(c[2])} ${op}`;

/** Content stream operators for one scene layer drawn in `color`. `gs(alpha)` names an ExtGState. */
function layerOps(l, color, gs, font, extraWidth = 0) {
  const out = [];
  if (color[3] < 1) out.push(`/${gs(color[3])} gs`);
  out.push(rgbOp(color, 'rg'), rgbOp(color, 'RG'));
  for (let i = 0; i < l.triangles.length; i += 9) {
    const t = l.triangles;
    out.push(`${num(t[i])} ${num(t[i + 1])} m ${num(t[i + 3])} ${num(t[i + 4])} l ${num(t[i + 6])} ${num(t[i + 7])} l h f`);
  }
  for (const f of l.fans) {
    const v = f.verts;
    const path = [`${num(v[0])} ${num(v[1])} m`];
    for (let i = 2; i < v.length; i += 2) path.push(`${num(v[i])} ${num(v[i + 1])} l`);
    out.push(path.join(' ') + ' h f*');
  }
  // Segments grouped by width: one path per width.
  const byWidth = new Map();
  for (let i = 0; i < l.segments.length; i += 6) {
    const s = l.segments;
    const w = num(Math.max(s[i + 4], 0.05) + extraWidth);
    if (!byWidth.has(w)) byWidth.set(w, []);
    byWidth.get(w).push(`${num(s[i])} ${num(s[i + 1])} m ${num(s[i + 2])} ${num(s[i + 3])} l`);
  }
  for (const [w, parts] of byWidth) out.push(`${w} w`, parts.join(' '), 'S');
  // Native-font text in Courier. Courier's cap height is ~0.57 em, its advance 0.6 em.
  for (const t of l.texts) {
    const size = t.h / 0.57;
    const { lines } = layout(t, line => line.length * 0.6 * size * (t.w / t.h));
    const a = (t.rot * Math.PI) / 180, c = Math.cos(a), s = Math.sin(a);
    const m = t.mirror ? -1 : 1;
    for (const line of lines) {
      const lx = t.mirror ? -line.x : line.x;
      const x = t.x + lx * c + line.y * s, y = t.y - lx * s + line.y * c;
      const sx = size * (t.w / t.h);
      out.push(`BT /${font.key} 1 Tf ${num(m * sx * c)} ${num(-m * sx * s)} ${num(-size * s)} ${num(-size * c)} ${num(x)} ${num(y)} Tm ${font.encode(line.str)} Tj ET`);
    }
  }
  if (color[3] < 1) out.push(`/${gs(1)} gs`);
  return out.join('\n');
}

/** Page transform: model box (mm, y down) → page points (y up), centred, keeping proportions. */
function pageTransform(box) {
  const w = box.x1 - box.x0 || 1, h = box.y1 - box.y0 || 1;
  const s = Math.min((PAGE.w - 2 * MARGIN) / w, (PAGE.h - 2 * MARGIN) / h);
  const tx = (PAGE.w - w * s) / 2 - box.x0 * s;
  const ty = PAGE.h - (PAGE.h - h * s) / 2 + box.y0 * s;
  return { s, tx, ty, toPage: (x, y) => [tx + x * s, ty - y * s] };
}

/**
 * Build a PDF.
 * @param {object} doc
 *   pages: [{title, box, background: [r,g,b], passes: [{scene, layers: [{name, color}], extraWidth?}],
 *            annotations?: [...]}]   (extraWidth widens lines, in mm)
 *   changes: [{kind, minor, summary, details}] listed on the last pages
 *   attachment?: {name, json}  (annotations document)
 *   title: string
 * @returns {Promise<Uint8Array>}
 */
export async function buildPdf({ pages, changes = [], attachment, title = 'KiCad diff' }) {
  const lib = await import('../../vendor/pdf-lib.esm.min.js');
  const { PDFDocument, PDFName, PDFHexString, PDFString, StandardFonts, rgb } = lib;
  const pdf = await PDFDocument.create();
  pdf.setTitle(title);
  pdf.setCreator('kicad-diff');
  const courier = await pdf.embedFont(StandardFonts.Courier);
  const helvetica = await pdf.embedFont(StandardFonts.Helvetica);
  const helveticaBold = await pdf.embedFont(StandardFonts.HelveticaBold);

  for (const p of pages) {
    const page = pdf.addPage([PAGE.w, PAGE.h]);
    const fontKey = page.node.newFontDictionary('Courier', courier.ref).asString().slice(1);
    const font = {
      key: fontKey,
      encode: str => courier.encodeText(str.replace(/[^\x20-\x7e\xa0-\xff]/g, '?')).toString(),
    };
    const states = new Map();
    const gs = alpha => {
      const key = `a${Math.round(alpha * 100)}`;
      if (!states.has(key)) states.set(key, page.node.newExtGState(key, pdf.context.obj({ ca: alpha, CA: alpha })).asString().slice(1));
      return states.get(key);
    };
    const T = pageTransform(p.box);
    const ops = [
      'q',
      rgbOp(p.background, 'rg'), `0 0 ${PAGE.w} ${PAGE.h} re f`,
      `${num(T.s)} 0 0 ${num(-T.s)} ${num(T.tx)} ${num(T.ty)} cm`,
      '1 J 1 j',
    ];
    for (const pass of p.passes) {
      for (const { name, color } of pass.layers) {
        const l = pass.scene?.layers.get(name);
        if (l) ops.push(layerOps(l, color, gs, font, pass.extraWidth));
      }
    }
    ops.push('Q');
    page.node.addContentStream(pdf.context.register(pdf.context.flateStream(ops.join('\n'))));
    page.drawText(p.title, { x: MARGIN, y: PAGE.h - MARGIN + 8, size: 10, font: helveticaBold, color: rgb(0.4, 0.4, 0.4) });

    for (const a of p.annotations ?? []) addAnnotation(pdf, page, a, T, { PDFName, PDFHexString, PDFString });
  }

  // Change list.
  let page = null, y = 0;
  const line = (text, { bold = false, indent = 0, size = 9, color = [0, 0, 0] } = {}) => {
    if (!page || y < MARGIN + 12) {
      page = pdf.addPage([PAGE.h, PAGE.w]); // portrait
      y = PAGE.w - MARGIN;
    }
    const safe = text.replace(/[^\x20-\x7e\xa0-\xff]/g, '?').replace(/“|”/g, '"').replace(/→/g, '->');
    page.drawText(safe.slice(0, 140), { x: MARGIN + indent, y, size, font: bold ? helveticaBold : helvetica, color: rgb(...color) });
    y -= size + 4;
  };
  if (changes.length) line(`${changes.length} changes`, { bold: true, size: 12 });
  const COLORS = { electrical: [0.8, 0.05, 0.4], metadata: [0.75, 0.4, 0], layout: [0.05, 0.45, 0.6] };
  for (const c of changes) {
    line(`${c.kind}${c.minor ? ' (minor)' : ''}: ${c.summary.replace(/[“”]/g, '"').replace(/→/g, '->')}`, { color: COLORS[c.kind] });
    for (const d of c.details) line(d.replace(/[“”]/g, '"').replace(/→/g, '->'), { indent: 14, size: 8 });
  }

  if (attachment) {
    await pdf.attach(new TextEncoder().encode(JSON.stringify(attachment.json, null, 1)), attachment.name, {
      mimeType: 'application/json',
      description: 'Annotations (kicad-diff)',
    });
  }
  return pdf.save();
}

/** A PDF annotation with an appearance stream, for one annotation in model coordinates. */
function addAnnotation(pdf, page, a, T, { PDFName, PDFHexString, PDFString }) {
  const ctx = pdf.context;
  const color = hexColor(a.color);
  const w = Math.max(0.5, (a.width ?? 0.3) * T.s);
  const pts = a.type === 'pen' ? a.points.map(p => T.toPage(p.x, p.y)) : null;
  let rect, ops, extra = {};
  if (a.type === 'pen') {
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    rect = [Math.min(...xs) - w, Math.min(...ys) - w, Math.max(...xs) + w, Math.max(...ys) + w];
    ops = `1 J 1 j ${num(w)} w ${rgbOp(color, 'RG')} ${pts.map((p, i) => `${num(p[0])} ${num(p[1])} ${i ? 'l' : 'm'}`).join(' ')} S`;
    extra = { InkList: [pts.flat()] };
  } else if (a.type === 'text') {
    const size = a.size * T.s;
    const [x, y] = T.toPage(a.x, a.y);
    rect = [x, y - size * 0.3, x + size * 0.6 * a.text.length, y + size];
    ops = `BT /Helv ${num(size)} Tf ${rgbOp(color, 'rg')} ${num(x)} ${num(y)} Td ${latin1Literal(a.text)} Tj ET`;
    extra = { Contents: PDFHexString.fromText(a.text), DA: PDFString.of(`/Helv ${num(size)} Tf ${rgbOp(color, 'rg')}`) };
  } else {
    const [x0, y1] = T.toPage(Math.min(a.x0, a.x1), Math.min(a.y0, a.y1));
    const [x1, y0] = T.toPage(Math.max(a.x0, a.x1), Math.max(a.y0, a.y1));
    rect = [x0 - w / 2, y0 - w / 2, x1 + w / 2, y1 + w / 2];
    if (a.type === 'rect') ops = `${num(w)} w ${rgbOp(color, 'RG')} ${num(x0)} ${num(y0)} ${num(x1 - x0)} ${num(y1 - y0)} re S`;
    else ops = `${num(w)} w ${rgbOp(color, 'RG')} ${ellipsePath((x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2)} S`;
  }
  const helv = ctx.obj({ Type: 'Font', Subtype: 'Type1', BaseFont: 'Helvetica', Encoding: 'WinAnsiEncoding' });
  const appearance = ctx.register(ctx.flateStream(ops, { Type: 'XObject', Subtype: 'Form', BBox: rect, Resources: { Font: { Helv: helv } } }));
  const subtype = { pen: 'Ink', text: 'FreeText', rect: 'Square', ellipse: 'Circle' }[a.type];
  const annot = ctx.register(ctx.obj({
    Type: 'Annot', Subtype: subtype, Rect: rect, C: color, F: 4, BS: { W: w }, AP: { N: appearance },
    T: PDFHexString.fromText('kicad-diff'), ...extra,
  }));
  const annots = page.node.lookup(PDFName.of('Annots'));
  if (annots) annots.push(annot);
  else page.node.set(PDFName.of('Annots'), ctx.obj([annot]));
}

/** PDF literal string for a WinAnsi font (characters outside Latin-1 become "?"). */
function latin1Literal(s) {
  return `(${s.replace(/[^\x20-\x7e\xa0-\xff]/g, '?').replace(/[\\()]/g, '\\$&')})`;
}

function ellipsePath(cx, cy, rx, ry) {
  const k = 0.5523;
  return [
    `${num(cx + rx)} ${num(cy)} m`,
    `${num(cx + rx)} ${num(cy + k * ry)} ${num(cx + k * rx)} ${num(cy + ry)} ${num(cx)} ${num(cy + ry)} c`,
    `${num(cx - k * rx)} ${num(cy + ry)} ${num(cx - rx)} ${num(cy + k * ry)} ${num(cx - rx)} ${num(cy)} c`,
    `${num(cx - rx)} ${num(cy - k * ry)} ${num(cx - k * rx)} ${num(cy - ry)} ${num(cx)} ${num(cy - ry)} c`,
    `${num(cx + k * rx)} ${num(cy - ry)} ${num(cx + rx)} ${num(cy - k * ry)} ${num(cx + rx)} ${num(cy)} c`,
  ].join(' ');
}

function hexColor(hex) {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i.exec(hex ?? '');
  return m ? [1, 2, 3].map(i => parseInt(m[i], 16) / 255) : [0.9, 0.2, 0.2];
}
