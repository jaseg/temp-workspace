# Analysis scripts for docs/COMPARISON.md

The scripts read the full-corpus result files (`*_full.json`). Compressed copies are in `../results/`. To use them:

```sh
mkdir -p /tmp/bench && for f in docs/comparison/results/*.json.gz; do gunzip -c $f > /tmp/bench/$(basename $f .gz); done
export KICOIL_BENCH=/tmp/bench
PYTHONPATH=src:tests .venv/bin/python docs/comparison/scripts/stats.py
```

Run them from the repository root. `reject_sites.py` needs the original upstream code on PYTHONPATH (see its docstring).
`crescent_rot.py` reruns layouts; the others only read the result files.
