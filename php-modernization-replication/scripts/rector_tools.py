"""Rector 2.1.0 (UP_TO_PHP_83) as a baseline modernizer and as the finding detector.

    rector_tools.py migrate SRC_DIR OUT_DIR    # Rector baseline, one isolated process per file
    rector_tools.py findings SRC_DIR OUT.json  # rules Rector still fires per file (dry run)

Mirrors the package's run_isolated_rector_migration.py and rector_analyzer.py: each file is
copied alone into a fresh directory with rector.php, so no other project file is visible.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools" / "rector"
RECTOR = TOOLS / "vendor" / "bin" / "rector"
CONFIG = TOOLS / "rector.php"


def _isolated(src, args):
    with tempfile.TemporaryDirectory() as wd:
        wd = Path(wd)
        shutil.copy2(src, wd / src.name)
        shutil.copy2(CONFIG, wd / "rector.php")
        p = subprocess.run(
            [str(RECTOR), "process", src.name, "--config", "rector.php", "--clear-cache", *args],
            cwd=wd, capture_output=True, text=True, timeout=300,
        )  # fmt: skip
        return p, (wd / src.name).read_bytes()


def migrate_one(src, out_dir):
    for _ in range(3):  # (retry transient worker failures)
        p, data = _isolated(src, [])
        if p.returncode == 0:
            break
    (out_dir / src.name).write_bytes(data)
    return {"file": src.name, "exit": p.returncode, "changed": data != src.read_bytes()}


def findings_one(src):
    for _ in range(3):  # (retry transient worker failures)
        p, _ = _isolated(src, ["--dry-run", "--output-format", "json"])
        try:
            out = json.loads(p.stdout)
        except json.JSONDecodeError:
            res = {"error": (p.stderr or p.stdout)[-2000:]}
            continue
        if out.get("errors") or out.get("totals", {}).get("errors", 0):
            res = {"error": out.get("errors")}
            continue
        break
    else:
        return src.name, res
    rules = sorted({r for d in out.get("file_diffs", []) for r in d.get("applied_rectors", [])})
    return src.name, {"rules": rules}


def files_in(d):
    return sorted(Path(d).glob("[0-9][0-9][0-9]_*.php"))


def main():
    cmd, src, dst = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    with ThreadPoolExecutor(4) as ex:
        if cmd == "migrate":
            dst.mkdir(parents=True, exist_ok=True)
            log = list(ex.map(lambda f: migrate_one(f, dst), files_in(src)))
            (dst.parent / "rector_migration_manifest.json").write_text(json.dumps(log, indent=1))
            print(sum(r["changed"] for r in log), "of", len(log), "files changed")
        elif cmd == "findings":
            res = dict(ex.map(findings_one, files_in(src)))
            dst.write_text(json.dumps(res, indent=1, sort_keys=True))
            print(len(res), "files,", sum("error" in v for v in res.values()), "unparseable")


if __name__ == "__main__":
    main()
