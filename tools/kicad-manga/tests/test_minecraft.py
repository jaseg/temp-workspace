"""The minecraft style, on small schematics written here and a tiny made-up resource pack (solid colour textures, no
models, so the built-in fallback models are used). Set KICAD_MANGA_TEST_PACK to a real pack (.zip or folder) to
also render with it."""

import os
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from kicad_manga import config
from kicad_manga.kicad import load
from kicad_manga.minecraft.circuit import Builder
from kicad_manga.minecraft.font import BitmapFont
from kicad_manga.minecraft.pack import ResourcePack
from kicad_manga.minecraft.render import build_svg

LIB = '''
    (symbol "Device:C_Small" (pin_names (offset 0.254) (hide yes)) (in_bom yes) (on_board yes)
      (property "Reference" "C" (at 0.254 1.778 0) (effects (font (size 1.27 1.27)) (justify left)))
      (property "Value" "C_Small" (at 0.254 -2.032 0) (effects (font (size 1.27 1.27)) (justify left)))
      (symbol "C_Small_0_1"
        (polyline (pts (xy -1.524 0.508) (xy 1.524 0.508)) (stroke (width 0.3) (type default)) (fill (type none)))
        (polyline (pts (xy -1.524 -0.508) (xy 1.524 -0.508)) (stroke (width 0.3) (type default)) (fill (type none))))
      (symbol "C_Small_1_1"
        (pin passive line (at 0 2.54 270) (length 2.032) (name "" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 0 -2.54 90) (length 2.032) (name "" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27)))))))
    (symbol "Device:D" (pin_names (offset 1.016) (hide yes)) (in_bom yes) (on_board yes)
      (property "Reference" "D" (at 0 2.54 0) (effects (font (size 1.27 1.27))))
      (property "Value" "D" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))
      (symbol "D_0_1"
        (polyline (pts (xy -1.27 1.27) (xy -1.27 -1.27)) (stroke (width 0.25) (type default)) (fill (type none))))
      (symbol "D_1_1"
        (pin passive line (at -3.81 0 0) (length 2.54) (name "K" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 3.81 0 180) (length 2.54) (name "A" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27)))))))
    (symbol "Device:Q_NPN_BCE" (pin_names (offset 0) (hide yes)) (in_bom yes) (on_board yes)
      (property "Reference" "Q" (at 5.08 1.27 0) (effects (font (size 1.27 1.27)) (justify left)))
      (property "Value" "Q_NPN_BCE" (at 5.08 -1.27 0) (effects (font (size 1.27 1.27)) (justify left)))
      (symbol "Q_NPN_BCE_0_1"
        (polyline (pts (xy 0.635 1.905) (xy 0.635 -1.905)) (stroke (width 0.5) (type default)) (fill (type none))))
      (symbol "Q_NPN_BCE_1_1"
        (pin input line (at -5.08 0 0) (length 5.715) (name "B" (effects (font (size 1.27 1.27))))
          (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 2.54 5.08 270) (length 2.54) (name "C" (effects (font (size 1.27 1.27))))
          (number "2" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 2.54 -5.08 90) (length 2.54) (name "E" (effects (font (size 1.27 1.27))))
          (number "3" (effects (font (size 1.27 1.27)))))))
'''


def sym(lib_id, ref, x, y, rot=0):
    return f'''
  (symbol (lib_id "{lib_id}") (at {x} {y} {rot}) (unit 1) (in_bom yes) (on_board yes) (dnp no)
    (property "Reference" "{ref}" (at {x + 2.5} {y - 1} 0) (effects (font (size 1.27 1.27)) (justify left)))
    (property "Value" "v" (at {x + 2.5} {y + 1} 0) (effects (font (size 1.27 1.27)) (justify left))))'''


def wire(x0, y0, x1, y1):
    return f'\n  (wire (pts (xy {x0} {y0}) (xy {x1} {y1})) (stroke (width 0) (type default)))'


def schematic(body):
    return f'''(kicad_sch (version 20231120) (generator "eeschema") (generator_version "8.0")
  (uuid "00000000-0000-0000-0000-000000000001")
  (paper "A5")
  (lib_symbols {LIB})
  {body}
)
'''


@pytest.fixture
def pack(tmp_path):
    """A resource pack with a few flat colour textures and nothing else."""
    root = tmp_path / 'pack'
    tex = root / 'assets/minecraft/textures/block'
    tex.mkdir(parents=True)
    (root / 'pack.mcmeta').write_text('{"pack": {"pack_format": 34, "description": "test"}}')
    for name, col in (('smooth_stone', (200, 200, 200)), ('repeater', (180, 180, 180)), ('bricks', (150, 60, 40)),
                      ('redstone_dust_dot', (255, 255, 255)), ('grass_block_top', (120, 120, 120))):
        Image.new('RGBA', (16, 16), col + (255,)).save(tex / f'{name}.png')
    zpath = tmp_path / 'pack.zip'
    with zipfile.ZipFile(zpath, 'w') as z:
        for p in root.rglob('*'):
            if p.is_file():
                z.write(p, Path('wrapped') / p.relative_to(root))     # a zip with a folder inside
    return root, zpath


def build(tmp_path, body, pack_path, block_mm=2.54):
    path = tmp_path / 't.kicad_sch'
    path.write_text(schematic(body))
    pk = ResourcePack([pack_path])
    b = Builder(load(path), pk, BitmapFont(pk), block_mm)
    b.build()
    return b, path


def states(b, name):
    return [blk for blk in b.world.blocks if blk.kind == 'state' and blk.args[0] == name]


def test_pack_sources(pack):
    root, zpath = pack
    for p in (root, zpath):
        pk = ResourcePack([p])
        assert pk.texture('block/bricks').getpixel((3, 3))[:3] == (150, 60, 40)
        assert pk.texture('block/nope').size == (16, 16)              # missing: the magenta check
        m = pk.model('block/repeater')                                 # built-in fallback
        assert m['elements'] and m['textures']['top'] == 'block/repeater'
        assert [mm for mm, _, _ in pk.state_models('repeater', {'facing': 'west'})] == ['block/repeater']


def test_stacked_packs(pack, tmp_path):
    root, _ = pack
    over = tmp_path / 'over'
    (over / 'assets/minecraft/textures/block').mkdir(parents=True)
    Image.new('RGBA', (32, 32), (1, 2, 3, 255)).save(over / 'assets/minecraft/textures/block/bricks.png')
    pk = ResourcePack([over, root])
    assert pk.texture('block/bricks').getpixel((0, 0))[:3] == (1, 2, 3)
    assert pk.texture('block/repeater').getpixel((0, 0))[:3] == (180, 180, 180)


def test_capacitors_are_chests(pack, tmp_path):
    """Capacitors 2.54 mm apart on a 1.27 mm block grid: one (wooden) chest each, side by side, wired to both
    pins."""
    body = ''.join(sym('Device:C_Small', f'C{k}', 50.8 + 2.54 * k, 50.8) for k in range(4))
    body += ''.join(wire(50.8 + 2.54 * k, 48.26, 50.8 + 2.54 * k, 43.18) for k in range(4))
    body += ''.join(wire(50.8 + 2.54 * k, 53.34, 50.8 + 2.54 * k, 58.42) for k in range(4))
    b, _ = build(tmp_path, body, pack[0], 1.27)
    chests = [blk for blk in b.world.blocks if blk.kind == 'mob' and blk.args[0].startswith('chest')]
    cells = [(p.i, p.j) for p in chests]
    assert len(cells) == 4 and len(set(cells)) == 4
    assert b.stats['unplaced'] == 0
    assert {c.args[0] for c in chests} == {'chest'}
    for k in range(4):
        x = round((50.8 + 2.54 * k) / 1.27)
        assert (x, round(48.26 / 1.27)) in b.world.dust and (x, round(53.34 / 1.27)) in b.world.dust


def test_diode_is_a_repeater_pointing_to_the_cathode(pack, tmp_path):
    body = sym('Device:D', 'D1', 50.8, 50.8) + wire(40.64, 50.8, 46.99, 50.8) + wire(54.61, 50.8, 60.96, 50.8)
    b, _ = build(tmp_path, body, pack[0])
    (rep,) = states(b, 'repeater')
    props = dict(rep.args[1])
    # K is pin 1 on the left: the signal runs west, so the repeater's back (its facing) is east
    assert props['facing'] == 'east'


def test_transistor_is_a_comparator(pack, tmp_path):
    body = sym('Device:Q_NPN_BCE', 'Q1', 50.8, 50.8)
    b, _ = build(tmp_path, body, pack[0])
    (cmp_,) = states(b, 'comparator')
    props = dict(cmp_.args[1])
    # the symbol's y points up: C is at the top of the sheet and E below, so the output points south and the
    # comparator's back (its facing) north
    assert props['facing'] == 'north' and props['mode'] == 'compare'
    c = (cmp_.i, cmp_.j)
    nets = {d for cell in ((c[0], c[1] + 1), (c[0], c[1] - 1), (c[0] - 1, c[1])) for d in b.world.dust.get(cell, {})}
    assert len(nets) == 3, 'base, collector and emitter all reach the comparator'


def test_render_svg(pack, tmp_path):
    body = sym('Device:D', 'D1', 50.8, 50.8) + sym('Device:C_Small', 'C1', 76.2, 50.8)
    path = tmp_path / 't.kicad_sch'
    path.write_text(schematic(body))
    cfg = config.load()
    cfg['minecraft']['packs'] = [str(pack[1])]
    svg, page = build_svg(path, cfg)
    assert svg.startswith('<?xml') and 'image-rendering:pixelated' in svg
    assert page.page_mm == (210, 148)


@pytest.mark.skipif(not os.environ.get('KICAD_MANGA_TEST_PACK'), reason='KICAD_MANGA_TEST_PACK not set')
def test_render_with_real_pack(tmp_path):
    body = (sym('Device:D', 'D1', 50.8, 50.8) + sym('Device:Q_NPN_BCE', 'Q1', 76.2, 50.8)
            + ''.join(sym('Device:C_Small', f'C{k}', 101.6 + 2.54 * k, 50.8) for k in range(4)))
    path = tmp_path / 't.kicad_sch'
    path.write_text(schematic(body))
    cfg = config.load()
    cfg['minecraft']['packs'] = [os.environ['KICAD_MANGA_TEST_PACK']]
    svg, _ = build_svg(path, cfg)
    assert '<use' in svg
