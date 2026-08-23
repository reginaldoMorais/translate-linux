#!/usr/bin/env python3
"""Answer PA-04 / R3: what does an interactive portal capture leave behind?

The specification assumes that ``interactive: true`` hands the image to the
requesting application and nothing else -- no copy in ~/Pictures/Screenshots,
nothing on the clipboard. That assumption has to be checked on a real GNOME
session rather than reasoned about, because the answer decides whether the
application needs a cleanup step.

Run it, select any region, and read the report:

    .venv/bin/python scripts/verify_portal_behaviour.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from translate_linux.capture.portal import (
    CaptureCancelled,
    CaptureError,
    capture_interactive,
    screenshot_portal_version,
)

SCREENSHOT_DIRS = [
    Path.home() / "Pictures" / "Screenshots",
    Path.home() / "Imagens" / "Capturas de tela",
    Path.home() / "Pictures",
]


def snapshot(directory: Path) -> set[Path]:
    return set(directory.iterdir()) if directory.is_dir() else set()


def clipboard_types() -> str:
    try:
        result = subprocess.run(
            ["wl-paste", "--list-types"], capture_output=True, text=True, timeout=5, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "(wl-paste unavailable)"
    return " ".join(result.stdout.split()) or "(empty)"


def main() -> int:
    print(f"session         : {os.environ.get('XDG_SESSION_TYPE', 'unknown')}")
    print(f"desktop         : {os.environ.get('XDG_CURRENT_DESKTOP', 'unknown')}")
    try:
        print(f"portal version  : {screenshot_portal_version()}")
    except CaptureError as error:
        print(f"portal version  : unavailable ({error})")
        return 1

    print(f"clipboard before: {clipboard_types()}")
    before = {directory: snapshot(directory) for directory in SCREENSHOT_DIRS}

    print("\n>>> Select any region containing text.\n")
    try:
        path = capture_interactive()
    except CaptureCancelled:
        print("Cancelled; nothing to report.")
        return 0
    except CaptureError as error:
        print(f"Capture failed: {error}")
        return 1

    print(f"returned path   : {path}")
    print(f"  exists        : {path.exists()}")
    if path.exists():
        stat = path.stat()
        print(f"  size          : {stat.st_size} bytes")
        print(f"  mode          : {stat.st_mode & 0o777:o}")
    print(f"clipboard after : {clipboard_types()}")

    print("\nNew files in the screenshot directories:")
    leaked = False
    for directory in SCREENSHOT_DIRS:
        added = snapshot(directory) - before[directory]
        if added:
            leaked = True
            for item in sorted(added):
                print(f"  {item}")
    if not leaked:
        print("  (none)")

    print("\nVerdict")
    print(f"  side copy saved by the desktop : {'YES -> R3 confirmed' if leaked else 'no'}")
    print(f"  file left for the caller       : {'yes' if path.exists() else 'no'}")
    print(f"\nThe capture is still at {path}; delete it once you are done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
