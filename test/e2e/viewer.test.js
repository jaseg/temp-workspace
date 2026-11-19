// End-to-end tests of the viewer in headless Chromium (Playwright).

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { serveStatic } from './server.js';

const { chromium } = createRequire(import.meta.url)('playwright');
const PAIR = 'old=/test/pairs/resistors/old.kicad_sch&new=/test/pairs/resistors/new.kicad_sch';

let server, browser, base;

before(async () => {
  server = await serveStatic();
  base = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
});

after(async () => {
  await browser?.close();
  server?.close();
});

async function open(query) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 700 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`${base}/web/index.html?${query}`);
  await page.waitForFunction(() => document.querySelector('kicad-diff')?.viewports?.length || document.querySelector('kicad-diff-project'));
  return { page, errors };
}

const state = page => page.evaluate(() => {
  const d = document.querySelector('kicad-diff');
  const r = d.shadowRoot;
  return {
    mode: d.mode,
    viewports: d.viewports.length,
    changes: d.changes.map(c => `${c.kind}: ${c.summary}`),
    selected: d.selected?.summary ?? null,
    visited: r.querySelectorAll('.change.visited').length,
    inspector: r.querySelector('.inspector').textContent,
    banner: r.querySelector('.banner').textContent,
    passes: d.viewports.map(v => v.passes.length),
  };
});

test('diff mode lists the changes', async () => {
  const { page, errors } = await open(PAIR);
  const s = await state(page);
  assert.equal(s.mode, 'diff');
  assert.equal(s.viewports, 1);
  assert.deepEqual(s.changes, [
    'electrical: 2 pins disconnected from net Net-(R2-Pad1)',
    'electrical: Label SDA renamed to SCL',
    'electrical: Net SDA renamed to SCL',
    'metadata: R1 Value: “10k” → “4k7”',
    'layout: R3 moved by (+2.54, 0) mm',
  ]);
  assert.deepEqual(errors, []);
});

test('keyboard navigation selects changes and marks them visited', async () => {
  const { page } = await open(PAIR);
  await page.evaluate(() => document.querySelector('kicad-diff').focus());
  await page.keyboard.press('n');
  await page.keyboard.press('n');
  let s = await state(page);
  assert.equal(s.selected, 'Label SDA renamed to SCL');
  assert.equal(s.visited, 2);
  assert.match(s.inspector, /Electrical/);
  await page.keyboard.press('p');
  s = await state(page);
  assert.equal(s.selected, '2 pins disconnected from net Net-(R2-Pad1)');
});

test('modes and the split-mode overlay toggle', async () => {
  const { page } = await open(PAIR);
  const shadowClick = sel => page.evaluate(sel => document.querySelector('kicad-diff').shadowRoot.querySelector(sel).click(), sel);
  await shadowClick('[data-mode="split"]');
  let s = await state(page);
  assert.equal(s.viewports, 2);
  const withOverlay = s.passes[0];
  await shadowClick('.overlay');
  s = await state(page);
  assert.ok(s.passes[0] < withOverlay, 'turning the overlay off removes highlight passes');
  await shadowClick('[data-mode="left"]');
  s = await state(page);
  assert.equal(s.viewports, 1);
  assert.equal(s.mode, 'left');
});

test('clicking a changed element selects its change', async () => {
  const { page } = await open(PAIR);
  // R1's value field sits left of R1 (x = 97.46 mm); find its screen position and click it.
  const point = await page.evaluate(() => {
    const d = document.querySelector('kicad-diff');
    const v = d.viewports[0];
    const i = d.scenes.new.items.findIndex(it => it.kind === 'field' && it.ref === 'R1' && it.field === 'Value');
    const b = d.scenes.new.items[i].bbox;
    const p = v.toScreen((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2);
    const r = v.getBoundingClientRect();
    return { x: r.left + p.x, y: r.top + p.y };
  });
  await page.mouse.click(point.x, point.y);
  await page.waitForTimeout(200);
  const s = await state(page);
  assert.equal(s.selected, 'R1 Value: “10k” → “4k7”');
});

test('unsupported versions show a warning banner', async () => {
  const { page } = await open('new=/test/pairs/future/new.kicad_sch');
  const s = await state(page);
  assert.match(s.banner, /newer than this viewer supports/);
  assert.equal(s.mode, 'right');
});

test('project overview lists the hierarchy and opens a file', async () => {
  const { page, errors } = await open('old=/test/pairs/project-old/demo.kicad_pro&new=/test/pairs/project-new/demo.kicad_pro');
  await page.waitForFunction(() => /files compared/.test(document.querySelector('kicad-diff-project')?.shadowRoot.textContent));
  const rows = await page.evaluate(() => [...document.querySelector('kicad-diff-project').shadowRoot.querySelectorAll('.file')].map(li => li.querySelector('.name').firstChild.textContent + ' ' + li.querySelector('.status').textContent));
  assert.deepEqual(rows, ['demo (root sheet) unchanged', 'resistors changed']);
  await page.evaluate(() => document.querySelector('kicad-diff-project').shadowRoot.querySelectorAll('.file')[1].click());
  await page.waitForFunction(() => document.querySelector('kicad-diff-project').shadowRoot.querySelector('kicad-diff')?.changes?.length);
  const n = await page.evaluate(() => document.querySelector('kicad-diff-project').shadowRoot.querySelector('kicad-diff').changes.length);
  assert.equal(n, 5);
  assert.deepEqual(errors, []);
});

test('annotations: draw, export as JSON, and embed in a PDF', async () => {
  const { page, errors } = await open(PAIR);
  const shadowClick = sel => page.evaluate(sel => document.querySelector('kicad-diff').shadowRoot.querySelector(sel).click(), sel);
  await shadowClick('.annotate');
  await shadowClick('[data-tool="rect"]');
  const box = await page.evaluate(() => {
    const r = document.querySelector('kicad-diff').viewports[0].getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });
  await page.mouse.move(box.x - 40, box.y - 30);
  await page.mouse.down();
  await page.mouse.move(box.x + 40, box.y + 30, { steps: 4 });
  await page.mouse.up();
  const count = await page.evaluate(() => document.querySelector('kicad-diff').annotations.length);
  assert.equal(count, 1);

  const [json] = await Promise.all([page.waitForEvent('download'), shadowClick('.export')]);
  const doc = JSON.parse(await streamText(await json.createReadStream()));
  assert.equal(doc.format, 'kicad-diff-annotations');
  assert.equal(doc.annotations[0].type, 'rect');
  assert.equal(doc.files.new.name, 'new.kicad_sch');

  const [pdf] = await Promise.all([page.waitForEvent('download'), shadowClick('.pdf')]);
  const bytes = Buffer.from(await streamText(await pdf.createReadStream(), 'latin1'), 'latin1');
  const { PDFDocument, PDFName } = await import('../../vendor/pdf-lib.esm.min.js');
  const loaded = await PDFDocument.load(bytes);
  assert.equal(loaded.getPageCount(), 4); // changes, old, new, change list
  assert.equal(loaded.getPage(0).node.lookup(PDFName.of('Annots')).size(), 1);
  assert.deepEqual(errors, []);
});

async function streamText(stream, encoding = 'utf8') {
  const chunks = [];
  for await (const c of stream) chunks.push(c);
  return Buffer.concat(chunks).toString(encoding);
}
