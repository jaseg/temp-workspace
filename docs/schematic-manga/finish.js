// Finish the SVG from render.py in Chromium: measure text with the embedded
// fonts, draw label pills, note bubbles and title banners behind it, then
// write the final SVG and a PNG.
//
//   node finish.js raw.svg out.svg out.png [px_per_mm]
const fs = require('fs');
const { chromium } = require('playwright');

(async () => {
  const [src, outSvg, outPng, scaleArg] = process.argv.slice(2);
  const k = parseFloat(scaleArg || '8');
  const svgText = fs.readFileSync(src, 'utf8');
  const vb = svgText.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/);
  const W = parseFloat(vb[1]), H = parseFloat(vb[2]);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: Math.ceil(W * k), height: Math.ceil(H * k) } });
  await page.setContent(`<!doctype html><html><body style="margin:0;background:#fff">${svgText}</body></html>`);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(500);

  await page.evaluate(({ W, H, k }) => {
    const NS = 'http://www.w3.org/2000/svg';
    const INK = '#4b3a5a';
    const svg = document.querySelector('svg');
    const mk = (tag, attrs) => {
      const e = document.createElementNS(NS, tag);
      for (const [a, v] of Object.entries(attrs)) e.setAttribute(a, v);
      return e;
    };

    // label pills
    for (const t of svg.querySelectorAll('text[data-pill]')) {
      const b = t.getBBox();
      const h = b.height * 0.86, y = b.y + b.height * 0.1;
      const r = mk('rect', {
        x: b.x - 0.55, y: y - 0.18, width: b.width + 1.1, height: h + 0.36, rx: (h + 0.36) / 2,
        fill: t.dataset.pill, stroke: INK, 'stroke-width': 0.16,
      });
      t.parentNode.insertBefore(r, t);
      t.removeAttribute('data-pill');
    }

    // speech bubbles for notes
    for (const t of svg.querySelectorAll('text[data-bubble]')) {
      const b = t.getBBox();
      const p = 1.1;
      const x0 = b.x - p, y0 = b.y - p * 0.7, x1 = b.x + b.width + p, y1 = b.y + b.height + p * 0.7;
      const rr = Math.min(2.2, (y1 - y0) / 2);
      const tx = x0 + Math.min(4, (x1 - x0) * 0.25);
      const d = `M${x0 + rr} ${y0}H${x1 - rr}Q${x1} ${y0} ${x1} ${y0 + rr}V${y1 - rr}Q${x1} ${y1} ${x1 - rr} ${y1}` +
        `H${tx + 2.2}L${tx - 0.6} ${y1 + 2}L${tx + 0.6} ${y1}H${x0 + rr}Q${x0} ${y1} ${x0} ${y1 - rr}V${y0 + rr}Q${x0} ${y0} ${x0 + rr} ${y0}Z`;
      const g = t.parentNode;
      g.insertBefore(mk('path', { d, fill: '#fff', stroke: INK, 'stroke-width': 0.28, 'stroke-linejoin': 'round' }), t);
      t.removeAttribute('data-bubble');
    }

    // ribbon banners for section titles
    for (const t of svg.querySelectorAll('text[data-banner]')) {
      const b = t.getBBox();
      const px = 3.2, py = 0.9;
      const x0 = b.x - px, x1 = b.x + b.width + px;
      const y0 = b.y + b.height * 0.08 - py, y1 = b.y + b.height * 0.92 + py;
      const ym = (y0 + y1) / 2, n = 1.6;
      const rib = `M${x0 - n} ${y0}H${x1 + n}L${x1} ${ym}L${x1 + n} ${y1}H${x0 - n}L${x0} ${ym}Z`;
      const g = t.parentNode;
      g.insertBefore(mk('path', { d: rib, transform: 'translate(.7 .7)', fill: 'url(#tone-ink)', opacity: 0.6 }), t);
      g.insertBefore(mk('path', { d: rib, fill: 'url(#banner-grad)', stroke: INK, 'stroke-width': 0.35, 'stroke-linejoin': 'round' }), t);
      g.insertBefore(mk('path', {
        d: `M${x0 + 0.6} ${y0 + 0.7}H${x1 - 0.6}M${x0 + 0.6} ${y1 - 0.7}H${x1 - 0.6}`,
        stroke: '#fff', 'stroke-width': 0.25, 'stroke-dasharray': '0.8 0.6', fill: 'none',
      }), t);
      for (const [sx, sc, c] of [[x0 - n - 2.6, 0.36, '#ffe58f'], [x1 + n + 2.6, 0.36, '#ff9cc2']]) {
        g.appendChild(mk('use', { href: '#sparkle', transform: `translate(${sx} ${ym}) scale(${sc})`, fill: c }));
      }
      t.removeAttribute('data-banner');
    }
  }, { W, H, k });

  const finalSvg = await page.evaluate(() => new XMLSerializer().serializeToString(document.querySelector('svg')));
  fs.writeFileSync(outSvg, finalSvg);

  // Render the PNG in tiles: one huge screenshot makes Chromium drop raster tiles.
  const T = 2000;
  const PW = Math.round(W * k), PH = Math.round(H * k);
  await page.setViewportSize({ width: T, height: T });
  await page.evaluate(() => { const s = document.querySelector('svg'); s.style.display = 'block'; });
  const tiles = [];
  for (let ty = 0; ty < PH; ty += T) {
    for (let tx = 0; tx < PW; tx += T) {
      const w = Math.min(T, PW - tx), h = Math.min(T, PH - ty);
      await page.evaluate(({ tx, ty, w, h, k }) => {
        const s = document.querySelector('svg');
        s.setAttribute('viewBox', `${tx / k} ${ty / k} ${w / k} ${h / k}`);
        s.setAttribute('width', w);
        s.setAttribute('height', h);
      }, { tx, ty, w, h, k });
      const file = `${outPng}.tile_${tx}_${ty}.png`;
      await page.screenshot({ path: file, clip: { x: 0, y: 0, width: w, height: h } });
      tiles.push({ file, tx, ty });
    }
  }
  fs.writeFileSync(`${outPng}.tiles.json`, JSON.stringify({ width: PW, height: PH, tiles }));
  await browser.close();
  console.log(`wrote ${outSvg} and ${outPng}`);
})();
