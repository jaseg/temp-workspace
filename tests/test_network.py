import math
import random

import pytest
from factorio_poles.network import Pole, connect, islands, orientations
from factorio_poles.prototypes import BIG, MEDIUM, SMALL, SUBSTATION, wire_reach


def pole(i, t, x, y, net="VCC"):
    return Pole(id=f"p{i:02d}", net=net, type=t, position=(float(x), float(y)))


def keys(wires):
    return sorted(w.key for w in wires)


def test_reach_is_the_shorter_of_the_two():
    assert wire_reach(SMALL, BIG) == 7.5
    assert wire_reach(BIG, BIG) == 32
    assert wire_reach(MEDIUM, SUBSTATION) == 9
    assert keys(connect([pole(1, SMALL, 0, 0), pole(2, BIG, 7.5, 0)])) == [("p01", "p02")]
    assert connect([pole(1, SMALL, 0, 0), pole(2, BIG, 7.6, 0)]) == []
    assert len(connect([pole(1, BIG, 0, 0), pole(2, BIG, 32, 0)])) == 1
    assert connect([pole(1, BIG, 0, 0), pole(2, BIG, 32.1, 0)]) == []


def test_only_same_net():
    poles = [pole(1, SMALL, 0, 0, "VCC"), pole(2, SMALL, 3, 0, "GND"), pole(3, SMALL, 6, 0, "VCC")]
    assert keys(connect(poles)) == [("p01", "p03")]


def test_tree_has_no_cycles_and_spans_everything():
    poles = [pole(i, SMALL, x, y) for i, (x, y) in enumerate([(0, 0), (5, 0), (0, 5), (5, 5), (10, 0)])]
    wires = connect(poles, "tree")
    assert len(wires) == len(poles) - 1
    assert len(islands(poles, wires)["VCC"]) == 1


def test_mesh_adds_redundant_wires():
    poles = [pole(i, SMALL, x, y) for i, (x, y) in enumerate([(0, 0), (5, 0), (0, 5), (5, 5)])]
    assert len(connect(poles, "tree")) == 3
    assert len(connect(poles, "mesh")) == 6  # all pairs are within 7.5 (diagonal 7.07)


def test_max_connections():
    hub = pole(0, MEDIUM, 0, 0)
    spokes = [pole(i, MEDIUM, 5 * math.cos(i), 5 * math.sin(i)) for i in range(1, 9)]
    wires = connect([hub, *spokes], "mesh", max_connections=5)
    degree = {}
    for w in wires:
        for p in (w.a, w.b):
            degree[p.id] = degree.get(p.id, 0) + 1
    assert max(degree.values()) <= 5


def test_deterministic_regardless_of_order():
    rng = random.Random(1)
    poles = [pole(i, rng.choice([SMALL, MEDIUM]), rng.uniform(0, 40), rng.uniform(0, 40)) for i in range(40)]
    ref = keys(connect(poles))
    for _ in range(5):
        rng.shuffle(poles)
        assert keys(connect(poles)) == ref


def test_islands_largest_first():
    poles = [pole(1, SMALL, 0, 0), pole(2, SMALL, 5, 0), pole(3, SMALL, 50, 0), pole(4, SMALL, 0, 0, "GND")]
    isl = islands(poles, connect(poles))
    assert [len(g) for g in isl["VCC"]] == [2, 1]
    assert [len(g) for g in isl["GND"]] == [1]


def test_orientations_face_the_wires():
    poles = [pole(1, SMALL, 0, 0), pole(2, SMALL, 6, 0), pole(3, SMALL, 6, 6)]
    frames = orientations(poles, connect(poles))
    assert frames["p01"] == 2  # east-west wire
    assert frames["p03"] == 0  # north-south wire


def test_bad_mode():
    with pytest.raises(ValueError):
        connect([], "spaghetti")
