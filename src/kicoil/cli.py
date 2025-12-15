# Copyright 2025 Jan Sebastian Götte <code@jaseg.de>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging
import subprocess
import webbrowser
import tempfile
import json
import os
import sys
from pathlib import Path
from collections import defaultdict
import warnings
import math

import click
from gerbonara.layers import LayerStack
from gerbonara.cad.kicad.primitives import kicad_mid_to_center_arc

from .geometry import PlanarInductor, divisors, CircleShape, SectorShape, StarShape, SVGShape, RectangleShape, RegularPolygonShape
from .kicad import footprint_to_board
from .svg import make_transparent_svg


def print_valid_twists(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return

    click.echo(f'Valid twist counts for {value} turns:', file=sys.stderr)
    for d in divisors(value, value):
        click.echo(f'  {d}', file=sys.stderr)

    ctx.exit()


def circle_center_to_tangents(center, a, b):
    """ Given two points on a circle and the center of the circle, calculate the intersection of two tangents at the two points """
    cx, cy = center
    ax, ay = a
    bx, by = b

    dax = ax - cx
    day = ay - cy
    dbx = bx - cx
    dby = by - cy

    v = dax*ax + day*ay
    w = dbx*bx + dby*by
    det = dax*dby - day*dbx

    ix = (v*dby - day*w) / det
    iy = (dax*w - v*dbx) / det

    return ix, iy


@click.group()
@click.option('--turns', type=int, default=5, help='Number of turns')
@click.option('--twists', type=int, default=1, help='Number of twists per revolution. Note that this number must be co-prime to the number of turns. Run with --show-twists to list valid values. (default: 1)')
@click.option('--clockwise/--counter-clockwise', help='Direction of generated top layer spiral. Default: counter-clockwise when wound from the inside.')
@click.option('--single-layer/--two-layer', help='Single-layer mode. This just forces twists to 0.')
@click.option('--show-twists', callback=print_valid_twists, expose_value=False, type=int, is_eager=True, help='Calculate and show valid --twists counts for the given number of turns. Takes the number of turns as a value.')
@click.option('--stagger-inner-vias/--no-stagger-inner-vias', default=False, help='Stagger inner via ring')
@click.option('--stagger-outer-vias/--no-stagger-outer-vias', default=False, help='Stagger outer via ring')
@click.option('--trace-width', type=float, default=None)
@click.option('--clearance', type=float, default=None)
@click.option('--via-diameter', type=float, default=0.6)
@click.option('--via-drill', type=float, default=None)
@click.option('--via-offset', type=float, default=None, help='Radially offset vias from trace endpoints [mm]')
@click.option('--keepout-zone/--no-keepout-zone', default=True, help='Add a keepout are to the footprint (default: yes)')
@click.option('--keepout-margin', type=float, default=5, help='Margin between outside of coil and keepout area (mm, default: 5)')
@click.option('--copper-thickness', type=float, default=0.035, help='Copper thickness for resistance calculation, in mm. Default: 0.035mm ^= 1 Oz')
@click.option('--circle-segments', type=int, default=64, help='When not using arcs, the number of points to use for arc interpolation per 360 degrees.')
@click.option('--arc-tolerance', type=float, default=0.02)
@click.option('--approximate-arcs/--no-approximate-arcs', default=True, help='Use circular arcs to smoothen output shape (default: on)')
@click.option('--format', type=click.Choice(['svg', 'gerber', 'kicad-footprint', 'kicad-pcb', 'json', 'gdsii', 'oasis', 'show']), default='kicad-footprint')
@click.option('--clipboard/--no-clipboard', help='Use clipboard integration (requires wl-clipboard)')
@click.option('--footprint-name', help="Name for the generated footprint. Default: Output file name sans extension.")
@click.option('--cell-name', help="Name for the generated cell when exporting GDSII. Default: Output file name sans extension.")
@click.option('--layer-pair', default='F.Cu,B.Cu', help="Target KiCad layer pair for the generated footprint, comma-separated. Default: F.Cu/B.Cu.")
@click.version_option()
@click.pass_context
def cli(ctx, footprint_name, cell_name, clipboard, single_layer, arc_tolerance, circle_segments, format, **kwargs):
    ctx.ensure_object(dict)
    logger = logging.getLogger('kicoil')
    logger.setLevel(logging.INFO)

    def write(shape, outfile):
        nonlocal footprint_name, clipboard, single_layer, arc_tolerance, circle_segments, format, cell_name
        logger = logging.getLogger('kicoil')

        if single_layer:
            kwargs['layers'] = 1
        else:
            kwargs['layers'] = 2

        try:
            model = PlanarInductor(shape=shape, **kwargs)

            if footprint_name is None and outfile:
                footprint_name = outfile.stem

            footprint = model.render_footprint(footprint_name, arc_tolerance, circle_segments)

        except ValueError as e:
            #raise click.ClickException(*e.args)
            raise

        data = None
        if format == 'kicad-footprint':
            data = footprint.serialize()

        elif format == 'kicad-pcb':
            data = footprint_to_board(footprint).serialize()

        elif format == 'gerber':
            stack = LayerStack()
            footprint.render(stack)

            if not clipboard and outfile and outfile.suffix.lower() != '.zip':
                stack.save_to_directory(outfile)
                return

            else:
                with tempfile.NamedTemporaryFile(delete_on_close=False) as f:
                    f = Path(f.name)
                    stack.save_to_zipfile(f)
                    data = f.read_bytes()
        
        elif format == 'json':
            lines = defaultdict(lambda: [])
            for l in footprint.lines:
                lines[l.layer].append({
                    'x1': l.start.x,
                    'y1': l.start.y,
                    'x2': l.end.x,
                    'y2': l.end.y})
            
            arcs = defaultdict(lambda: [])
            for a in footprint.arcs:
                center, r, direction = kicad_mid_to_center_arc(a.mid, a.start, a.end)
                arcs[a.layer].append({
                    'x1': a.start.x,
                    'y1': a.start.y,
                    'x2': a.end.x,
                    'y2': a.end.y,
                    'cx': center[0],
                    'cy': center[1],
                })

            vias = [{
                    'x': p.at.x,
                    'y': p.at.y,
                    'pad': p.size.x,
                    'drill': p.drill.diameter,
                } for p in footprint.pads if p.number == 'NC']
            
            pads = [{
                    'x': p.at.x,
                    'y': p.at.y,
                    'pad': p.size.x,
                } for p in footprint.pads if p.number != 'NC']
            
            d = {
                'lines': dict(lines),
                'arcs': dict(arcs),
                'vias': vias,
                'pads': pads
            }

            data = json.dumps(d, indent=4)

        elif format in ('gdsii', 'oasis'):
            import gdstk

            DRILL_LAYER = 2
            lib = gdstk.Library()

            if cell_name is None:
                if outfile:
                    cell_name = outfile.stem
                else:
                    cell_name = f'planar_coil'
            cell = lib.new_cell(cell_name)
            
            for line in footprint.lines:
                layer = model.layer_pair.index(line.layer)
                path = gdstk.FlexPath([(line.start.x, line.start.y), (line.end.x, line.end.y)], line.stroke.width, ends=['round'], layer=layer)
                cell.add(path)
            
            for arc in footprint.arcs:
                layer = model.layer_pair.index(arc.layer)
                center, r, _direction = kicad_mid_to_center_arc(arc.mid, arc.start, arc.end)
                proj_x, proj_y = circle_center_to_tangents(center, tuple(arc.start), tuple(arc.end))
                # multiply r with 0.99 to make sure gdstk's interpolation routine catches on since the arc endpoints are calculated exactly
                path = gdstk.FlexPath([(arc.start.x, arc.start.y), (proj_x, proj_y), (arc.end.x, arc.end.y)], arc.stroke.width, bend_radius=r*0.99, ends=['round'], layer=layer)
                cell.add(path)

            for pad in footprint.pads:
                for layer in pad.layers:
                    layer = model.layer_pair.index(layer)
                    layer_obj = gdstk.ellipse(tuple(pad.at), pad.size.x/2, layer=layer)
                    cell.add(layer_obj)
                
                if pad.drill:
                    drill = gdstk.ellipse(tuple(pad.at), pad.drill.diameter/2, layer=DRILL_LAYER)
                    cell.add(drill)

            if clipboard or not outfile:
                raise click.ClickException('outfile is required for GDSII or OASIS export')

            if format == 'gdsii':
                lib.write_gds(outfile)
            else:
                lib.write_oas(outfile)
            return

        elif format in ('svg', 'show'):
            data = str(make_transparent_svg(footprint))

            if format == 'show':
                with tempfile.NamedTemporaryFile('w', suffix='.svg', delete=False) as f:
                    f.write(data)
                    f.flush()
                    webbrowser.open_new_tab(f'file://{f.name}')
                    return

        if clipboard:
            if 'WAYLAND_DISPLAY' in os.environ:
                copy, paste, cliputil = ['wl-copy'], ['wl-paste'], 'xclip'
            else:
                copy, paste, cliputil = ['xclip', '-i', '-sel', 'clipboard'], ['xclip', '-o', '-sel' 'clipboard'], 'wl-clipboard'

            try:
                logger.info(f'Running {copy[0]}.', file=sys.stderr)
                proc = subprocess.Popen(copy, stdin=subprocess.PIPE, text=isinstance(data, str))
                proc.communicate(data)

            except FileNotFoundError:
                raise click.ClickException(f'Error: --clipboard requires the {copy[0]} and {paste[0]} utilities from {cliputil} to be installed.', file=sys.stderr)

        elif not outfile:
            if isinstance(data, str):
                print(data)
            else:
                sys.stdout.buffer.write(data)

        else:
            outfile.write_text(data)
        
    ctx.obj['write'] = write

@cli.command()
@click.option('--outer-diameter', type=float, default=50, help='Outer diameter [mm]')
@click.option('--inner-diameter', type=float, default=25, help='Inner diameter [mm]')
@click.argument('outfile', required=False, type=click.Path(writable=True, dir_okay=False, path_type=Path))
@click.pass_context
def circle(ctx, inner_diameter, outer_diameter, outfile):
    shape = CircleShape(outer_diameter, inner_diameter)
    ctx.obj['write'](shape, outfile)

@cli.command()
@click.option('--width', type=float, default=50, help='Base width [mm]')
@click.option('--height', type=float, default=40, help='Shape height [mm]')
@click.option('--offset', type=float, default=10, help='Offset of each corner at the shorter edge compared to the longer edge [mm]')
@click.option('--annular-width', type=float, default=10, help='Width of the trace area on the outside of the shape [mm]')
@click.argument('outfile', required=False, type=click.Path(writable=True, dir_okay=False, path_type=Path))
@click.pass_context
def trapezoid(ctx, outfile, **kwargs):
    shape = TrapezoidShape(**kwargs)
    ctx.obj['write'](shape, outfile)


@cli.command()
@click.option('--width', type=float, default=50, help='Width [mm]')
@click.option('--height', type=float, default=40, help='Height [mm]')
@click.option('--annular-width', type=float, default=10, help='Width of the trace area on the outside of the shape [mm]')
@click.argument('outfile', required=False, type=click.Path(writable=True, dir_okay=False, path_type=Path))
@click.pass_context
def rectangle(ctx, outfile, **kwargs):
    shape = RectangleShape(**kwargs)
    ctx.obj['write'](shape, outfile)


@cli.command()
@click.option('--diameter', type=float, default=50, help='Width [mm]')
@click.option('-n', '--corners', type=int, default=8, help='Number of corners')
@click.option('--annular-width', type=float, default=10, help='Width of the trace area on the outside of the shape [mm]')
@click.argument('outfile', required=False, type=click.Path(writable=True, dir_okay=False, path_type=Path))
@click.pass_context
def regular_polygon(ctx, outfile, **kwargs):
    shape = RegularPolygonShape(**kwargs)
    ctx.obj['write'](shape, outfile)


@cli.command()
@click.option('--inner-diameter', type=float, default=25, help='Inner diameter [mm]')
@click.option('--outer-diameter', type=float, default=50, help='Outer diameter [mm]')
@click.option('--angle', type=float, default=45, help='Sector angle [deg]')
@click.option('--arc-tolerance', type=float, default=0.05, help='Tolerance for splitting arc into straight segments [mm] (default: 0.05 mm)')
@click.option('--annular-width', type=float, default=5, help='Width of the trace area on the outside of the shape [mm]')
@click.argument('outfile', required=False, type=click.Path(writable=True, dir_okay=False, path_type=Path))
@click.pass_context
def sector(ctx, outfile, angle, **kwargs):
    angle = math.radians(angle)
    shape = SectorShape(angle=angle, **kwargs)
    ctx.obj['write'](shape, outfile)


@cli.command()
@click.option('--inner-diameter', type=float, default=25, help='Inner diameter [mm]')
@click.option('--outer-diameter', type=float, default=50, help='Outer diameter [mm]')
@click.option('--points', type=int, default=5, help='Number of points')
@click.option('--arc-tolerance', type=float, default=0.05, help='Tolerance for splitting arc into straight segments [mm] (default: 0.05 mm)')
@click.option('--annular-width', type=float, default=5, help='Width of the trace area on the outside of the shape [mm]')
@click.argument('outfile', required=False, type=click.Path(writable=True, dir_okay=False, path_type=Path))
@click.pass_context
def star(ctx, outfile, **kwargs):
    shape = StarShape(**kwargs)
    ctx.obj['write'](shape, outfile)


@cli.command()
@click.option('--arc-tolerance', type=float, default=0.05, help='Tolerance for splitting arc into straight segments [mm] (default: 0.05 mm)')
@click.option('--annular-width', type=float, default=5, help='Width of the trace area on the outside of the shape [mm]')
@click.argument('svg_file', required=False, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument('outfile', required=False, type=click.Path(writable=True, dir_okay=False, path_type=Path))
@click.pass_context
def svg(ctx, svg_file, outfile, **kwargs):
    shape = SVGShape(svg_file, **kwargs)
    ctx.obj['write'](shape, outfile)
