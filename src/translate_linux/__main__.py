"""Allow the package to be executed with ``python -m translate_linux``."""

from __future__ import annotations

import sys

from translate_linux.cli import main

if __name__ == "__main__":
    sys.exit(main())
