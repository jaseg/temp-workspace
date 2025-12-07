#!/usr/bin/env python3

import warnings
import subprocess
import sys
import math
import multiprocessing
import os
from math import *
from pathlib import Path
from itertools import cycle
from contextlib import contextmanager

from scipy.constants import mu_0
import numpy as np
import click
import matplotlib as mpl

from gerbonara.cad.kicad import pcb as kicad_pcb
from gerbonara.cad.kicad import footprints as kicad_fp
from gerbonara.cad.kicad import graphical_primitives as kicad_gr
from gerbonara.cad.kicad import primitives as kicad_pr
from gerbonara.utils import Tag
from gerbonara import graphic_primitives as gp
from gerbonara import graphic_objects as go

from . import svg
from . import kicad


__version__ = '1.0.0'


def point_line_distance(p, l1, l2):
    x0, y0 = p
    x1, y1 = l1
    x2, y2 = l2
    # https://en.wikipedia.org/wiki/Distance_from_a_point_to_a_line
    return abs((x2-x1)*(y1-y0) - (x1-x0)*(y2-y1)) / sqrt((x2-x1)**2 + (y2-y1)**2)

def line_line_intersection(l1, l2):
    p1, p2 = l1
    p3, p4 = l2
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    
    # https://en.wikipedia.org/wiki/Line%E2%80%93line_intersection
    px = ((x1*y2-y1*x2)*(x3-x4)-(x1-x2)*(x3*y4-y3*x4))/((x1-x2)*(y3-y4)-(y1-y2)*(x3-x4))
    py = ((x1*y2-y1*x2)*(y3-y4)-(y1-y2)*(x3*y4-y3*x4))/((x1-x2)*(y3-y4)-(y1-y2)*(x3-x4))
    return px, py

def angle_between_vectors(va, vb):
    angle = atan2(vb[1], vb[0]) - atan2(va[1], va[0])
    if angle < 0:
        angle += 2*pi
    return angle


def traces_to_magneticalc(traces, out, pcb_thickness=0.8):
    coords = []
    last_x, last_y, last_z = None, None, None
    def coord(x, y, z):
        nonlocal coords, last_x, last_y, last_z
        if (x, y, z) != (last_x, last_y, last_z):
            coords.append((x, y, z))

    render_cache = {}
    for tr in traces:
        z = pcb_thickness if tr[1].layer == 'F.Cu' else 0
        objs = [obj
                 for elem in tr
                 for obj in elem.render(cache=render_cache)
                 if isinstance(elem, (kicad_pcb.TrackSegment, kicad_pcb.TrackArc))]

        # start / switch layer
        coord(objs[0].x1, objs[0].y1, z)

        for ob in objs:
            coord(ob.x2, ob.y2, z)

    np.savetxt(out, np.array(coords) / 10) # magneticalc expects centimeters, not millimeters.

# https://en.wikipedia.org/wiki/Farey_sequence#Next_term
def farey_sequence(n: int, descending: bool = False) -> None:
    """Print the n'th Farey sequence. Allow for either ascending or descending."""
    a, b, c, d = 0, 1, 1, n
    if descending:
        a, c = 1, n - 1
    #print(f"{a}/{b}")
    yield a, b

    while c <= n and not descending or a > 0 and descending:
        k = (n + b) // d
        a, b, c, d = c, d, k * c - a, k * d - b
        #print(f"{a}/{b}")
        yield a, b


def divisors(n, max_b=10):
    for a, b in farey_sequence(n):
        if a == n and b < max_b:
            yield b
        if b == n and a < max_b:
            yield a


def print_valid_twists(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return

    print(f'Valid twist counts for {value} turns:', file=sys.stderr)
    for d in divisors(value, value):
        print(f'  {d}', file=sys.stderr)

    click.echo()
    ctx.exit()


def arc_approximate(points, layer, tolerance=0.02, level=0):
    """ Approximate spiral arm using circular arcs. This results in a smoother output using less segments than if we
    approximate the arc using straight line segments.

    The input to this function is a list of points of a straight line segment approximation, and it returns a list of
    gerbonara arc objects approximating the input. """ 
    indent = '    ' * level
    if len(points) < 3:
        raise ValueError()

    i_mid = len(points)//2

    x0, y0 = points[0]
    x1, y1 = points[i_mid]
    x2, y2 = points[-1]

    if len(points) < 5:
        yield make_arc(x0, y0, x2, y2, x1, y1, layer)

    # https://stackoverflow.com/questions/56224824/how-do-i-find-the-circumcenter-of-the-triangle-using-python-without-external-lib
    d = 2 * (x0 * (y2 - y1) + x2 * (y1 - y0) + x1 * (y0 - y2))
    cx = ((x0 * x0 + y0 * y0) * (y2 - y1) + (x2 * x2 + y2 * y2) * (y1 - y0) + (x1 * x1 + y1 * y1) * (y0 - y2)) / d
    cy = ((x0 * x0 + y0 * y0) * (x1 - x2) + (x2 * x2 + y2 * y2) * (x0 - x1) + (x1 * x1 + y1 * y1) * (x2 - x0)) / d
    r = dist((cx, cy), (x1, y1))
    if any(abs(dist((px, py), (cx, cy)) - r) > tolerance for px, py in points):
        yield from arc_approximate(points[:i_mid+1], layer, tolerance, level+1)
        yield from arc_approximate(points[i_mid:], layer, tolerance, level+1)

    else:
        yield make_arc(x0, y0, x2, y2, x1, y1, layer)


def compute_spiral(r1, r2, a1, a2, start_frac, end_frac, fn=64):
    fn = ceil(fn * (a2-a1)/(2*pi))
    x0, y0 = cos(a1)*r1, sin(a1)*r1
    dr = 3 if r2 < r1 else -3

    xn, yn = x0, y0
    points = [(x0, y0)]
    dists = []
    for i in range(fn):
        xp, yp = xn, yn
        r = r1 + (i+1)*(r2-r1)/fn
        a = a1 + (i+1)*(a2-a1)/fn
        xn, yn = cos(a)*r, sin(a)*r
        points.append((xn, yn))
        dists.append(dist((xp, yp), (xn, yn)))

    return points, sum(dists)

@click.command()
@click.argument('outfile', required=False, type=click.Path(writable=True, dir_okay=False, path_type=Path))
@click.option('--footprint-name', help="Name for the generated footprint. Default: Output file name sans extension.")
@click.option('--layer-pair', default='F.Cu,B.Cu', help="Target KiCad layer pair for the generated footprint, comma-separated. Default: F.Cu/B.Cu.")
@click.option('--turns', type=int, default=5, help='Number of turns')
@click.option('--outer-diameter', type=float, default=50, help='Outer diameter [mm]')
@click.option('--inner-diameter', type=float, default=25, help='Inner diameter [mm]')
@click.option('--stagger-inner-vias/--no-stagger-inner-vias', default=False, help='Stagger inner via ring')
@click.option('--stagger-outer-vias/--no-stagger-outer-vias', default=False, help='Stagger outer via ring')
@click.option('--trace-width', type=float, default=None)
@click.option('--via-diameter', type=float, default=0.6)
@click.option('--two-layer/--single-layer', default=True)
@click.option('--via-drill', type=float, default=0.3)
@click.option('--via-offset', type=float, default=None, help='Radially offset vias from trace endpoints [mm]')
@click.option('--keepout-zone/--no-keepout-zone', default=True, help='Add a keepout are to the footprint (default: yes)')
@click.option('--keepout-margin', type=float, default=5, help='Margin between outside of coil and keepout area (mm, default: 5)')
@click.option('--copper-thickness', type=float, default=0.035, help='Copper thickness for resistance calculation, in mm. Default: 0.035mm ^= 1 Oz')
@click.option('--twists', type=int, default=1, help='Number of twists per revolution. Note that this number must be co-prime to the number of turns. Run with --show-twists to list valid values. (default: 1)')
@click.option('--circle-segments', type=int, default=64, help='When not using arcs, the number of points to use for arc interpolation per 360 degrees.')
@click.option('--show-twists', callback=print_valid_twists, expose_value=False, type=int, is_eager=True, help='Calculate and show valid --twists counts for the given number of turns. Takes the number of turns as a value.')
@click.option('--clearance', type=float, default=None)
@click.option('--arc-tolerance', type=float, default=0.02)
@click.option('--format', type=click.Choice(['svg', 'gerber', 'kicad-footprint', 'kicad-pcb', 'magneticalc', 'show']), default='kicad-footprint')
@click.option('--clipboard/--no-clipboard', help='Use clipboard integration (requires wl-clipboard)')
@click.option('--counter-clockwise/--clockwise', help='Direction of generated spiral. Default: clockwise when wound from the inside.')
@click.version_option()
def generate(outfile, turns, outer_diameter, inner_diameter, via_diameter, via_drill, via_offset, trace_width,
             clearance, footprint_name, layer_pair, twists, clipboard, counter_clockwise, keepout_zone, keepout_margin,
             arc_tolerance, circle_segments, copper_thickness, format, two_layer, stagger_inner_vias,
             stagger_outer_vias):

    if 'WAYLAND_DISPLAY' in os.environ:
        copy, paste, cliputil = ['wl-copy'], ['wl-paste'], 'xclip'
    else:
        copy, paste, cliputil = ['xclip', '-i', '-sel', 'clipboard'], ['xclip', '-o', '-sel' 'clipboard'], 'wl-clipboard'

    if gcd(twists, turns) != 1:
        raise click.ClickException(f'For the geometry to work out, the --twists parameter must be co-prime to --turns, i.e. the two must have 1 as their greatest common divisor. You can print valid values for --twists by running this command with --show-twists [turns number].\n\n'
                                   f'Right now, both are divisible by {gcd(twists, turns)}.\n'
                                   f'Valid twist counts for n={turns} turns are: {list(divisors(turns, max(turns, 25)))}'
                                   f'Valid turn counts for k={twists} twists are: {list(divisors(twists, max(twists, 25)))}')

    if (stagger_inner_vias or stagger_outer_vias) and twists%2 != 0:
        raise click.ClickException('For --stagger-inner/outer-vias to work, --twists must be even and --turns must be odd.')

    outer_radius = outer_diameter/2
    inner_radius = inner_diameter/2
    turns_per_layer = turns/2 if two_layer else turns

    sweeping_angle = 2*pi * turns_per_layer / twists
    spiral_pitch = (outer_radius-inner_radius) / turns_per_layer
    c1 = inner_radius
    c2 = inner_radius + spiral_pitch
    alpha1 = atan((outer_radius - inner_radius) / sweeping_angle / c1)
    alpha2 = atan((outer_radius - inner_radius) / sweeping_angle / c2)
    alpha = (alpha1+alpha2)/2
    projected_spiral_pitch = spiral_pitch*cos(alpha)

    if trace_width is None and clearance is None:
        trace_width = 0.15
        print(f'Warning: Defaulting to {trace_width:.2f} mm trace width.', file=sys.stderr)

    if trace_width is None:
        if round(clearance, 3) > round(projected_spiral_pitch, 3):
            raise click.ClickException(f'Error: Given clearance of {clearance:.2f} mm is larger than the projected spiral pitch of {projected_spiral_pitch:.2f} mm. Reduce clearance or increase the size of the coil.')
        trace_width = projected_spiral_pitch - clearance
        print(f'Calculated trace width for {clearance:.2f} mm clearance is {trace_width:.2f} mm.', file=sys.stderr)

    elif clearance is None:
        if round(trace_width, 2) > round(projected_spiral_pitch, 2):
            raise click.ClickException(f'Error: Given trace width of {trace_width:.2f} mm is larger than the projected spiral pitch of {projected_spiral_pitch:.2f} mm. Reduce clearance or increase the size of the coil.')
        clearance = projected_spiral_pitch - trace_width
        print(f'Calculated clearance for {trace_width:.2f} mm trace width is {clearance:.2f} mm.', file=sys.stderr)

    else:
        if round(trace_width, 2) > round(projected_spiral_pitch, 2):
            raise click.ClickException(f'Error: Given trace width of {trace_width:.2f} mm is larger than the projected spiral pitch of {projected_spiral_pitch:.2f} mm. Reduce clearance or increase the size of the coil.')
        clearance_actual = projected_spiral_pitch - trace_width
        if round(clearance_actual, 3) < round(clearance, 3):
            raise click.ClickException(f'Error: Actual clearance for {trace_width:.2f} mm trace is {clearance_actual:.2f} mm, which is lower than the given clearance of {clearance:.2f} mm.')

    if round(via_diameter, 2) < round(trace_width, 2):
        print(f'Clipping via diameter from {via_diameter:.2f} mm to trace width of {trace_width:.2f} mm.', file=sys.stderr)
        via_diameter = trace_width

    if via_offset is None:
        via_offset = max(0, (via_diameter-trace_width)/2)
        print(f'Autocalculated via offset {via_offset:.2f} mm', file=sys.stderr)

    inner_via_ring_radius = inner_radius - via_offset
    #print(f'{inner_radius=} {via_offset=} {via_diameter=}', file=sys.stderr)
    inner_via_angle = 2*asin((via_diameter + clearance)/2 / inner_via_ring_radius)

    outer_via_ring_radius = outer_radius + via_offset
    outer_via_angle = 2*asin((via_diameter + clearance)/2 / outer_via_ring_radius)

    print(f'Inner via ring @r={inner_via_ring_radius:.2f} mm (from {inner_radius:.2f} mm)', file=sys.stderr)
    print(f'    {degrees(inner_via_angle):.1f} deg / via', file=sys.stderr)
    print(f'Outer via ring @r={outer_via_ring_radius:.2f} mm (from {outer_radius:.2f} mm)', file=sys.stderr)
    print(f'    {degrees(outer_via_angle):.1f} deg / via', file=sys.stderr)

    # Check if the vias of the inner ring are so large that they would overlap
    if inner_via_angle*twists > (4*pi if stagger_inner_vias else 2*pi):
        min_dia = 2*((via_diameter + clearance) / (2*sin(pi / twists * (2 if stagger_inner_vias else 1))) + via_offset)
        warnings.warn(f'Overlapping vias in inner via ring. Calculated minimum inner diameter is {min_dia:.2f} mm.')

    pitch = clearance + trace_width
    t, _, b = layer_pair.partition(',')
    layer_pair = (t.strip(), b.strip())
    rainbow = '#817 #a35 #c66 #e94 #ed0 #9d5 #4d8 #2cb #0bc #09c #36b #639'.split()
    rainbow = rainbow[2::3] + rainbow[1::3] + rainbow[0::3]
    n = 5
    rainbow = rainbow[n:] + rainbow[:n]
    out_paths = []
    svg_stuff = [*out_paths]

    # For fill factor & inductance formulas, See https://coil32.net/pcb-coil.html for details
    d_avg = (outer_diameter + inner_diameter)/2
    phi = (outer_diameter - inner_diameter) / (outer_diameter + inner_diameter)
    c1, c2, c3, c4 = 1.00, 2.46, 0.00, 0.20
    L = mu_0 * turns**2 * d_avg*1e3 * c1 / 2 * (log(c2/phi) + c3*phi + c4*phi**2)
    print(f'Outer diameter: {outer_diameter:g} mm', file=sys.stderr)
    print(f'Average diameter: {d_avg:g} mm', file=sys.stderr)
    print(f'Inner diameter: {inner_diameter:g} mm', file=sys.stderr)
    print(f'Fill factor: {phi:g}', file=sys.stderr)
    print(f'Approximate inductance: {L:g} µH', file=sys.stderr)

    pads = []
    lines = []
    arcs = []

    sector_angle = 2*pi / twists
    total_angle = twists*2*sweeping_angle if two_layer else twists*sweeping_angle

    inverse = {}
    for i in range(twists):
        inverse[i*turns%twists] = i

    layer_sections = []
    for i in range(twists):
        start_angle = i*sector_angle
        fold_angle = start_angle + sweeping_angle
        end_angle = fold_angle + sweeping_angle

        x = inverse[i]*floor(2*sweeping_angle / (2*pi)) * 2*pi
        points_layer0, arm_length = compute_spiral(outer_radius, inner_radius, start_angle, fold_angle, (x + start_angle)/total_angle, (x + fold_angle)/total_angle, circle_segments)
        x0, y0 = points_layer0[0]
        xn, yn = points_layer0[-1]

        if two_layer:
            points_layer1, _ = compute_spiral(inner_radius, outer_radius, fold_angle, end_angle, (x + fold_angle)/total_angle, (x + end_angle)/total_angle, circle_segments)

        else:
            # Add a straight connecting segment connecting the inner point to the outside of the spiral.
            dr = outer_radius - inner_radius
            xq = xn + cos(fold_angle) * dr
            yq = yn - sin(fold_angle) * dr
            points_layer1 = [(xn, yn), (xq, yq)]

        #r, g, b, _a = mpl.cm.plasma(start_frac + (end_frac - start_frac)/fn * (i + 0.5))
        #path = SVGPath(fill='none', stroke=f'#{round(r*255):02x}{round(g*255):02x}{round(b*255):02x}', stroke_width=trace_width, stroke_linejoin='round', stroke_linecap='round')
        #svg_stuff.append(path)
        #path.move(xp, yp)
        #path.line(xn, yn)
#        lines.append(make_line(xp, yp, xn, yn, layer_pair[layer]))
#    if use_arcs:
#        arcs.extend(arc_approximate(points, layer_pair[layer], arc_tolerance))
        #svg_vias.append(Tag('circle', cx=xv, cy=yv, r=via_diameter/2, stroke='none', fill='white'))
        #svg_vias.append(Tag('circle', cx=xv, cy=yv, r=via_drill/2, stroke='none', fill='black'))
        #pads.append(make_via(xv, yv, layer_pair))

        r = inner_via_ring_radius
        if stagger_inner_vias:
            if i%2 != 0:
                r -= 2*via_offset
        xv, yv = r*cos(fold_angle), r*sin(fold_angle)
        if not isclose(via_offset, 0, abs_tol=1e-6):
            points_layer0.append([xv, yv])
            points_layer1.insert(0, [xv, yv])

        if i > 0:
            r = outer_via_ring_radius
            if stagger_outer_vias:
                if i%2 != 0:
                    r += 2*via_offset
            xv, yv = r*cos(start_angle), r*sin(start_angle)
            if not isclose(via_offset, 0, abs_tol=1e-6):
                points_layer0.insert(0, [xv, yv])
                points_layer1.insert(0, [xv, yv])
                lines.append(make_line(x0, y0, xv, yv, layer_pair[0]))
                lines.append(make_line(x0, y0, xv, yv, layer_pair[1]))
            svg_vias.append(Tag('circle', cx=xv, cy=yv, r=via_diameter/2, stroke='none', fill='white'))
            svg_vias.append(Tag('circle', cx=xv, cy=yv, r=via_drill/2, stroke='none', fill='black'))

    l_total = arm_length*twists*(2 if two_layer else 1)
    print(f'Approximate track length: {l_total:.2f} mm', file=sys.stderr)
    A = copper_thickness/1e3 * trace_width/1e3
    rho = 1.68e-8
    R = l_total/1e3 * rho / A
    print(f'Approximate resistance: {R:g} Ω', file=sys.stderr)

    top_pad = make_pad(1, [layer_pair[0]], outer_radius, 0)
    pads.append(top_pad)
    bottom_pad = make_pad(2, [layer_pair[1]], outer_radius, 0)
    pads.append(bottom_pad)

    svg_stuff += svg_vias

    svg_stuff.append(Tag('path', d=f'M {inner_radius} 0 L {outer_radius} 0', stroke=rainbow[n+1], fill='none',
                         stroke_width='0.05mm', stroke_linecap='round'))
    ntraces = int(turns_per_layer)+1
    alpha = [0] * ntraces
    for i in range(ntraces):
        c = inner_radius + (outer_radius-inner_radius) / turns_per_layer * i
        #dalpha = dy / c
        #dx / dalpha = (outer_radius - inner_radius) / sweeping_angle
        #c * (dx / dy) = (outer_radius - inner_radius) / sweeping_angle
        #dx / dy = (outer_radius - inner_radius) / sweeping_angle / c
        dx = (outer_radius - inner_radius) / sweeping_angle / c
        alpha[i] = atan(dx)
        dy = 0.3
        dx *= dy
        r = trace_width/2 / cos(alpha[i])
        svg_stuff.append(Tag('path', d=f'M {c-r+dx} {-dy} L {c-r-dx} {dy}', stroke=rainbow[n+1], fill='none',
                             stroke_width='0.05mm', stroke_linecap='round'))
        svg_stuff.append(Tag('path', d=f'M {c+r+dx} {-dy} L {c+r-dx} {dy}', stroke=rainbow[n+1], fill='none',
                             stroke_width='0.05mm', stroke_linecap='round'))

        #print(f'spiral angle {degrees(alpha[i]):.2f}', file=sys.stderr)

    for i, (a1, a2) in enumerate(zip(alpha[::-1], alpha[1::])):
        amean = (a2+a1)/2
        pitch = (outer_radius - inner_radius) / turns_per_layer
        clearance = pitch - trace_width
        clearance *= cos(amean)

        x, y = inner_radius + (i + 1/2)*pitch, -0.5
        svg_stuff.append(Tag('text',
                             [f'{clearance:.5f}mm'],
                             x=x,
                             y=y,
                             text_anchor='start',
                             transform=f'rotate(-45 {x} {y})',
                             style=f'font: 1px bold sans-serif; fill: {rainbow[n+1]}'))

    if svg_out:
        svg_file(svg_out, svg_stuff, 100, 100, -50, -50)

    if footprint_name:
        name = footprint_name
    elif outfile:
        name = outfile.stem,
    else:
        name = 'generated_coil'

    if keepout_zone:
        r = outer_diameter/2 + keepout_margin
        tol = 0.05 # mm
        n = ceil(pi / acos(1 - tol/r))
        pts = [(r*cos(a*2*pi/n), r*sin(a*2*pi/n)) for a in range(n)]
        zones = [kicad_pr.Zone(layers=['*.Cu'],
            hatch=kicad_pr.Hatch(),
            filled_areas_thickness=False,
            keepout=kicad_pr.ZoneKeepout(copperpour_allowed=False),
            polygon=kicad_pr.ZonePolygon(pts=[kicad_pr.XYCoord(x=x, y=y) for x, y in pts]))]
    else:
        zones = []

    if pcb:
        obj = kicad_pcb.Board.empty_board(
                zones=zones,
                track_segments=[kicad_pcb.TrackSegment.from_footprint_line(line) for line in lines],
                vias=[kicad_pcb.Via.from_pad(pad) for pad in pads if pad.type == kicad_pcb.Atom.thru_hole])
        obj.rebuild_trace_index()
        seg = obj.track_segments[-1]
        traces = []
        end = top_pad
        layer = 'F.Cu'
        while True:
            tr = list(obj.find_connected_traces(end, layers=[layer]))
            traces.append(tr)
            if not isinstance(tr[-1], kicad_pcb.Via):
                break
            layer = 'B.Cu' if layer == 'F.Cu' else 'F.Cu'
            end = tr[-1]
        # remove start pad
        traces[0] = traces[0][1:]

        r = outer_diameter/2 + 20

        if magneticalc_out:
            traces_to_magneticalc(traces, magneticalc_out)

    else:
        obj = kicad_fp.Footprint(
                name=name,
                generator=kicad_fp.Atom('GerbonaraTwistedCoilGenV1'),
                layer='F.Cu',
                descr=f"{turns} turn {outer_diameter:.2f} mm diameter twisted coil footprint, inductance approximately {L:.6f} µH. Generated by gerbonara'c Twisted Coil generator, version {__version__}.",
                clearance=clearance,
                zone_connect=0,
                lines=lines,
                arcs=arcs,
                pads=pads,
                zones=zones,
                )

    if clipboard:
        try:
            data = obj.serialize()
            print(f'Running {copy[0]}.', file=sys.stderr)
            proc = subprocess.Popen(copy, stdin=subprocess.PIPE, text=True)
            proc.communicate(data)
            print('passed to wl-clip:', data)
        except FileNotFoundError:
            print(f'Error: --clipboard requires the {copy[0]} and {paste[0]} utilities from {cliputil} to be installed.', file=sys.stderr)
    elif not outfile:
        print(obj.serialize())
    else:
        obj.write(outfile)

if __name__ == '__main__':
    generate()
