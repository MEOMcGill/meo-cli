"""Authentication: login, logout, token management via OS keychain."""

from __future__ import annotations

import keyring
import keyring.errors
import typer

from meo_cli.config import load_config

SERVICE_NAME = "meo-cli"


def _ensure_backend() -> None:
    """Select a usable keyring backend if the default one is broken."""
    kr = keyring.get_keyring()
    # keyrings.gauth raises NotImplementedError for set/get
    if type(kr).__module__.startswith("keyrings.gauth"):
        try:
            from keyring.backends import SecretService

            keyring.set_keyring(SecretService.Keyring())
            return
        except Exception:
            pass
        try:
            from keyrings.alt.file import PlaintextKeyring

            keyring.set_keyring(PlaintextKeyring())
            return
        except Exception:
            pass


_ensure_backend()


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
