#!/usr/bin/env python3
"""Atheris fuzz target for the DLP scanner's core detection logic.

Exercises every regex detector and the entropy scanner with arbitrary
text so crashes and hangs in pattern matching surface during CI.

Usage (manual):
    pip install atheris
    python fuzz/fuzz_scanner.py -runs=10000

Usage (via corpus):
    python fuzz/fuzz_scanner.py corpus/ -runs=0
"""

import sys

import atheris

with atheris.instrument_imports():
    from dlp import detectors
    from dlp.ignore import has_inline_ignore, is_path_ignored
    from dlp.scanner import _is_probably_binary


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    text = fdp.ConsumeUnicodeNoSurrogates(len(data))

    _is_probably_binary(data)

    first_line = text.split("\n")[0] if text else ""
    is_path_ignored(first_line, ["tests/*", "*.log", "vendor/*"])

    for line in text.splitlines():
        has_inline_ignore(line)
        detectors.scan_line_entropy(line, 3.5)
        for det in detectors.REGEX_DETECTORS:
            det.scan_line(line)


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
