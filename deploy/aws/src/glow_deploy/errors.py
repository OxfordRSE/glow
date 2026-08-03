"""Shared exception types for glow_deploy.

Kept separate from core.py so lower-level modules (binaries, github_api) can
raise the same error type as core.py without importing it back and creating a
circular import.
"""

from __future__ import annotations


class DeployError(RuntimeError):
    """Raised when deployment cannot continue."""
