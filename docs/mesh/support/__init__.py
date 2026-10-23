"""Support for the mesh notebook: the generic operations its algorithm port stands on.

These are ports of the Rust core's basic modules (vector arithmetic, a point grid, segment
buckets, polygons, closed polylines, the ChaCha20 random stream, Edmonds' matching) and the
few package pieces ``sfc.py`` imports, kept out of the notebook so that it shows the
algorithm. Each keeps the Rust code's order of operations and its tie-breaking, so that the
port's results match the core's to the last bit where nothing else intervenes.
"""
