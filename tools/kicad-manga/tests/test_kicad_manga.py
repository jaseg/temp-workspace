"""High-level sanity checks. They don't compare against reference output, only that
everything in the schematic shows up and the outputs are well-formed."""

import collections
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from kicad_manga import config, kicad
from kicad_manga.page import FM
from kicad_manga.render import build_svg, pdf_tool
from kicad_manga.util import parse_si

FIXTURE = Path(__file__).parent / 'fixtures' / 'demo.kicad_sch'
# data-kind -> the list of those items in gerbonara's Schematic
ITEM_KINDS = {'wire': 'wires', 'bus': 'buses', 'bus_entry': 'bus_entries', 'junction': 'junctions',
              'no_connect': 'no_connects', 'label': 'local_labels', 'global_label': 'global_labels',
              'hierarchical_label': 'hierarchical_labels', 'netclass_flag': 'netclass_flags', 'text': 'texts',
              'text_box': 'text_boxes', 'table': 'tables', 'image': 'images', 'sheet': 'subsheets',
              'polyline': 'polylines', 'rectangle': 'rectangles', 'circle': 'circles', 'arc': 'arcs',
              'bezier': 'beziers', 'rule_area': 'rule_areas'}


def render(path=FIXTURE, **settings):
    cfg = config.load()
    cfg.update(settings)
    svg, page = build_svg(path, cfg)
    return ET.fromstring(svg), page


def test_every_schematic_item_is_drawn():
    sch = kicad.load(FIXTURE)
    root, _ = render()
    drawn = collections.Counter(e.get('data-kind') for e in root.iter() if e.get('data-kind'))
    for kind, attr in ITEM_KINDS.items():
        assert drawn[kind] == len(getattr(sch, attr)) > 0, kind
    refs = {p.value for s in sch.symbols for p in s.properties if p.key == 'Reference'}
    assert {e.get('data-ref') for e in root.iter() if e.get('data-kind') == 'symbol'} == refs
    text = ''.join(root.itertext())
    for attr in ('local_labels', 'global_labels', 'hierarchical_labels', 'texts'):
        for item in getattr(sch, attr):
            assert item.text in text
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
    from click.testing import CliRunner
    from kicad_manga.cli import main
    cfg = tmp_path / 'settings.toml'
    cfg.write_text('png_px_per_mm = 2\n[title]\nkicker = "テスト"\n')
    out = tmp_path / 'out' / 'demo'
    args = [str(FIXTURE), '-o', str(out), '-c', str(cfg), '--title', 'Hello Board', '--font-dir', str(tmp_path)]
    if pdf_tool() is None:
        args += ['-f', 'svg', '-f', 'png']
    res = CliRunner().invoke(main, args)
    assert res.exit_code == 0, res.output
    svg = out.with_suffix('.svg').read_text()
    assert 'Hello Board' in svg and 'テスト' in svg
    ET.fromstring(svg)
    assert kicad.png_info(out.with_suffix('.png').read_bytes())[:2] == (594, 420)
    if pdf_tool() is not None:
        assert out.with_suffix('.pdf').read_bytes()[:5] == b'%PDF-'
