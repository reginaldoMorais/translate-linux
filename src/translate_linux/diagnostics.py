"""Report the state of the environment the application depends on.

There is no telemetry, by design, so supporting an installation means being able
to ask for one command's output. Every check answers a question that has already
gone wrong at least once during development.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from translate_linux import __version__

OK = "ok"
WARN = "warn"
FAIL = "fail"


@dataclass(frozen=True, slots=True)
class Check:
    """One line of the diagnostic report."""

    label: str
    value: str
    status: str = OK

    @property
    def marker(self) -> str:
        return {OK: "  ", WARN: " !", FAIL: " x"}.get(self.status, "  ")


def _session() -> list[Check]:
    session_type = os.environ.get("XDG_SESSION_TYPE", "unknown")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
    return [
        Check("version", __version__),
        Check("session type", session_type, OK if session_type != "unknown" else WARN),
        Check("desktop", desktop),
    ]


def _portal() -> list[Check]:
    from translate_linux.capture.portal import CaptureError, screenshot_portal_version

    try:
        version = screenshot_portal_version()
    except CaptureError as error:
        return [Check("screenshot portal", f"unavailable ({error})", FAIL)]

    status = OK if version >= 2 else FAIL
    note = "" if version >= 2 else " (version 2 is required for region selection)"
    return [Check("screenshot portal", f"version {version}{note}", status)]


def _tray() -> list[Check]:
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio

    from translate_linux.tray import watcher_is_running

    try:
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except Exception:
        return [Check("tray host", "no session bus", FAIL)]

    running = watcher_is_running(connection)
    return [
        Check(
            "tray host",
            "running" if running else "absent (the tray icon will not appear)",
            OK if running else WARN,
        )
    ]


def _tesseract() -> list[Check]:
    from translate_linux.ocr.tesseract import TesseractError, available_languages

    if shutil.which("tesseract") is None:
        return [Check("tesseract", "not installed (sudo apt install tesseract-ocr)", FAIL)]

    try:
        version = subprocess.run(
            ["tesseract", "--version"], capture_output=True, text=True, timeout=10, check=False
        ).stdout.splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        version = "installed"

    checks = [Check("tesseract", version)]
    try:
        languages = available_languages()
    except TesseractError as error:
        checks.append(Check("ocr languages", str(error), FAIL))
    else:
        checks.append(
            Check(
                "ocr languages",
                ", ".join(languages) or "none",
                OK if languages else FAIL,
            )
        )
    return checks


def _translation() -> list[Check]:
    from translate_linux.constants import data_dir
    from translate_linux.translate import engine, models

    available = engine.is_available()
    checks = [Check("offline engine", engine.describe(), OK if available else FAIL)]
    if not available:
        # Name every path that was searched: "not installed" after a successful
        # install means it landed somewhere this process does not look.
        checks.append(
            Check(
                "searched for engine in",
                " | ".join(str(path) for path in engine.candidate_venvs()),
                WARN,
            )
        )
    checks.append(Check("data directory", str(data_dir())))

    installed = models.installed()
    if installed:
        checks.append(
            Check("offline models", ", ".join(f"{m.pair} v{m.version}" for m in installed))
        )
    else:
        checks.append(
            Check(
                "offline models",
                "none (translate-linux --install-model en-pt)",
                WARN,
            )
        )
    return checks


def _settings() -> list[Check]:
    from translate_linux.autostart import is_enabled
    from translate_linux.config import SchemaMissing, Settings

    try:
        settings = Settings()
    except SchemaMissing as error:
        return [Check("settings", str(error).splitlines()[0], FAIL)]

    checks = [
        Check("provider", settings.provider),
        Check("target language", settings.target_language),
        Check("ocr configuration", f"{settings.ocr_languages}, psm {settings.ocr_psm}"),
        Check("autostart", "enabled" if is_enabled() else "disabled"),
    ]

    from translate_linux.shortcuts import ShortcutError, current_binding

    try:
        binding = current_binding()
    except ShortcutError as error:
        checks.append(Check("global shortcut", str(error), WARN))
    else:
        checks.append(Check("global shortcut", binding or "not registered"))
    return checks


SECTIONS: tuple[Callable[[], list[Check]], ...] = (
    _session,
    _portal,
    _tray,
    _tesseract,
    _translation,
    _settings,
)


def collect() -> list[Check]:
    """Run every check, surviving any that fails outright."""
    results: list[Check] = []
    for section in SECTIONS:
        try:
            results.extend(section())
        except Exception as error:
            results.append(Check(section.__name__.strip("_"), f"check failed: {error}", FAIL))
    return results


def render(checks: list[Check]) -> str:
    """Format the report for a terminal."""
    width = max((len(check.label) for check in checks), default=0)
    lines = [f"{check.marker} {check.label.ljust(width)} : {check.value}" for check in checks]

    problems = [check for check in checks if check.status == FAIL]
    warnings = [check for check in checks if check.status == WARN]
    lines.append("")
    if problems:
        lines.append(f"{len(problems)} problem(s) will stop the application from working.")
    elif warnings:
        lines.append(f"{len(warnings)} warning(s); the application should still work.")
    else:
        lines.append("Everything checks out.")
    return "\n".join(lines)


def has_failures(checks: list[Check]) -> bool:
    return any(check.status == FAIL for check in checks)
