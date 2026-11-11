"""KiCad action entry point: see factorio_poles/actions.py."""

import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
# Packaged builds bundle a kicad-python with the schematic API in vendor/ (see
# tools/build_pcm.py); it must win over the older release KiCad installs from PyPI.
sys.path[:0] = [p for p in (os.path.join(here, "vendor"), here) if os.path.isdir(p)]

from factorio_poles.actions import main  # noqa: E402

sys.exit(main(["clear", *sys.argv[1:]]))
