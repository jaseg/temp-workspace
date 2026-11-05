"""High-level sanity checks. They don't compare against reference output, only that
everything in the schematic shows up and the outputs are well-formed."""

import collections
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from kicad_manga import config
from kicad_manga.page import FM
from kicad_manga.render import build_svg
from kicad_manga.sexp import kids, parse_si, parse_sexp

FIXTURE = Path(__file__).parent / 'fixtures' / 'demo.kicad_sch'
ITEM_KINDS = ('wire', 'bus', 'bus_entry', 'junction', 'no_connect', 'label', 'global_label', 'hierarchical_label',
              'netclass_flag', 'text', 'text_box', 'table', 'image', 'sheet', 'polyline', 'rectangle', 'circle',
              'arc', 'bezier', 'rule_area')


def render(path=FIXTURE, **settings):
    cfg = config.load()
    cfg.update(settings)
    svg, page = build_svg(path, cfg)
    return ET.fromstring(svg), page


def test_every_schematic_item_is_drawn():
    sch = parse_sexp(FIXTURE.read_text())
    root, _ = render()
    drawn = collections.Counter(e.get('data-kind') for e in root.iter() if e.get('data-kind'))
    for kind in ITEM_KINDS:
        assert drawn[kind] == len(kids(sch, kind)), kind
    refs = {p[2] for s in kids(sch, 'symbol') for p in kids(s, 'property') if p[1] == 'Reference'}
    assert {e.get('data-ref') for e in root.iter() if e.get('data-kind') == 'symbol'} == refs
    text = ''.join(root.itertext())
    for kind in ('label', 'global_label', 'hierarchical_label', 'text'):
        for item in kids(sch, kind):
            assert item[1] in text
    assert 'Demo Board' in text and 'a tiny test sheet' in text      # title block -> title panel


def test_passives_become_characters_unless_disabled():
    root, _ = render()
    chars = {e.get('data-ref'): [c.get('data-character') for c in e.iter() if c.get('class') == 'character']
             for e in root.iter() if e.get('data-kind') == 'symbol'}
    assert chars['R1'] == ['res'] and chars['C1'] == ['cap'] and chars['L1'] == ['ind'] and chars['Y1'] == ['xtal']
    assert chars['U1'] == [] and chars['#PWR01'] == []
    root, _ = render(characters=False)
    assert not [e for e in root.iter() if e.get('class') == 'character']


@pytest.mark.parametrize('paper, size', [('"A3" portrait', (297, 420)), ('"User" 200 150', (200, 150)),
                                         ('"USLetter"', (279.4, 215.9))])
def test_page_sizes_and_content_stays_inside_the_frame(tmp_path, paper, size):
    path = tmp_path / 'demo.kicad_sch'
    path.write_text(FIXTURE.read_text().replace('(paper "A4")', f'(paper {paper})'))
    root, page = render(path)
    assert [float(v) for v in root.get('viewBox').split()] == [0, 0, *size]
    x0, y0, x1, y1 = page.c.grid.bbox()
    (dx0, dy0), (dx1, dy1) = page.to_design(x0, y0), page.to_design(x1, y1)
    assert FM < dx0 < dx1 < page.DW - FM and FM < dy0 < dy1 < page.DH - FM
    layers = [e.get('{http://www.inkscape.org/namespaces/inkscape}label') for e in root
              if e.get('{http://www.inkscape.org/namespaces/inkscape}groupmode') == 'layer']
    assert 'Schematic' in layers and 'Title & legend' in layers


def test_value_parser():
    for s, v in [('100n', 1e-7), ('100 nF', 1e-7), ('0.1uF', 1e-7), ('0.1µF', 1e-7), ('4u7', 4.7e-6),
                 ('4.7µF/10V', 4.7e-6), ('22u/6V3', 22e-6), ('1e-9', 1e-9), ('10pF 50V', 1e-11), ('3k3', 3300)]:
        assert parse_si(s) == pytest.approx(v), s
    for s in ('?', 'DNP', 'C', ''):
        assert parse_si(s) is None


def test_cli_writes_all_formats(tmp_path):
    from kicad_manga.browser import Browser
    from kicad_manga.cli import main
    try:
        with Browser():
            pass
    except Exception as e:  # pragma: no cover
        pytest.skip(f'no usable Chromium: {e}')
    cfg = tmp_path / 'settings.toml'
    cfg.write_text('png_px_per_mm = 2\n[title]\nkicker = "テスト"\n')
    out = tmp_path / 'out' / 'demo'
    assert main([str(FIXTURE), '-o', str(out), '-c', str(cfg), '--title', 'Hello Board',
                 '--font-dir', str(tmp_path / 'nofonts')]) == 0
    svg = out.with_suffix('.svg').read_text()
    assert 'Hello Board' in svg and 'テスト' in svg and '<!--bg:' not in svg
    ET.fromstring(svg)
    from PIL import Image
    with Image.open(out.with_suffix('.png')) as im:
        assert im.size == (594, 420)
    assert out.with_suffix('.pdf').read_bytes()[:5] == b'%PDF-'
