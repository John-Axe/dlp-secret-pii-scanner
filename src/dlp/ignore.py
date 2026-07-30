"""Allowlist / suppression mechanism.

Two layers:
  1. `.dlpignore` file (gitignore-style glob patterns, one per line) found at
     the root of the scanned tree, skipping entire files/directories.
  2. Inline `# dlp-ignore`, `// dlp-ignore`, or `<!-- dlp-ignore -->` trailing
     comment on a line, suppressing findings on that specific line - three
     comment styles so every common file type (code, C-family, Markdown/HTML)
     has a native-looking option.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

DLPIGNORE_FILENAME = ".dlpignore"
_INLINE_IGNORE_RE = re.compile(r"(?:#|//|<!--)\s*dlp-ignore\b")


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
    return bool(_INLINE_IGNORE_RE.search(line))
