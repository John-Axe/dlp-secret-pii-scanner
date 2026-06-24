"""Tests for diff-only mode's changed-files detection against a real git repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

from dlp.diff import changed_files


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(root: Path) -> None:
    _git("init", "-q", cwd=root)
    _git("config", "user.email", "test@example.com", cwd=root)
    _git("config", "user.name", "Test", cwd=root)


def test_changed_files_detects_modified_and_new_files(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("original\n")
    (tmp_path / "b.txt").write_text("untouched\n")
    _git("add", "-A", cwd=tmp_path)
    _git("commit", "-q", "-m", "base", cwd=tmp_path)

    (tmp_path / "a.txt").write_text("modified\n")
    (tmp_path / "c.txt").write_text("new file\n")
    _git("add", "-A", cwd=tmp_path)
    _git("commit", "-q", "-m", "change", cwd=tmp_path)

    changed = changed_files("HEAD~1", tmp_path)
    changed_names = {p.name for p in changed}

    assert changed_names == {"a.txt", "c.txt"}
    assert "b.txt" not in changed_names


def test_changed_files_empty_when_no_diff(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("only commit\n")
    _git("add", "-A", cwd=tmp_path)
    _git("commit", "-q", "-m", "base", cwd=tmp_path)

    changed = changed_files("HEAD", tmp_path)

    assert changed == []


def test_changed_files_returns_empty_for_nonexistent_ref(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("x\n")
    _git("add", "-A", cwd=tmp_path)
    _git("commit", "-q", "-m", "base", cwd=tmp_path)

    changed = changed_files("not-a-real-ref", tmp_path)

    assert changed == []


def test_changed_files_returns_empty_when_not_a_git_repo(tmp_path: Path):
    changed = changed_files("HEAD", tmp_path)

    assert changed == []
