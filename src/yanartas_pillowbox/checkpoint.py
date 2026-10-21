"""The layout's steps timed, and (with ``YANARTAS_CHECKPOINT`` set to a directory) each step's
inputs and output written there as gzipped JSON, so that any one step can be run again on
its own from what the run before it gave it (``resume``), or a part of it cut out (see
scripts/crop_checkpoint.py), without laying out the whole board again.

A step is a function decorated with ``step(name)``. Its checkpoint is
``<dir>/<nnn>-<stage>-<name>.in.json.gz`` (its arguments) and ``….out.json.gz`` (what it
returned), numbered in the order the steps began; ``<stage>`` is the layer being laid
(``progress``'s stage). Values: numbers, strings, lists, tuples, dicts and dataclasses as JSON;
numpy arrays exactly (their float64 bytes, base64); shapely geometries as WKB (hex); numpy
random generators by their state."""

from __future__ import annotations

import base64
import contextlib
import dataclasses
import functools
import gzip
import importlib
import itertools
import json
import os
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
import shapely

from . import progress

F = TypeVar("F", bound=Callable[..., Any])

_steps: dict[str, Callable[..., Any]] = {}
_count = itertools.count()
_lock = threading.Lock()
_times: dict[tuple[str, str], list[float]] = {}  # ((stage, step) -> [seconds, calls])


def step(name: str) -> Callable[[F], F]:
    """``name``'s calls timed and, when checkpointing, their arguments and results saved."""

    def wrap(f: F) -> F:
        _steps[name] = f

        @functools.wraps(f)
        def run(*args: Any, **kwargs: Any) -> Any:
            stage = progress.current() or "-"
            where = _dir()
            path = None
            if where is not None:
                path = where / f"{next(_count):03d}-{_safe(stage)}-{name}"
                save(Path(f"{path}.in.json.gz"), {"step": name, "args": args, "kwargs": kwargs})
            t = time.perf_counter()
            out = f(*args, **kwargs)
            spent = time.perf_counter() - t
            with _lock:
                got = _times.setdefault((stage, name), [0.0, 0])
                got[0] += spent
                got[1] += 1
            if path is not None:
                save(Path(f"{path}.out.json.gz"), {"step": name, "seconds": spent, "out": out})
            return out

        return run  # type: ignore[return-value]

    return wrap


def timed_step(name: str) -> Callable[[F], F]:
    """``name``'s calls timed (not checkpointed: arguments too big or not plain values)."""

    def wrap(f: F) -> F:
        @functools.wraps(f)
        def run(*args: Any, **kwargs: Any) -> Any:
            with timed(name):
                return f(*args, **kwargs)

        return run  # type: ignore[return-value]

    return wrap


@contextlib.contextmanager
def timed(name: str) -> Iterator[None]:
    """The block timed as step ``name`` (not checkpointed)."""
    stage = progress.current() or "-"
    t = time.perf_counter()
    try:
        yield
    finally:
        spent = time.perf_counter() - t
        with _lock:
            got = _times.setdefault((stage, name), [0.0, 0])
            got[0] += spent
            got[1] += 1


def resume(path: str | Path) -> Any:
    """Run the step whose inputs ``path`` holds again (as checkpointed: the steps' modules
    imported), returning what it returns."""
    from . import partition, pcb, sfc  # noqa: F401  (the steps registered)

    d = load(path)
    return _steps[d["step"]](*d["args"], **d["kwargs"])


def times() -> dict[tuple[str, str], tuple[float, int]]:
    """Each (stage, step)'s total seconds and calls so far."""
    with _lock:
        return {k: (v[0], v[1]) for k, v in _times.items()}


def reset() -> None:
    with _lock:
        _times.clear()


def report() -> str:
    """The times as a table: each step's seconds per stage and in all (the stages run side
    by side: their sum is more than the wall-clock time)."""
    t = times()
    stages = sorted({s for s, _ in t})
    names = list(dict.fromkeys(n for _, n in t))
    rows = [["step", *stages, "all", "calls"]]
    for n in names:
        per = [t.get((s, n), (0.0, 0)) for s in stages]
        rows.append([n, *(f"{x[0]:.1f}" for x in per), f"{sum(x[0] for x in per):.1f}",
                     str(sum(x[1] for x in per))])  # fmt: skip
    width = [max(len(r[k]) for r in rows) for k in range(len(rows[0]))]
    return "\n".join(
        "  ".join(
            c.ljust(w) if k == 0 else c.rjust(w)
            for k, (c, w) in enumerate(zip(r, width, strict=True))
        )
        for r in rows
    )


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", compresslevel=3) as f:
        json.dump(_enc(value), f)


def load(path: str | Path) -> Any:
    with gzip.open(path, "rt") as f:
        return _dec(json.load(f))


def _dir() -> Path | None:
    d = os.environ.get("YANARTAS_CHECKPOINT")
    return Path(d) if d else None


def _safe(s: str) -> str:
    return "".join(c if c.isalnum() or c in "._" else "_" for c in s)


def _enc(v: Any) -> Any:
    if isinstance(v, np.ndarray):
        a = np.ascontiguousarray(v)
        return {"__nd__": base64.b64encode(a.tobytes()).decode(), "dtype": a.dtype.str,
                "shape": list(a.shape)}  # fmt: skip
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, shapely.Geometry):
        return {"__wkb__": shapely.to_wkb(v, hex=True)}
    if isinstance(v, np.random.Generator):
        return {"__rng__": _enc(v.bit_generator.state)}
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        t = type(v)
        fields = {f.name: _enc(getattr(v, f.name)) for f in dataclasses.fields(v)}
        return {"__dc__": f"{t.__module__}:{t.__qualname__}", "fields": fields}
    if isinstance(v, tuple):
        return {"__tuple__": [_enc(x) for x in v]}
    if isinstance(v, list):
        return [_enc(x) for x in v]
    if isinstance(v, dict):
        return {"__dict__": [[_enc(k), _enc(x)] for k, x in v.items()]}
    return v


def _dec(v: Any) -> Any:
    if isinstance(v, list):
        return [_dec(x) for x in v]
    if not isinstance(v, dict):
        return v
    if "__nd__" in v:
        a = np.frombuffer(base64.b64decode(v["__nd__"]), dtype=np.dtype(v["dtype"]))
        return a.reshape(v["shape"]).copy()
    if "__wkb__" in v:
        return shapely.from_wkb(v["__wkb__"])
    if "__rng__" in v:
        state = _dec(v["__rng__"])
        g = np.random.Generator(getattr(np.random, state["bit_generator"])())
        g.bit_generator.state = state
        return g
    if "__dc__" in v:
        module, name = v["__dc__"].split(":")
        return getattr(importlib.import_module(module), name)(
            **{k: _dec(x) for k, x in v["fields"].items()}
        )
    if "__tuple__" in v:
        return tuple(_dec(x) for x in v["__tuple__"])
    if "__dict__" in v:
        return {_dec(k): _dec(x) for k, x in v["__dict__"]}
    return v
