"""How far a long layout has got: the mesh layouts report their phases and steps here, and
whoever listens (the CLI's progress bar, the web UI's) shows them.

An event is a dict: ``stage`` (the mesh's layer, as ``pcb.layout`` names it), ``phase``
(``graph``, ``relax``, ``lanes``, ``settle``, ``match``, ``done``), ``step`` and ``steps``
(the most there may be: a phase may finish early), ``done`` (the whole layout's share done,
0 to 1, over all stages), and figures of the phase (vertices, moved, apart, ...)."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Iterator

# each phase's rough share of a mesh's time (settling natively: about as long as laying)
WEIGHT = {"graph": 0.25, "relax": 0.2, "lanes": 0.05, "settle": 0.4, "match": 0.1}
_ORDER = list(WEIGHT)

_local = threading.local()


def _state() -> dict:
    if not hasattr(_local, "s"):
        _local.s = {"listener": None, "stage": "", "stages": 1, "index": 0}
    return _local.s


@contextlib.contextmanager
def listening(listener: Callable[[dict], None] | None) -> Iterator[None]:
    """Events reported in the block (on this thread) go to ``listener``."""
    s = _state()
    was = s["listener"]
    s["listener"] = listener
    try:
        yield
    finally:
        s["listener"] = was


@contextlib.contextmanager
def stage(name: str, index: int = 0, stages: int = 1) -> Iterator[None]:
    """Events reported in the block are of stage ``name``, the ``index``-th of ``stages``."""
    s = _state()
    was = (s["stage"], s["index"], s["stages"])
    s["stage"], s["index"], s["stages"] = name, index, stages
    try:
        yield
    finally:
        s["stage"], s["index"], s["stages"] = was


def report(phase: str, step: int = 1, steps: int = 1, **figures: object) -> None:
    """Phase ``phase`` has got to ``step`` of at most ``steps``."""
    s = _state()
    if s["listener"] is None:
        return
    if phase == "done":
        within = 1.0
    else:
        k = _ORDER.index(phase)
        within = sum(WEIGHT[p] for p in _ORDER[:k]) + WEIGHT[phase] * min(step / max(steps, 1), 1)
    done = (s["index"] + within) / max(s["stages"], 1)
    s["listener"](
        {
            "stage": s["stage"],
            "phase": phase,
            "step": step,
            "steps": steps,
            "done": round(done, 4),
            **figures,
        }
    )
