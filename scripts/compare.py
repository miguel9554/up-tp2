#!/usr/bin/env python3
"""Compare placement runs of a design, one row per run.

Usage: compare.py <design_dir> [run_tag ...]

Without run tags, every run that reached detailed placement is compared, in
chronological order. The comparison is written to <design_dir>/runs/compare.md
(and printed to stdout).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from report import Run, fmt, pct, table  # noqa: E402


def row(run: Run):
    m, c = run.m, run.corner
    die, _ = run.die_core()
    rep = run.repair() or {}
    return [
        run.path.name,
        f"{die[2] - die[0]:.0f} x {die[3] - die[1]:.0f}" if die else "-",
        pct(m("design__instance__utilization")),
        pct(m("design__instance__utilization__stdcell")),
        fmt(m("route__wirelength__estimated"), 0),
        fmt(run.congestion(), 3),
        rep.get("slew/cap/fanout repair buffers", "-"),
        fmt(m("timing__setup__ws", c), 2),
        fmt(m("timing__hold__ws", c), 3),
        m("design__max_slew_violation__count", c),
        m("design__max_cap_violation__count", c),
    ]


HEADERS = ["Run", "Die (µm)", "Util", "Std util", "HPWL (µm)", "Congestion",
           "Repair buffers", "Setup WS (ns)", "Hold WS (ns)", "Slew vio", "Cap vio"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("design", type=Path, help="design directory")
    ap.add_argument("runs", nargs="*", help="run tags (default: every placement run)")
    args = ap.parse_args()

    runs_dir = args.design / "runs"
    if args.runs:
        paths = [runs_dir / r for r in args.runs]
        missing = [p.name for p in paths if not (p / "resolved.json").exists()]
        if missing:
            sys.exit(f"error: runs not found: {', '.join(missing)}")
    else:
        paths = sorted((p.parent for p in runs_dir.glob("*/resolved.json")),
                       key=lambda p: p.stat().st_mtime)
    runs = [r for r in map(Run, paths) if r.sta]
    if not runs:
        sys.exit("error: no placement runs to compare (use `make place`)")

    rows = [["-" if v is None else v for v in row(r)] for r in runs]
    corner = runs[0].corner
    text = "\n".join([
        f"# Placement comparison: `{runs[0].cfg['DESIGN_NAME']}`",
        "",
        f"Timing and slew/cap violations at corner `{corner}`, after placement.",
        "",
        table(HEADERS, rows),
        "",
    ])
    dest = runs_dir / "compare.md"
    dest.write_text(text)
    print(text)
    print(f"Comparison written to {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
