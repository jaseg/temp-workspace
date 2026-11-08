"""The resource pack's bitmap font (`font/default.json`), for text drawn onto blocks.

Glyphs come from the font's `bitmap` providers (following `reference` providers), and spaces from `space`
providers, like in the game. Characters the pack has no bitmap for are drawn as '?'. Each glyph is as wide as its
rightmost opaque column, plus one pixel of spacing; lines are 8 font pixels apart for an 8-pixel high font."""

import io

from PIL import Image

from .pack import split_id

LINE = 9            # line pitch in font pixels (the game uses 9 for its 8 pixel font)


class BitmapFont:
    def __init__(self, pack, rid='minecraft:default'):
        self.pack = pack
        self.glyphs = {}            # char -> (image or None, advance, ascent, height)
        self.load(rid, set())
        if ' ' not in self.glyphs:
            self.glyphs[' '] = (None, 4, 7, 8)

    def load(self, rid, seen):
        if rid in seen:
            return
        seen.add(rid)
        d = self.pack.json('font', rid)
        if d is None:
            return
        for p in d.get('providers', []):
            kind = split_id(p.get('type', ''))[1]
            if kind == 'reference':
                self.load(p['id'], seen)
            elif kind == 'space':
                for ch, adv in p.get('advances', {}).items():
                    self.glyphs.setdefault(ch, (None, adv, 7, 8))
            elif kind == 'bitmap':
                self.bitmap(p)

    def bitmap(self, p):
        ns, path = split_id(p['file'])
        data = self.pack.read(f'assets/{ns}/textures/{path}')
        if data is None:
            return
        sheet = Image.open(io.BytesIO(data)).convert('RGBA')
        rows = p['chars']
        ncols = max(len(r) for r in rows)
        cw, ch = sheet.width // ncols, sheet.height // len(rows)
        height = p.get('height', 8)
        ascent = p.get('ascent', 7)
        scale = height / ch
        alpha = sheet.getchannel('A')
        for j, row in enumerate(rows):
            for i, c in enumerate(row):
                if c in ('\0', ' ') or c in self.glyphs:
                    continue
                box = (i * cw, j * ch, (i + 1) * cw, (j + 1) * ch)
                a = alpha.crop(box)
                bb = a.getbbox()
                if bb is None:
                    continue
                w = bb[2]
                g = sheet.crop((box[0], box[1], box[0] + w, box[3]))
                if scale != 1:
                    g = g.resize((max(1, round(w * scale)), height), Image.NEAREST)
                self.glyphs[c] = (g, g.width + 1, ascent, height)

    def glyph(self, c):
        return self.glyphs.get(c) or self.glyphs.get('?') or (None, 6, 7, 8)

    def width(self, s):
        """Width of one line in font pixels (without the trailing spacing)."""
        return max(0, sum(self.glyph(c)[1] for c in s) - 1)

    def render(self, text, color=(255, 255, 255), shadow=True):
        """Text (possibly several lines, centred) as an RGBA image in font pixels, with the game's drop shadow."""
        lines = text.split('\n')
        w = max(self.width(s) for s in lines) + (1 if shadow else 0)
        h = LINE * (len(lines) - 1) + 8 + (1 if shadow else 0)
        img = Image.new('RGBA', (max(1, w), h), (0, 0, 0, 0))
        sh = tuple(c // 4 for c in color)
        for k, s in enumerate(lines):
            x = (w - (1 if shadow else 0) - self.width(s)) // 2
            y0 = k * LINE
            for c in s:
                g, adv, asc, _ = self.glyph(c)
                if g is not None:
                    a = g.getchannel('A')
                    top = y0 + 7 - asc
                    if shadow:
                        img.paste(Image.new('RGBA', g.size, sh + (255,)), (x + 1, top + 1), a)
                    fg = Image.new('RGBA', g.size, tuple(color) + (255,))
                    # keep the glyph's own shading (accented letters are drawn grey in places)
                    img.paste(fg, (x, top), a)
                x += adv
        return img
