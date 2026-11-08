"""Around the circuit: the stone platform it is built on, the meadow, the page border, the title block and the
decorations in the empty space. All of it is made of blocks on the schematic's grid."""


class Page:
    def __init__(self, world, builder, sch, path, cfg, pack, font):
        self.w, self.b, self.sch, self.path, self.cfg, self.pack, self.font = world, builder, sch, path, cfg, pack, font
        grass, foliage = pack.colormap('grass'), pack.colormap('foliage')
        self.tints = {'grass_block': grass, 'short_grass': grass, 'tall_grass': grass, 'fern': grass,
                      'large_fern': grass, 'oak_leaves': foliage, 'jungle_leaves': foliage,
                      'acacia_leaves': foliage, 'dark_oak_leaves': foliage, 'mangrove_leaves': foliage,
                      'vine': foliage, 'birch_leaves': (128, 167, 85), 'spruce_leaves': (97, 153, 97),
                      'lily_pad': (32, 128, 48), 'water': (63, 118, 228)}
        self.extra_tall = []
        self.platform = set()
        self.page_mm = None

    def report(self):
        st = self.b.stats
        return [f'minecraft: {st["nudged"]} parts nudged to fit, {st["unplaced"]} could not be fitted; '
                f'{st["plaques_moved"]} text plaques moved, {st["plaques_stuck"]} overlap something']

    def build(self):
        self.platform = dilate(self.w.circuit, 2)

    def floor_of(self, c):
        f = self.w.floor.get(c)
        if f:
            return f
        return 'smooth_stone' if c in self.platform else 'grass_block'

    def sky(self):
        return {'fill': '#9ec6ff'}


def dilate(cells, r):
    out = set(cells)
    for _ in range(r):
        nxt = set(out)
        for (i, j) in out:
            nxt.update(((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)))
        out = nxt
    return out
