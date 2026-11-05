// Print the finished SVG to a vector PDF at the sheet's real size.
//   node topdf.js in.svg out.pdf
const fs = require('fs');
const { chromium } = require('playwright');

(async () => {
  const [src, out] = process.argv.slice(2);
  const svg = fs.readFileSync(src, 'utf8');
  const [, W, H] = svg.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/);
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(`<!doctype html><html><head><style>@page{size:${W}mm ${H}mm;margin:0}
    html,body{margin:0;padding:0}svg{display:block;width:${W}mm;height:${H}mm}</style></head><body>${svg}</body></html>`);
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({ path: out, width: `${W}mm`, height: `${H}mm`, printBackground: true, pageRanges: '1' });
  await browser.close();
  console.log(`wrote ${out}`);
})();
