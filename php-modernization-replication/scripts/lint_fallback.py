"""`php -l` each output and build the paper's lint-fallback variant (Table II).

    lint_fallback.py VARIANT OUTPUT_DIR ORIGINAL_DIR RESULTS_DIR FALLBACK_DIR

Writes RESULTS_DIR/lint_VARIANT.json ({file: passes lint}) and fills FALLBACK_DIR with the
generated file where it passes lint and the original where it does not (or is missing).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    variant, out, orig, res, fb = sys.argv[1], *map(Path, sys.argv[2:])
    fb.mkdir(parents=True, exist_ok=True)
    lint = {}
    for o in sorted(orig.glob("[0-9][0-9][0-9]_*.php")):
        g = out / o.name
        ok = g.exists() and subprocess.run(["php", "-l", str(g)], capture_output=True).returncode == 0
        lint[o.name] = ok
        shutil.copy2(g if ok else o, fb / o.name)
    (res / f"lint_{variant}.json").write_text(json.dumps(lint, indent=1))
    print(f"{variant}: {sum(lint.values())} of {len(lint)} pass php -l")


if __name__ == "__main__":
    main()
