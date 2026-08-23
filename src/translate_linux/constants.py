"""Identifiers and filesystem locations shared across the application."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

APP_NAME = "translate-linux"
APP_ID = "io.github.rmorais.TranslateLinux"
APP_TITLE = "Translate Linux"


def runtime_dir() -> Path:
    """Return a private directory for short-lived files.

    Captures contain whatever was on screen, so they belong in the per-session
    runtime directory with owner-only permissions, not in a shared ``/tmp``.
    """
    base = os.environ.get("XDG_RUNTIME_DIR")
    root = Path(base) if base else Path(tempfile.gettempdir())
    directory = root / APP_NAME
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


def data_dir() -> Path:
    """Return the directory for data that must survive a reboot."""
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    directory = root / APP_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def cache_dir() -> Path:
    """Return the directory for data that can be regenerated at any time."""
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    directory = root / APP_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory
