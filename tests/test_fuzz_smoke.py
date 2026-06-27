"""Smoke test: import and call the fuzz target without the atheris runtime.

Catches syntax errors and import failures in fuzz/fuzz_scanner.py on every
pytest run, before the dedicated CI fuzz job runs.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
import unittest.mock
from pathlib import Path


def _make_atheris_stub() -> types.ModuleType:
    """Minimal atheris stub that satisfies the fuzz target's imports."""
    stub = types.ModuleType("atheris")

    class _FuzzedDataProvider:
        def __init__(self, data: bytes):
            self._data = data

        def ConsumeUnicodeNoSurrogates(self, count: int) -> str:
            return self._data.decode("utf-8", errors="replace")[:count]

    class _instrument_imports:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    stub.FuzzedDataProvider = _FuzzedDataProvider
    stub.instrument_imports = _instrument_imports
    stub.Setup = lambda argv, fn: None
    stub.Fuzz = lambda: None
    return stub


_FUZZ_SCRIPT = Path(__file__).parent.parent / "fuzz" / "fuzz_scanner.py"


def test_fuzz_target_imports_and_runs():
    atheris_stub = _make_atheris_stub()
    spec = importlib.util.spec_from_file_location("fuzz_scanner", _FUZZ_SCRIPT)
    with unittest.mock.patch.dict(sys.modules, {"atheris": atheris_stub}):
        fuzz_mod = importlib.util.module_from_spec(spec)
        sys.modules.pop("fuzz_scanner", None)
        spec.loader.exec_module(fuzz_mod)

        fuzz_mod.TestOneInput(b"AKIAIOSFODNN7EXAMPLE")
        fuzz_mod.TestOneInput(b"password = 'hunter2'")
        fuzz_mod.TestOneInput(b"")
        fuzz_mod.TestOneInput(b"\x00\x01\x02binary")
