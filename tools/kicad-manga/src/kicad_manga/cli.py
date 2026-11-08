"""kicad-manga: render a KiCad schematic as a pastel, manga-styled poster.

    kicad-manga board.kicad_sch                 # board-manga.svg/.png/.pdf
    kicad-manga board.kicad_sch -f pdf -o out/board --title "My Board"
"""

from pathlib import Path

import click

from . import config, fonts
from .render import build_svg, write_pdf, write_png


@click.command(help='Render a KiCad schematic as a pastel, manga-styled poster.\n\n'
                    'SCHEMATIC is one .kicad_sch file; sub-sheets are drawn as boxes.')
@click.argument('schematic', type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option('-o', '--output', type=click.Path(path_type=Path),
              help='Output path without extension (default: ./<schematic name>-manga).')
@click.option('-c', '--config', 'config_file', type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help=f'Settings file (default: {config.FILENAME} next to the schematic or here).')
@click.option('-f', '--format', 'formats', multiple=True, type=click.Choice(['svg', 'png', 'pdf']),
              help='Output format, repeatable (default: all three).')
@click.option('--dpmm', type=float, help='PNG resolution in pixels per mm (default 10).')
@click.option('--title', help='Title panel heading (default: title block title or file name).')
@click.option('--subtitle', help='Line under the title (default: title block comment 1).')
@click.option('--kicker', help='Small line above the title (default: 回路図).')
@click.option('--bubble', help="The mascot's speech bubble (default: title block comment 2).")
@click.option('--seed', type=int, help='Random seed for the decorations.')
@click.option('--no-decorations', is_flag=True, help='No plants, cables, shelves or sparkles.')
@click.option('--no-characters', is_flag=True, help='Draw passives as plain symbols.')
@click.option('-s', '--style', type=click.Choice(['manga', 'minecraft']),
              help='Drawing style (default: manga).')
@click.option('--pack', 'packs', multiple=True, type=click.Path(exists=True, path_type=Path),
              help='Minecraft resource pack (.zip or folder), repeatable; the first one given wins.')
@click.option('--font-dir', type=click.Path(file_okay=False, path_type=Path),
              help='Where the fonts are (default: downloaded once into ~/.cache/kicad-manga/fonts).')
def main(schematic, output, config_file, formats, dpmm, title, subtitle, kicker, bubble, seed, no_decorations,
         no_characters, style, packs, font_dir):
    cfg = config.load(config.find(schematic, config_file))
    if style:
        cfg['style'] = style
    if packs:
        cfg['minecraft']['packs'] = [str(p) for p in packs]
    if formats:
        cfg['formats'] = list(formats)
    if dpmm:
        cfg['png_px_per_mm'] = dpmm
    if seed is not None:
        cfg['seed'] = seed
    if no_decorations:
        cfg['decorations'] = False
    if no_characters:
        cfg['characters'] = False
    if font_dir:
        cfg['font_dir'] = str(font_dir)
    for k, v in (('title', title), ('subtitle', subtitle), ('kicker', kicker), ('bubble', bubble)):
        if v is not None:
            cfg['title'][k] = v

    if cfg['style'] == 'minecraft':
        return minecraft(schematic, output, cfg)

    out = output or Path.cwd() / f'{schematic.stem}-manga'
    out.parent.mkdir(parents=True, exist_ok=True)
    font_list = fonts.load(cfg['font_dir'] or None)
    svg, page = build_svg(schematic, cfg, font_list)
    if 'svg' in cfg['formats']:
        out.with_suffix('.svg').write_text(svg, encoding='utf-8')
        click.echo(f'wrote {out.with_suffix(".svg")}')
    if 'png' in cfg['formats']:
        write_png(svg, font_list, cfg['png_px_per_mm'], page.W, out.with_suffix('.png'))
        click.echo(f'wrote {out.with_suffix(".png")}')
    if 'pdf' in cfg['formats']:
        try:
            write_pdf(svg, font_list, out.with_suffix('.pdf'))
        except RuntimeError as e:
            raise click.ClickException(str(e))
        click.echo(f'wrote {out.with_suffix(".pdf")}')


def minecraft(schematic, output, cfg):
    from .minecraft.render import build_svg, write_pdf as mc_pdf
    out = output or Path.cwd() / f'{schematic.stem}-minecraft'
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        svg, page = build_svg(schematic, cfg)
    except ValueError as e:
        raise click.ClickException(str(e))
    for line in page.report():
        click.echo(line)
    if 'svg' in cfg['formats']:
        out.with_suffix('.svg').write_text(svg, encoding='utf-8')
        click.echo(f'wrote {out.with_suffix(".svg")}')
    if 'png' in cfg['formats']:
        write_png(svg, [], cfg['png_px_per_mm'], page.page_mm[0], out.with_suffix('.png'))
        click.echo(f'wrote {out.with_suffix(".png")}')
    if 'pdf' in cfg['formats']:
        try:
            mc_pdf(svg, out.with_suffix('.pdf'))
        except RuntimeError as e:
            raise click.ClickException(str(e))
        click.echo(f'wrote {out.with_suffix(".pdf")}')


if __name__ == '__main__':
    main()
