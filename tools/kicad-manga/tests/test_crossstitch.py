"""The cross-stitch sampler style, on the demo schematic."""

from pathlib import Path

from kicad_manga import config
from kicad_manga.crossstitch import motifs
from kicad_manga.crossstitch.chart import Embroiderer
from kicad_manga.crossstitch.render import build_svg
from kicad_manga.kicad import load

DEMO = Path(__file__).parent / 'fixtures' / 'demo.kicad_sch'


def test_chart_has_every_kind_of_stitch():
    emb = Embroiderer(load(DEMO))
    chart = emb.build()
    weights = {s.weight for s in chart.stitches}
    assert {'wire', 'text', 'line'} <= weights
    assert sum(s.weight == 'wire' for s in chart.stitches) >= len(emb.sch.wires)
    assert chart.knots and chart.crosses
    assert emb.threads.used


def test_svg_has_cloth_border_and_title():
    cfg = config.load()
    svg, page = build_svg(DEMO, cfg)
    assert svg.count('<image') == 1               # the cloth is one raster
    assert 'stroke-dasharray' in svg              # backstitch
    assert '<path' in svg
    assert not any('title panel' in n for n in page.report())


def test_alphabet_glyphs_are_rectangular():
    for ch, rows in motifs.ALPHABET.items():
        assert len(rows) == 7, ch
        assert len({len(r) for r in rows}) == 1, ch
    for chart in (motifs.VINE, motifs.STEM, motifs.CORNER, motifs.BIRD, motifs.TULIP, motifs.STRAWBERRY):
        assert len({len(r) for r in chart}) == 1
        assert set(''.join(chart)) <= set(motifs.KEY) | {'.'}
