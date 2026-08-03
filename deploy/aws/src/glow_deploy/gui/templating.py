"""Shared Jinja2Templates instance for the GUI's routes and app factory.

Kept separate from app.py so routes can import it without a circular import
(app.py imports the routers, which need this).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
