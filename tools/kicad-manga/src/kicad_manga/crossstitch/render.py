"""Schematic file -> cross-stitch sampler SVG, and the SVG -> PDF."""

from ..kicad import load, paper_size
from ..render import write_pdf as svg_to_pdf
from .chart import Embroiderer
from .draw import Drawer
from .page import Page, title_info


def build_svg(path, cfg):
    """Render a .kicad_sch in the cross-stitch style: (SVG string, Page)."""
    cs = cfg['crossstitch']
    sch = load(path)
    emb = Embroiderer(sch, cs['hole_mm'])
    chart = emb.build()
    page = Page(chart, sch, path, cfg, title_info(sch, path, cfg['title']))
    page.build(emb.threads)
    W, H = paper_size(sch)
    svg = Drawer(chart, cs['px_per_cell']).svg(W, H)
    page.page_mm = (W, H)
    return svg, page


def write_pdf(svg, path):
    svg_to_pdf(svg, [], path)
