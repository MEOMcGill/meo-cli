"""Tests for config load/save roundtrip."""

from __future__ import annotations

from pathlib import Path

import pytest

from meo_cli import config


@pytest.fixture(autouse=True)
def _tmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect config to a temp directory."""
    cfg_dir = tmp_path / "meo"
    cfg_dir.mkdir()
    monkeypatch.setattr(config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", cfg_dir / "config.toml")


def test_load_defaults_when_no_file():
    cfg = config.load_config()
    assert cfg["base_url"] == "https://api.meoinsightshub.net"
    assert cfg["username"] == ""
    assert cfg["default_format"] == "jsonl"


def test_save_and_load_roundtrip():
    cfg = config.load_config()
    cfg["base_url"] = "https://custom.example.com"
    cfg["username"] = "alice"
    config.save_config(cfg)

    loaded = config.load_config()
    assert loaded["base_url"] == "https://custom.example.com"
    assert loaded["username"] == "alice"


def test_get_base_url_override():
    assert config.get_base_url("https://override.example.com/") == "https://override.example.com"


def test_get_base_url_from_config():
    cfg = config.load_config()
    cfg["base_url"] = "https://saved.example.com"
    config.save_config(cfg)
    assert config.get_base_url() == "https://saved.example.com"


def test_config_path():
    p = config.config_path()
    assert p.name == "config.toml"
