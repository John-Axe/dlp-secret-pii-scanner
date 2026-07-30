"""Loads optional per-project defaults from pyproject.toml's [tool.dlp]
table, so a team doesn't have to repeat CLI flags on every invocation or
wrap them in a Makefile/CI step. CLI flags always win when both are given -
config only fills in what wasn't explicitly passed on the command line.

Uses the stdlib tomllib (Python 3.11+) rather than adding a TOML-parsing
runtime dependency, matching this repo's deliberately zero-dependency
design (see pyproject.toml, shared_finding.py's docstring for the same
principle applied elsewhere). On Python 3.10 - still within this project's
declared `requires-python = ">=3.10"` - config loading is a documented
no-op (returns {}) rather than a hard failure: the CLI still works exactly
as it did before this feature existed, just without this one convenience.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import severity

try:
    import tomllib  # type: ignore[import-not-found]  # 3.11+ only; see module docstring
except ModuleNotFoundError:  # Python 3.10
    tomllib = None

CONFIG_TABLE = "dlp"

# Explicit allowlist rather than accepting arbitrary keys, so a typo in
# pyproject.toml (e.g. "fail-on" instead of "fail_on") fails loudly instead
# of silently doing nothing - the same reasoning CONTRIBUTING.md documents
# for why suppressions are explicit rather than worked around silently.
_ALLOWED_KEYS = {"format", "fail_on", "no_entropy", "entropy_threshold", "no_color", "base_ref"}

_CHOICE_VALUES: dict[str, set[str]] = {
    "format": {"table", "json", "sarif"},
    "fail_on": {*severity.ORDER, "none"},
}
_BOOL_KEYS = {"no_entropy", "no_color"}


def find_pyproject(start: Path) -> Path | None:
    """Walks upward from `start` looking for a pyproject.toml, the same
    direction git/pre-commit/most other project-config tools search in."""
    current = start.resolve()
    for directory in (current, *current.parents):
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def _validate(table: dict[str, Any], path: Path) -> None:
    unknown = set(table) - _ALLOWED_KEYS
    if unknown:
        raise ValueError(
            f"Unknown key(s) in [tool.{CONFIG_TABLE}] ({path}): {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(_ALLOWED_KEYS))}."
        )
    for key, allowed in _CHOICE_VALUES.items():
        if key in table and table[key] not in allowed:
            raise ValueError(
                f"[tool.{CONFIG_TABLE}] '{key}' in {path} is {table[key]!r}; "
                f"expected one of: {', '.join(sorted(allowed))}."
            )
    for key in _BOOL_KEYS:
        if key in table and not isinstance(table[key], bool):
            raise ValueError(f"[tool.{CONFIG_TABLE}] '{key}' in {path} must be true or false.")
    if "entropy_threshold" in table:
        value = table["entropy_threshold"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"[tool.{CONFIG_TABLE}] 'entropy_threshold' in {path} must be a number.")


def load_config(start: Path | None = None) -> dict[str, Any]:
    """Returns the [tool.dlp] table from the nearest pyproject.toml walking
    up from `start` (default: cwd), or {} if tomllib isn't available
    (Python 3.10), no pyproject.toml is found, or it has no [tool.dlp]
    section.

    Raises ValueError for an unknown key or an invalid value - see module
    docstring for why this fails loudly rather than silently ignoring it.
    """
    if tomllib is None:
        return {}
    path = find_pyproject(start or Path.cwd())
    if path is None:
        return {}
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    table: dict[str, Any] = data.get("tool", {}).get(CONFIG_TABLE, {})
    _validate(table, path)
    return table
