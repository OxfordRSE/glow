"""Background nudge: check GitHub Releases for a newer tag than this build.

No auto-updater, no auto-download — just a small banner (see app.py/base.html).
These partner-org users won't know to check GitHub themselves.
"""

from __future__ import annotations

import httpx

_RELEASES_API = "https://api.github.com/repos/OxfordRSE/glow/releases/latest"


def latest_release_tag(timeout: float = 5.0) -> str | None:
    """Return the latest release tag, or None on any failure (best-effort)."""
    try:
        response = httpx.get(
            _RELEASES_API,
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
        return response.json()["tag_name"]
    except Exception:
        return None
