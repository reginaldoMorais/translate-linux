"""Capture a screen region, recognise its text and translate it.

The public surface of the package is intentionally small: the version string
below is the single source of truth for the release pipeline, which validates
it against the git tag before publishing an artifact.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.1.0"
