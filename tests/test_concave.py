"""Tests specific to the concave corpus family (tests/corpus_concave.py)."""

import re
import warnings

import pytest
from shapely import affinity
from shapely.geometry import Polygon

import corpus_concave
from kicoil import geometry


def _raw_path(svg_file):
    d = re.search(r' d="([^"]+)"', svg_file.read_text()).group(1)
    return [tuple(map(float, p.split())) for p in d.strip('MZ ').split(',')]


def _import(svg_file):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore') # recentering warning
        return geometry.SVGShape(filename=str(svg_file), annular_width=3.0)


def test_shark_svg_fixture_is_clockwise_and_repeats_start():
    # The corpus fixture has to exercise SVGShape's reorientation branch
    raw = _raw_path(corpus_concave.SHARK_SVG)
    assert raw[0] == raw[-1]
    assert geometry.polygon_is_clockwise(raw)


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('repeat_start', [True, False])
def test_svg_import_independent_of_orientation(tmp_path, reverse, repeat_start):
    svg = tmp_path / 'shark.svg'
    corpus_concave.write_shark_svg(svg, reverse=reverse)
    if not repeat_start:
        text = svg.read_text()
        d = re.search(r' d="([^"]+)"', text).group(1)
        pts = d.strip('MZ ').split(',')
        svg.write_text(text.replace(d, 'M ' + ','.join(pts[:-1]) + ' Z'))
    raw = _raw_path(svg)
    assert geometry.polygon_is_clockwise(raw) == (not reverse)
    shape = _import(svg)
    assert not geometry.polygon_is_clockwise(shape.polygon)
    # Same outline as the polygon, mirrored in y (SVG and KiCad both have y pointing down)
    ref = Polygon([(x, -y) for x, y in corpus_concave.shark()])
    got = Polygon(shape.polygon)
    assert got.is_valid
    # (SVGShape recenters on the centroid, the corpus polygon is centered before rounding and simplification)
    c, cr = got.centroid, ref.centroid
    assert abs(c.x) < 1e-6 and abs(c.y) < 1e-6
    ref = affinity.translate(ref, -cr.x, -cr.y)
    assert got.symmetric_difference(ref).area < 1e-3
    assert abs(shape.sk.max_depth - corpus_concave.split_depth(corpus_concave.shark())) < 1e-3
