"""Paths inside the PDK, for the scripts that run in the container.

The PDK version is the one LibreLane uses, installed by ciel under $PDK_ROOT.
"""
import os
from pathlib import Path

import ciel
from librelane.common import get_pdk_hash

PDK = "sky130A"


def pdk_dir() -> Path:
    home = ciel.get_ciel_home(os.environ.get("PDK_ROOT"))
    return Path(home) / "ciel" / "sky130" / "versions" / get_pdk_hash(PDK) / PDK


def resolve(path: str, design_dir: Path) -> Path:
    """Resolve a LibreLane config path (pdk_dir::, dir:: or plain)."""
    if path.startswith("pdk_dir::"):
        return pdk_dir() / path[len("pdk_dir::"):]
    if path.startswith("dir::"):
        return design_dir / path[len("dir::"):]
    return Path(path)
