"""Allowlist / suppression mechanism.

Two layers:
  1. `.dlpignore` file (gitignore-style glob patterns, one per line) found at
     the root of the scanned tree, skipping entire files/directories.
  2. Inline `# dlp-ignore` (or `// dlp-ignore`) trailing comment on a line,
     suppressing findings on that specific line.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

DLPIGNORE_FILENAME = ".dlpignore"
INLINE_MARKER = "dlp-ignore"


def load_dlpignore(root: Path) -> list[str]:
    ignore_file = root / DLPIGNORE_FILENAME
    if not ignore_file.is_file():
        return []
    patterns = []
    for raw in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def is_path_ignored(rel_path: str, patterns: list[str]) -> bool:
    normalized = rel_path.replace("\\", "/")
    for pattern in patterns:
        pat = pattern.rstrip("/")
        if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(normalized, f"*/{pattern}"):
            return True
        if fnmatch.fnmatch(normalized, f"{pat}/*") or fnmatch.fnmatch(normalized, f"*/{pat}/*"):
            return True
    return False


def has_inline_ignore(line: str) -> bool:
    return INLINE_MARKER in line
