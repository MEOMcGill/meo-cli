"""Non-secret configuration stored in ~/.config/meo/config.toml."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w

CONFIG_DIR = Path(user_config_dir("meo", ensure_exists=True))
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG: dict[str, Any] = {
    "base_url": "https://api.meoinsightshub.net",
    "username": "",
    "default_format": "jsonl",
}


def config_path() -> Path:
    """Return path to the config file."""
    return CONFIG_FILE


def load_config() -> dict[str, Any]:
    """Load config from disk, returning defaults for missing keys."""
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "rb") as f:
            cfg.update(tomllib.load(f))
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    """Write config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "wb") as f:
        tomli_w.dump(cfg, f)


def get_base_url(override: str | None = None) -> str:
    """Return base URL from override, config, or default."""
    if override:
        return override.rstrip("/")
    return load_config().get("base_url", DEFAULT_CONFIG["base_url"]).rstrip("/")
