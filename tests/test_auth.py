"""Tests for auth token management with mocked keyring."""

from __future__ import annotations

import pytest

from meo_cli import auth, config


# In-memory keyring mock
class FakeKeyring:
    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, user: str, pw: str) -> None:
        self._store[(service, user)] = pw

    def get_password(self, service: str, user: str) -> str | None:
        return self._store.get((service, user))

    def delete_password(self, service: str, user: str) -> None:
        if (service, user) not in self._store:
            raise Exception("not found")
        del self._store[(service, user)]


@pytest.fixture(autouse=True)
def _mock_keyring(monkeypatch: pytest.MonkeyPatch, tmp_path):
    fake = FakeKeyring()
    monkeypatch.setattr(auth, "keyring", fake)

    # Also redirect config so load_config works
    cfg_dir = tmp_path / "meo"
    cfg_dir.mkdir()
    monkeypatch.setattr(config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", cfg_dir / "config.toml")


def test_save_and_load_token():
    auth.save_token("bob", "tok123")
    assert auth.load_token("bob") == "tok123"


def test_load_token_missing():
    assert auth.load_token("nobody") is None


def test_delete_token():
    auth.save_token("bob", "tok123")
    auth.delete_token("bob")
    assert auth.load_token("bob") is None


def test_delete_token_noop_when_missing():
    # Should not raise
    auth.delete_token("ghost")


def test_require_token_exits_when_missing():
    with pytest.raises((SystemExit, Exception)):
        auth.require_token("nobody")


def test_require_token_returns_when_present():
    auth.save_token("alice", "tok456")
    assert auth.require_token("alice") == "tok456"


def test_load_token_uses_config_username():
    """load_token() with no arg reads username from config."""
    cfg = config.load_config()
    cfg["username"] = "carol"
    config.save_config(cfg)

    auth.save_token("carol", "tok789")
    assert auth.load_token() == "tok789"
