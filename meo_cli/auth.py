"""Authentication: login, logout, token management."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from meo_cli.config import CONFIG_DIR, load_config

SERVICE_NAME = "meo-cli"
_TOKEN_FILE = CONFIG_DIR / "tokens.json"


def _load_tokens() -> dict[str, str]:
    if _TOKEN_FILE.exists():
        try:
            return json.loads(_TOKEN_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_tokens(tokens: dict[str, str]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(json.dumps(tokens))
    _TOKEN_FILE.chmod(0o600)


def save_token(username: str, token: str) -> None:
    """Store access token."""
    try:
        import keyring
        import keyring.errors

        keyring.set_password(SERVICE_NAME, username, token)
        return
    except Exception:
        pass
    # Fallback: file-based storage
    tokens = _load_tokens()
    tokens[username] = token
    _save_tokens(tokens)


def load_token(username: str | None = None) -> str | None:
    """Load access token. Returns None if not found."""
    user = username or load_config().get("username", "")
    if not user:
        return None
    try:
        import keyring

        val = keyring.get_password(SERVICE_NAME, user)
        if val:
            return val
    except Exception:
        pass
    return _load_tokens().get(user)


def delete_token(username: str | None = None) -> None:
    """Remove access token."""
    user = username or load_config().get("username", "")
    if not user:
        return
    try:
        import keyring

        keyring.delete_password(SERVICE_NAME, user)
    except Exception:
        pass
    tokens = _load_tokens()
    tokens.pop(user, None)
    _save_tokens(tokens)


def require_token(username: str | None = None) -> str:
    """Load token or exit with a helpful message."""
    token = load_token(username)
    if not token:
        typer.echo(
            "Not authenticated. Run 'meo login' first.",
            err=True,
        )
        raise typer.Exit(1)
    return token