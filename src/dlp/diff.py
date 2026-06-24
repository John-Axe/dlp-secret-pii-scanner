"""Diff-only mode: restrict a scan to files changed against a base ref,
so PR checks only look at what the PR actually touches.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def changed_files(base_ref: str, root: Path) -> list[Path]:
    """Files added/copied/modified/renamed between base_ref and the working
    tree, as absolute paths. Returns [] if root isn't a git repo, base_ref
    doesn't exist, or git isn't available - callers should treat that as
    "nothing to scan" rather than an error.
    """
    root = Path(root)
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", base_ref],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return []

    files = []
    for line in result.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        path = root / rel
        if path.is_file():
            files.append(path)
    return files
