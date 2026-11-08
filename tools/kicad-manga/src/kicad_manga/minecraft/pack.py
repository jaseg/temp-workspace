"""Minecraft resource packs: textures, block models, blockstates, colormaps and bitmap fonts.

A pack is a .zip file or a folder (with `pack.mcmeta` at its top or one folder down). Several packs can be
stacked like in the game: the first one listed wins, and anything it lacks is looked up in the next ones. A
texture-only pack therefore works when it is stacked on top of a complete pack, such as the default one; when no
pack has a model at all, the simple built-in models in `builtin.py` are used.

Resource ids are written like in the game: `minecraft:block/stone`, or `block/stone` for the minecraft
namespace."""

import io
import json
import zipfile
from functools import cache
from pathlib import Path

from PIL import Image

from . import builtin


def split_id(rid, default_ns='minecraft'):
    rid = rid.lstrip('#')
    ns, _, path = rid.rpartition(':')
    return ns or default_ns, path


class _Zip:
    def __init__(self, path):
        self.zf = zipfile.ZipFile(path)
        names = self.zf.namelist()
        meta = sorted((n for n in names if n.endswith('pack.mcmeta')), key=len)
        self.prefix = meta[0][:-len('pack.mcmeta')] if meta else ''
        self.names = set(names)
        self.name = Path(path).name

    def read(self, rel):
        n = self.prefix + rel
        return self.zf.read(n) if n in self.names else None


class _Dir:
    def __init__(self, path):
        path = Path(path)
        if not (path / 'pack.mcmeta').exists():
            sub = [p.parent for p in path.glob('*/pack.mcmeta')]
            path = sub[0] if sub else path
        self.root = path
        self.name = path.name

    def read(self, rel):
        p = self.root / rel
        return p.read_bytes() if p.is_file() else None


class ResourcePack:
    def __init__(self, paths):
        if isinstance(paths, (str, Path)):
            paths = [paths]
        self.sources = [_Zip(p) if zipfile.is_zipfile(p) else _Dir(p) for p in paths]
        if not self.sources:
            raise ValueError('no resource pack given')
        self.texture = cache(self._texture)
        self.model = cache(self._model)
        self.blockstate = cache(self._blockstate)

    def __repr__(self):
        return f'ResourcePack({", ".join(s.name for s in self.sources)})'

    # -- raw files ----------------------------------------------------------
    def read(self, rel):
        for s in self.sources:
            data = s.read(rel)
            if data is not None:
                return data
        return None

    def asset(self, kind, rid, ext):
        ns, path = split_id(rid)
        return self.read(f'assets/{ns}/{kind}/{path}{ext}')

    def json(self, kind, rid):
        data = self.asset(kind, rid, '.json')
        return json.loads(data) if data is not None else None

    # -- textures -------------------------------------------------------------
    def _texture(self, rid):
        """A texture as an RGBA image; animated textures give their first frame. Missing ones are magenta and black
        like in the game."""
        data = self.asset('textures', rid, '.png')
        if data is None:
            img = Image.new('RGBA', (16, 16), (248, 0, 248, 255))
            for y in range(16):
                for x in range(16):
                    if (x < 8) != (y < 8):
                        img.putpixel((x, y), (0, 0, 0, 255))
            return img
        img = Image.open(io.BytesIO(data)).convert('RGBA')
        meta = self.asset('textures', rid, '.png.mcmeta')
        if meta is not None and img.height > img.width:
            anim = json.loads(meta).get('animation', {})
            fw = anim.get('width', img.width)
            fh = anim.get('height', fw)
            frames = anim.get('frames') or [0]
            first = frames[0]['index'] if isinstance(frames[0], dict) else frames[0]
            per_row = max(1, img.width // fw)
            fx, fy = (first % per_row) * fw, (first // per_row) * fh
            img = img.crop((fx, fy, fx + fw, fy + fh))
        return img

    def colormap(self, name, temperature=0.8, downfall=0.4):
        """The biome colour for grass or foliage from the pack's colormap (plains by default)."""
        data = self.asset('textures', f'colormap/{name}', '.png')
        if data is None:
            return {'grass': (145, 189, 89), 'foliage': (119, 171, 47)}.get(name, (128, 180, 80))
        img = Image.open(io.BytesIO(data)).convert('RGB')
        t, d = min(max(temperature, 0), 1), min(max(downfall, 0), 1) * min(max(temperature, 0), 1)
        x, y = int((1 - t) * (img.width - 1)), int((1 - d) * (img.height - 1))
        return img.getpixel((x, y))

    # -- models ---------------------------------------------------------------
    def _raw_model(self, rid):
        m = self.json('models', rid)
        if m is None:
            m = builtin.MODELS.get(split_id(rid)[1])
        if m is None and split_id(rid)[1].startswith('block/'):     # unknown block: a cube with its own texture
            m = {'parent': 'block/cube_all', 'textures': {'all': rid}}
        return m

    def _model(self, rid):
        """A block model with its parents merged: {'textures': {...}, 'elements': [...], 'ambientocclusion': ...}.
        Texture variables are resolved to texture ids where they can be."""
        chain, seen = [], set()
        cur = rid
        while cur and cur not in seen:
            seen.add(cur)
            m = self._raw_model(cur)
            if m is None:
                break
            chain.append(m)
            cur = m.get('parent')
            if cur and split_id(cur)[1].startswith('builtin/'):
                break
        textures, elements = {}, None
        for m in reversed(chain):
            textures.update(m.get('textures', {}))
            if 'elements' in m:
                elements = m['elements']

        def resolve(v, depth=0):
            if isinstance(v, dict):         # newer packs: {"sprite": ..., "force_translucent": ...}
                v = v.get('sprite')
            while isinstance(v, str) and v.startswith('#') and depth < 16:
                v = textures.get(v[1:])
                v = v.get('sprite') if isinstance(v, dict) else v
                depth += 1
            return v
        textures = {k: resolve(v) for k, v in textures.items()}
        return {'textures': textures, 'elements': elements or []}

    # -- blockstates ------------------------------------------------------------
    def _blockstate(self, name):
        bs = self.json('blockstates', name)
        if bs is None:
            bs = builtin.BLOCKSTATES.get(split_id(name)[1])
        if bs is None:      # a plain block: its model has the block's name
            bs = {'variants': {'': {'model': f'block/{split_id(name)[1]}'}}}
        return bs

    def state_models(self, name, props=None):
        """The models of a block in a state, as [(model id, x rotation, y rotation)]."""
        props = {k: str(v).lower() for k, v in (props or {}).items()}
        bs = self.blockstate(name)
        out = []
        if 'variants' in bs:
            # the variant agreeing with most given properties; properties not given match anything
            best, best_n = None, -1
            for key, v in bs['variants'].items():
                conds = dict(kv.split('=', 1) for kv in key.split(',') if '=' in kv)
                given = {k: props.get(k, _default(k)) for k in conds}
                if any(given[k] and given[k] != val for k, val in conds.items()):
                    continue
                n = sum(1 for k, val in conds.items() if given[k] == val)
                if n > best_n:
                    best, best_n = v, n
            if best is None:
                best = next(iter(bs['variants'].values()))
            out.append(_pick(best))
        for part in bs.get('multipart', []):
            if _when(part.get('when'), props):
                out.append(_pick(part['apply']))
        return [(m['model'], m.get('x', 0), m.get('y', 0)) for m in out]


def _default(key):
    return {'north': 'none', 'south': 'none', 'east': 'none', 'west': 'none', 'up': 'false',
            'down': 'false', 'waterlogged': 'false', 'powered': 'false', 'lit': 'false'}.get(key, '')


def _pick(v):
    return v[0] if isinstance(v, list) else v


def _when(cond, props):
    if cond is None:
        return True
    if 'OR' in cond:
        return any(_when(c, props) for c in cond['OR'])
    if 'AND' in cond:
        return all(_when(c, props) for c in cond['AND'])
    for k, v in cond.items():
        if props.get(k, _default(k)) not in str(v).lower().split('|'):
            return False
    return True
