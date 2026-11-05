"""Schematic file -> finished SVG."""

import re
from pathlib import Path

from . import backgrounds
from .circuit import Circuit
from .page import Page
from .sexp import kid, kids, parse_si, parse_sexp, val  # noqa: F401  (parse_si re-exported)
from .styles import defs

DEFAULT_BUBBLE = "let's build something cute~! ♡"


def title_info(sch, path, overrides):
    """Title panel text from the title block, with config/command-line overrides."""
    tb = kid(sch, 'title_block') or []
    comments = {c[1]: c[2] for c in kids(tb, 'comment') if len(c) > 2}
    stem = re.sub(r'^[0-9a-f]{8}-', '', Path(path).stem)
    pages = [val(p, 'page') for p in kids(kid(sch, 'sheet_instances') or [], 'path')]
    paper = kid(sch, 'paper') or ['paper', 'A4']
    paper_name = paper[1] if paper[1] != 'User' else f'{paper[2]}×{paper[3]} mm'
    rev, date, company = val(tb, 'rev', default=''), val(tb, 'date', default=''), val(tb, 'company', default='')
    right = [company, f'rev {rev}' if rev else '', date, f'paper {paper_name}', 'drawn with love ♪']
    return {
        'title': overrides.get('title') or val(tb, 'title') or stem,
        'subtitle': overrides.get('subtitle') or comments.get('1', ''),
        'kicker': overrides.get('kicker', ''),
        'bubble': overrides.get('bubble') or comments.get('2') or DEFAULT_BUBBLE,
        'footer_left': f'sheet ♡ {pages[0]}' if pages and pages[0] else '',
        'footer_right': ' · '.join(x for x in right if x),
    }


def build_svg(path, cfg, fonts=(), browser=None):
    """Render a .kicad_sch to an SVG string. With a browser, text is measured with the real
    fonts and gets its pills, flags, bubbles and banners; without one those are left out."""
    sch = parse_sexp(Path(path).read_text(encoding='utf-8'))
    circuit = Circuit(sch, characters=cfg['characters']).render()
    page = Page(circuit, title_info(sch, path, cfg['title']), cfg)
    svg = page.svg(defs(list(fonts), page.DW, page.DH), decorations=cfg['decorations'], seed=cfg['seed'],
                   sound_effects=cfg['sound_effects'], legend=cfg['characters'])
    boxes = browser.measure(svg, list(circuit.bgs)) if browser else {}
    return backgrounds.fill(svg, circuit.bgs, boxes), page
