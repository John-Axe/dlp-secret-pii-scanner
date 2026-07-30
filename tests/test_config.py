"""Tests for pyproject.toml [tool.dlp] config-file loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from dlp import config


def _write_pyproject(tmp_path: Path, tool_dlp_body: str) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(f"[tool.dlp]\n{tool_dlp_body}\n", encoding="utf-8")
    return path


def test_find_pyproject_walks_upward_from_a_nested_directory(tmp_path: Path):
    _write_pyproject(tmp_path, 'fail_on = "critical"')
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)

    found = config.find_pyproject(nested)

    assert found == tmp_path / "pyproject.toml"


def test_find_pyproject_returns_none_when_absent(tmp_path: Path):
    assert config.find_pyproject(tmp_path) is None


def test_load_config_is_a_documented_noop_without_tomllib(tmp_path: Path, monkeypatch):
    """Simulates the Python 3.10 fallback path (tomllib is stdlib-only from
    3.11) without needing to actually run on 3.10 - a real [tool.dlp]
    section must still be silently ignored, not raise, so the CLI keeps
    working exactly as it did before this feature existed."""
    monkeypatch.setattr(config, "tomllib", None)
    _write_pyproject(tmp_path, 'fail_on = "critical"\n')

    assert config.load_config(tmp_path) == {}


def test_load_config_returns_empty_dict_when_no_pyproject(tmp_path: Path):
    assert config.load_config(tmp_path) == {}


def test_load_config_returns_empty_dict_when_no_tool_dlp_section(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[tool.other]\nx = 1\n', encoding="utf-8")
    assert config.load_config(tmp_path) == {}


def test_load_config_reads_tool_dlp_table(tmp_path: Path):
    _write_pyproject(tmp_path, 'fail_on = "critical"\nentropy_threshold = 4.7\nno_color = true\n')

    cfg = config.load_config(tmp_path)

    assert cfg == {"fail_on": "critical", "entropy_threshold": 4.7, "no_color": True}


def test_load_config_rejects_unknown_key(tmp_path: Path):
    _write_pyproject(tmp_path, 'fial_on = "critical"\n')  # typo, deliberately

    with pytest.raises(ValueError, match="Unknown key"):
        config.load_config(tmp_path)


@pytest.mark.parametrize("bad_value", ['"critcal"', '"CRITICAL"', "1"])
def test_load_config_rejects_invalid_fail_on_value(tmp_path: Path, bad_value: str):
    _write_pyproject(tmp_path, f"fail_on = {bad_value}\n")

    with pytest.raises(ValueError, match="fail_on"):
        config.load_config(tmp_path)


def test_load_config_rejects_invalid_format_value(tmp_path: Path):
    _write_pyproject(tmp_path, 'format = "xml"\n')

    with pytest.raises(ValueError, match="format"):
        config.load_config(tmp_path)


def test_load_config_rejects_non_numeric_entropy_threshold(tmp_path: Path):
    _write_pyproject(tmp_path, 'entropy_threshold = "high"\n')

    with pytest.raises(ValueError, match="entropy_threshold"):
        config.load_config(tmp_path)


def test_load_config_rejects_bool_entropy_threshold(tmp_path: Path):
    """bool is technically an int subclass in Python - must not silently
    accept `entropy_threshold = true` as if it were the number 1."""
    _write_pyproject(tmp_path, "entropy_threshold = true\n")

    with pytest.raises(ValueError, match="entropy_threshold"):
        config.load_config(tmp_path)


@pytest.mark.parametrize("key", ["no_entropy", "no_color"])
def test_load_config_rejects_non_bool_flag_values(tmp_path: Path, key: str):
    _write_pyproject(tmp_path, f'{key} = "yes"\n')

    with pytest.raises(ValueError, match=key):
        config.load_config(tmp_path)


def test_load_config_accepts_all_known_keys_together(tmp_path: Path):
    _write_pyproject(
        tmp_path,
        'format = "json"\n'
        'fail_on = "low"\n'
        "no_entropy = true\n"
        "entropy_threshold = 5.0\n"
        "no_color = true\n"
        'base_ref = "origin/develop"\n',
    )

    cfg = config.load_config(tmp_path)

    assert cfg == {
        "format": "json",
        "fail_on": "low",
        "no_entropy": True,
        "entropy_threshold": 5.0,
        "no_color": True,
        "base_ref": "origin/develop",
    }
