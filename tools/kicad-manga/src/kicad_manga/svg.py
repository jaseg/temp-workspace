"""SVG output.

- Elements built in code use gerbonara's `Tag` (`tag()` below adds escaping and number formatting).
- Drawings with real artwork in them are jinja2 templates in `templates/`, rendered with `render()`.
- Fixed artwork (symbols, faces, the mascot, patterns) are standalone SVG files in `static/`. `static_defs()`
  returns what is inside their `<defs>`, so each file can be opened and edited on its own.

Templates get the `f` filter (numbers with at most three decimals) and the palette and font names as globals.
Everything they produce is `Markup`, so it can be passed into other templates and tags as is.
"""

import functools
import re
from importlib import resources

import jinja2
from gerbonara.utils import Tag
from markupsafe import Markup, escape

from . import palette

# CSS font families, as named inside the font files (see fonts.py)
FONT_POP = 'Pop'
FONT_ZEN = 'Zen'
FONT_MPR = 'MPR'


def num(v):
    """Numbers for SVG: at most three decimals, no trailing zeros."""
    return f'{v:.3f}'.rstrip('0').rstrip('.') or '0'


def _attr(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return num(v)
    return escape(str(v))


def tag(name, children=(), **attrs):
    """A gerbonara `Tag`. Attribute names map as in `Tag` (`stroke_width` -> `stroke-width`, `xlink__href` ->
    `xlink:href`), plus `cls` -> `class`. None values are left out, numbers are formatted with `num`, strings
    escaped. Children are tags or (already escaped) markup."""
    if 'cls' in attrs:
        attrs['class'] = attrs.pop('cls')
    attrs = {k: _attr(v) for k, v in attrs.items() if v is not None}
    return Markup(_compact(name, [c for c in children if c is not None and c != ''], attrs))


def _compact(name, children, attrs):
    # Tag puts every child on its own line. Inside text elements that whitespace would show up, so these are
    # written in one piece.
    t = Tag(name, children=list(children), **attrs)
    if name in ('text', 'tspan', 'textPath', 'style') and children:
        opening = str(Tag(name, **attrs))[:-2]
        return f'{opening}>{"".join(str(c) for c in children)}</{name}>'
    return str(t)


def group(children, **attrs):
    return tag('g', children, **attrs)


def path(d, **attrs):
    return tag('path', d=d, **attrs)


# ----------------------------------------------------------------------------
# Templates

@functools.cache
def env():
    e = jinja2.Environment(loader=jinja2.PackageLoader('kicad_manga', 'templates'),
                           autoescape=True, trim_blocks=True, lstrip_blocks=True,
                           undefined=jinja2.StrictUndefined)
    e.filters['f'] = num
    e.globals.update(INK=palette.INK, INK_SOFT=palette.INK_SOFT, LINE=palette.LINE, PAPER=palette.PAPER,
                     FONT_POP=FONT_POP, FONT_ZEN=FONT_ZEN, FONT_MPR=FONT_MPR)
    return e


def render(name, **ctx):
    """Render templates/<name> (e.g. 'characters/brick.svg.j2')."""
    return Markup(env().get_template(name).render(**ctx).strip())


# ----------------------------------------------------------------------------
# Static artwork

DEFS = re.compile(r'<defs[^>]*>(.*?)</defs>', re.S)


@functools.cache
def static_defs(name):
    """What is inside the <defs> of static/<name>.svg."""
    text = resources.files('kicad_manga').joinpath('static', f'{name}.svg').read_text(encoding='utf-8')
    m = DEFS.search(text)
    if not m:
        raise ValueError(f'static/{name}.svg has no <defs>')
    return Markup(m.group(1).strip())


def all_static_defs():
    """The <defs> content of every file in static/, for the document's <defs>."""
    names = sorted(p.name[:-4] for p in resources.files('kicad_manga').joinpath('static').iterdir()
                   if p.name.endswith('.svg'))
    return Markup('\n'.join(static_defs(n) for n in names))
