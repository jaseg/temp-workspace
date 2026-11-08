"""Sanity checks for the paper craft style: the SVG is well-formed and the schematic's items show up."""

import collections
import xml.etree.ElementTree as ET
from pathlib import Path

from kicad_manga import config, kicad
from kicad_manga.papercraft.circuit import BANDS, colour_code
from kicad_manga.papercraft.render import build_svg

FIXTURE = Path(__file__).parent / 'fixtures' / 'demo.kicad_sch'


def render(**settings):
    cfg = config.load()
    cfg.update(settings, style='papercraft')
    svg, page = build_svg(FIXTURE, cfg)
    return ET.fromstring(svg), page


def test_items_are_drawn():
    sch = kicad.load(FIXTURE)
    root, _ = render()
    drawn = collections.Counter(e.get('data-kind') for e in root.iter() if e.get('data-kind'))
    for kind, attr in {'junction': 'junctions', 'no_connect': 'no_connects', 'label': 'local_labels',
                       'text': 'texts', 'bus': 'buses', 'bus_entry': 'bus_entries'}.items():
        assert drawn[kind] == len(getattr(sch, attr)), kind
    refs = {p.value for s in sch.symbols for p in s.properties if p.key == 'Reference'}
    assert {e.get('data-ref') for e in root.iter() if e.get('data-kind') == 'symbol'} == refs
    assert any(e.get('class') == 'net' for e in root.iter())
    assert any(e.get('class') == 'pc-sticker' for e in root.iter())


def test_no_group_opacity():
    """Shadows use fill/stroke opacity only, so PDFs don't fill up with transparency groups."""
    root, _ = render()
    assert not [e for e in root.iter() if e.get('opacity') and e.tag.endswith('}g')]


def test_colour_code():
    assert colour_code('4k7') == [BANDS[4], BANDS[7], BANDS[2]]
    assert colour_code('100') == [BANDS[1], BANDS[0], BANDS[1]]
    assert colour_code('10') == [BANDS[1], BANDS[0], BANDS[0]]
    assert colour_code('0') == [BANDS[0]]
    assert colour_code('DNP') == []
