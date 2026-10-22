import collections

import numpy as np
import pytest

from yanartas_pillowbox import checkpoint, rand
from yanartas_pillowbox.rand import Rand


def test_a_seed_gives_the_same_stream_and_another_another():
    a, b = Rand.of("my box", "sfc"), Rand.of("my box", "sfc")
    assert a.take(100) == b.take(100)
    assert Rand.of("my box!", "sfc").take(100) != Rand.of("my box", "sfc").take(100)
    # (text and a number with the same digits: seeds of different kinds)
    assert rand.key_of("7") != rand.key_of(7)
    assert len(rand.key_of("")) == 32 and rand.key_of(None) != rand.key_of(None)


def test_each_consumer_its_own_stream():
    """Domain separation: each label's key differs, as do a stream's bytes and the keys
    derived from the same key; a child's stream is independent of where its parent is."""
    key = rand.key_of("seed")
    labels = ["layer/F.Cu", "layer/B.Cu", "kimesh", "partition", "sfc", "sfc/relax"]
    keys = {rand.derive(key, label) for label in labels}
    assert len(keys) == len(labels) and key not in keys
    r = Rand(key.hex())
    assert r.take(32) not in keys
    assert rand.derive(key, "a") != rand.derive(key, "a\0")  # (lengths framed)
    p, q = Rand(key.hex()), Rand(key.hex())
    p.take(1000)
    assert p.child("x").take(64) == q.child("x").take(64)
    assert p.key_for("graph/0") != p.key_for("graph/1")


def test_draws_in_range_and_unbiased():
    r = Rand.of(1, "test")
    x = r.random(10000)
    assert x.shape == (10000,) and x.min() >= 0 and x.max() < 1
    assert abs(x.mean() - 0.5) < 0.02
    u = r.uniform((0.0, 10.0), (1.0, 20.0), (500, 2))
    assert u.shape == (500, 2) and (u[:, 0] < 1).all() and (u[:, 1] >= 10).all()
    assert isinstance(r.uniform(0, 1), float) and isinstance(r.random(), float)
    counts = collections.Counter(r.below(6) for _ in range(6000))
    assert set(counts) == set(range(6)) and min(counts.values()) > 850
    v = list(range(30))
    r.shuffle(v)
    assert sorted(v) == list(range(30)) and v != list(range(30))
    with pytest.raises(ValueError):
        r.below(0)


def test_a_checkpoint_keeps_the_stream_where_it_was(tmp_path):
    r = Rand.of("seed", "sfc")
    r.take(1500)
    back = checkpoint._dec(checkpoint._enc(r))
    assert back == r and back.take(64) == r.take(64)
    assert np.array_equal(back.random(5), r.random(5))
