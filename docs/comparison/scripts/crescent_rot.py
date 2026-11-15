"""cornerflat on concave_crescent_a0.9_n5k1 rotated by 0/90/270 deg, using the helpers of tests/test_cornerflat_round.py.
Run: cd /tmp/claude-0/wt/next && PYTHONPATH=src:tests .venv/bin/python docs/comparison/scripts/crescent_rot.py"""
import time, test_cornerflat_round as t
for rot in (0, 90, 270):
    spec = t._variant('concave_crescent_a0.9_n5k1', rot, (0, 0))
    t0 = time.time()
    model, rep, kinds, caught = t._check_spec(spec)
    print(f"rot {rot:3d}: kinds={sorted(kinds)} uncovered={getattr(rep,'uncovered_fraction',None)} "
          f"undershoot={getattr(rep,'undershoot',None)} warnings={len(caught)} t={time.time()-t0:.1f}s")
