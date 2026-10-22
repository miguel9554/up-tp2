#!/usr/bin/env python3
"""Check the macro placement before running the flow.

Usage: check_macros.py <design>

Reads DIE_AREA, MACROS and MACRO_PLACEMENT_CFG from designs/<design>/config.json
and checks that every macro instance:

  - has a line in the placement file, with a valid orientation,
  - lies inside the core (the die minus the margins LibreLane leaves),
  - does not overlap any other macro.

LibreLane itself does not check this until signoff: an overlap makes global
placement diverge, and a macro outside the die goes unnoticed.
"""
import json
import math
import re
import sys
from pathlib import Path

from pdk import resolve

# sky130_fd_sc_hd site (SITE unithd in the tech LEF) and LibreLane's default
# core margins, in sites (left/right) and rows (bottom/top).
SITE_W, SITE_H = 0.46, 2.72
MARGIN_X, MARGIN_Y = 12 * SITE_W, 4 * SITE_H

ORIENTATIONS = {"N", "S", "FN", "FS"}


def core_area(die):
    """Core as OpenROAD's floorplan computes it: margins, then whole sites/rows."""
    x0, y0, x1, y1 = die
    sites = math.floor(round((x1 - x0 - 2 * MARGIN_X) / SITE_W, 6))
    rows = math.floor(round((y1 - y0 - 2 * MARGIN_Y) / SITE_H, 6))
    cx, cy = x0 + MARGIN_X, y0 + MARGIN_Y
    return cx, cy, cx + sites * SITE_W, cy + rows * SITE_H


def lef_size(lef: Path, macro: str):
    m = re.search(rf"MACRO {re.escape(macro)}\b.*?SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", lef.read_text(), re.S)
    if not m:
        sys.exit(f"error: no SIZE for {macro} in {lef}")
    return float(m[1]), float(m[2])


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    design_dir = Path("designs") / sys.argv[1]
    config = json.loads((design_dir / "config.json").read_text())
    if not config.get("DIE_AREA"):
        sys.exit("error: DIE_AREA is not set: run make footprint first")
    core = core_area([float(v) for v in config["DIE_AREA"]])

    sizes = {}  # instance -> (w, h)
    for macro, views in config["MACROS"].items():
        size = lef_size(resolve(views["lef"][0], design_dir), macro)
        sizes.update({inst: size for inst in views["instances"]})

    cfg_file = resolve(config["MACRO_PLACEMENT_CFG"], design_dir)
    placed = {}  # instance -> (x0, y0, x1, y1)
    errors = []
    for n, line in enumerate(cfg_file.read_text().splitlines(), 1):
        fields = line.split("#")[0].split()
        if not fields:
            continue
        where = f"{cfg_file.name}:{n}"
        if len(fields) != 4:
            errors.append(f"{where}: expected '<instance> <x> <y> <orientation>'")
            continue
        inst, x, y, orient = fields
        if inst not in sizes:
            errors.append(f"{where}: {inst} is not a macro instance of the design")
            continue
        if orient not in ORIENTATIONS:
            errors.append(f"{where}: orientation {orient} is not one of {', '.join(sorted(ORIENTATIONS))}")
        try:
            x, y = float(x), float(y)
        except ValueError:
            errors.append(f"{where}: x and y must be numbers (µm)")
            continue
        w, h = sizes[inst]
        placed[inst] = (x, y, x + w, y + h)

    for inst in sizes:
        if inst not in placed:
            errors.append(f"{inst} has no location in {cfg_file.name}")

    fmt = lambda b: f"({b[0]:.2f}, {b[1]:.2f}) - ({b[2]:.2f}, {b[3]:.2f})"
    for inst, b in placed.items():
        if b[0] < core[0] or b[1] < core[1] or b[2] > core[2] or b[3] > core[3]:
            errors.append(f"{inst} at {fmt(b)} is not inside the core {fmt(core)}")
    insts = list(placed)
    for i, a in enumerate(insts):
        for b in insts[i + 1:]:
            pa, pb = placed[a], placed[b]
            if pa[0] < pb[2] and pb[0] < pa[2] and pa[1] < pb[3] and pb[1] < pa[3]:
                errors.append(f"{a} at {fmt(pa)} overlaps {b} at {fmt(pb)}")

    if errors:
        print(f"error: illegal macro placement ({cfg_file}):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Macro placement OK: {len(placed)} macros inside the core {fmt(core)}, no overlaps.")


if __name__ == "__main__":
    main()
