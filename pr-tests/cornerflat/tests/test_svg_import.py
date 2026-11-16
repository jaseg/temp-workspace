"""SVG outline import (kicoil.svg_import, parsing with svgelements)."""

import math
import warnings

import pytest
from shapely.geometry import Polygon

from kicoil import svg_import


def outline(tmp_path, body, svg_attrs='', **kw):
    f = tmp_path / 'outline.svg'
    f.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" {svg_attrs}>'
                 f'{body}</svg>')
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        pts = svg_import.read_outline(f, **kw)
    return Polygon(pts), [str(x.message) for x in w]


def box(poly):
    return tuple(round(v, 6) for v in poly.bounds)


@pytest.mark.parametrize('d', ['M 0 0 L 30 0 L 30 20 L 0 20 Z', 'M 0,0 L 30,0 30,20 0,20 z', 'M0 0H30V20H0Z',
                               'm 0 0 l 30 0 l 0 20 l -30 0 z', 'M 0 0 30 0 30 20 0 20 Z', 'M0,0 30,0 30,20 0,20 0,0'])
def test_path_syntax(tmp_path, d):
    # The original import read only 'M x y L x y ... Z' and 'M x y,x y ... Z'
    poly, _ = outline(tmp_path, f'<path d="{d}"/>')
    assert box(poly) == (0, 0, 30, 20) and len(poly.exterior.coords) == 5


def test_curves_are_flattened_within_the_tolerance(tmp_path):
    poly, _ = outline(tmp_path, '<circle cx="0" cy="0" r="20"/>', tolerance=0.01)
    r = [math.hypot(x, y) for x, y in poly.exterior.coords]
    assert max(r) <= 20 + 1e-9 and min(r) >= 20 - 0.01 - 1e-9
    poly, _ = outline(tmp_path, '<path d="M 0 0 C 10 -10 20 -10 30 0 L 30 20 L 0 20 Z"/>', tolerance=0.001)
    assert len(poly.exterior.coords) > 20
    # A straight line written as a curve stays one segment
    poly, _ = outline(tmp_path, '<path d="M 0 0 C 0 0 30 0 30 0 L 30 20 L 0 20 Z"/>')
    assert len(poly.exterior.coords) == 5


def test_shapes_transforms_and_use(tmp_path):
    poly, _ = outline(tmp_path, '<g transform="scale(2)"><rect x="0" y="0" width="30" height="20"/></g>')
    assert box(poly) == (0, 0, 60, 40) # (the original import ignored transforms)
    poly, _ = outline(tmp_path, '<polygon points="0,0 30,0 30,20"/>')
    assert poly.area == pytest.approx(300)
    poly, _ = outline(tmp_path, '<defs><rect id="r" width="30" height="20"/></defs><use xlink:href="#r" x="5"/>')
    assert box(poly) == (5, 0, 35, 20)


def test_units(tmp_path):
    # Absolute units of width and height scale the viewBox; without them one user unit is one mm. (svgelements' unit
    # constants are good to about 1 ppm.)
    poly, _ = outline(tmp_path, '<rect width="30" height="20"/>', 'width="60mm" height="40mm" viewBox="0 0 30 20"')
    assert poly.bounds == pytest.approx((0, 0, 60, 40), rel=1e-5)
    poly, _ = outline(tmp_path, '<rect width="96" height="48"/>', 'width="1in" height="0.5in" viewBox="0 0 96 48"')
    assert poly.bounds == pytest.approx((0, 0, 25.4, 12.7), rel=1e-5)
    poly, _ = outline(tmp_path, '<rect width="30" height="20"/>')
    assert box(poly) == (0, 0, 30, 20)


def test_hidden_elements_are_not_part_of_the_outline(tmp_path):
    big = '<rect width="100" height="100"/>'
    poly, _ = outline(tmp_path, f'<g style="display:none">{big}</g><rect width="30" height="20"/>')
    assert box(poly) == (0, 0, 30, 20)
    poly, _ = outline(tmp_path, f'<defs>{big}</defs><rect width="30" height="20"/>')
    assert box(poly) == (0, 0, 30, 20)
    poly, _ = outline(tmp_path, f'<style>.h {{ display: none }}</style><g class="h">{big}</g>'
                                f'<rect width="30" height="20"/>')
    assert box(poly) == (0, 0, 30, 20)


def test_first_shape_is_the_outline(tmp_path):
    poly, _ = outline(tmp_path, '<rect width="3" height="2"/><rect x="10" width="30" height="20"/>')
    assert box(poly) == (0, 0, 3, 2)


def test_errors(tmp_path):
    with pytest.raises(ValueError, match='not closed'):
        outline(tmp_path, '<path d="M 0 0 L 30 20"/>')
    with pytest.raises(ValueError, match='more than one contour'):
        outline(tmp_path, '<path d="M 0 0 L 30 0 L 30 20 Z M 40 0 L 50 0 L 50 10 Z"/>')
    with pytest.raises(ValueError, match='no path'):
        outline(tmp_path, '<text>x</text>')
