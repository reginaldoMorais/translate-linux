"""Start the application with the desktop session.

An XDG autostart entry rather than a systemd user unit: it is the convention
for tray applications, and it inherits the session environment -- the Wayland
socket, the D-Bus address, the display -- which a user unit only gets after
extra plumbing.

The delay matters. The tray icon needs a StatusNotifierWatcher, and on GNOME
that is provided by a shell extension which is not ready the instant the
session starts. Without it the application launches, finds no host, and sits
there invisible.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from translate_linux.constants import APP_NAME, APP_TITLE

DESKTOP_FILE = f"{APP_NAME}.desktop"
STARTUP_DELAY_SECONDS = 5


def autostart_dir() -> Path:
    """Return the XDG autostart directory for this user."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "autostart"


def entry_path(directory: Path | None = None) -> Path:
    return (directory or autostart_dir()) / DESKTOP_FILE


def executable() -> str:
    """Return the command that starts the tray, preferring an installed one."""
    installed = shutil.which(APP_NAME)
    if installed:
        return installed
    # A checkout: point at the console script inside the virtualenv.
    candidate = Path(__file__).resolve().parents[2] / ".venv" / "bin" / APP_NAME
    return str(candidate) if candidate.exists() else APP_NAME


def desktop_entry(command: str | None = None) -> str:
    """Render the autostart desktop entry."""
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            f"Name={APP_TITLE}",
            "Comment=Traduz o texto de uma região da tela",
            f"Exec={command or executable()} --tray",
            "Icon=accessories-dictionary",
            "Terminal=false",
            "X-GNOME-Autostart-enabled=true",
            f"X-GNOME-Autostart-Delay={STARTUP_DELAY_SECONDS}",
            "",
        ]
    )


def enable(directory: Path | None = None, command: str | None = None) -> Path:
    """Install the autostart entry and return where it landed."""
    target = entry_path(directory)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(desktop_entry(command), encoding="utf-8")
    return target


def disable(directory: Path | None = None) -> bool:
    """Remove the autostart entry; report whether one was there."""
    target = entry_path(directory)
    if not target.is_file():
        return False
    target.unlink()
    return True


def is_enabled(directory: Path | None = None) -> bool:
    """Report whether the application is set to start with the session."""
    target = entry_path(directory)
    if not target.is_file():
        return False
    try:
        content = target.read_text(encoding="utf-8")
    except OSError:
        return False
    return "X-GNOME-Autostart-enabled=false" not in content


def apply(enabled: bool, directory: Path | None = None) -> bool:
    """Make the on-disk state match ``enabled``; report the resulting state."""
    if enabled:
        enable(directory)
        return True
    disable(directory)
    return False
