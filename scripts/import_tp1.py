#!/usr/bin/env python3
"""Import the synthesized netlist of a TP1 run, so PnR starts from it.

Usage: import_tp1.py <run_dir> <design> <run_name>

<run_dir> is the TP1 run directory as seen from the container (/tp1_run),
<run_name> its name on the host (the mount point hides it). The run must have
a finished pre-PnR STA (`make sta` in TP1). Everything is copied to
designs/<design>/tp1/:

    tp1/<design>.nl.v     gate-level netlist (input of the floorplan)
    tp1/<design>.h.json   JSON header (power pins of the macros)
    tp1/reports/          TP1 reports (qor, area, timing, ...) to compare with
    tp1/state.json        initial state for LibreLane (--with-initial-state)
    tp1/SOURCE            which TP1 run this came from
"""
import json
import shutil
import sys
from pathlib import Path

STA_STEP = "openroad-staprepnr"

# Values the TP2 config assumes; a TP1 run with other values is not comparable.
EXPECTED = {"STD_CELL_LIBRARY": "sky130_fd_sc_hd", "CLOCK_PERIOD": 100}


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    run, design, name = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]).name

    if not (run / "resolved.json").is_file():
        sys.exit(f"error: {name} is not a LibreLane run directory (no resolved.json)")
    states = sorted(run.glob(f"*-{STA_STEP}/state_out.json"))
    if not states:
        sys.exit(f"error: {name} has no pre-PnR STA step: use a run made with "
                 f"`make sta DESIGN={design}` in TP1")
    state = json.loads(states[-1].read_text())
    resolved = json.loads((run / "resolved.json").read_text())

    config = json.loads((Path("designs") / design / "config.json").read_text())
    expected = dict(EXPECTED, DESIGN_NAME=config["DESIGN_NAME"])
    for key, want in expected.items():
        if resolved.get(key) != want:
            sys.exit(f"error: {name} has {key} = {resolved.get(key)}, expected {want}. "
                     f"Use a run with the original TP1 configuration.")

    dest = Path("designs") / design / "tp1"
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)

    def localize(path: str) -> str:
        """Copy a file of the run (path inside the TP1 container,
        /work/designs/<design>/runs/<name>/...) to dest."""
        parts = Path(path).parts
        if name not in parts:
            sys.exit(f"error: {path} is not inside run {name}")
        src = run.joinpath(*parts[parts.index(name) + 1:])
        shutil.copy(src, dest / src.name)
        return f"/work/{dest}/{src.name}"

    new_state = {"nl": localize(state["nl"]), "json_h": localize(state["json_h"]),
                 "metrics": state.get("metrics", {})}
    (dest / "state.json").write_text(json.dumps(new_state, indent=2) + "\n")
    if (run / "reports").is_dir():
        shutil.copytree(run / "reports", dest / "reports")
    (dest / "SOURCE").write_text(f"{name}\n")

    print(f"Imported TP1 run {name} into {dest}/")


if __name__ == "__main__":
    main()
