# Test setup for the jaseg/kicoil PRs

The two PRs on github.com/jaseg/kicoil (branches `fix-base` and `cornerflat`) contain only kicoil code. The checker,
the 1008-case corpus and the regression tests that verified them are here, one copy per branch:

- `fix-base/tests`, `cornerflat/tests`: geometric checker (`geomcheck.py`), corpus (`corpus*.py`), corpus runner
  (`run_corpus.py`), result comparison (`compare_results.py`), pytest suites. `tests/README.md` describes them.
- `fix-base/docs/DEFECTS.md`, `cornerflat/docs/DEFECTS.md`: every defect found in the base layout and its fix (D1–D45).
- `results/`: full-corpus results (`run_corpus.py --kind full -j 3 --timeout 600`) of main 373f65c, fix-base and
  cornerflat, and the pytest logs of both branches.

To run them, copy the branch's `tests/` into a checkout of that PR branch:

```bash
git clone -b cornerflat https://github.com/jaseg/kicoil && cd kicoil
cp -r /path/to/pr-tests/cornerflat/tests .
# build src/kicoil/skeleton.wasm from cgal_skeleton_core (the v0.11.1 release's wasm lacks the outline error messages)
uv run --with pytest pytest tests                     # quick corpus and regression tests, ~5-9 min
uv run python tests/run_corpus.py --kind full -j 3 --out results.json --svg-dir failures/
uv run python tests/compare_results.py before=a.json after=results.json
```

| | main 373f65c | fix-base | cornerflat |
|---|---:|---:|---:|
| pass (of 1008) | 18 | 509 | 736 |

These are the results after the second review round, which removed helpers from fix-base: protrusions narrower
than one pitch are no longer cut, arms are no longer trimmed at their via, and the SVG import takes one closed path
only. `docs/DEFECTS.md` still describes the fixes of the first round, including those two. The skeleton.wasm must be
built from the branch's `cgal_skeleton_core` (it now prints 17 digits). Earlier versions of the tests and results are
in this directory's git history (0c71e60, ff8e866).
