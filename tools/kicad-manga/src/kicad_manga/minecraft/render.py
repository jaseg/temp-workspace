"""Schematic file -> Minecraft-style SVG (seen from high up, see `oblique`), and the SVG -> PDF."""

from ..render import write_pdf as svg_to_pdf
from ..kicad import load, paper_size
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
    builder = Builder(sch, pack, font, mc['block_mm'], mc['camera_deg'], mc['yaw_deg'])
    world = builder.build()
    page = Page(world, builder, sch, path, cfg, pack, font)
    page.build()
    drawer = Drawer(world, pack, font, page, px=mc['px_per_block'], dust_width=mc['dust_width'], fpx=builder.fpx,
                    camera_deg=mc['camera_deg'], yaw_deg=mc['yaw_deg'])
    svg = drawer.svg(builder.power, builder.mm, mc['block_mm'], builder.paper, paper_size(sch))
    page.page_mm = drawer.page_mm
    page.image = drawer.image
    return svg, page


def write_pdf(svg, path):
    svg_to_pdf(svg, [], path)
