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


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    text = fdp.ConsumeUnicodeNoSurrogates(len(data))
    for line in text.splitlines():
        detectors.scan_line_entropy(line, 3.5)
        for det in detectors.REGEX_DETECTORS:
            det.scan_line(line)


if __name__ == "__main__":
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()
