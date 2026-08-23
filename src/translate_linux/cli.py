"""Command-line entry point.

Milestone M0 ships only ``--version``; the capture pipeline arrives in M1 and
the D-Bus single-instance activation described in RF-09/RF-10 in M2.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from translate_linux import __version__

PROG = "translate-linux"


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``translate-linux`` command."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Capture a screen region, recognise its text and translate it.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{PROG} {__version__}",
        help="show the installed version and exit",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return a process exit code."""
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through __main__.py
    sys.exit(main())
