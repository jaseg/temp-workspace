"""Fallback block models, used only when none of the resource packs has a model (texture-only packs that are not
stacked on a complete pack). They are simple cuboids written for this tool, enough to draw every block it uses:
the textures still come from the packs."""


def _box(fr, to, tex, faces=('down', 'up', 'north', 'south', 'west', 'east'), tint=None):
    f = {d: {'texture': tex.get(d, tex.get('side', tex.get('all'))) if isinstance(tex, dict) else tex} for d in faces}
    if tint is not None:
        for v in f.values():
            v['tintindex'] = tint
    return {'from': list(fr), 'to': list(to), 'faces': f}


def _torch(x, z, h, tex):
    return _box((x, 2, z), (x + 2, 2 + h, z + 2), tex)


MODELS = {
    'block/cube': {'elements': [_box((0, 0, 0), (16, 16, 16), {'down': '#down', 'up': '#up', 'north': '#north',
                                                               'south': '#south', 'west': '#west', 'east': '#east'})]},
    'block/cube_all': {'parent': 'block/cube', 'textures': {d: '#all' for d in
                                                           ('down', 'up', 'north', 'south', 'west', 'east')}},
    'block/cube_column': {'parent': 'block/cube', 'textures': {'down': '#end', 'up': '#end', 'north': '#side',
                                                               'south': '#side', 'west': '#side', 'east': '#side'}},
    'block/cube_bottom_top': {'parent': 'block/cube', 'textures': {'down': '#bottom', 'up': '#top', 'north': '#side',
                                                                   'south': '#side', 'west': '#side',
                                                                   'east': '#side'}},
    'block/slab': {'elements': [_box((0, 0, 0), (16, 8, 16), {'down': '#bottom', 'up': '#top', 'side': '#side'})]},
    'block/cross': {'elements': [
        {'from': [0.8, 0, 8], 'to': [15.2, 16, 8], 'rotation': {'origin': [8, 8, 8], 'axis': 'y', 'angle': 45},
         'shade': False, 'faces': {'north': {'texture': '#cross'}, 'south': {'texture': '#cross'}}},
        {'from': [8, 0, 0.8], 'to': [8, 16, 15.2], 'rotation': {'origin': [8, 8, 8], 'axis': 'y', 'angle': 45},
         'shade': False, 'faces': {'west': {'texture': '#cross'}, 'east': {'texture': '#cross'}}}]},
    'block/pressure_plate_up': {'elements': [_box((1, 0, 1), (15, 1, 15), '#texture')]},
    'block/carpet': {'elements': [_box((0, 0, 0), (16, 1, 16), '#wool')]},
    'block/repeater': {'textures': {'slab': 'block/smooth_stone', 'top': 'block/repeater',
                                    'torch': 'block/redstone_torch_off'},
                       'elements': [_box((0, 0, 0), (16, 2, 16), {'up': '#top', 'side': '#slab', 'down': '#slab'}),
                                    _torch(7, 2, 5, '#torch'), _torch(7, 8, 5, '#torch')]},
    'block/repeater_on': {'parent': 'block/repeater', 'textures': {'top': 'block/repeater_on',
                                                                   'torch': 'block/redstone_torch'}},
    'block/comparator': {'textures': {'slab': 'block/smooth_stone', 'top': 'block/comparator',
                                      'torch': 'block/redstone_torch_off'},
                         'elements': [_box((0, 0, 0), (16, 2, 16), {'up': '#top', 'side': '#slab', 'down': '#slab'}),
                                      _torch(4, 11, 5, '#torch'), _torch(10, 11, 5, '#torch'),
                                      _torch(7, 2, 3, '#torch')]},
    'block/comparator_subtract': {'parent': 'block/comparator', 'textures': {'top': 'block/comparator_on'}},
    'block/redstone_dust_dot': {'elements': [_box((5, .25, 5), (11, .25, 11), {'up': 'block/redstone_dust_dot'},
                                                  faces=('up',), tint=0)]},
    'block/redstone_dust_side0': {'elements': [_box((7, .25, 0), (9, .25, 8), {'up': 'block/redstone_dust_dot'},
                                                    faces=('up',), tint=0)]},
    'block/redstone_torch': {'elements': [_box((7, 0, 7), (9, 10, 9), 'block/redstone_torch')]},
    'block/hopper': {'elements': [_box((0, 10, 0), (16, 16, 16), {'up': 'block/hopper_inside',
                                                                  'side': 'block/hopper_outside'}),
                                  _box((4, 4, 4), (12, 10, 12), 'block/hopper_outside')]},
}

BLOCKSTATES = {
    'repeater': {'variants': {f'facing={f},powered={p}': {'model': 'block/repeater' + ('_on' if p == 'true' else ''),
                                                           'y': y}
                              for f, y in (('south', 0), ('west', 90), ('north', 180), ('east', 270))
                              for p in ('false', 'true')}},
    'comparator': {'variants': {f'facing={f},mode={m}': {'model': 'block/comparator' + ('_subtract' if m == 'subtract'
                                                                                         else ''), 'y': y}
                                for f, y in (('south', 0), ('west', 90), ('north', 180), ('east', 270))
                                for m in ('compare', 'subtract')}},
    'redstone_wire': {'multipart': [{'apply': {'model': 'block/redstone_dust_dot'}},
                                    {'when': {'north': 'side|up'}, 'apply': {'model': 'block/redstone_dust_side0'}},
                                    {'when': {'east': 'side|up'}, 'apply': {'model': 'block/redstone_dust_side0',
                                                                            'y': 90}},
                                    {'when': {'south': 'side|up'}, 'apply': {'model': 'block/redstone_dust_side0',
                                                                             'y': 180}},
                                    {'when': {'west': 'side|up'}, 'apply': {'model': 'block/redstone_dust_side0',
                                                                            'y': 270}}]},
}
