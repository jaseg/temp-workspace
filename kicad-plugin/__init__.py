from pathlib import Path

from kipy import KiCad
from kipy.errors import ConnectionError

import kicoil.gui

if __name__ == '__main__':
    kicad_inst = KiCad()
    kicoil.gui.main(kicad_inst)
