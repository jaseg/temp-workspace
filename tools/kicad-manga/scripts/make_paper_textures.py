"""Generate the paper craft style's bitmap textures (src/kicad_manga/papercraft/textures/).

All of them tile seamlessly: the noise is filtered in the frequency domain, which makes it periodic, and the
fibres wrap around the tile's edges. Run with numpy and Pillow available:

    uv run --with numpy --with pillow python scripts/make_paper_textures.py
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / 'src' / 'kicad_manga' / 'papercraft' / 'textures'


def noise(n, rng, lo, hi):
    """Periodic band-limited noise in [-1, 1]: frequencies (cycles per tile) between lo and hi."""
    f = np.fft.fftfreq(n) * n
    r = np.hypot(*np.meshgrid(f, f))
    amp = np.where((r >= lo) & (r <= hi), 1 / np.maximum(r, 1) ** .8, 0)
    spec = amp * np.exp(2j * np.pi * rng.random((n, n)))
    v = np.real(np.fft.ifft2(spec))
    return v / (np.abs(v).max() or 1)


def fibres(n, rng, count, length, width, scale=1):
    """A layer of short curved fibres, wrapping around the tile edges; values 0..1."""
    big = Image.new('L', (n * 3 * scale, n * 3 * scale), 0)
    d = ImageDraw.Draw(big)
    for _ in range(count):
        x, y = rng.uniform(n, 2 * n), rng.uniform(n, 2 * n)
        a = rng.uniform(0, np.pi)
        L = rng.uniform(.4, 1) * length
        bend = rng.uniform(-.6, .6)
        pts = []
        for t in np.linspace(0, 1, 8):
            aa = a + bend * t
            pts.append(((x + np.cos(aa) * L * t) * scale, (y + np.sin(aa) * L * t) * scale))
        val = int(rng.uniform(90, 255))
        for ox in (-n, 0, n):
            for oy in (-n, 0, n):
                d.line([(px + ox * scale, py + oy * scale) for px, py in pts], fill=val,
                       width=max(1, int(width * scale)))
    big = big.crop((n * scale, n * scale, 2 * n * scale, 2 * n * scale))
    if scale > 1:
        big = big.resize((n, n), Image.LANCZOS)
    return np.asarray(big, dtype=float) / 255


def tint(base, light):
    """RGB image from a base colour and a lightness field (0 = as is, + lighter, - darker)."""
    base = np.array(base, dtype=float)
    out = np.where(light[..., None] >= 0, base + (255 - base) * light[..., None], base * (1 + light[..., None]))
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), 'RGB')


def cardstock(n, rng, base, mottle=.025, grain=.05, fib=.1):
    light = (noise(n, rng, 3, 24) * mottle + noise(n, rng, 60, n / 2) * grain
             + fibres(n, rng, 260, n * .05, 1.2, 2) * fib - fibres(n, rng, 120, n * .04, 1, 2) * fib * .8)
    return tint(base, light)


def grain_overlay(n, rng):
    """Light and dark specks and fibres with a low alpha, laid over everything to make it read as paper."""
    v = noise(n, rng, 70, n / 2) * .7 + noise(n, rng, 8, 30) * .3
    fl = fibres(n, rng, 220, n * .05, 1.1, 2)
    fd = fibres(n, rng, 90, n * .035, 1, 2)
    light = np.clip(v, 0, None) * .5 + fl * .55
    dark = np.clip(-v, 0, None) * .5 + fd * .45
    rgba = np.zeros((n, n, 4))
    w = light > dark
    rgba[..., :3] = np.where(w[..., None], [255, 252, 244], [92, 70, 50])
    rgba[..., 3] = np.where(w, light, dark) * 120
    return Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), 'RGBA')


def blur(im, r):
    """Gaussian blur that wraps around the edges, so the tile stays seamless."""
    w, h = im.size
    big = Image.new(im.mode, (w * 3, h * 3))
    for i in range(3):
        for j in range(3):
            big.paste(im, (i * w, j * h))
    return big.filter(ImageFilter.GaussianBlur(r)).crop((w, h, 2 * w, 2 * h))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    import random
    prng = random.Random(7)
    rng_u = type('R', (), {'uniform': staticmethod(prng.uniform), 'random': rng.random})
    blur(cardstock(768, rng_u, (247, 240, 226)), .4).save(
        OUT / 'card.jpg', quality=82, optimize=True)
    grain_overlay(512, rng_u).save(OUT / 'grain.png', optimize=True)
    for p in sorted(OUT.iterdir()):
        print(p.name, p.stat().st_size)


if __name__ == '__main__':
    main()
