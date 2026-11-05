"""kicad-manga: render a KiCad schematic as a pastel, manga-styled poster.

    kicad-manga board.kicad_sch                 # board-manga.svg/.png/.pdf
    kicad-manga board.kicad_sch -f pdf -o out/board --title "My Board"
"""

import argparse
import sys
from pathlib import Path

from . import config, fonts
from .browser import Browser
from .render import build_svg


def parse_args(argv):
    ap = argparse.ArgumentParser(prog='kicad-manga', description=__doc__.split('\n')[0].split(': ', 1)[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('schematic', help='a .kicad_sch file (one sheet; sub-sheets are drawn as boxes)')
    ap.add_argument('-o', '--output', help='output path without extension (default: ./<schematic name>-manga)')
    ap.add_argument('-c', '--config', help=f'settings file (default: {config.FILENAME} next to the schematic or here)')
    ap.add_argument('-f', '--format', action='append', choices=['svg', 'png', 'pdf'],
                    help='output format, repeatable (default: all three)')
    ap.add_argument('--dpmm', type=float, help='PNG resolution in pixels per mm (default 10)')
    ap.add_argument('--title', help='title panel heading (default: title block title or file name)')
    ap.add_argument('--subtitle', help='line under the title (default: title block comment 1)')
    ap.add_argument('--kicker', help='small line above the title (default: 回路図)')
    ap.add_argument('--bubble', help="the mascot's speech bubble (default: title block comment 2)")
    ap.add_argument('--seed', type=int, help='random seed for the decorations')
    ap.add_argument('--no-decorations', action='store_true', help='no plants, cables, shelves or sparkles')
    ap.add_argument('--no-characters', action='store_true', help='draw passives as plain symbols')
    ap.add_argument('--font-dir', help='where the fonts are (or get downloaded to)')
    return ap.parse_args(argv)


def settings(args):
    cfg = config.load(config.find(args.schematic, args.config))
    if args.format:
        cfg['formats'] = args.format
    if args.dpmm:
        cfg['png_px_per_mm'] = args.dpmm
    if args.seed is not None:
        cfg['seed'] = args.seed
    if args.no_decorations:
        cfg['decorations'] = False
    if args.no_characters:
        cfg['characters'] = False
    if args.font_dir:
        cfg['font_dir'] = args.font_dir
    for k in ('title', 'subtitle', 'kicker', 'bubble'):
        if getattr(args, k) is not None:
            cfg['title'][k] = getattr(args, k)
    return cfg


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    cfg = settings(args)
    src = Path(args.schematic)
    out = Path(args.output) if args.output else Path.cwd() / f'{src.stem}-manga'
    out.parent.mkdir(parents=True, exist_ok=True)
    font_list = fonts.load(cfg['font_dir'] or None)
    with Browser() as browser:
        svg, page = build_svg(src, cfg, font_list, browser)
        written = []
        if 'svg' in cfg['formats']:
            out.with_suffix('.svg').write_text(svg, encoding='utf-8')
            written.append(out.with_suffix('.svg'))
        if 'png' in cfg['formats']:
            browser.png(svg, page.W, page.H, cfg['png_px_per_mm'], out.with_suffix('.png'))
            written.append(out.with_suffix('.png'))
        if 'pdf' in cfg['formats']:
            browser.pdf(svg, page.W, page.H, out.with_suffix('.pdf'))
            written.append(out.with_suffix('.pdf'))
    for p in written:
        print(f'wrote {p}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
