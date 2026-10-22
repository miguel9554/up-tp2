#!/usr/bin/env python3
"""Open the footprint of a design (designs/<design>/footprint.def) in the
OpenROAD GUI, without running any flow: only the die and the I/O pins.

Usage: gui_footprint.py <design>

Runs inside the container. The technology LEF (needed for the metal layers of
the pins) is taken from the same PDK version LibreLane uses.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import ciel
from librelane.common import get_pdk_hash

PDK = "sky130A"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    design_dir = Path("designs") / sys.argv[1]
    footprint = design_dir / "footprint.def"
    if not footprint.is_file():
        sys.exit(f"error: {footprint} not found: run make footprint first")
    scl = json.loads((design_dir / "config.json").read_text())["STD_CELL_LIBRARY"]

    home = ciel.get_ciel_home(os.environ.get("PDK_ROOT"))
    pdk_dir = Path(home) / "ciel" / "sky130" / "versions" / get_pdk_hash(PDK) / PDK
    tech_lef = pdk_dir / "libs.ref" / scl / "techlef" / f"{scl}__nom.tlef"
    if not tech_lef.is_file():
        sys.exit(f"error: {tech_lef} not found: is the PDK installed (make pdk in TP1)?")

    script = tempfile.NamedTemporaryFile("w", suffix=".tcl", delete=False)
    script.write(f"read_lef {tech_lef}\nread_def {footprint}\n")
    script.close()
    os.execvp("openroad", ["openroad", "-gui", "-no_splash", script.name])


if __name__ == "__main__":
    main()
