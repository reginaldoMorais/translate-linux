"""Reach the offline translation engine, which lives outside this environment.

Ubuntu does not package CTranslate2, so it cannot appear in the ``.deb``
dependencies. The application installs it into a private virtualenv instead and
extends ``sys.path`` to import it (RF-42). Loading it in-process rather than
shelling out is deliberate: it is the only way to keep a model resident between
captures, which is what makes the second translation instant.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from translate_linux.constants import data_dir

ENV_OVERRIDE = "TRANSLATE_LINUX_OFFLINE_VENV"
VENV_NAME = "venv-offline"

INSTALL_HINT = (
    "The offline translation engine is not installed.\n"
    "  Install it with: translate-linux --install-engine\n"
    "  (for development: make offline-engine)"
)


class EngineNotInstalled(Exception):
    """CTranslate2 could not be found in any known location."""

    def __init__(self) -> None:
        super().__init__(INSTALL_HINT)


class EngineInstallFailed(Exception):
    """The private virtualenv could not be created or populated."""


def default_venv() -> Path:
    """Return the location the application installs the engine into."""
    return data_dir() / VENV_NAME


def candidate_venvs() -> list[Path]:
    """Return every place the engine may live, most specific first."""
    candidates: list[Path] = []

    override = os.environ.get(ENV_OVERRIDE)
    if override:
        candidates.append(Path(override))

    candidates.append(default_venv())

    # A checkout being developed against: src/translate_linux/translate/ -> repo
    repo_root = Path(__file__).resolve().parents[3]
    candidates.append(repo_root / f".{VENV_NAME}")

    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def site_packages_of(venv: Path) -> Path | None:
    """Return the ``site-packages`` directory of ``venv`` that holds the engine."""
    for lib in sorted((venv / "lib").glob("python3.*/site-packages")):
        if (lib / "ctranslate2").is_dir():
            return lib
    return None


def find_engine() -> Path | None:
    """Return the ``site-packages`` directory holding CTranslate2, if any."""
    for venv in candidate_venvs():
        found = site_packages_of(venv)
        if found is not None:
            return found
    return None


def is_available() -> bool:
    """Report whether the engine can be loaded without installing anything."""
    if _already_importable():
        return True
    return find_engine() is not None


def load() -> tuple[Any, Any]:
    """Import and return ``(ctranslate2, sentencepiece)``.

    Raises:
        EngineNotInstalled: the engine is not present in any known location.
    """
    if not _already_importable():
        location = find_engine()
        if location is None:
            raise EngineNotInstalled
        if str(location) not in sys.path:
            sys.path.append(str(location))

    try:
        import ctranslate2
        import sentencepiece
    except ImportError as error:  # pragma: no cover - guarded by find_engine
        raise EngineNotInstalled from error
    return ctranslate2, sentencepiece


def _already_importable() -> bool:
    from importlib.util import find_spec

    try:
        return find_spec("ctranslate2") is not None and find_spec("sentencepiece") is not None
    except (ImportError, ValueError):
        return False


REQUIREMENTS = ("ctranslate2>=4.0,<5", "sentencepiece>=0.2,<0.3")


def install(target: Path | None = None) -> Path:
    """Create the private virtualenv and install the engine into it.

    Returns the ``site-packages`` directory the engine landed in.
    """
    venv = target or default_venv()
    venv.parent.mkdir(parents=True, exist_ok=True)

    steps: list[list[str]] = [
        [sys.executable, "-m", "venv", str(venv)],
        [str(venv / "bin" / "python"), "-m", "pip", "install", "--upgrade", "pip"],
        [str(venv / "bin" / "python"), "-m", "pip", "install", *REQUIREMENTS],
    ]
    for command in steps:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise EngineInstallFailed(
                f"'{' '.join(command[:3])}...' exited with {completed.returncode}:\n"
                f"{completed.stderr.strip()[:500]}"
            )

    location = site_packages_of(venv)
    if location is None:
        raise EngineInstallFailed("The engine was installed but cannot be found afterwards.")
    return location


def describe() -> str:
    """Return a short human-readable status line, for diagnostics."""
    if _already_importable():
        return "installed (importable from the current environment)"
    location = find_engine()
    if location is None:
        return f"not installed (looked in: {', '.join(str(p) for p in candidate_venvs())})"
    return f"installed at {location}"


__all__ = [
    "EngineInstallFailed",
    "EngineNotInstalled",
    "candidate_venvs",
    "default_venv",
    "describe",
    "find_engine",
    "install",
    "is_available",
    "load",
    "site_packages_of",
]
