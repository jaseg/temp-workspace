"""Stand-in for rtree in the in-browser build: Pyodide has no libspatialindex.

gerbonara imports ``rtree.index`` at the top of ``gerbonara.cad.kicad.pcb`` for its trace
look-up index (``Board.rebuild_trace_index`` and the queries built on it), which the PCB
layout never uses. Using it here fails loudly instead of quietly misbehaving.
"""
