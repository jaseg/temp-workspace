"""Die-cut stickers: small pieces of cute artwork with a white margin and a soft shadow.

Each sticker is a list of shapes around (0, 0), about 20 units across. `defs()` turns each one into two
<symbol>s: `st-NAME-cut`, the white die-cut margin with its shadow (every shape fattened by a thick white
stroke), and `st-NAME`, the artwork. A sticker is placed with `use()`."""

from markupsafe import Markup

from ..svg import num as f2, tag
from . import paper as P

EYE = P.INK
CHEEK = '#ff9db5'


def face(x, y, s=1.0, mood='smile'):
    """Two dot eyes, pink cheeks and a little mouth, `s` times the size of the 20-unit stickers' faces."""
    out = [('circle', dict(cx=x - 1.6 * s, cy=y, r=.45 * s, fill=EYE)),
           ('circle', dict(cx=x + 1.6 * s, cy=y, r=.45 * s, fill=EYE)),
           ('ellipse', dict(cx=x - 2.5 * s, cy=y + .9 * s, rx=.7 * s, ry=.45 * s, fill=CHEEK)),
           ('ellipse', dict(cx=x + 2.5 * s, cy=y + .9 * s, rx=.7 * s, ry=.45 * s, fill=CHEEK))]
    if mood == 'smile':
        out.append(('path', dict(d=f'M{f2(x - .6 * s)} {f2(y + .6 * s)}q{f2(.6 * s)} {f2(.6 * s)} {f2(1.2 * s)} 0',
                                 fill='none', stroke=EYE, stroke_width=.3 * s, stroke_linecap='round')))
    else:   # 'o'
        out.append(('ellipse', dict(cx=x, cy=y + .9 * s, rx=.35 * s, ry=.45 * s, fill=EYE)))
    return out


def star():
    d = 'M0-9 2.7-3.4 8.9-2.7 4.3 1.5 5.5 7.6 0 4.6-5.5 7.6-4.3 1.5-8.9-2.7-2.7-3.4Z'
    return [('path', dict(d=d, fill='#ffd86b', stroke='#e9b33f', stroke_width=.4, stroke_linejoin='round'))] + \
        face(0, .4, .8)


def heart():
    d = 'M0 8C-9 2-9.6-4-6.4-6.6-4-8.4-1.2-7.2 0-5 1.2-7.2 4-8.4 6.4-6.6 9.6-4 9 2 0 8Z'
    return [('path', dict(d=d, fill='#ff9fbf', stroke='#ec7ba0', stroke_width=.4)),
            ('path', dict(d='M-5.2-4.6q1-1.6 2.6-1.2', fill='none', stroke='#fff', stroke_width=.8,
                          stroke_linecap='round', stroke_opacity=.8))] + face(0, -.8, .75)


def flower():
    out = []
    for i in range(6):
        out.append(('ellipse', dict(cx=0, cy=-5, rx=3.2, ry=4.4, fill='#c9b6f7', stroke='#a993e6', stroke_width=.35,
                                    transform=f'rotate({i * 60})')))
    out.append(('circle', dict(cx=0, cy=0, r=3.6, fill='#ffe07a', stroke='#e9b94a', stroke_width=.35)))
    return out + face(0, -.2, .55)


def cloud():
    d = 'M-8 4.5C-10.5 4.5-10.6.4-7.8 0-8.2-3.6-4-5-2.2-2.8-1.4-6.6 4-7 5-2.6 8.6-3.2 10 2 7.6 4.5Z'
    return [('path', dict(d=d, fill='#eaf6ff', stroke='#a9cfee', stroke_width=.4, stroke_linejoin='round'))] + \
        face(0, .6, .7)


def rainbow():
    out = []
    for r, c in ((8.4, '#ff9fae'), (6.8, '#ffc98a'), (5.2, '#fff09a'), (3.6, '#a8e3b9')):
        out.append(('path', dict(d=f'M{-r} 3A{r} {r} 0 0 1 {r} 3', fill='none', stroke=c, stroke_width=1.6)))
    for x in (-6, 6):
        out.append(('path', dict(d=f'M{x - 3.2} 5.4c-1.8 0-1.8-2.6 0-2.6.4-1.6 3-1.6 3.4 0 1.8-.2 2 2.6.2 2.6Z',
                                 fill='#fff', stroke='#bcd6ee', stroke_width=.35)))
    return out


def resistor():
    out = [('path', dict(d='M-9.5 0H9.5', fill='none', stroke='#a6a0ae', stroke_width=.8, stroke_linecap='round')),
           ('rect', dict(x=-6, y=-2.6, width=12, height=5.2, rx=2.4, fill='#f5dcaa', stroke='#d6b67c',
                         stroke_width=.4))]
    for x, c in ((-3.4, '#a0714f'), (-1.6, '#4b3a5a'), (.2, '#f39a4c'), (3.4, '#d9b04a')):
        out.append(('rect', dict(x=x - .45, y=-2.6, width=.9, height=5.2, fill=c)))
    return out


def led():
    return [('path', dict(d='M-2 3V9.5M2 3V8', fill='none', stroke='#a6a0ae', stroke_width=.8, stroke_linecap='round')),
            ('path', dict(d='M-4.4 3.4V-2.6A4.4 4.4 0 0 1 4.4-2.6V3.4Z', fill='#ff8fa3', stroke='#e46a83',
                          stroke_width=.4)),
            ('rect', dict(x=-5.2, y=2.6, width=10.4, height=1.6, rx=.5, fill='#ff8fa3', stroke='#e46a83',
                          stroke_width=.4)),
            ('path', dict(d='M-2.4-3.4q.4-2 2-2.4', fill='none', stroke='#fff', stroke_width=.8,
                          stroke_linecap='round')),
            ('path', dict(d='M6.4-6.4l2-1.6M7-3l2.6-.2M4-8.6l.8-2.2', fill='none', stroke='#ffd86b',
                          stroke_width=.8, stroke_linecap='round'))]


def chip():
    legs = ''.join(f'M{x} -8.2V-6M{x} 6V8.2' for x in (-4.5, -1.5, 1.5, 4.5))
    return [('path', dict(d=legs, fill='none', stroke='#a6a0ae', stroke_width=1.1, stroke_linecap='round')),
            ('rect', dict(x=-7.2, y=-6, width=14.4, height=12, rx=1.6, fill='#b9e4f7', stroke='#86c3e0',
                          stroke_width=.4)),
            ('circle', dict(cx=-5.2, cy=-4, r=.6, fill='#86c3e0'))] + face(0, .2, .8)


def strawberry():
    d = 'M0 9C-6 6-7.6 0-6.6-2.8-5.4-5.4-2-5 0-4.4 2-5 5.4-5.4 6.6-2.8 7.6 0 6 6 0 9Z'
    out = [('path', dict(d=d, fill='#ff8f9e', stroke='#e46a7c', stroke_width=.4)),
           ('path', dict(d='M0-4.4-2.8-7.6-.8-6.6 0-8.8.8-6.6 2.8-7.6Z', fill='#8fd18f', stroke='#67b067',
                         stroke_width=.35, stroke_linejoin='round'))]
    for x, y in ((-3.4, -1), (3.4, -1), (-2.4, 3.6), (2.4, 3.6), (0, 6.2), (-4.2, 1.6), (4.2, 1.6)):
        out.append(('ellipse', dict(cx=x, cy=y, rx=.3, ry=.45, fill='#fff3b0')))
    return out + face(0, 1, .55)


def mushroom():
    return [('path', dict(d='M-2.8 1.6H2.8L3.4 7.2Q0 8.6-3.4 7.2Z', fill='#fff5e6', stroke='#d9c3a5',
                          stroke_width=.4)),
            ('path', dict(d='M-8.6 2C-8.6-4.2-4.6-7.6 0-7.6S8.6-4.2 8.6 2Z', fill='#ff8f9e', stroke='#e46a7c',
                          stroke_width=.4)),
            ('circle', dict(cx=-4.4, cy=-2.6, r=1.3, fill='#fff')),
            ('circle', dict(cx=1, cy=-5, r=1.1, fill='#fff')),
            ('circle', dict(cx=4.8, cy=-1.4, r=1.2, fill='#fff'))] + face(0, 4.2, .5)


def scissors():
    return [('path', dict(d='M-1.2 1.2 7.8-7.2M1.2 1.2-7.8-7.2', fill='none', stroke='#b8c0cc', stroke_width=1.5,
                          stroke_linecap='round')),
            ('circle', dict(cx=-3.6, cy=5.4, r=2.6, fill='none', stroke='#ff9fbf', stroke_width=1.5)),
            ('circle', dict(cx=3.6, cy=5.4, r=2.6, fill='none', stroke='#ff9fbf', stroke_width=1.5)),
            ('circle', dict(cx=0, cy=0, r=.7, fill='#8a7499'))]


def bolt():
    d = 'M1.6-9.4-5.4 1.2H-.8L-2.4 9.4 5.4-1.6H.8Z'
    return [('path', dict(d=d, fill='#ffe07a', stroke='#e9b94a', stroke_width=.45, stroke_linejoin='round'))] + \
        face(-.2, -.4, .45)


def sun():
    out = []
    for i in range(10):
        out.append(('path', dict(d='M0-6.6V-9.2', fill='none', stroke='#ffc35c', stroke_width=1.4,
                                 stroke_linecap='round', transform=f'rotate({i * 36})')))
    out.append(('circle', dict(cx=0, cy=0, r=5.6, fill='#ffd86b', stroke='#e9b33f', stroke_width=.4)))
    return out + face(0, .2, .7)


STICKERS = {'star': star, 'heart': heart, 'flower': flower, 'cloud': cloud, 'rainbow': rainbow,
            'resistor': resistor, 'led': led, 'chip': chip, 'strawberry': strawberry, 'mushroom': mushroom,
            'scissors': scissors, 'bolt': bolt, 'sun': sun}

CUT = 2.6          # width of the white margin around the artwork
SHADOW_ON_CARD = '#e3d3c0'


def _fat(shapes, colour, extra):
    out = []
    for name, a in shapes:
        a = dict(a)
        sw = float(a.get('stroke_width', 0) or 0)
        a.pop('stroke_opacity', None)
        a.pop('fill_opacity', None)
        if a.get('fill', '') not in ('none',):
            a['fill'] = colour
        a.update(stroke=colour, stroke_width=sw + extra, stroke_linejoin='round', stroke_linecap='round')
        out.append(tag(name, **a))
    return out


def defs():
    out = []
    for name, fn in STICKERS.items():
        shapes = fn()
        cut = [tag('g', _fat(shapes, SHADOW_ON_CARD, CUT * 2), transform='translate(.7 .9)'),
               tag('g', _fat(shapes, '#ffffff', CUT * 2))]
        out.append(tag('symbol', cut, id=f'st-{name}-cut', overflow='visible'))
        out.append(tag('symbol', [tag(n, **a) for n, a in shapes], id=f'st-{name}', overflow='visible'))
    return Markup('\n'.join(out))


def use(name, x, y, size, rot=0.0):
    """A sticker `size` units across at (x, y)."""
    s = size / 20
    tr = f'translate({f2(x)} {f2(y)}) rotate({f2(rot)}) scale({f2(s)})'
    return tag('g', [tag('use', href=f'#st-{name}-cut'), tag('use', href=f'#st-{name}')], transform=tr,
               cls='pc-sticker', data_sticker=name)
