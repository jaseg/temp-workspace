"""Schematic file -> paper craft SVG."""

import base64

from markupsafe import Markup

from .. import kicad, text
from ..render import flatten_opacity, title_info
from ..svg import all_static_defs, tag
from . import stickers
from .circuit import PaperCircuit
from .page import MAT, MAT_DOT, PaperPage
from .paper import INK, INK_SOFT, WHITE
from .text import FONTS, FREDOKA, HAND  # noqa: F401  (FONTS is what the CLI loads for this style)
from ..fonts import MPR, POP

STYLE = f"""
.tape{{fill:none;stroke-linecap:square;stroke-linejoin:miter;stroke-opacity:.88}}
.tape-dots{{fill:none;stroke:{WHITE};stroke-linecap:round;stroke-opacity:.85}}
.tape-stitch{{fill:none;stroke:{WHITE};stroke-linecap:butt;stroke-opacity:.9}}
.tape-stripe{{fill:none;stroke:{WHITE};stroke-opacity:.85}}
.tape-bus{{fill:none;stroke:{WHITE};stroke-width:.32;stroke-opacity:.8}}
.pc-strip{{fill:none;stroke-linecap:round;stroke-linejoin:round}}
.pc-pin{{fill:none;stroke:#7d6a8c;stroke-width:.24;stroke-linecap:round}}
.pc-pin-deco{{fill:none;stroke:#7d6a8c;stroke-width:.22;stroke-linecap:round;stroke-linejoin:round}}
.pc-bubble{{fill:{WHITE};stroke:#7d6a8c;stroke-width:.22}}
.flag{{fill:none;stroke:#9a86a8;stroke-width:.3;stroke-linecap:round}}
.pinname{{font-weight:500;fill:{INK}}}
.pinnum{{fill:#b0709d;font-weight:500}}
.ref{{font-family:'{MPR}';font-weight:800;fill:#c94f7c}}
.value{{font-family:'{MPR}';font-weight:800;fill:#2f8578}}
.ref,.value{{paint-order:stroke;stroke:#fffaf0;stroke-width:.3;stroke-linejoin:round}}
.pwr{{font-family:'{FREDOKA}';font-weight:600;fill:{INK};paint-order:stroke;stroke:#fffaf0;stroke-width:.35}}
.symtxt{{font-weight:500}}
.field{{font-weight:500;fill:{INK_SOFT}}}
.remark{{font-family:'{HAND}';fill:#7b5b94}}
.boxtext{{font-family:'{HAND}'}}
.sheetname{{font-family:'{FREDOKA}';font-weight:600;fill:{INK}}}
.sheetfile{{font-family:'{HAND}';fill:{INK_SOFT}}}
.ovl{{text-decoration:overline}}
.pc-lbl{{font-family:'{FREDOKA}';font-weight:600;fill:{INK}}}
.pc-title{{font-family:'{FREDOKA}';font-weight:600;fill:{INK}}}
.pc-caption{{font-family:'{FREDOKA}';font-weight:500;fill:#7b5b94}}
.pc-hand{{font-family:'{HAND}';fill:#6b5a7a}}
.pc-coord{{font-family:'{FREDOKA}';font-weight:600;font-size:3.8px;fill:#c9708e}}
.pc-kicker{{font-family:'{POP}';font-size:5px;fill:#e27798;letter-spacing:.6px}}
.pc-cut-letter{{font-family:'{FREDOKA}';font-weight:600;fill:{INK}}}
.pc-sub{{font-family:'{HAND}';fill:#6b5a7a}}
.pc-foot{{font-family:'{HAND}';font-size:4.4px;fill:#8a7499}}
.pc-bubble-t{{font-family:'{HAND}';font-size:5.2px;fill:{INK}}}
.pc-card{{font-family:'{FREDOKA}';font-weight:600;fill:{INK}}}
"""


def defs(fonts):
    face = ''.join(f"@font-face{{font-family:'{f.family}';font-weight:{f.weight};"
                   f"src:url(data:font/woff2;base64,{base64.b64encode(f.woff2.read_bytes()).decode()}) "
                   f"format('woff2')}}" for f in fonts)
    dots = tag('pattern', [tag('circle', cx=2, cy=2, r=1.05, fill=MAT_DOT), tag('circle', cx=6, cy=6, r=1.05,
                                                                               fill=MAT_DOT)],
               id='pc-mat-dots', width=8, height=8, patternUnits='userSpaceOnUse')
    faces = []
    for i, (eye, mouth) in enumerate((('dot', 'smile'), ('dot', 'o'), ('arc', 'smile'))):
        parts = []
        if eye == 'dot':
            parts += [tag('circle', cx=-2.4, cy=-.6, r=.7, fill=INK), tag('circle', cx=2.4, cy=-.6, r=.7, fill=INK)]
        else:
            parts.append(tag('path', d='M-3.2-.2q.8-1.2 1.6 0M1.6-.2q.8-1.2 1.6 0', fill='none', stroke=INK,
                             stroke_width=.45, stroke_linecap='round'))
        parts += [tag('ellipse', cx=-3.6, cy=.9, rx=1.1, ry=.65, fill='#ff9db5', fill_opacity=.85),
                  tag('ellipse', cx=3.6, cy=.9, rx=1.1, ry=.65, fill='#ff9db5', fill_opacity=.85)]
        if mouth == 'smile':
            parts.append(tag('path', d='M-.9.5q.9 1 1.8 0', fill='none', stroke=INK, stroke_width=.4,
                             stroke_linecap='round'))
        else:
            parts.append(tag('ellipse', cx=0, cy=1.1, rx=.5, ry=.6, fill=INK))
        faces.append(tag('g', parts, id=f'pc-face-{i}'))
    return Markup(f'<defs>\n<style>{face}{STYLE}</style>\n{dots}\n{"".join(faces)}\n{stickers.defs()}\n'
                  f'{all_static_defs()}\n</defs>')


def build_svg(path, cfg, fonts=()):
    sch = kicad.load(path)
    text.use_fonts(fonts)
    circuit = PaperCircuit(sch, characters=cfg['characters']).render()
    page = PaperPage(circuit, title_info(sch, path, cfg['title']), cfg)
    svg = page.svg(defs(fonts), decorations=cfg['decorations'], seed=cfg['seed'])
    return flatten_opacity(svg), page
