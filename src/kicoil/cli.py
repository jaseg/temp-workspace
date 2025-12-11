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
import os
import sys
from pathlib import Path
import warnings
import math

import click
from gerbonara.layers import LayerStack

from .geometry import PlanarInductor, divisors, CircleShape, SectorShape
from .kicad import footprint_to_board
from .svg import make_transparent_svg


def print_valid_twists(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return

    click.echo(f'Valid twist counts for {value} turns:', file=sys.stderr)
    for d in divisors(value, value):
        click.echo(f'  {d}', file=sys.stderr)

    ctx.exit()


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
@click.option('--format', type=click.Choice(['svg', 'gerber', 'kicad-footprint', 'kicad-pcb', 'show']), default='kicad-footprint')
@click.option('--clipboard/--no-clipboard', help='Use clipboard integration (requires wl-clipboard)')
@click.option('--footprint-name', help="Name for the generated footprint. Default: Output file name sans extension.")
@click.option('--layer-pair', default='F.Cu,B.Cu', help="Target KiCad layer pair for the generated footprint, comma-separated. Default: F.Cu/B.Cu.")
@click.version_option()
@click.pass_context
def cli(ctx, footprint_name, clipboard, single_layer, arc_tolerance, circle_segments, format, **kwargs):
    ctx.ensure_object(dict)

    def write(shape, outfile):
        nonlocal footprint_name, clipboard, single_layer, arc_tolerance, circle_segments, format
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
            raise click.ClickException(*e.args)
        except:
            import pdb
            pdb.post_mortem()

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
