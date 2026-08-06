"""Shared Jinja2Templates instance for the GUI's routes and app factory.

Kept separate from app.py so routes can import it without a circular import
(app.py imports the routers, which need this).
"""

from __future__ import annotations

from fastapi.templating import Jinja2Templates

from glow_deploy.gui.paths import gui_dir

templates = Jinja2Templates(directory=str(gui_dir() / "templates"))
