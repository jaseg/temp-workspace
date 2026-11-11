"""KiCad action entry point: see factorio_poles/actions.py."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factorio_poles.actions import main

sys.exit(main(["update", *sys.argv[1:]]))
