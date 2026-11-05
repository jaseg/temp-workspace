// Print the finished SVG to a vector PDF at the sheet's real size.
//   node topdf.js in.svg out.pdf
//
// Chromium rasterizes every SVG <pattern> and <mask> when printing, once per use,
// which made the PDF ~16 MB and slow to draw. So before printing this swaps:
//  * the halftone dot patterns for flat tints of the same average shade,
//  * the masked halftone vignette for a radial gradient (stays vector),
//  * element opacity on single shapes for fill/stroke opacity, so viewers don't
//    have to composite a transparency group for each sparkle and confetti dot.
const fs = require('fs');
const { chromium } = require('playwright');

// pattern id -> [colour, fill-opacity]: dot area / tile area × the dot's own opacity
const TINTS = {
  'tone-w': ['#ffffff', 0.08],
  'tone-ink': ['#4b3a5a', 0.35],
  'tone-pink': ['#ffc2da', 0.2],
  'tone-bg': ['#ffd3e4', 0.25],
};

(async () => {
  const [src, out] = process.argv.slice(2);
  const svg = fs.readFileSync(src, 'utf8');
  const [, W, H] = svg.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/);
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(`<!doctype html><html><head><style>@page{size:${W}mm ${H}mm;margin:0}
    html,body{margin:0;padding:0}svg{display:block;width:${W}mm;height:${H}mm}</style></head><body>${svg}</body></html>`);
  await page.evaluate(() => document.fonts.ready);

  const stats = await page.evaluate((TINTS) => {
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.querySelector('svg');
    const n = { tints: 0, opacity: 0 };

    // the vignette: a rect filled with a pattern through a mask -> radial gradient
    for (const r of svg.querySelectorAll('[mask]')) {
      const defs = svg.querySelector('defs');
      const g = document.createElementNS(NS, 'radialGradient');
      g.id = 'print-vignette';
      g.setAttribute('cx', '.5'); g.setAttribute('cy', '.5'); g.setAttribute('r', '.72');
      const [col, op] = TINTS['tone-bg'];
      for (const [off, o] of [['.75', 0], ['1', op]]) {
        const s = document.createElementNS(NS, 'stop');
        s.setAttribute('offset', off); s.setAttribute('stop-color', col); s.setAttribute('stop-opacity', o);
        g.appendChild(s);
      }
      defs.appendChild(g);
      r.removeAttribute('mask');
      r.setAttribute('fill', 'url(#print-vignette)');
      r.removeAttribute('opacity');
    }

    // halftone patterns -> flat tints
    for (const el of svg.querySelectorAll('[fill^="url(#tone-"]')) {
      const id = el.getAttribute('fill').slice(5, -1);
      const [col, op] = TINTS[id] || ['#000000', 0.2];
      el.setAttribute('fill', col);
      el.setAttribute('fill-opacity', op * parseFloat(el.getAttribute('fill-opacity') || '1'));
      n.tints++;
    }

    // opacity on a single shape -> fill/stroke opacity (no transparency group needed)
    const single = new Set(['circle', 'ellipse', 'path', 'rect', 'line', 'polyline', 'polygon', 'use', 'text']);
    for (const el of svg.querySelectorAll('[opacity]')) {
      if (!single.has(el.localName)) continue;
      const o = parseFloat(el.getAttribute('opacity'));
      for (const a of ['fill-opacity', 'stroke-opacity']) {
        el.setAttribute(a, o * parseFloat(el.getAttribute(a) || '1'));
      }
      el.removeAttribute('opacity');
      n.opacity++;
    }
    return n;
  }, TINTS);

  await page.pdf({ path: out, width: `${W}mm`, height: `${H}mm`, printBackground: true, pageRanges: '1' });
  await browser.close();
  console.log(`wrote ${out} (${stats.tints} pattern fills flattened, ${stats.opacity} opacities moved)`);
})();
