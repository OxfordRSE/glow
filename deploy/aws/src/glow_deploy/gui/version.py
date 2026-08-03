"""The GUI's own version, baked in at build time by the release workflow.

The release workflow writes the release tag into a `VERSION` file next to
this module before running PyInstaller (bundled the same way as
templates/static — see paths.py); that file doesn't exist when running from
source (`uv run`), so CURRENT_VERSION falls back to "dev" and the
update-nudge check in app.py is skipped entirely, since there's nothing
meaningful to compare against.
"""

from __future__ import annotations

from glow_deploy.gui.paths import gui_dir

_VERSION_FILE = gui_dir() / "VERSION"


def _read_version() -> str:
    try:
        return _VERSION_FILE.read_text().strip()
    except OSError:
        return "dev"


CURRENT_VERSION = _read_version()
