// Usage: node svg2png.js out_dir in1.svg [in2.svg ...]  -> out_dir/<name>.png (white background)
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
(async () => {
  const [outDir, ...files] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage();
  for (const f of files) {
    const svg = fs.readFileSync(f, 'utf8');
    const m = svg.match(/viewBox="([\d.\-]+) ([\d.\-]+) ([\d.]+) ([\d.]+)"/);
    const w = m ? parseFloat(m[3]) : 420, h = m ? parseFloat(m[4]) : 297;
    const W = 3200, H = Math.round(W * h / w);
    await page.setViewportSize({ width: W, height: H });
    await page.setContent(`<html><body style="margin:0;background:#fff"><img src="data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}" style="width:${W}px;height:${H}px"></body></html>`);
    await page.waitForTimeout(200);
    const out = path.join(outDir, path.basename(f).replace(/\.svg$/, '.png'));
    await page.screenshot({ path: out });
    console.log('wrote', out);
  }
  await browser.close();
})();
