"""Background nudge: check for a newer gui-v* tag than this build.

No auto-updater, no auto-download — just a small banner (see app.py/base.html).
These partner-org users won't know to check GitHub themselves.

Compares real semantic versions across every gui-v* tag rather than trusting
GitHub's "latest release" designation + string inequality — a hotfix tagged
out of chronological order, or a draft/prerelease marked "latest" by mistake,
would otherwise be missed or misreported.
"""

from __future__ import annotations

from glow_deploy import core, github_api, versions

_GUI_TAG_PREFIX = "gui-v"


def latest_release_tag(current_version: str, timeout: float = 5.0) -> str | None:
    """Return the highest gui-v* tag newer than current_version, or None if
    current_version is unparseable (e.g. "dev") or already the newest."""
    current = versions.parse(current_version, _GUI_TAG_PREFIX)
    if current is None:
        return None

    tags = github_api.list_tags_with_prefix(
        core.DEFAULT_GIT_REPO_URL, _GUI_TAG_PREFIX, timeout=timeout
    )
    newer = [tag for tag in tags if versions.parse(tag, _GUI_TAG_PREFIX) > current]
    return versions.highest(newer, _GUI_TAG_PREFIX) if newer else None
