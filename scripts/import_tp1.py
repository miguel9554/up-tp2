#!/usr/bin/env python3
"""Import the synthesized netlist of a TP1 run, so PnR starts from it.

Usage: import_tp1.py <tp1_project_dir> <design> [run_tag]

<tp1_project_dir> is the TP1 project as seen from the container (/tp1).
Without run_tag, the most recent hd_* run of <design> with a finished
pre-PnR STA is used. Everything is copied to designs/<design>/tp1/:

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


def sta_state(run: Path):
    states = sorted(run.glob(f"*-{STA_STEP}/state_out.json"))
    return states[-1] if states else None


def main():
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    tp1, design = Path(sys.argv[1]), sys.argv[2]
    runs_dir = tp1 / "designs" / design / "runs"
    if not runs_dir.is_dir():
        sys.exit(f"error: {runs_dir} does not exist. Is TP1 the TP1 project directory?")

    if len(sys.argv) == 4:
        run = runs_dir / sys.argv[3]
        if not run.is_dir():
            sys.exit(f"error: run {sys.argv[3]} not found in {runs_dir}")
    else:
        runs = sorted((r for r in runs_dir.glob("hd_*") if sta_state(r)),
                      key=lambda r: r.name)
        if not runs:
            sys.exit(f"error: no hd run with STA in {runs_dir}. "
                     f"Run `make sta DESIGN={design}` in the TP1 project.")
        run = runs[-1]

    state_file = sta_state(run)
    if state_file is None:
        sys.exit(f"error: {run.name} has no pre-PnR STA step: use a run made with `make sta`")
    state = json.loads(state_file.read_text())
    resolved = json.loads((run / "resolved.json").read_text())
    for key, want in EXPECTED.items():
        if resolved.get(key) != want:
            sys.exit(f"error: {run.name} has {key} = {resolved.get(key)}, expected {want}. "
                     f"Use a run with the original TP1 configuration (FROM=<run>).")

    dest = Path("designs") / design / "tp1"
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)

    def localize(path: str) -> str:
        """Copy a TP1 file (path inside the TP1 container, /work/...) to dest."""
        src = tp1 / Path(path).relative_to("/work")
        shutil.copy(src, dest / src.name)
        return f"/work/{dest}/{src.name}"

    new_state = {"nl": localize(state["nl"]), "json_h": localize(state["json_h"]),
                 "metrics": state.get("metrics", {})}
    (dest / "state.json").write_text(json.dumps(new_state, indent=2) + "\n")
    if (run / "reports").is_dir():
        shutil.copytree(run / "reports", dest / "reports")
    (dest / "SOURCE").write_text(f"{run.name}\n")

    print(f"Imported TP1 run {run.name} into {dest}/")


if __name__ == "__main__":
    main()
