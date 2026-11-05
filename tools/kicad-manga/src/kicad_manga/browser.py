"""Headless Chromium (via Playwright) for the steps that need real fonts and a renderer:
measuring text, rasterising to PNG and printing to PDF."""

import glob
import io
import os

from PIL import Image

PAGE = '<!doctype html><html><head><meta charset="utf-8"><style>{css}html,body{{margin:0;padding:0;background:#fff}}' \
       'svg{{display:block}}</style></head><body>{svg}</body></html>'

# Chromium rasterises every SVG <pattern> and <mask> when printing, once per use, which makes
# PDFs huge and slow to draw. For printing: halftone patterns become flat tints of the same
# average shade, the masked vignette a radial gradient, and opacity on single shapes becomes
# fill/stroke opacity (no transparency group per sparkle).
PRINT_JS = '''(tints) => {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.querySelector('svg');
  for (const r of svg.querySelectorAll('[mask]')) {
    const g = document.createElementNS(NS, 'radialGradient');
    g.id = 'print-vignette';
    for (const [k, v] of [['cx', '.5'], ['cy', '.5'], ['r', '.72']]) g.setAttribute(k, v);
    const [col, op] = tints['tone-bg'];
    for (const [off, o] of [['.75', 0], ['1', op]]) {
      const s = document.createElementNS(NS, 'stop');
      s.setAttribute('offset', off); s.setAttribute('stop-color', col); s.setAttribute('stop-opacity', o);
      g.appendChild(s);
    }
    svg.querySelector('defs').appendChild(g);
    r.removeAttribute('mask'); r.removeAttribute('opacity');
    r.setAttribute('fill', 'url(#print-vignette)');
  }
  for (const el of svg.querySelectorAll('[fill^="url(#tone-"]')) {
    const [col, op] = tints[el.getAttribute('fill').slice(5, -1)] || ['#000000', 0.2];
    el.setAttribute('fill', col);
    el.setAttribute('fill-opacity', op * parseFloat(el.getAttribute('fill-opacity') || '1'));
  }
  const single = new Set(['circle', 'ellipse', 'path', 'rect', 'line', 'polyline', 'polygon', 'use', 'text']);
  for (const el of svg.querySelectorAll('[opacity]')) {
    if (!single.has(el.localName)) continue;
    const o = parseFloat(el.getAttribute('opacity'));
    for (const a of ['fill-opacity', 'stroke-opacity'])
      el.setAttribute(a, o * parseFloat(el.getAttribute(a) || '1'));
    el.removeAttribute('opacity');
  }
}'''
TINTS = {'tone-w': ['#ffffff', 0.08], 'tone-ink': ['#4b3a5a', 0.35], 'tone-pink': ['#ffc2da', 0.2],
         'tone-bg': ['#ffd3e4', 0.25]}


class Browser:
    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        self.browser = self.launch()
        self.page = self.browser.new_page()
        return self

    def __exit__(self, *exc):
        self.browser.close()
        self.pw.stop()

    def launch(self):
        try:
            return self.pw.chromium.launch()
        except Exception as first:
            # a Playwright release that doesn't match the installed browser: try any Chromium around
            cands = [os.environ.get('KICAD_MANGA_CHROMIUM', '')]
            root = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', os.path.expanduser('~/.cache/ms-playwright'))
            cands += sorted(glob.glob(f'{root}/chromium-*/chrome-linux*/chrome'), reverse=True)
            cands += [f'{root}/chromium', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']
            for c in cands:
                if c and os.path.isfile(c):
                    try:
                        return self.pw.chromium.launch(executable_path=c, args=['--headless', '--no-sandbox'])
                    except Exception:
                        pass
            raise first

    def load(self, svg, css=''):
        self.page.set_content(PAGE.format(svg=svg, css=css))
        self.page.evaluate('() => document.fonts.ready')
        self.page.wait_for_timeout(200)

    def measure(self, svg, ids):
        """Bounding boxes {id: (x, y, w, h)} of elements, in their own coordinates."""
        self.page.set_viewport_size({'width': 1200, 'height': 900})
        self.load(svg)
        boxes = self.page.evaluate('''(ids) => ids.map(id => {
            const e = document.getElementById(id);
            if (!e) return null;
            const b = e.getBBox();
            return [b.x, b.y, b.width, b.height];
        })''', list(ids))
        return {i: tuple(b) for i, b in zip(ids, boxes) if b}

    def png(self, svg, width_mm, height_mm, px_per_mm, path, tile=2000):
        """Rasterise in tiles: one huge screenshot makes Chromium drop raster tiles."""
        PW, PH = round(width_mm * px_per_mm), round(height_mm * px_per_mm)
        self.page.set_viewport_size({'width': tile, 'height': tile})
        self.load(svg)
        img = Image.new('RGB', (PW, PH), 'white')
        for ty in range(0, PH, tile):
            for tx in range(0, PW, tile):
                w, h = min(tile, PW - tx), min(tile, PH - ty)
                self.page.evaluate('''([x, y, w, h, k]) => {
                    const s = document.querySelector('svg');
                    s.setAttribute('viewBox', `${x / k} ${y / k} ${w / k} ${h / k}`);
                    s.setAttribute('width', w); s.setAttribute('height', h);
                }''', [tx, ty, w, h, px_per_mm])
                shot = self.page.screenshot(clip={'x': 0, 'y': 0, 'width': w, 'height': h})
                with Image.open(io.BytesIO(shot)) as t:
                    img.paste(t.convert('RGB'), (tx, ty))
        img.save(path, optimize=True)

    def pdf(self, svg, width_mm, height_mm, path):
        css = f'@page{{size:{width_mm}mm {height_mm}mm;margin:0}}svg{{width:{width_mm}mm;height:{height_mm}mm}}'
        self.load(svg, css)
        self.page.evaluate(PRINT_JS, TINTS)
        self.page.pdf(path=str(path), width=f'{width_mm}mm', height=f'{height_mm}mm', print_background=True,
                      page_ranges='1')
