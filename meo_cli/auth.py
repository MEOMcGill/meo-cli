"""Authentication: login, logout, token management via OS keychain."""

from __future__ import annotations

import keyring
import typer

from meo_cli.config import load_config

SERVICE_NAME = "meo-cli"


def save_token(username: str, token: str) -> None:
    """Store access token in the OS keychain."""
    keyring.set_password(SERVICE_NAME, username, token)


def load_token(username: str | None = None) -> str | None:
    """Load access token from keychain. Returns None if not found."""
    user = username or load_config().get("username", "")
    if not user:
        return None
    return keyring.get_password(SERVICE_NAME, user)


def delete_token(username: str | None = None) -> None:
    """Remove access token from keychain."""
    user = username or load_config().get("username", "")
    if not user:
        return
    try:
        keyring.delete_password(SERVICE_NAME, user)
    except Exception:
        pass


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
