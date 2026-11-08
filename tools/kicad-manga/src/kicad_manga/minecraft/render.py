"""Schematic file -> Minecraft-style SVG, and the SVG -> PDF."""

import hashlib
import sys

from ..kicad import load, paper_size
from ..render import write_pdf as svg_to_pdf
from .circuit import Builder
from .draw import Drawer
from .font import BitmapFont
from .pack import ResourcePack
from .page import Page


def build_svg(path, cfg):
    """Render a .kicad_sch in the minecraft style: (SVG string, Page)."""
    mc = cfg['minecraft']
    if not mc['packs']:
        raise ValueError('the minecraft style needs a resource pack (--pack, or packs = [...] under [minecraft] '
                         'in the settings)')
    pack = ResourcePack(mc['packs'])
    font = BitmapFont(pack)
    sch = load(path)
    builder = Builder(sch, pack, font, mc['block_mm'])
    world = builder.build()
    page = Page(world, builder, sch, path, cfg, pack, font)
    page.build()
    drawer = Drawer(world, pack, font, page.floor_of, page.tints)
    drawer.dust_width = mc['dust_width']
    page.page_mm = paper_size(sch)
    svg = drawer.svg(builder.power, page.sky(), extra_tall=page.extra_tall, page_mm=page.page_mm)
    return svg, page


def write_pdf(svg, path):
    """SVG -> PDF with rsvg-convert, then with every copy of the same texture merged into one (the converter writes
    each use of an image anew, which makes the file many times larger)."""
    svg_to_pdf(svg, [], path)
    try:
        import pikepdf
    except ImportError:
        print('kicad-manga: pikepdf is not installed, so the PDF is left large', file=sys.stderr)
        return
    dedupe_images(pikepdf, path)


def dedupe_images(pikepdf, path):
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        canon, remap = {}, {}
        for obj in pdf.objects:
            if isinstance(obj, pikepdf.Stream) and obj.get('/Subtype') == '/Image':
                smask = obj.get('/SMask')
                h = hashlib.sha1(obj.read_raw_bytes())
                h.update(repr(sorted((k, str(v)) for k, v in obj.items() if k not in ('/SMask', '/Length'))).encode())
                if smask is not None:
                    h.update(smask.read_raw_bytes())
                key = h.digest()
                if key in canon:
                    remap[obj.objgen] = canon[key]
                else:
                    canon[key] = obj
        for obj in pdf.objects:
            if not isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream)) or '/Resources' not in obj:
                continue
            xo = obj['/Resources'].get('/XObject')
            if xo is None:
                continue
            for k in list(xo.keys()):
                if xo[k].objgen in remap:
                    xo[k] = remap[xo[k].objgen]
        pdf.remove_unreferenced_resources()
        pdf.save(path, object_stream_mode=pikepdf.ObjectStreamMode.generate, compress_streams=True)
