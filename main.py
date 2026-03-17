"""
meo — MEO data CLI
Query the Media Ecosystem Observatory social media database.

Usage:
    meo search "climate change" --from 2024-01-01 --to 2024-12-31
    meo count "tariff" --platform twitter --from 2025-01-01
    meo timeline "election" --from 2024-01-01 --interval week
    meo top "immigration" --from 2025-01-01 --by likes --limit 20
    meo seeds --collection main
    meo scroll "query" --from 2024-01-01 --out posts.jsonl
    meo stats
    meo mapping twitter

Setup:
    Copy .env.example to .env and fill in credentials, or set env vars:
        MEOAPI_USERNAME, MEOAPI_PASSWORD

Install:
    pip install -e ".[cli]"
    # or: python -m cli.main --help
"""

import csv
import io
import json
import os
from pathlib import Path
from typing import Optional

import requests
import typer
from typing_extensions import Annotated

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MEO_API_BASE = "https://api.meoinsightshub.net"

PLATFORMS = [
    "twitter", "facebook", "instagram", "youtube",
    "tiktok", "telegram", "bluesky", "dashboard",
]


# ---------------------------------------------------------------------------
# Credentials — search for .env walking up from cwd and script location
# ---------------------------------------------------------------------------

def _find_env() -> Optional[Path]:
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).parent.parent / ".env",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_env() -> None:
    p = _find_env()
    if p:
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class _Auth:
    _token: Optional[str] = None

    @classmethod
    def token(cls) -> str:
        if cls._token is None:
            cls._token = cls._fetch_token()
        return cls._token

    @classmethod
    def _fetch_token(cls) -> str:
        username = os.environ.get("MEOAPI_USERNAME") or os.environ.get("MEO_USERNAME")
        password = os.environ.get("MEOAPI_PASSWORD") or os.environ.get("MEO_PASSWORD")
        if not username or not password:
            typer.echo(
                "Error: MEO credentials not found.\n"
                "Set MEOAPI_USERNAME and MEOAPI_PASSWORD in a .env file or environment.\n"
                f"Searched: {_find_env() or 'no .env found — see .env.example'}",
                err=True,
            )
            raise typer.Exit(1)

        r = requests.post(
            f"{MEO_API_BASE}/meologin",
            params={"username": username, "password": password},
            timeout=30,
        )
        r.raise_for_status()
        token = r.json().get("access_token")
        if not token:
            typer.echo(f"Authentication failed: {r.json()}", err=True)
            raise typer.Exit(1)
        return token

    @classmethod
    def headers(cls) -> dict:
        return {"Authorization": f"Bearer {cls.token()}"}

    @classmethod
    def refresh(cls) -> str:
        cls._token = None
        return cls.token()


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _api(
    endpoint: str,
    method: str = "POST",
    json_data: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: int = 90,
) -> dict:
    """Authenticated API call with automatic token refresh on 401."""
    headers = _Auth.headers()
    url = f"{MEO_API_BASE}{endpoint}"
    r = requests.request(method, url, headers=headers, json=json_data, params=params, timeout=timeout)
    if r.status_code == 401:
        headers["Authorization"] = f"Bearer {_Auth.refresh()}"
        r = requests.request(method, url, headers=headers, json=json_data, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Date helper
# ---------------------------------------------------------------------------

def _to_api_date(d: str) -> str:
    """Convert YYYY-MM-DD → DD-MM-YYYY as required by the MEO API."""
    if not d:
        return d
    parts = d.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return d


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _out(data, fmt: str, fields: Optional[list] = None) -> None:
    """Print data in the requested format to stdout."""
    if fmt == "json":
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
    elif fmt == "jsonl":
        items = data if isinstance(data, list) else [data]
        for item in items:
            typer.echo(json.dumps(item, ensure_ascii=False))
    elif fmt == "csv":
        items = data if isinstance(data, list) else [data]
        if not items:
            return
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf, fieldnames=fields or list(items[0].keys()), extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(items)
        typer.echo(buf.getvalue().rstrip())
    elif fmt == "table":
        items = data if isinstance(data, list) else [data]
        if not items:
            typer.echo("(no results)")
            return
        cols = fields or list(items[0].keys())
        widths = {
            c: max(len(c), max((len(str(i.get(c, ""))) for i in items), default=0))
            for c in cols
        }
        header = "  ".join(c.ljust(widths[c]) for c in cols)
        typer.echo(header)
        typer.echo("-" * len(header))
        for item in items:
            typer.echo("  ".join(str(item.get(c, "")).ljust(widths[c]) for c in cols))
    else:
        typer.echo(str(data))


def _post_to_row(hit: dict) -> dict:
    """Flatten a raw API post object into a consistent, minimal row."""
    seed = hit.get("seed") or {}
    return {
        "id":         hit.get("id", ""),
        "platform":   hit.get("platform", ""),
        "date":       hit.get("date", ""),
        "text":       (
            hit.get("text_all") or hit.get("rawContent") or hit.get("message")
            or hit.get("description") or hit.get("text") or ""
        )[:280],
        "likes":      hit.get("like_count", 0) or 0,
        "shares":     hit.get("share_count", 0) or 0,
        "comments":   hit.get("comment_count", 0) or 0,
        "views":      hit.get("view_count", 0) or 0,
        "handle":     (
            seed.get("Handle") or seed.get("SeedName")
            or hit.get("user_name") or ""
        ),
        "collection": seed.get("Collection", ""),
        "url":        hit.get("url") or hit.get("postUrl") or "",
    }


# ---------------------------------------------------------------------------
# CLI app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="meo",
    help="MEO social media data CLI — query the Media Ecosystem Observatory database.",
    no_args_is_help=True,
    add_completion=False,
)

# Reusable type aliases for common options
FmtOpt  = Annotated[str,          typer.Option("--format", "-f", help="Output format: json|jsonl|csv|table")]
ToOpt   = Annotated[Optional[str], typer.Option("--to",    help="End date YYYY-MM-DD")]


# ---------------------------------------------------------------------------
# meo search
# ---------------------------------------------------------------------------

@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query (Lucene syntax supported)")],
    platform: Annotated[
        str, typer.Option("--platform", "-p",
        help=f"Platform to search: {', '.join(PLATFORMS)}. 'dashboard' = all platforms (slower).")
    ] = "twitter",
    from_date: Annotated[str,  typer.Option("--from",  help="Start date YYYY-MM-DD (required)")] = ...,
    to_date:   ToOpt = None,
    size:      Annotated[int,  typer.Option("--size",  "-n", help="Max results, 1–10000")] = 100,
    fmt:       FmtOpt = "jsonl",
    full:      Annotated[bool, typer.Option("--full",  help="Return raw API response without flattening")] = False,
    no_rt:     Annotated[bool, typer.Option("--no-rt", help="Exclude retweets (Twitter)")] = False,
    out:       Annotated[Optional[Path], typer.Option("--out", "-o", help="Write output to file")] = None,
) -> None:
    """Search posts. Requires --from date."""
    payload: dict = {
        "platform": platform,
        "query":    query,
        "size":     min(size, 10000),
        "from_date": _to_api_date(from_date),
    }
    if to_date:
        payload["to_date"] = _to_api_date(to_date)

    endpoint = "/dashboard" if platform == "dashboard" else "/search"
    data = _api(endpoint, json_data=payload)
    hits = data if isinstance(data, list) else data.get("data", [])

    if no_rt:
        hits = [
            h for h in hits
            if not (h.get("text_all") or h.get("rawContent") or h.get("message") or "")
            .strip().startswith("RT @")
        ]

    rows = hits if full else [_post_to_row(h) for h in hits]

    if out:
        with open(out, "w") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        typer.echo(f"Wrote {len(rows)} records to {out}", err=True)
    else:
        _out(rows, fmt)


# ---------------------------------------------------------------------------
# meo count
# ---------------------------------------------------------------------------

@app.command()
def count(
    query:     Annotated[str, typer.Argument(help="Search query")] = "*",
    platform:  Annotated[str, typer.Option("--platform", "-p", help="Platform (default: dashboard = all)")] = "dashboard",
    from_date: Annotated[str, typer.Option("--from", help="Start date YYYY-MM-DD (required)")] = ...,
    to_date:   ToOpt = None,
) -> None:
    """Count posts matching a query. Requires --from date."""
    if platform == "dashboard":
        typer.echo("Note: cross-platform count via /dashboard may be slow.", err=True)

    payload: dict = {
        "platform": platform,
        "query":    query,
        "size":     1,
        "from_date": _to_api_date(from_date),
    }
    if to_date:
        payload["to_date"] = _to_api_date(to_date)

    endpoint = "/dashboard" if platform == "dashboard" else "/search"
    data = _api(endpoint, json_data=payload)
    total = (
        data.get("recordsTotal")
        or data.get("recordsFiltered")
        or len(data if isinstance(data, list) else [])
    )
    typer.echo(json.dumps({"query": query, "platform": platform, "count": total}))


# ---------------------------------------------------------------------------
# meo timeline
# ---------------------------------------------------------------------------

@app.command()
def timeline(
    query:     Annotated[str, typer.Argument(help="Search query")] = "*",
    from_date: Annotated[str, typer.Option("--from", help="Start date YYYY-MM-DD (required)")] = ...,
    to_date:   ToOpt = None,
    interval:  Annotated[str, typer.Option("--interval", "-i", help="Aggregation interval: day|week|month")] = "day",
    fmt:       FmtOpt = "csv",
    out:       Annotated[Optional[Path], typer.Option("--out", "-o")] = None,
) -> None:
    """Post counts over time. Requires --from date."""
    params: dict = {"query": query, "interval": interval, "date_start": from_date}
    if to_date:
        params["date_end"] = to_date

    data = _api("/timeline", method="GET", params=params)

    # Normalise varied response shapes from the API
    buckets = (
        data.get("aggregations", {}).get("timeline", {}).get("buckets")
        or data.get("buckets")
        or data.get("data")
        or (data if isinstance(data, list) else [])
    )

    rows = [
        {
            "date":  (b.get("key_as_string") or b.get("date") or b.get("key", ""))[:10],
            "count": b.get("doc_count") or b.get("count") or 0,
        }
        for b in buckets
    ]

    if out:
        with open(out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "count"])
            writer.writeheader()
            writer.writerows(rows)
        typer.echo(f"Wrote {len(rows)} rows to {out}", err=True)
    else:
        _out(rows, fmt, fields=["date", "count"])


# ---------------------------------------------------------------------------
# meo top
# ---------------------------------------------------------------------------

@app.command()
def top(
    query:     Annotated[str, typer.Argument(help="Search query")],
    by:        Annotated[str, typer.Option("--by",       help="Sort metric: likes|shares|comments|views")] = "likes",
    platform:  Annotated[str, typer.Option("--platform", "-p")] = "dashboard",
    from_date: Annotated[str, typer.Option("--from",     help="Start date YYYY-MM-DD (required)")] = ...,
    to_date:   ToOpt = None,
    limit:     Annotated[int, typer.Option("--limit",    "-n")] = 10,
    fmt:       FmtOpt = "table",
) -> None:
    """Top posts by engagement. Requires --from date."""
    field_map = {
        "likes": "like_count", "shares": "share_count",
        "comments": "comment_count", "views": "view_count",
    }
    payload: dict = {
        "platform":   platform,
        "query":      query,
        "size":       min(limit, 10000),
        "sort_field": field_map.get(by, "like_count"),
        "sort_type":  "desc",
        "from_date":  _to_api_date(from_date),
    }
    if to_date:
        payload["to_date"] = _to_api_date(to_date)

    endpoint = "/dashboard" if platform == "dashboard" else "/search"
    data = _api(endpoint, json_data=payload)
    hits = data if isinstance(data, list) else data.get("data", [])
    rows = [_post_to_row(h) for h in hits[:limit]]
    _out(rows, fmt, fields=["date", "platform", "handle", "likes", "shares", "views", "text"])


# ---------------------------------------------------------------------------
# meo seeds
# ---------------------------------------------------------------------------

@app.command()
def seeds(
    collection: Annotated[Optional[str], typer.Option("--collection", "-c", help="Filter by collection")] = None,
    platform:   Annotated[Optional[str], typer.Option("--platform",   "-p", help="Filter by platform")]   = None,
    province:   Annotated[Optional[str], typer.Option("--province",        help="Filter by province")]    = None,
    fmt:        FmtOpt = "table",
    limit:      Annotated[int, typer.Option("--limit", "-n")] = 50,
) -> None:
    """List tracked seed accounts (politicians, news outlets, influencers)."""
    params: dict = {}
    if collection: params["collection"] = collection
    if platform:   params["platform"]   = platform
    if province:   params["province"]   = province

    data = _api("/seedlist", method="GET", params=params)
    items = data if isinstance(data, list) else data.get("data", [])

    rows = [
        {
            "name":       s.get("Name") or s.get("SeedName", ""),
            "handle":     s.get("Handle", ""),
            "platform":   s.get("Platform", ""),
            "collection": s.get("Collection", ""),
            "province":   s.get("Province", ""),
        }
        for s in items[:limit]
    ]
    _out(rows, fmt, fields=["name", "handle", "platform", "collection", "province"])


# ---------------------------------------------------------------------------
# meo scroll  — bulk paginated export
# ---------------------------------------------------------------------------

@app.command()
def scroll(
    query:     Annotated[str, typer.Argument(help="Search query")],
    platform:  Annotated[str, typer.Option("--platform", "-p")] = "dashboard",
    from_date: Annotated[str, typer.Option("--from", help="Start date YYYY-MM-DD (required)")] = ...,
    to_date:   ToOpt = None,
    out:       Annotated[Optional[Path], typer.Option("--out", "-o", help="Output .jsonl file")] = None,
    max_posts: Annotated[int,  typer.Option("--max",  help="Maximum posts to fetch")] = 100000,
    full:      Annotated[bool, typer.Option("--full", help="Return raw API response")] = False,
) -> None:
    """Bulk paginated export (>10k posts). Writes JSONL. Requires --from date."""
    payload: dict = {
        "platform": platform,
        "query":    query,
        "size":     10000,
        "from_date": _to_api_date(from_date),
    }
    if to_date:
        payload["to_date"] = _to_api_date(to_date)

    out_f = open(out, "w") if out else None
    total = 0
    scroll_id = None

    try:
        while total < max_posts:
            if scroll_id:
                payload["scroll_id"] = scroll_id

            endpoint = "/search_scroll" if platform != "dashboard" else "/dashboard"
            data = _api(endpoint, json_data=payload)
            hits = data if isinstance(data, list) else data.get("data", [])
            if not hits:
                break

            scroll_id = data.get("scroll_id") if isinstance(data, dict) else None

            for hit in hits:
                row = hit if full else _post_to_row(hit)
                line = json.dumps(row, ensure_ascii=False)
                if out_f:
                    out_f.write(line + "\n")
                else:
                    typer.echo(line)
                total += 1
                if total >= max_posts:
                    break

            typer.echo(f"  Fetched {total:,} posts...", err=True)
            if not scroll_id or len(hits) < 10000:
                break
    finally:
        if out_f:
            out_f.close()
            typer.echo(f"Wrote {total:,} posts to {out}", err=True)
        else:
            typer.echo(f"Total: {total:,} posts", err=True)


# ---------------------------------------------------------------------------
# meo stats
# ---------------------------------------------------------------------------

@app.command()
def stats(
    fmt: FmtOpt = "table",
) -> None:
    """Show total post counts per platform."""
    rows = []
    for p in ["twitter", "facebook", "instagram", "youtube", "tiktok", "telegram", "bluesky"]:
        try:
            data = _api("/search", json_data={"platform": p, "query": "*", "size": 1})
            n = data.get("recordsTotal") or data.get("recordsFiltered") or 0
            rows.append({"platform": p, "total_posts": n})
        except Exception as e:
            rows.append({"platform": p, "total_posts": f"error: {e}"})
    _out(rows, fmt, fields=["platform", "total_posts"])


# ---------------------------------------------------------------------------
# meo mapping
# ---------------------------------------------------------------------------

@app.command()
def mapping(
    platform: Annotated[str, typer.Argument(help="Platform name (e.g. twitter, facebook)")],
    fmt: FmtOpt = "json",
) -> None:
    """Show Elasticsearch field mapping for a platform."""
    data = _api(f"/mapping/{platform}", method="GET")
    _out(data, fmt)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app()


if __name__ == "__main__":
    main()
