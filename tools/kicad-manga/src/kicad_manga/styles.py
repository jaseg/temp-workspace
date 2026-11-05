"""The SVG <defs>: fonts, styles, screentone patterns, faces and the mascot."""

from .characters import resistor_face_defs
from .palette import INK, INK_SOFT, LINE, PAPER
from .sexp import f2


def defs(fonts, width, height):
    faces = ''.join(
        f"@font-face{{font-family:'{fam}';font-weight:{wt};src:url(data:font/woff2;base64,{b64}) format('woff2');{rng}}}"
        for fam, wt, b64, rng in fonts)
    return f'''<defs>
<style>
{faces}
text{{font-family:'MPR','M PLUS Rounded 1c',sans-serif}}
:where(text:not([fill])){{fill:{INK}}}
.wire-o{{fill:none;stroke:{LINE};stroke-width:.62;stroke-linecap:round;stroke-linejoin:round}}
.wire-i{{fill:none;stroke-width:.3;stroke-linecap:round;stroke-linejoin:round}}
.bus-o{{fill:none;stroke:{LINE};stroke-width:1.35;stroke-linecap:round}}
.bus-i{{fill:none;stroke:#c7a9ff;stroke-width:.85;stroke-linecap:round}}
.sym-s{{fill:none;stroke:{LINE};stroke-width:.3;stroke-linecap:round;stroke-linejoin:round}}
.sym-s.thick{{stroke-width:.4}}
.pin{{fill:none;stroke:{LINE};stroke-width:.24;stroke-linecap:round}}
.nc-o{{fill:none;stroke:{LINE};stroke-width:.7;stroke-linecap:round}}
.nc-i{{fill:none;stroke:#ff8fa8;stroke-width:.35;stroke-linecap:round}}
.flag{{fill:none;stroke:{LINE};stroke-width:.25}}
.dnp{{fill:none;stroke:#ff6f91;stroke-width:.8;stroke-linecap:round;opacity:.75}}
.pinname{{font-weight:500}}
.pinnum{{fill:#b0709d;font-weight:500}}
.ref{{font-family:'MPR';font-weight:800;fill:#d6457f}}
.value{{font-family:'MPR';font-weight:800;fill:#2f8f86}}
.ref,.value{{paint-order:stroke;stroke:{PAPER};stroke-width:.32;stroke-linejoin:round}}
.pwr{{font-family:'Pop';fill:{INK};paint-order:stroke;stroke:#fff;stroke-width:.35}}
.symtxt{{font-weight:500}}
.lbl{{font-weight:800}}
.title{{font-family:'Pop';fill:#fff;paint-order:stroke;stroke:{INK};stroke-width:.55;stroke-linejoin:round}}
.caption{{font-family:'Zen';font-weight:700;fill:#7b5b94}}
.note{{font-family:'Zen';font-weight:700;fill:{INK}}}
.remark{{font-family:'Zen';font-weight:700;fill:#7b5b94}}
.ovl{{text-decoration:overline}}
.boxtext{{font-family:'Zen';font-weight:700}}
.sheetname{{font-family:'Pop';fill:{INK}}}
.sheetfile{{font-family:'Zen';font-weight:700;font-style:italic;fill:{INK_SOFT}}}
.field{{font-weight:500;fill:{INK_SOFT}}}
.pin-deco{{fill:none;stroke:{LINE};stroke-width:.24;stroke-linecap:round;stroke-linejoin:round}}
.pin-bubble{{fill:#fff;stroke:{LINE};stroke-width:.24}}
.sfx{{font-family:'Pop';paint-order:stroke;stroke:#fff;stroke-width:.9;stroke-linejoin:round;opacity:.55}}
.sfx-ro{{font-family:'Zen';font-weight:700;fill:{INK_SOFT};opacity:.5}}
.frame{{fill:none;stroke:{INK};stroke-width:1.6}}
.frame2{{fill:none;stroke:#ffb8d0;stroke-width:.6;stroke-dasharray:2.2 1.4}}
.coord{{font-family:'Pop';font-size:3.6px;fill:#d68ab5}}
.t-jp{{font-family:'Pop';font-size:7.5px;fill:#ff7fb2;paint-order:stroke;stroke:#fff;stroke-width:1.2}}
.t-main{{font-family:'Pop';font-size:8.6px;fill:#fff;paint-order:stroke;stroke:{INK};stroke-width:1.1;stroke-linejoin:round}}
.t-sub{{font-family:'Zen';font-weight:700;font-size:5px;fill:#7b5b94}}
.t-small{{font-family:'MPR';font-weight:800;font-size:3.2px;fill:{INK_SOFT}}}
.bubble-t{{font-family:'Pop';font-size:4.6px;fill:{INK}}}
</style>
<pattern id="tone-w" width="1.1" height="1.1" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><circle cx=".55" cy=".55" r=".2" fill="#fff" opacity=".7"/></pattern>
<pattern id="tone-ink" width=".9" height=".9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><circle cx=".45" cy=".45" r=".3" fill="{INK}"/></pattern>
<pattern id="tone-pink" width="3" height="3" patternUnits="userSpaceOnUse" patternTransform="rotate(30)"><circle cx="1.5" cy="1.5" r=".7" fill="#ffc2da"/></pattern>
<pattern id="tone-bg" width="3.2" height="3.2" patternUnits="userSpaceOnUse" patternTransform="rotate(30)"><circle cx="1.6" cy="1.6" r=".42" fill="#ffd3e4"/></pattern>
<radialGradient id="vig-g" cx=".5" cy=".5" r=".72"><stop offset=".75" stop-color="#000"/><stop offset="1" stop-color="#fff"/></radialGradient>
<mask id="vignette"><rect width="{f2(width)}" height="{f2(height)}" fill="url(#vig-g)"/></mask>
<linearGradient id="title-grad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffd6e8"/><stop offset=".5" stop-color="#e7dcff"/><stop offset="1" stop-color="#cdf3ea"/></linearGradient>
<linearGradient id="banner-grad" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffc1dc"/><stop offset=".5" stop-color="#d9c8ff"/><stop offset="1" stop-color="#bdeee2"/></linearGradient>
<path id="heart" d="M0 .55C-.95-.1-1-.75-.62-.95-.32-1.1-.08-.9 0-.65.08-.9.32-1.1.62-.95 1-.75.95-.1 0 .55Z" fill="#ff7fb2" stroke="{INK}" stroke-width=".16" stroke-linejoin="round"/>
<g id="blossom"><circle r=".75" stroke="{INK}" stroke-width=".18"/><circle r=".28" fill="#fff6a8"/></g>
<path id="sparkle" d="M0-5C.6-1.2 1.2-.6 5 0 1.2.6.6 1.2 0 5-.6 1.2-1.2.6-5 0-1.2-.6-.6-1.2 0-5Z" stroke="{INK}" stroke-width=".35" stroke-linejoin="round"/>
<path id="heart-d" d="M0 4C-6.5-.5-6.8-4.6-4.2-5.8-2.2-6.7-.6-5.3 0-3.8.6-5.3 2.2-6.7 4.2-5.8 6.8-4.6 6.5-.5 0 4Z" transform="translate(0 1)" stroke="{INK}" stroke-width=".4" stroke-linejoin="round"/>
<path id="star" d="M0-5 1.4-1.6 5-1.5 2.2.8 3.1 4.4 0 2.4-3.1 4.4-2.2.8-5-1.5-1.4-1.6Z" stroke="{INK}" stroke-width=".4" stroke-linejoin="round"/>
<g id="blossom-d" stroke="{INK}" stroke-width=".35">
  <g id="petals">{''.join(f'<ellipse cx="0" cy="-2.6" rx="1.9" ry="2.6" transform="rotate({a})"/>' for a in range(0, 360, 72))}</g>
  <circle r="1.3" fill="#fff3a0"/>
</g>
{face_defs()}
{resistor_face_defs()}
{mascot_def()}
</defs>'''


def face_defs():
    eye = '<ellipse cx="{x}" cy="-.6" rx=".75" ry="1.05" fill="#4b3a5a"/><circle cx="{hx}" cy="-1" r=".3" fill="#fff"/>'
    blush = '<ellipse cx="-3" cy=".9" rx="1.1" ry=".6" fill="#ff9cc2" opacity=".75"/><ellipse cx="3" cy=".9" rx="1.1" ry=".6" fill="#ff9cc2" opacity=".75"/>'
    eyes = eye.format(x=-1.9, hx=-1.65) + eye.format(x=1.9, hx=2.15)
    st = 'fill="none" stroke="#4b3a5a" stroke-width=".38" stroke-linecap="round" stroke-linejoin="round"'
    return f'''
<g id="face-happy">{eyes}{blush}<path d="M-.7 .7Q0 1.5.7 .7" {st}/></g>
<g id="face-smile"><path d="M-2.7 -.4Q-1.9 -1.5 -1.1 -.4M1.1 -.4Q1.9 -1.5 2.7 -.4" {st}/>{blush}<path d="M-.9 .6Q0 1.7.9 .6Z" fill="#ff7f9e" stroke="#4b3a5a" stroke-width=".3"/></g>
<g id="face-wink">{eye.format(x=-1.9, hx=-1.65)}<path d="M1.2 -.5Q1.9 -1.3 2.6 -.5" {st}/>{blush}<path d="M-.7 .7Q0 1.4.7 .7" {st}/></g>
<g id="face-cat">{eyes}{blush}<path d="M-1 .6Q-.5 1.2 0 .6Q.5 1.2 1 .6" {st}/></g>
<g id="face-sparkle"><path d="M-1.9 -1.6l.35 .8.8 .35-.8 .35-.35 .8-.35-.8-.8-.35.8-.35zM1.9 -1.6l.35 .8.8 .35-.8 .35-.35 .8-.35-.8-.8-.35.8-.35z" fill="#4b3a5a"/>{blush}<path d="M-.7 .7Q0 1.5.7 .7" {st}/></g>'''


def mascot_def():
    """A small bunny-ish blob holding a probe, drawn around (0, 0)."""
    ink = INK
    return f'''<g id="mascot" stroke="{ink}" stroke-width=".45" stroke-linejoin="round" stroke-linecap="round">
  <ellipse cx="0" cy="9.2" rx="8" ry="1.4" fill="url(#tone-ink)" stroke="none" opacity=".5"/>
  <path d="M-3.4 -5.5C-5.4 -11 -5.6 -15.6 -3.7 -16 -1.8 -16.3 -1.2 -11.5 -1.6 -6Z" fill="#fff"/>
  <path d="M-3.1 -7C-4.3 -10.8 -4.3 -13.8 -3.5 -14.1 -2.7 -14.3 -2.3 -11 -2.4 -7Z" fill="#ffc2da" stroke="none"/>
  <path d="M1.6 -6C1.9 -11.5 3.2 -15.8 5.1 -15.4 7 -15 6.1 -10.6 3.4 -5.4Z" fill="#fff"/>
  <path d="M2.4 -7C2.9 -10.6 3.9 -13.6 4.7 -13.4 5.5 -13.2 4.7 -10.2 3.2 -6.8Z" fill="#ffc2da" stroke="none"/>
  <path d="M-8 3C-8 -4 -4.5 -7.5 0 -7.5 4.5 -7.5 8 -4 8 3 8 7.5 4.5 9 0 9 -4.5 9 -8 7.5 -8 3Z" fill="#fff"/>
  <path d="M-8 3C-8 -4 -4.5 -7.5 0 -7.5 4.5 -7.5 8 -4 8 3 8 7.5 4.5 9 0 9 -4.5 9 -8 7.5 -8 3Z" fill="url(#tone-pink)" stroke="none" opacity=".35"/>
  <g transform="translate(0 0.4) scale(.95)" stroke="none"><use href="#face-happy"/></g>
  <path d="M6.5 2.5L12 -3" stroke-width=".9"/>
  <path d="M12 -3L13.6 -4.6" stroke="#ff7fb2" stroke-width=".9"/>
  <circle cx="7" cy="2.4" r="1.4" fill="#fff"/>
  <circle cx="-7" cy="3" r="1.4" fill="#fff"/>
  <path d="M-3 9.2v-1.2M3 9.2v-1.2" />
  <use href="#sparkle" transform="translate(15.5 -7) scale(.35)" fill="#ffe58f"/>
  <use href="#heart-d" transform="translate(-10 -10) scale(.3)" fill="#ff9cc2"/>
</g>'''
