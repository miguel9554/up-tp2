#!/usr/bin/env python3
"""Generate human-readable Markdown reports for a floorplan/placement run.

Usage: report.py <design_dir | run_dir> [--stage STAGE]

Given a design directory, the most recent run under <design_dir>/runs is used
(only runs tagged <STAGE>_* if --stage is given, e.g. fp or pl).
One file per report is written to <run_dir>/reports/:

    qor.md        summary: area, utilization, wirelength, timing vs TP1
    floorplan.md  die/core, rows, macros, tap/endcap cells, power grid
    placement.md  instances by class, density/congestion, wirelength,
                  buffers inserted by the resizer             (needs place)
    timing.md     post-placement STA vs TP1 + critical paths  (needs place)
"""
import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------- helpers

def find_run(path: Path, stage=None) -> Path:
    if (path / "resolved.json").exists():
        return path
    runs = sorted(
        (path / "runs").glob(f"{stage}_*/resolved.json" if stage else "*/resolved.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not runs:
        sys.exit(f"error: no {stage + ' ' if stage else ''}runs found under {path}")
    return runs[-1].parent


def step_dir(run: Path, name: str):
    """Return the (last) step directory whose name ends with `name`."""
    dirs = sorted(d for d in run.iterdir() if d.is_dir() and d.name.endswith(name))
    return dirs[-1] if dirs else None


def step_log(run: Path, name: str) -> str:
    d = step_dir(run, name)
    logs = sorted(d.glob("*.log")) if d else []
    return logs[0].read_text() if logs else ""


def table(headers, rows, align=None):
    """Markdown table with columns padded so every '|' lines up."""
    align = align or ["l"] + ["r"] * (len(headers) - 1)
    cells = [[str(c) for c in headers]] + [[str(c) for c in r] for r in rows]
    widths = [max(3, *(len(r[i]) for r in cells)) for i in range(len(headers))]

    def line(r):
        return "| " + " | ".join(
            c.rjust(w) if a == "r" else c.ljust(w) for c, w, a in zip(r, widths, align)
        ) + " |"

    sep = "| " + " | ".join(
        "-" * (w - 1) + ":" if a == "r" else ":" + "-" * (w - 1) for w, a in zip(widths, align)
    ) + " |"
    return "\n".join([line(cells[0]), sep] + [line(r) for r in cells[1:]])


def fmt(v, nd=3):
    if isinstance(v, (int, float)):
        return "inf" if v == float("inf") else f"{v:.{nd}f}"
    return str(v) if v is not None else "-"


def pct(v):
    return f"{100 * v:.1f}%" if isinstance(v, (int, float)) else "-"


def code(text):
    return "```\n" + text.rstrip() + "\n```"


def grab(pattern, text, cast=float):
    """First group of `pattern` in `text`, converted with `cast` (None if absent)."""
    m = re.search(pattern, text, re.M)
    return cast(m[1]) if m else None


def grab_last(pattern, text, cast=float):
    found = re.findall(pattern, text, re.M)
    return cast(found[-1]) if found else None


def grab_all(pattern, text, cast=int):
    return sum(cast(x) for x in re.findall(pattern, text, re.M))


# ---------------------------------------------------------------- parsers

def first_path(path: Path):
    """Return the first (worst) timing path of an OpenSTA report_checks file."""
    m = re.search(r"^Startpoint:.*?slack \((?:MET|VIOLATED)\)", path.read_text(), re.M | re.S)
    return m[0] if m else None


def macro_sizes(cfg):
    """Macro cell name -> (width, height) in µm, from the macros' LEF files."""
    sizes = {}
    for name, macro in (cfg.get("MACROS") or {}).items():
        for lef in macro.get("lef", []):
            m = re.search(rf"MACRO {re.escape(name)}\b.*?SIZE\s+([\d.]+)\s+BY\s+([\d.]+)",
                          Path(lef).read_text(), re.S)
            if m:
                sizes[name] = (float(m[1]), float(m[2]))
    return sizes


def placed_macros(def_file: Path, cfg):
    """[(instance, cell, x, y, orientation)] for the macros in a DEF (µm)."""
    text = def_file.read_text()
    dbu = grab(r"^UNITS DISTANCE MICRONS (\d+)", text) or 1000
    cells = "|".join(re.escape(c) for c in (cfg.get("MACROS") or {}))
    if not cells:
        return []
    out = []
    for m in re.finditer(rf"^\s*- (\S+) ({cells}) .*?\+ (?:FIXED|PLACED) \( (-?\d+) (-?\d+) \) (\w+)",
                         text, re.M):
        out.append((m[1].replace("\\", ""), m[2], int(m[3]) / dbu, int(m[4]) / dbu, m[5]))
    return sorted(out)


# ---------------------------------------------------------------- reports

class Run:
    def __init__(self, path: Path):
        self.path = path
        self.cfg = json.loads((path / "resolved.json").read_text())
        mf = path / "final" / "metrics.json"
        self.metrics = json.loads(mf.read_text()) if mf.exists() else {}

        tp1_state = path.parent.parent / "tp1" / "state.json"
        self.tp1 = json.loads(tp1_state.read_text()) if tp1_state.exists() else None
        tp1_source = path.parent.parent / "tp1" / "SOURCE"
        self.tp1_run = tp1_source.read_text().strip() if tp1_source.exists() else None

        self.fp_log = step_log(path, "openroad-floorplan")
        self.dpl = step_dir(path, "openroad-detailedplacement")
        # The STA added after detailed placement (the last mid-PnR STA step).
        self.sta = step_dir(path, "openroad-stamidpnr-1") if self.dpl else None
        self.corner = self.cfg.get("DEFAULT_CORNER")

    def step_cfg(self, name):
        """Configuration seen by a step (includes step-only variables)."""
        d = step_dir(self.path, name)
        return json.loads((d / "config.json").read_text()) if d else {}

    def m(self, key, corner=None):
        return self.metrics.get(f"{key}__corner:{corner}" if corner else key)

    def m1(self, key, corner=None):
        """Metric of the TP1 run (pre-PnR STA)."""
        if not self.tp1:
            return None
        return self.tp1["metrics"].get(f"{key}__corner:{corner}" if corner else key)

    def header(self, title):
        period = self.cfg.get("CLOCK_PERIOD")
        return "\n".join([
            f"# {title}: `{self.cfg['DESIGN_NAME']}`",
            "",
            table(["Item", "Value"], [
                ["Run", self.path.name],
                ["Netlist from TP1 run", self.tp1_run or "-"],
                ["Std cell library", self.cfg.get("STD_CELL_LIBRARY")],
                ["Clock", f"{self.cfg.get('CLOCK_PORT')} @ {period} ns ({1000 / period:.1f} MHz)"
                 if period else "-"],
            ], ["l", "l"]),
            "",
        ])

    # -- data ---------------------------------------------------------------

    def die_core(self):
        """((x0, y0, x1, y1) die, (x0, y0, x1, y1) core) in µm, from the floorplan log."""
        box = r"\(\s*([\d.]+)\s+([\d.]+)\s*\)\s*\(\s*([\d.]+)\s+([\d.]+)\s*\)"
        die = re.search(r"Die BBox:\s*" + box, self.fp_log)
        core = re.search(r"Core BBox:\s*" + box, self.fp_log)
        return (tuple(map(float, die.groups())) if die else None,
                tuple(map(float, core.groups())) if core else None)

    def macros(self):
        d = step_dir(self.path, "odb-manualmacroplacement")
        defs = sorted(d.glob("*.def")) if d else []
        return placed_macros(defs[0], self.cfg) if defs else []

    def repair(self):
        log = step_log(self.path, "openroad-repairdesignpostgpl")
        if not log:
            return None
        return {
            "input buffers": grab_all(r"RSZ-0027\] Inserted (\d+)", log),
            "output buffers": grab_all(r"RSZ-0028\] Inserted (\d+)", log),
            "slew/cap/fanout repair buffers": grab_all(r"RSZ-0038\] Inserted (\d+) buffers", log),
            "resized instances": grab_all(r"RSZ-0039\] Resized (\d+)", log),
            "tie cells": grab_all(r"RSZ-0042\] Inserted (\d+) tie", log),
            "slew violations found": grab_all(r"RSZ-0034\] Found (\d+) slew", log),
            "cap violations found": grab_all(r"RSZ-0036\] Found (\d+) cap", log),
        }

    # -- individual reports -------------------------------------------------

    def qor(self):
        m = self.m
        die, core = self.die_core()
        rows = [
            ["Die (µm)", f"{die[2] - die[0]:.2f} x {die[3] - die[1]:.2f}" if die else "-"],
            ["Die area (µm²)", fmt(m("design__die__area"))],
            ["Core area (µm²)", fmt(m("design__core__area"))],
            ["Macros", m("design__instance__count__macros")],
            ["Macro area (µm²)", fmt(m("design__instance__area__macros"))],
            ["Std cell instances", m("design__instance__count__stdcell")],
            ["Std cell area (µm²)", fmt(m("design__instance__area__stdcell"))],
            ["Utilization (all instances / core)", pct(m("design__instance__utilization"))],
            ["Std cell utilization", pct(m("design__instance__utilization__stdcell"))],
            ["Power grid violations", m("design__power_grid_violation__count")],
        ]
        if self.dpl:
            rows += [
                ["Estimated wirelength, HPWL (µm)", fmt(m("route__wirelength__estimated"), 0)],
                ["Routing congestion after global placement", fmt(self.congestion(), 4)],
            ]
        if self.sta:
            c = self.corner
            rows += [
                [f"Setup WS @ {c} (ns): TP1 -> placed",
                 f"{fmt(self.m1('timing__setup__ws', c))} -> {fmt(m('timing__setup__ws', c))}"],
                [f"Hold WS @ {c} (ns): TP1 -> placed",
                 f"{fmt(self.m1('timing__hold__ws', c))} -> {fmt(m('timing__hold__ws', c))}"],
                [f"Max slew violations @ {c}: TP1 -> placed",
                 f"{self.m1('design__max_slew_violation__count', c)} -> "
                 f"{m('design__max_slew_violation__count', c)}"],
                [f"Max cap violations @ {c}: TP1 -> placed",
                 f"{self.m1('design__max_cap_violation__count', c)} -> "
                 f"{m('design__max_cap_violation__count', c)}"],
            ]
        else:
            rows.append(["Placement / timing", "not run (use `make place`)"])
        rows = [[k, "-" if v is None else v] for k, v in rows]
        return self.header("QoR report") + "\n" + table(["Metric", "Value"], rows)

    def floorplan(self):
        die, core = self.die_core()
        log = self.fp_log
        rows = []
        if die and core:
            rows += [
                ["Die", f"({die[0]:.2f}, {die[1]:.2f}) - ({die[2]:.2f}, {die[3]:.2f})",
                 f"{die[2] - die[0]:.2f} x {die[3] - die[1]:.2f}"],
                ["Core", f"({core[0]:.2f}, {core[1]:.2f}) - ({core[2]:.2f}, {core[3]:.2f})",
                 f"{core[2] - core[0]:.2f} x {core[3] - core[1]:.2f}"],
            ]
        cfg = self.step_cfg("openroad-floorplan")
        how = (f"relative: FP_CORE_UTIL = {cfg.get('FP_CORE_UTIL')}%, "
               f"FP_ASPECT_RATIO = {cfg.get('FP_ASPECT_RATIO')}"
               if cfg.get("FP_SIZING") == "relative" else f"absolute: DIE_AREA = {cfg.get('DIE_AREA')}")
        if self.cfg.get("FP_DEF_TEMPLATE"):
            how += f"; I/O pins from {Path(self.cfg['FP_DEF_TEMPLATE']).name}"
        out = [
            self.header("Floorplan report"),
            f"Sizing: {how}.",
            "",
            table(["Box", "Lower left - upper right (µm)", "W x H (µm)"], rows, ["l", "l", "r"]),
            "",
            table(["Item", "Value"], [
                ["Rows", grab(r"Added (\d+) rows", log, int) or "-"],
                ["Sites per row", grab(r"rows of (\d+) site", log, int) or "-"],
                ["Site", grab(r"rows of \d+ site (\S+)\.", log, str) or "-"],
                ["Instance area at floorplan (µm²)", fmt(grab(r"Total instances area:\s+([\d.]+)", log))],
                ["Effective utilization", fmt(grab(r"Effective utilization:\s+([\d.]+)", log))],
            ]),
        ]

        macros = self.macros()
        if macros:
            sizes = macro_sizes(self.cfg)
            rows = []
            for inst, cell, x, y, orient in macros:
                w, h = sizes.get(cell, (None, None))
                if orient in ("E", "W", "FE", "FW") and w:
                    w, h = h, w
                rows.append([inst, f"{x:.2f}", f"{y:.2f}",
                             f"{x + w:.2f}" if w else "-", f"{y + h:.2f}" if h else "-", orient])
            out += ["", "## Macros", "",
                    "Lower-left and upper-right corner of each macro, in µm.", "",
                    table(["Instance", "x0", "y0", "x1", "y1", "Orient"], rows,
                          ["l", "r", "r", "r", "r", "l"])]

        tap = step_log(self.path, "openroad-tapendcapinsertion")
        m = self.m
        out += ["", "## Physical-only cells and power grid", "",
                table(["Item", "Value"], [
                    ["Endcap cells", grab(r"Inserted (\d+) endcaps", tap, int) or "-"],
                    ["Tap cells", grab(r"Inserted (\d+) tapcells", tap, int) or "-"],
                    ["Tap cell area (µm²)", fmt(m("design__instance__area__class:tap_cell"))],
                    ["Power grid violations", m("design__power_grid_violation__count")
                     if m("design__power_grid_violation__count") is not None else "-"],
                ])]
        return "\n".join(out)

    def congestion(self):
        log = step_log(self.path, "openroad-globalplacement")
        return grab(r"Routability final weighted congestion:\s+([\d.]+)", log)

    def placement(self):
        if not self.dpl:
            return None
        m = self.m
        classes = sorted({k.split("class:")[1] for k in self.metrics
                          if k.startswith("design__instance__count__class:")})
        rows = [[c, m(f"design__instance__count__class:{c}"),
                 fmt(m(f"design__instance__area__class:{c}"))] for c in classes]
        gpl = step_log(self.path, "openroad-globalplacement")
        dpl = step_log(self.path, "openroad-detailedplacement")
        out = [
            self.header("Placement report"),
            "## Instances by class", "",
            table(["Class", "Instances", "Area (µm²)"], rows),
            "",
            "## Global placement", "",
            table(["Item", "Value"], [
                ["Target density", fmt(grab(r"GPL-\d+\] Placement target density:\s+([\d.]+)", gpl))],
                ["Final overflow", fmt(grab_last(r"overflow:\s*([\d.]+)", gpl), 4)],
                ["Routing congestion (weighted)", fmt(self.congestion(), 4)],
                ["Overflowed routing tiles",
                 grab_last(r"Number of overflowed tiles:\s*(.+)$", gpl, str) or "-"],
                ["Cell area inflated for routability", grab(r"Final placement area:.*\((.+)\)", gpl, str) or "-"],
            ]),
            "",
            "## Detailed placement", "",
            table(["Item", "Value"], [
                ["Final HPWL (µm)", fmt(m("route__wirelength__estimated"), 0)],
                ["Instances mirrored to reduce wirelength",
                 grab(r"Mirrored (\d+) instances", dpl, int) or "-"],
                ["HPWL change from mirroring", grab(r"HPWL delta\s+(.+)$", dpl, str) or "-"],
            ]),
        ]
        rep = self.repair()
        if rep:
            out += ["", "## Design repair after global placement", "",
                    "Buffers and resizing done by the resizer to fix max slew / max cap /"
                    " max fanout, using wire parasitics estimated from the placement.", "",
                    table(["Item", "Value"], [[k, v] for k, v in rep.items()])]
        return "\n".join(out)

    def timing(self):
        if not self.sta:
            return None
        c, m, m1 = self.corner, self.m, self.m1
        keys = [("Setup WS (ns)", "timing__setup__ws", 3), ("Setup TNS (ns)", "timing__setup__tns", 3),
                ("Setup violations", "timing__setup_vio__count", 0),
                ("Hold WS (ns)", "timing__hold__ws", 3), ("Hold TNS (ns)", "timing__hold__tns", 3),
                ("Hold violations", "timing__hold_vio__count", 0),
                ("Max slew violations", "design__max_slew_violation__count", 0),
                ("Max cap violations", "design__max_cap_violation__count", 0)]
        rows = [[label, fmt(m1(k, c), nd) if nd else m1(k, c), fmt(m(k, c), nd) if nd else m(k, c)]
                for label, k, nd in keys]
        rows = [[a, "-" if b is None else b, "-" if d is None else d] for a, b, d in rows]
        out = [
            self.header("Timing report"),
            f"Corner `{c}`. TP1: pre-PnR STA (no wires). Placed: wire parasitics estimated"
            " from the placement. Clocks are ideal in both (no clock tree yet).",
            "",
            table(["Metric", f"TP1 ({self.tp1_run})", "Placed"], rows),
        ]
        for kind, rpt in (("setup", "max.rpt"), ("hold", "min.rpt")):
            p = first_path(self.sta / rpt)
            if p:
                out += ["", f"## Critical {kind} path (corner `{c}`)", "", code(p)]
        return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", type=Path, help="design directory or run directory")
    ap.add_argument("--stage", help="only consider runs of this stage (fp, pl)")
    args = ap.parse_args()

    run = Run(find_run(args.path, args.stage))
    outdir = run.path / "reports"
    outdir.mkdir(exist_ok=True)

    for name in ("qor", "floorplan", "placement", "timing"):
        text = getattr(run, name)()
        dest = outdir / f"{name}.md"
        if text is None:
            dest.unlink(missing_ok=True)
            continue
        dest.write_text(text + "\n")
        print(f"wrote {dest}")

    print()
    print((outdir / "qor.md").read_text())


if __name__ == "__main__":
    main()
