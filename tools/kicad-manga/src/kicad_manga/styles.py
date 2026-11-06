"""The SVG <defs>: fonts, styles, screentone patterns, faces and the mascot.

The stylesheet and the vignette mask (which covers the page) are in templates/styles/defs.svg.j2; the fixed
artwork (screentones and gradients, symbols, faces, the mascot) in static/page-*.svg."""

from markupsafe import Markup

from .characters import resistor_face_defs
from .svg import all_static_defs, render


def defs(fonts, width, height):
    return render('styles/defs.svg.j2', fonts=fonts, width=width, height=height,
                  resistor_faces=Markup(resistor_face_defs()), static=all_static_defs())
