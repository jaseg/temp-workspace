"""Run occt_model.py on each STEP file in its own process, with a timeout and a memory cap.

  run_occt.py <list-of-step-files.txt> <out.jsonl> [--timeout S] [--jobs N]
A run that crashes or times out keeps the stages it finished (the child writes as it goes).
"""

import argparse
import json
import os
import resource
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
FC = os.environ.get("FREECAD_PREFIX", os.path.join(ROOT, "tools", "fc"))
PY = os.path.join(FC, "bin", "python")
LIB = os.path.join(FC, "lib")

ap = argparse.ArgumentParser()
ap.add_argument("files")
ap.add_argument("out")
ap.add_argument("--timeout", type=float, default=300)
ap.add_argument("--jobs", type=int, default=1)
ap.add_argument("--mem-gb", type=float, default=6)
a = ap.parse_args()

files = [line.strip() for line in open(a.files) if line.strip()]
done = set()
if os.path.exists(a.out):
    done = {json.loads(line)["file"] for line in open(a.out)}


def limit():
    m = int(a.mem_gb * 2**30)
    resource.setrlimit(resource.RLIMIT_AS, (m, m))


def one(f):
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
    t = time.perf_counter()
    status = "ok"
    try:
        p = subprocess.run(
            [PY, "-I", os.path.join(HERE, "occt_model.py"), f, tmp, LIB],
            capture_output=True,
            timeout=a.timeout,
            preexec_fn=limit,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "OMP_NUM_THREADS": "1"},
        )
        if p.returncode != 0:
            status = f"exit {p.returncode}"
    except subprocess.TimeoutExpired:
        status = "timeout"
    wall = time.perf_counter() - t
    try:
        r = json.load(open(tmp))
    except Exception:  # noqa: BLE001
        r = {"file": f}
    os.unlink(tmp)
    r.update(file=f, status=status if r.get("done") or status != "ok" else "incomplete", wall_s=wall)
    return r


with open(a.out, "a") as o, ThreadPoolExecutor(a.jobs) as ex:
    for r in ex.map(one, [f for f in files if f not in done]):
        o.write(json.dumps(r) + "\n")
        o.flush()
        print(r["status"], round(r["wall_s"], 1), os.path.basename(r["file"]), flush=True)
