// Renders an SVG file to PNG with the pre-installed Chromium:  node render.js in.svg out.png [scale]
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const [inp, out, scale] = process.argv.slice(2);
  const svg = fs.readFileSync(inp, 'utf8');
  const m = svg.match(/viewBox="0 0 (\d+) (\d+)"/);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: +m[1], height: +m[2] }, deviceScaleFactor: +(scale || 1) });
  await p.setContent(`<html><body style="margin:0;background:#fff">${svg}</body></html>`);
  await p.screenshot({ path: out });
  await b.close();
})();
