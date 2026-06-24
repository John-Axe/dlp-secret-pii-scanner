"""Walks a directory tree (or scans a single file) and runs all detectors."""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

from . import detectors, ignore

DEFAULT_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache"}
DEFAULT_ENTROPY_THRESHOLD = 4.3
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024


@dataclasses.dataclass(frozen=True)
class Finding:
    file: str
    line: int
    column: int
    rule_id: str
    rule_name: str
    severity: str
    redacted: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @property
    def fingerprint(self) -> str:
        """Stable identity for this finding, used by baseline mode and SARIF
        partialFingerprints. Deliberately excludes the line number so it
        survives unrelated edits earlier in the file.
        """
        digest = hashlib.sha256(f"{self.file}|{self.rule_id}|{self.redacted}".encode()).hexdigest()
        return digest[:16]


def _is_probably_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def _iter_files(root: Path, ignore_patterns: list[str], ignore_base: Path):
    if root.is_file():
        if root.is_relative_to(ignore_base):
            rel = root.relative_to(ignore_base).as_posix()
        else:
            rel = root.name
        if ignore.is_path_ignored(rel, ignore_patterns):
            return
        yield root
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in DEFAULT_SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if ignore.is_path_ignored(rel, ignore_patterns):
            continue
        yield path


def scan_file(
    path: Path,
    *,
    display_path: str | None = None,
    enable_entropy: bool = True,
    entropy_threshold: float = DEFAULT_ENTROPY_THRESHOLD,
) -> list[Finding]:
    display = display_path if display_path is not None else str(path)
    try:
        data = path.read_bytes()
    except OSError:
        return []
    if not data or _is_probably_binary(data) or len(data) > MAX_FILE_SIZE_BYTES:
        return []

    text = data.decode("utf-8", errors="ignore")
    findings: list[Finding] = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        if ignore.has_inline_ignore(line):
            continue

        for det in detectors.REGEX_DETECTORS:
            for match in det.scan_line(line):
                findings.append(
                    Finding(
                        file=display,
                        line=line_no,
                        column=match.start + 1,
                        rule_id=det.rule_id,
                        rule_name=det.name,
                        severity=det.severity,
                        redacted=detectors.redact(match.text),
                    )
                )

        if enable_entropy:
            for match in detectors.scan_line_entropy(line, entropy_threshold):
                findings.append(
                    Finding(
                        file=display,
                        line=line_no,
                        column=match.start + 1,
                        rule_id=detectors.ENTROPY_RULE_ID,
                        rule_name="High Entropy String",
                        severity=detectors.ENTROPY_SEVERITY,
                        redacted=detectors.redact(match.text),
                    )
                )

    return findings


def scan_paths(
    paths: list[Path],
    *,
    enable_entropy: bool = True,
    entropy_threshold: float = DEFAULT_ENTROPY_THRESHOLD,
    ignore_root: Path | None = None,
) -> list[Finding]:
    """Scans files and/or directories.

    `ignore_root` anchors where `.dlpignore` is loaded from and what
    individual file paths are matched against. It matters for callers like
    `--diff-only` that pass a list of individual changed files rather than
    a single directory: without a shared root, each file would only ever
    look for a `.dlpignore` next to itself, so a repo-root `.dlpignore`
    would never apply. Defaults to each path's own directory (or parent,
    for a single file), preserving the original single-root behavior.
    """
    findings: list[Finding] = []
    resolved_ignore_root = ignore_root.resolve() if ignore_root is not None else None
    ignore_cache: dict[Path, list[str]] = {}

    for root in paths:
        root = root.resolve()
        ignore_base = resolved_ignore_root or (root if root.is_dir() else root.parent)
        if ignore_base not in ignore_cache:
            ignore_cache[ignore_base] = ignore.load_dlpignore(ignore_base)
        ignore_patterns = ignore_cache[ignore_base]

        for file_path in _iter_files(root, ignore_patterns, ignore_base):
            try:
                display = str(file_path.relative_to(Path.cwd()))
            except ValueError:
                display = str(file_path)
            findings.extend(
                scan_file(
                    file_path,
                    display_path=display,
                    enable_entropy=enable_entropy,
                    entropy_threshold=entropy_threshold,
                )
            )
    return findings
