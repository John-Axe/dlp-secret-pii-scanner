"""Enables `python -m dlp` as an alternative to the `dlp-scan` console script —
useful when the package is installed but the script isn't on PATH (e.g. inside
a container that only does `pip install --target`)."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
