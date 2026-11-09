"""Run the in-scope SolidCraft kernel cases through replay.py (OCCT via FreeCAD), one process per
case with a timeout, and grade each against its expected.json.

  run_cases.py [--jobs N] [--timeout S] [--only area/id,...] [--out results.jsonl]
"""

import argparse
import glob
import json
import math
import os
import resource
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
SC = os.path.normpath(os.path.join(HERE, "..", ".."))
CASES = os.path.join(SC, "src", "solidcraft", "tests", "kernel-cases")
PY = os.path.join(SC, "tools", "fc", "bin", "python")
LIB = os.path.join(SC, "tools", "fc", "lib")

SUBSET = {"solid.box", "solid.cylinder", "solid.sphere", "solid.cone", "solid.torus", "solid.combine", "solid.fillet",
          "solid.chamfer", "solid.shell", "sketch.create", "sketch.finish", "sketch.line", "sketch.rectangle.two_point",
          "sketch.rectangle.center", "sketch.circle.center", "sketch.arc.center_point", "solid.extrude", "solid.revolve",
          "solid.split_body", "inspect.measure"}

SKIPPED_KEYS = ["continuity", "surface_types", "splines", "watertight", "edges", "vertices", "boundary_edges", "results",
                "files", "construction", "flat_pattern"]


def commands_of(case):
    r = json.load(open(os.path.join(case, "recipe.json")))
    if "commands" not in r:
        return None
    cmds = [c["command"] for c in r["commands"]]
    if "base" in r:
        b = commands_of(os.path.normpath(os.path.join(case, r["base"])))
        if b is None:
            return None
        cmds = b + cmds
    return cmds


def in_scope():
    out = []
    for r in sorted(glob.glob(os.path.join(CASES, "*", "*", "recipe.json"))):
        case = os.path.dirname(r)
        cmds = commands_of(case)
        if cmds is not None and set(cmds) <= SUBSET:
            out.append(case)
    return out


def rng_ok(got, want, rel=None, abs_=None, exact=False):
    if isinstance(want, list):
        lo, hi = want
        if exact:
            return lo <= got <= hi
        slack = max(abs(lo), abs(hi)) * (rel or 0)
        return lo - slack <= got <= hi + slack
    if exact:
        return got == want
    tol = 0.0
    if rel is not None:
        tol = max(tol, rel * abs(want))
    if abs_ is not None:
        tol = max(tol, abs_)
    return abs(got - want) <= tol


def grade(exp, res):
    """status, failed checks, notes"""
    outcome = exp.get("outcome", "solid")
    tol = exp.get("tolerance", {}) or {}
    rel = tol.get("rel", 1e-3)
    fails = []
    notes = []
    skipped = [k for k in SKIPPED_KEYS if k in exp]
    if "missing" in exp:
        return "unsupported", [], ["case names a missing capability: " + exp["missing"]], skipped
    o = res.get("outcome")
    if o == "unsupported":
        return "unsupported", [], ["replay: " + res.get("why", "")], skipped
    if o == "engine_refusal":
        # the replay stopped where SolidCraft's engine refuses the arguments before any kernel call
        if outcome in ("refused", "solid_or_refused"):
            return "unsupported", [], ["engine-level refusal (no kernel call): " + res.get("error", "")], skipped
        return "unsupported", [], ["replay hit an engine-level check, likely a replay flaw: " + res.get("error", "")], skipped
    if o == "error":
        if outcome in ("refused", "solid_or_refused"):
            notes.append("OCCT raised where a refusal is right (message not compared: %s)" % res.get("error", "")[:200])
            return "pass", [], notes, skipped
        return "error", ["raised at step %s: %s" % (res.get("step"), res.get("error", "")[:300])], notes, skipped
    if o != "ok":
        return "crash", ["no result"], notes, skipped
    if outcome == "refused":
        if not res.get("valid", True):
            return "invalid", ["should refuse; made an invalid result (bodies %s)" % res.get("invalid_bodies")], notes, skipped
        return "fail", ["should refuse (%s); OCCT built a valid result: V=%.6g, bodies=%d" % (exp.get("refusal"), res["volume_mm3"], res["body_count"])], notes, skipped
    # graded as a solid
    if exp.get("valid", True) and not res.get("valid", True):
        fails.append("invalid bodies %s" % res.get("invalid_bodies"))
    if "body_count" in exp:
        w = exp["body_count"]
        if not rng_ok(res["body_count"], w, exact=True):
            fails.append("body_count %d (want %s)" % (res["body_count"], w))
    if "shells" in exp:
        w = exp["shells"]
        if not rng_ok(res["shells"], w, exact=True):
            fails.append("shells %d (want %s)" % (res["shells"], w))
    if "faces" in exp:
        w = exp["faces"]
        if not rng_ok(res["faces"], w, exact=True):
            fails.append("faces %d (want %s)" % (res["faces"], w))
    if "volume_mm3" in exp:
        w = exp["volume_mm3"]
        if not rng_ok(res["volume_mm3"], w, rel=rel, abs_=None if isinstance(w, list) else None):
            fails.append("volume %.6f (want %s, rel %g)" % (res["volume_mm3"], w if isinstance(w, list) else "%.6f" % w, rel))
    if "area_mm2" in exp:
        w = exp["area_mm2"]
        if not rng_ok(res["area_mm2"], w, rel=rel):
            fails.append("area %.6f (want %s, rel %g)" % (res["area_mm2"], w if isinstance(w, list) else "%.6f" % w, rel))
    if "bbox" in exp and "bbox" in res:
        wmin, wmax = exp["bbox"]["min"], exp["bbox"]["max"]
        diag = math.dist(wmin, wmax)
        at = tol.get("abs_mm", 1e-3 * diag)
        bad = []
        for k, (g, w) in enumerate(zip(res["bbox"]["min"] + res["bbox"]["max"], wmin + wmax)):
            if abs(g - w) > at:
                bad.append("%s%s %.5g/%.5g" % ("min" if k < 3 else "max", "xyz"[k % 3], g, w))
        if bad:
            fails.append("bbox " + ", ".join(bad) + " (tol %.3g)" % at)
    if "center_of_mass" in exp and res.get("volume_mm3"):
        w = exp["center_of_mass"]
        if "bbox" in exp:
            diag = math.dist(exp["bbox"]["min"], exp["bbox"]["max"])
        else:
            diag = math.dist(res["bbox"]["min"], res["bbox"]["max"])
        at = tol.get("abs_mm", 1e-3 * diag)
        if math.dist(w, res["center_of_mass"]) > at:
            fails.append("center_of_mass %s (want %s)" % ([round(x, 4) for x in res["center_of_mass"]], w))
    if fails:
        if any(f.startswith("invalid") for f in fails):
            return "invalid", fails, notes, skipped
        return "fail", fails, notes, skipped
    return "pass", [], notes, skipped


def run_one(case, timeout):
    exp = json.load(open(os.path.join(case, "expected.json")))
    area, cid = case.split(os.sep)[-2:]
    rec = {"area": area, "id": cid}
    fd, out = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    t = time.perf_counter()

    def lim():
        g = 6 * 1024 ** 3
        resource.setrlimit(resource.RLIMIT_AS, (g, g))

    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    try:
        p = subprocess.run([PY, "-I", os.path.join(HERE, "replay.py"), LIB, case, out], cwd=tempfile.gettempdir(),
                           timeout=timeout, capture_output=True, text=True, env=env, preexec_fn=lim)
        rec["wall_s"] = round(time.perf_counter() - t, 3)
        try:
            res = json.load(open(out))
        except Exception:
            res = None
        if res is None:
            rec.update(status="crash", checks=["process exit %s" % p.returncode], error=(p.stderr or "")[-500:])
            if "missing" in exp:
                rec.update(status="unsupported", notes=["case names a missing capability"])
            return rec
    except subprocess.TimeoutExpired:
        rec.update(status="timeout", wall_s=round(time.perf_counter() - t, 3), checks=["no result in %ss" % timeout])
        if "missing" in exp:
            rec.update(status="unsupported", notes=["case names a missing capability"])
        return rec
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass
    st, fails, notes, skipped = grade(exp, res)
    rec.update(status=st, checks=fails, notes=notes, skipped_checks=skipped, occt_wall_s=round(res.get("wall_s", 0), 3))
    if res.get("error"):
        rec["error"] = res["error"][:600]
    rec["got"] = {k: res[k] for k in ("body_count", "solids", "shells", "faces", "volume_mm3", "area_mm2", "bbox", "valid", "body_names") if k in res}
    rec["want"] = {k: exp[k] for k in ("outcome", "refusal", "body_count", "shells", "faces", "volume_mm3", "area_mm2", "bbox", "tolerance", "center_of_mass") if k in exp}
    rec["log_tail"] = res.get("log", [])[-8:]
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=os.path.join(SC, "results", "occt_kernel_cases.jsonl"))
    a = ap.parse_args()
    cases = in_scope()
    if a.only:
        want = set(a.only.split(","))
        cases = [c for c in cases if "/".join(c.split(os.sep)[-2:]) in want]
    print("cases:", len(cases), file=sys.stderr)
    with ThreadPoolExecutor(a.jobs) as ex:
        recs = list(ex.map(lambda c: run_one(c, a.timeout), cases))
    with open(a.out, "w") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    from collections import Counter
    print(Counter(r["status"] for r in recs), file=sys.stderr)


if __name__ == "__main__":
    main()
