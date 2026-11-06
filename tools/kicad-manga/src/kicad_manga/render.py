"""Schematic file -> finished SVG, and the SVG -> PNG and PDF."""

import base64
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import kicad, text
from .circuit import Circuit
from .page import Page
from .styles import defs

DEFAULT_BUBBLE = "let's build something cute~! ♡"


def title_info(sch, path, overrides):
    """Title panel text from the title block, with config/command-line overrides."""
    tb = sch.title_block
    comment = tb.comment if tb is not None else (lambda n: '')
    stem = re.sub(r'^[0-9a-f]{8}-', '', Path(path).stem)
    pages = [p.page for p in sch.sheet_instances]
    rev, date, company = (tb.rev, tb.date, tb.company) if tb is not None else ('', '', '')
    right = [company, f'rev {rev}' if rev else '', date, f'paper {kicad.paper_name(sch)}', 'drawn with love ♪']
    return {
        'title': overrides.get('title') or (tb.title if tb is not None else '') or stem,
        'subtitle': overrides.get('subtitle') or comment(1),
        'kicker': overrides.get('kicker', ''),
        'bubble': overrides.get('bubble') or comment(2) or DEFAULT_BUBBLE,
        'footer_left': f'sheet ♡ {pages[0]}' if pages and pages[0] else '',
        'footer_right': ' · '.join(x for x in right if x),
    }


def build_svg(path, cfg, fonts=()):
    """Render a .kicad_sch to an SVG string. `fonts` (fonts.Font) are embedded and used to measure text."""
    sch = kicad.load(path)
    text.use_fonts(fonts)
    circuit = Circuit(sch, characters=cfg['characters']).render()
    page = Page(circuit, title_info(sch, path, cfg['title']), cfg)
    embedded = [(f.family, f.weight, base64.b64encode(f.woff2.read_bytes()).decode(), '') for f in fonts]
    svg = page.svg(defs(embedded, page.DW, page.DH), decorations=cfg['decorations'], seed=cfg['seed'],
                   sound_effects=cfg['sound_effects'], legend=cfg['characters'])
    return flatten_opacity(svg), page


SHAPE_OPACITY = re.compile(r'<(circle|ellipse|path|rect|line|polyline|polygon|use|text)\b([^<>]*?)\sopacity="([\d.]+)"([^<>]*)>')


def flatten_opacity(svg):
    """`opacity` on a single shape -> fill-opacity and stroke-opacity. It looks the same, but PDF writers turn
    every `opacity` into a transparency group with a soft mask, which makes PDFs slow to display."""
    def sub(m):
        name, a, op, b = m.groups()
        attrs = a + b
        if 'fill-opacity=' in attrs or 'stroke-opacity=' in attrs:
            return m.group()
        return f'<{name}{a} fill-opacity="{op}" stroke-opacity="{op}"{b}>'
    return SHAPE_OPACITY.sub(sub, svg)


def write_png(svg, fonts, px_per_mm, width_mm, path):
    """Rasterise with resvg, in the page's fonts."""
    import resvg_py
    png = resvg_py.svg_to_bytes(svg_string=svg, width=round(width_mm * px_per_mm), background='#ffffff',
                                font_files=[str(f.ttf) for f in fonts], dpi=96)
    Path(path).write_bytes(png)


def pdf_tool():
    """The PDF converter on this system: rsvg-convert (librsvg), else Inkscape."""
    for tool in (os.environ.get('KICAD_MANGA_PDF_TOOL'), 'rsvg-convert', 'inkscape'):
        if tool and shutil.which(tool):
            return shutil.which(tool)
    return None


def write_pdf(svg, fonts, path):
    """Convert with rsvg-convert or Inkscape. Both find fonts through fontconfig, so they get a configuration
    that adds the directory of the page's fonts."""
    tool = pdf_tool()
    if tool is None:
        raise RuntimeError('PDF output needs rsvg-convert (librsvg, e.g. the librsvg2-bin package) or Inkscape')
    with tempfile.TemporaryDirectory(prefix='kicad-manga-') as tmp:
        tmp = Path(tmp)
        src = tmp / 'page.svg'
        src.write_text(svg, encoding='utf-8')
        dirs = sorted({str(f.ttf.parent) for f in fonts})
        conf = tmp / 'fonts.conf'
        conf.write_text('<?xml version="1.0"?>\n<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n<fontconfig>\n'
                        '  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>\n'
                        + ''.join(f'  <dir>{d}</dir>\n' for d in dirs)
                        + f'  <cachedir>{tmp / "cache"}</cachedir>\n</fontconfig>\n')
        env = dict(os.environ, FONTCONFIG_FILE=str(conf))
        if Path(tool).name.startswith('inkscape'):
            cmd = [tool, str(src), '--export-type=pdf', f'--export-filename={path}']
        else:
            cmd = [tool, '-f', 'pdf', '-o', str(path), str(src)]
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if res.returncode:
            raise RuntimeError(f'{Path(tool).name} failed: {res.stderr.strip()[-2000:]}')
