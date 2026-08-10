"""Resolve GUI asset directories (templates/static), frozen-app aware.

Mirrors binaries.py's pattern: PyInstaller's onefile mode extracts `datas` to
a temp directory at ``sys._MEIPASS`` at runtime — pure-Python module
``__file__`` paths point into the bundled PYZ archive once frozen, not a real
filesystem location, so templates/static must be looked up relative to
``_MEIPASS`` instead.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_GUI_DIR = Path(__file__).resolve().parent


def gui_dir() -> Path:
    frozen_meipass = getattr(sys, "_MEIPASS", None)
    if frozen_meipass:
        return Path(frozen_meipass) / "glow_deploy" / "gui"
    return _GUI_DIR


def log_file() -> Path:
    return Path(tempfile.gettempdir()) / "glow-deploy-gui.log"
