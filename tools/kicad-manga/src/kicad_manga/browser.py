"""Headless Chromium (via Playwright) for the steps that need real fonts and a renderer:
measuring text, rasterising to PNG and printing to PDF."""

import glob
import io
import math
import os

from PIL import Image

PAGE = '<!doctype html><html><head><meta charset="utf-8"><style>{css}html,body{{margin:0;padding:0;background:#fff}}' \
       'svg{{display:block}}</style></head><body>{svg}</body></html>'

# Chromium rasterises every SVG <pattern> and <mask> when printing, once per use, which makes
# PDFs huge and slow to draw. So for printing, each screentone becomes real vector dots: one
# path of little circles per filled shape (only the visible sliver of drop shadows), and the
# masked page vignette a halftone whose dots grow towards the edges. Opacity on single shapes
# becomes fill/stroke opacity, so there's no transparency group per sparkle.
# tone id: (pitch, dot radius, lattice angle, colour, opacity) -- as in styles.py
TONES = {'tone-w': [1.1, .2, 45, '#ffffff', .7], 'tone-ink': [.9, .3, 45, '#4b3a5a', 1],
         'tone-pink': [3, .7, 30, '#ffc2da', 1], 'tone-bg': [3.2, .42, 30, '#ffd3e4', 1]}
PRINT_JS = '''(tones) => {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.querySelector('svg');
  const f = (v) => +v.toFixed(2);
  const stats = {};
  function dots(box, spec, keep, scale) {
    const [p, r, ang, col, op] = spec;
    const a = ang * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
    const xs = [box.x, box.x + box.width], ys = [box.y, box.y + box.height];
    let u0 = 1e9, u1 = -1e9, v0 = 1e9, v1 = -1e9;
    for (const x of xs) for (const y of ys) {
      const u = c * x + s * y, v = -s * x + c * y;
      u0 = Math.min(u0, u); u1 = Math.max(u1, u); v0 = Math.min(v0, v); v1 = Math.max(v1, v);
    }
    const out = [];
    for (let i = Math.floor(u0 / p); i <= Math.ceil(u1 / p); i++)
      for (let j = Math.floor(v0 / p); j <= Math.ceil(v1 / p); j++) {
        const u = (i + .5) * p, v = (j + .5) * p;
        const x = c * u - s * v, y = s * u + c * v;
        if (x < xs[0] || x > xs[1] || y < ys[0] || y > ys[1] || !keep(x, y)) continue;
        const rr = r * (scale ? scale(x, y) : 1);
        if (rr <= .03) continue;
        stats[col] = (stats[col] || 0) + 1;
        if (rr < .35) {   // tiny: a diamond of the same area reads as a dot and is much lighter
          const d = f(rr * 1.25);
          out.push(`M${f(x)} ${f(y - d)}l${d} ${d} ${-d} ${d} ${-d} ${-d}z`);
        } else {
          out.push(`M${f(x - rr)} ${f(y)}a${f(rr)} ${f(rr)} 0 1 0 ${f(2 * rr)} 0a${f(rr)} ${f(rr)} 0 1 0 ${f(-2 * rr)} 0`);
        }
      }
    return out.join('');
  }
  function dotPath(d, col, op, like) {
    const e = document.createElementNS(NS, 'path');
    e.setAttribute('d', d); e.setAttribute('fill', col);
    if (op < 1) e.setAttribute('fill-opacity', f(op));
    for (const a of ['transform', 'opacity']) if (like && like.hasAttribute(a)) e.setAttribute(a, like.getAttribute(a));
    return e;
  }
  const inside = (el, x, y) => el.isPointInFill(new DOMPoint(x, y));
  // drop shadows are tagged with their offset (data-shadow="dx dy"): a dot is hidden where
  // the shape casting the shadow sits on top of it
  const keeper = (el, tagged) => {
    const off = (tagged.getAttribute('data-shadow') || '').split(' ').map(Number);
    if (off.length !== 2) return (x, y) => inside(el, x, y);
    return (x, y) => inside(el, x, y) && !inside(el, x + off[0], y + off[1]);
  };
  // the page vignette: halftone dots that grow towards the edges
  for (const r of [...svg.querySelectorAll('[mask]')]) {
    const spec = tones['tone-bg'], b = r.getBBox();
    const scale = (x, y) => {
      const dx = ((x - b.x) / b.width - .5) / .72, dy = ((y - b.y) / b.height - .5) / .72;
      return Math.max(0, Math.min(1, (Math.hypot(dx, dy) - .75) / .25));
    };
    r.replaceWith(dotPath(dots(b, spec, () => true, scale), spec[3], spec[4] * parseFloat(r.getAttribute('opacity') || '1'), null));
  }
  const shapes = 'path,rect,circle,ellipse,polygon';
  for (const el of [...svg.querySelectorAll('[fill^="url(#tone-"]')]) {
    const id = el.getAttribute('fill').slice(5, -1), spec = tones[id];
    if (!spec) continue;
    const flat = (e) => { e.setAttribute('fill', spec[3]); e.setAttribute('fill-opacity', f(spec[4] * .3)); };
    if (el.localName === 'g') {          // e.g. a drop shadow group: each shape in it
      const todo = [...el.querySelectorAll(shapes)].filter(sh => !sh.hasAttribute('fill'));
      const out = todo.map(sh => { const b = sh.getBBox(); return b.width ? dots(b, spec, keeper(sh, el)) : null; });
      el.removeAttribute('fill');
      todo.forEach((sh, i) => out[i] === null ? flat(sh) : sh.replaceWith(dotPath(out[i], spec[3], spec[4], sh)));
      continue;
    }
    const b = el.getBBox();
    if (!b.width) { flat(el); continue; }      // e.g. inside <defs>
    const op = spec[4] * parseFloat(el.getAttribute('fill-opacity') || '1');
    el.replaceWith(dotPath(dots(b, spec, keeper(el, el)), spec[3], op, el));
  }
  const single = new Set(['circle', 'ellipse', 'path', 'rect', 'line', 'polyline', 'polygon', 'use', 'text']);
  for (const el of svg.querySelectorAll('[opacity]')) {
    if (!single.has(el.localName)) continue;
    const o = parseFloat(el.getAttribute('opacity'));
    for (const a of ['fill-opacity', 'stroke-opacity'])
      el.setAttribute(a, o * parseFloat(el.getAttribute(a) || '1'));
    el.removeAttribute('opacity');
  }
  return stats;
}'''


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
        self.page.set_viewport_size({'width': math.ceil(width_mm * 96 / 25.4), 'height': math.ceil(height_mm * 96 / 25.4)})
        self.load(svg, css)
        self.stats = self.page.evaluate(PRINT_JS, TONES)
        self.page.pdf(path=str(path), width=f'{width_mm}mm', height=f'{height_mm}mm', print_background=True,
                      page_ranges='1')
