"""
Path resolution shared by generate_lir.py, parse_rotation_report.py, and run_lir.py.

Normally (running as plain .py files), "base dir" is the package root -- the folder containing
scripts/ and assets/, i.e. this file's grandparent.

When bundled into a standalone .exe with PyInstaller, __file__ points into a temporary
extraction folder instead, and the actual data files (JSON configs, PDF templates) are NOT
embedded in the exe -- they're kept as plain external files next to the exe so they stay
editable without rebuilding. In that case "base dir" is the folder the .exe itself lives in.
"""

import sys
from pathlib import Path


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent
