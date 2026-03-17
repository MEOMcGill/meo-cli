"""HTTP client for the MEO API."""

from __future__ import annotations

from typing import Any

import httpx
import typer

from meo_cli.auth import require_token
from meo_cli.config import get_base_url

# Default timeout in seconds
TIMEOUT = 90


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(base_url: str, username: str, password: str) -> dict[str, Any]:
    """Authenticate via POST /meologin.

    Returns the full response body (contains access_token, collection, etc.).
    """
    url = f"{base_url}/meologin"
    try:
        r = httpx.post(
            url,
            params={"username": username, "password": password},
            timeout=30,
        )
    except httpx.ConnectError:
        typer.echo(f"Could not connect to {base_url}", err=True)
        raise typer.Exit(1)

    if r.status_code >= 400:
        typer.echo(f"Login failed (HTTP {r.status_code}): {r.text[:300]}", err=True)
        raise typer.Exit(1)

    body = r.json()

    # Server returns {"error": "...", "status": 400} on bad credentials
    if body.get("error"):
        typer.echo(f"Login failed: {body['error']}", err=True)
        raise typer.Exit(1)

    token = body.get("access_token") or body.get("token")
    if not token:
        typer.echo(f"Login response did not contain a token: {body}", err=True)
        raise typer.Exit(1)
    return body


def request(
    endpoint: str,
    *,
    method: str = "POST",
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    base_url: str | None = None,
    token: str | None = None,
    timeout: int = TIMEOUT,
) -> Any:
    """Authenticated API request with automatic 401 handling."""
    tok = token or require_token()
    # Ensure trailing slash — FastAPI redirects without it
    if not endpoint.endswith("/"):
        endpoint += "/"
    url = f"{get_base_url(base_url)}{endpoint}"
    headers = _headers(tok)

    try:
        r = httpx.request(
            method, url, headers=headers, json=json_data, params=params,
            timeout=timeout, follow_redirects=True,
        )
    except httpx.ConnectError:
        typer.echo(f"Could not connect to {get_base_url(base_url)}", err=True)
        raise typer.Exit(1)

    if r.status_code == 401:
        typer.echo("Session expired. Run 'meo login' again.", err=True)
        raise typer.Exit(1)

    if r.status_code >= 400:
        typer.echo(f"API error (HTTP {r.status_code}): {r.text[:300]}", err=True)
        raise typer.Exit(1)

    return r.json()
