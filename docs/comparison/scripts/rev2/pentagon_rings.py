"""Where are the original's clearance-shortfall rings on pentagon_a0.30_n13k1 (render 1)? For each orange ring in the
original's render SVG, the distance to the nearest outline vertex vs. to the nearest edge midpoint, measured along the
nearest edge as a fraction of the edge (0 = at a corner, 0.5 = mid-edge). Run from /tmp/claude-0/wt/next with
PYTHONPATH=src:tests and the venv python."""
import re, math
import corpus
S = 'docs/comparison/scripts/svg/original/pentagon_a0.30_n13k1.svg'
spec = next(c for c in corpus.corpus('full') if c['name'] == 'pentagon_a0.30_n13k1')
poly = spec['polygon']
txt = open(S).read()
rings = [(float(a), float(b)) for a, b in re.findall(r'<circle cx="([-\d.e]+)" cy="([-\d.e]+)" r="[^"]*" fill="none" stroke="orange"', txt)]
rings = sorted(set(rings))
def proj(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    L2 = (bx-ax)**2 + (by-ay)**2
    t = max(0, min(1, ((px-ax)*(bx-ax) + (py-ay)*(by-ay)) / L2))
    q = (ax + t*(bx-ax), ay + t*(by-ay))
    return math.dist(p, q), t
fr = []
for p in rings:
    # nearest edge of the outline; also try y-flipped coordinates (SVG y down)
    best = None
    for flip in (1, -1):
        pp = (p[0], flip*p[1])
        for i in range(len(poly)):
            d, t = proj(pp, poly[i], poly[(i+1) % len(poly)])
            if best is None or d < best[0]:
                best = (d, t)
    fr.append(min(best[1], 1-best[1]))
near_corner = sum(f < 0.15 for f in fr)
mid = sum(f > 0.3 for f in fr)
print(f'{len(rings)} distinct ring positions; within 15 % of edge length from a corner: {near_corner}; '
      f'in the middle 40 % of an edge: {mid}; other: {len(rings)-near_corner-mid}')
