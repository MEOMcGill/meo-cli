"""meo — CLI client for the MEO social media database.

Usage examples:
    meo login
    meo search "climate change" --from 2024-01-01       # all platforms
    meo search "climate change" -p twitter --from 2024-01-01  # twitter only
    meo count "tariff" --from 2025-01-01
    meo timeline "election" --from 2024-01-01 --interval week
    meo timeline "climate" --from 2024-01-01 --by seed.MainType
    meo agg --by seed.MainType --from 2024-01-01
    meo top "immigration" --from 2025-01-01 --by likes --limit 20
    meo seeds --collection main
    meo scroll "query" --from 2024-01-01 --out posts.jsonl
    meo stats
    meo mapping twitter
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from meo_cli import api, auth, config, output
from meo_cli.models import (
    ENGAGEMENT_FIELDS,
    PLATFORMS,
    flatten_post,
    to_api_date,
)

# ---------------------------------------------------------------------------
# App & sub-apps
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="meo",
    help="MEO social media data CLI — query the Media Ecosystem Observatory database.",
    no_args_is_help=True,
    add_completion=False,
)

config_app = typer.Typer(help="Manage CLI configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")

# ---------------------------------------------------------------------------
# Shared option types
# ---------------------------------------------------------------------------

FmtOpt = Annotated[str, typer.Option("--format", "-f", help="Output format: json|jsonl|csv|table")]
ToOpt = Annotated[Optional[str], typer.Option("--to", help="End date YYYY-MM-DD")]
BaseUrlOpt = Annotated[Optional[str], typer.Option("--base-url", help="Override API base URL", envvar="MEO_BASE_URL")]
QuietOpt = Annotated[bool, typer.Option("--quiet", "-q", help="Suppress result summary")]
IndexOpt = Annotated[Optional[str], typer.Option("--index", help="Search a dedicated platform index directly (for platform-specific fields).")]


def _resolve_platform_and_query(
    platform: str,
    query: str,
    index: str | None,
) -> tuple[str, str, str]:
    """Resolve the actual API platform, query, and endpoint.

    Always uses /search — never /dashboard (which loads all results into
    server memory and can crash on large queries).

    - ``--index twitter``  → platform="twitter", query unchanged
    - ``-p twitter``       → platform="dashboard", query="platform:twitter AND (…)"
    - no flag / dashboard  → platform="dashboard", query unchanged
    """
    if index:
        return index, query, "/search"

    if platform != "dashboard":
        wrapped = f"platform:{platform} AND ({query})" if query != "*" else f"platform:{platform}"
        return "dashboard", wrapped, "/search"

    return "dashboard", query, "/search"


# ---------------------------------------------------------------------------
# Auth commands
# ---------------------------------------------------------------------------

@app.command()
def login(
    base_url: BaseUrlOpt = None,
) -> None:
    """Authenticate with the MEO API and store your token securely."""
    cfg = config.load_config()

    # Resolve base URL
    url = base_url or cfg.get("base_url") or ""
    if not url:
        url = typer.prompt("MEO API base URL", default=config.DEFAULT_CONFIG["base_url"])
    url = url.rstrip("/")

    username = typer.prompt("Username", default=cfg.get("username") or "")
    password = typer.prompt("Password", hide_input=True)

    result = api.login(url, username, password)
    token = result.get("access_token") or result.get("token")

    # Persist
    auth.save_token(username, token)
    cfg["base_url"] = url
    cfg["username"] = username
    cfg["collection"] = result.get("collection", "")
    config.save_config(cfg)

    typer.echo(f"Logged in as {username}.")


@app.command()
def logout() -> None:
    """Remove stored credentials from the OS keychain."""
    auth.delete_token()
    typer.echo("Logged out. Token removed from keychain.")


@app.command()
def whoami() -> None:
    """Show current authenticated user."""
    cfg = config.load_config()
    username = cfg.get("username", "")
    if not username:
        typer.echo("Not logged in. Run 'meo login' first.", err=True)
        raise typer.Exit(1)

    token = auth.load_token(username)
    status = "active" if token else "no token (run meo login)"

    typer.echo(f"username:   {username}")
    typer.echo(f"base_url:   {cfg.get('base_url', '')}")
    typer.echo(f"collection: {cfg.get('collection', '')}")
    typer.echo(f"token:      {status}")


# ---------------------------------------------------------------------------
# Config commands
# ---------------------------------------------------------------------------

@config_app.command("show")
def config_show() -> None:
    """Display current configuration."""
    cfg = config.load_config()
    typer.echo(f"Config file: {config.config_path()}")
    for k, v in cfg.items():
        typer.echo(f"  {k} = {v}")


@config_app.command("set-base-url")
def config_set_base_url(
    url: Annotated[str, typer.Argument(help="New API base URL")],
) -> None:
    """Set the API base URL."""
    cfg = config.load_config()
    cfg["base_url"] = url.rstrip("/")
    config.save_config(cfg)
    typer.echo(f"base_url set to {cfg['base_url']}")


# ---------------------------------------------------------------------------
# Query commands
# ---------------------------------------------------------------------------

@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Lucene query. Supports field:value, AND/OR/NOT, wildcards.")],
    platform: Annotated[str, typer.Option("--platform", "-p", help="Filter by platform (searches dashboard index).")] = "dashboard",
    from_date: Annotated[str, typer.Option("--from", help="Start date YYYY-MM-DD (required)")] = ...,
    to_date: ToOpt = None,
    size: Annotated[int, typer.Option("--size", "-n", help="Max results, 1–10000")] = 10,
    sort_field: Annotated[str, typer.Option("--sort-field", help="Field to sort by (e.g. date, like_count, share_count)")] = "date",
    sort_order: Annotated[str, typer.Option("--sort-order", help="Sort order: asc or desc")] = "desc",
    fields: Annotated[Optional[str], typer.Option("--fields", help="Comma-separated list of fields to display (e.g. date,handle,text,likes)")] = None,
    fmt: FmtOpt = "jsonl",
    full: Annotated[bool, typer.Option("--full", help="Return raw API response without flattening")] = False,
    no_rt: Annotated[bool, typer.Option("--no-rt", help="Exclude retweets (Twitter)")] = False,
    out: Annotated[Optional[Path], typer.Option("--out", "-o", help="Write output to file")] = None,
    quiet: QuietOpt = False,
    index: IndexOpt = None,
    base_url: BaseUrlOpt = None,
) -> None:
    """Search posts across all platforms (or a specific one with -p). Requires --from date.

    By default, -p filters within the dashboard index (normalized fields).
    Use --index to query a dedicated platform index (platform-specific fields).

    Query examples:

        "climate change"                          free-text search

        seed.MainType:influencer                  filter by seed field

        rawContent:climate AND seed.Province:Ontario     (use --index twitter)

        seed.Handle.keyword:justinpjtrudeau       exact handle match

    Use --fields to pick any field from the raw API response, including
    nested fields with dot notation (e.g. seed.Province, seed.MainType).
    """
    if full:
        quiet = True

    api_platform, api_query, endpoint = _resolve_platform_and_query(platform, query, index)

    payload: dict = {
        "platform": api_platform,
        "query": api_query,
        "size": min(size, 10000),
        "from_date": to_api_date(from_date),
        "sort_field": sort_field,
        "sort_type": sort_order,
    }
    if fields:
        payload["select_fields"] = [f.strip() for f in fields.split(",")]
    if to_date:
        payload["to_date"] = to_api_date(to_date)

    data = api.request(endpoint, json_data=payload, base_url=base_url)
    hits = data if isinstance(data, list) else data.get("data", [])
    total = (
        data.get("recordsTotal") or data.get("recordsFiltered") or len(hits)
    ) if isinstance(data, dict) else len(hits)

    if no_rt:
        hits = [
            h for h in hits
            if not (h.get("text_all") or h.get("rawContent") or h.get("message") or "")
            .strip().startswith("RT @")
        ]

    if not quiet:
        showing = len(hits)
        if total > showing:
            typer.echo(
                f"{total:,} total matches, showing {showing}."
                f" Use -n to change limit, --out to save, or 'meo scroll' for bulk export.",
                err=True,
            )
        output.print_result_summary(hits)

    if fields:
        rows = [
            {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in h.items()}
            for h in hits
        ]
    elif full:
        rows = hits
    else:
        rows = [flatten_post(h) for h in hits]

    if out:
        n = output.write_jsonl(rows, str(out))
        typer.echo(f"Wrote {n} records to {out}", err=True)
    else:
        output.print_data(rows, fmt)


@app.command()
def count(
    query: Annotated[str, typer.Argument(help="Lucene query (field:value, AND/OR/NOT, wildcards).")] = "*",
    platform: Annotated[str, typer.Option("--platform", "-p", help="Filter by platform (searches dashboard index).")] = "dashboard",
    from_date: Annotated[str, typer.Option("--from", help="Start date YYYY-MM-DD (required)")] = ...,
    to_date: ToOpt = None,
    fmt: FmtOpt = "json",
    index: IndexOpt = None,
    base_url: BaseUrlOpt = None,
) -> None:
    """Count posts matching a query. Requires --from date."""
    api_platform, api_query, endpoint = _resolve_platform_and_query(platform, query, index)

    payload: dict = {
        "platform": api_platform,
        "query": api_query,
        "size": 1,
        "from_date": to_api_date(from_date),
    }
    if to_date:
        payload["to_date"] = to_api_date(to_date)

    data = api.request(endpoint, json_data=payload, base_url=base_url)
    total = (
        data.get("recordsTotal")
        or data.get("recordsFiltered")
        or len(data if isinstance(data, list) else [])
    )
    rows = [{"query": query, "platform": platform, "count": total}]
    output.print_data(rows, fmt, fields=["query", "platform", "count"])


@app.command()
def timeline(
    query: Annotated[str, typer.Argument(help="Lucene query (field:value, AND/OR/NOT, wildcards).")] = "*",
    platform: Annotated[str, typer.Option("--platform", "-p", help="Filter by platform (searches dashboard index).")] = "dashboard",
    from_date: Annotated[str, typer.Option("--from", help="Start date YYYY-MM-DD (required)")] = ...,
    to_date: ToOpt = None,
    interval: Annotated[str, typer.Option("--interval", "-i", help="Aggregation interval: day|week|month")] = "day",
    by: Annotated[Optional[str], typer.Option("--by", help="Group by field (e.g. seed.MainType, seed.Collection).")] = None,
    metric: Annotated[Optional[str], typer.Option("--metric", help="Metric as func:field (e.g. avg:view_count, sum:like_count).")] = None,
    fmt: FmtOpt = "csv",
    out: Annotated[Optional[Path], typer.Option("--out", "-o")] = None,
    index: IndexOpt = None,
    base_url: BaseUrlOpt = None,
) -> None:
    """Post counts over time, optionally grouped by a field. Requires --from date.

    Examples:

        meo timeline "climate" --from 2024-01-01

        meo timeline "climate" --from 2024-01-01 --by seed.MainType

        meo timeline "*" -p twitter --from 2024-01-01 --by seed.Collection --metric avg:like_count
    """
    api_platform, api_query, _ = _resolve_platform_and_query(platform, query, index)
    interval_map = {"day": "1d", "week": "1w", "month": "1M"}
    api_interval = interval_map.get(interval, interval)

    payload: dict = {
        "platform": api_platform,
        "query": api_query,
        "from_date": to_api_date(from_date),
        "agg_time_interval": api_interval,
    }
    if to_date:
        payload["to_date"] = to_api_date(to_date)

    # Simple timeline vs advanced (grouped/metric)
    if by or metric:
        if by:
            payload["agg_field"] = by
        if metric:
            func, _, field = metric.partition(":")
            if not field:
                typer.echo("--metric format: func:field (e.g. avg:view_count)", err=True)
                raise typer.Exit(1)
            payload["agg_funct"] = func
            payload["agg_funct_field"] = field

        data = api.request("/timeline_advanced", json_data=payload, base_url=base_url)
        buckets = data.get("timeline", [])
        rows = _parse_advanced_timeline(buckets, by, metric)
    else:
        data = api.request("/timeline", json_data=payload, base_url=base_url)
        buckets = data.get("timeline", [])
        rows = [
            {
                "date": (b.get("date") or b.get("key_as_string") or "")[:10],
                "count": b.get("count") or b.get("doc_count") or 0,
            }
            for b in buckets
        ]

    if not rows:
        typer.echo("(no results)", err=True)
        return

    fields = list(rows[0].keys())

    if out:
        import csv as csv_mod

        with open(out, "w", newline="") as f:
            writer = csv_mod.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        typer.echo(f"Wrote {len(rows)} rows to {out}", err=True)
    else:
        output.print_data(rows, fmt, fields=fields)


def _parse_advanced_timeline(
    buckets: list[dict], by: str | None, metric: str | None
) -> list[dict]:
    """Flatten /timeline_advanced composite buckets into simple rows."""
    rows = []
    for b in buckets:
        key = b.get("key", {})
        row: dict = {}

        # Extract date
        row["date"] = str(key.get("date", ""))[:10]

        # Extract grouping fields
        if by:
            for field in by.split(","):
                field_key = f"field_{field.strip()}"
                row[field.strip().split(".")[-1]] = key.get(field_key, "")

        row["count"] = b.get("doc_count", 0)

        # Extract metric values
        if metric:
            func, _, field_str = metric.partition(":")
            for f in field_str.split(","):
                f = f.strip()
                metric_key = f"{func}_{f}"
                val = b.get(metric_key, {})
                row[f"{func}_{f}"] = val.get("value", 0) if isinstance(val, dict) else val

        rows.append(row)
    return rows


@app.command()
def agg(
    query: Annotated[str, typer.Argument(help="Lucene query (field:value, AND/OR/NOT, wildcards).")] = "*",
    by: Annotated[str, typer.Option("--by", help="Group by field(s), comma-separated (e.g. seed.MainType,seed.Collection).")] = ...,
    platform: Annotated[str, typer.Option("--platform", "-p", help="Filter by platform (searches dashboard index).")] = "dashboard",
    from_date: Annotated[Optional[str], typer.Option("--from", help="Start date YYYY-MM-DD")] = None,
    to_date: ToOpt = None,
    metric: Annotated[Optional[str], typer.Option("--metric", help="Metric as func:field (e.g. avg:view_count, sum:like_count).")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max buckets to return")] = 50,
    fmt: FmtOpt = "table",
    index: IndexOpt = None,
    base_url: BaseUrlOpt = None,
) -> None:
    """Aggregate posts by field.

    Examples:

        meo agg --by seed.MainType --from 2024-01-01

        meo agg "climate" --by seed.MainType -p twitter --from 2024-01-01

        meo agg --by seed.MainType,seed.Collection --metric sum:like_count --from 2024-01-01

        meo agg --by Platform --index seeds

        meo agg --by Collection,Platform --index seeds
    """
    if not from_date and not index:
        typer.echo("--from is required (unless using --index).", err=True)
        raise typer.Exit(1)
    api_platform, api_query, _ = _resolve_platform_and_query(platform, query, index)

    payload: dict = {
        "platform": api_platform,
        "query": api_query,
        "agg_field": by,
        "size": limit,
    }
    if from_date:
        payload["from_date"] = to_api_date(from_date)
    if to_date:
        payload["to_date"] = to_api_date(to_date)
    if metric:
        func, _, field = metric.partition(":")
        if not field:
            typer.echo("--metric format: func:field (e.g. avg:view_count)", err=True)
            raise typer.Exit(1)
        payload["agg_funct"] = func
        payload["agg_funct_field"] = field

    data = api.request("/aggregations", json_data=payload, base_url=base_url)
    buckets = data.get("aggregations", [])

    if not buckets:
        typer.echo("(no results)", err=True)
        return

    # Parse buckets — single field returns {"key": "val", ...}, multi returns {"key": ["v1","v2"], ...}
    by_fields = [f.strip() for f in by.split(",")]

    def _col_name(field: str) -> str:
        """Turn 'Collection.keyword' → 'Collection', 'seed.MainType' → 'MainType'."""
        parts = field.split(".")
        # Drop trailing '.keyword' if present
        if parts[-1] == "keyword" and len(parts) > 1:
            parts = parts[:-1]
        return parts[-1]

    col_names = [_col_name(f) for f in by_fields]
    # Deduplicate if needed (e.g. two fields both map to same name)
    if len(set(col_names)) < len(col_names):
        col_names = [f.replace(".", "_") for f in by_fields]

    rows = []
    for b in buckets:
        row: dict = {}
        key = b.get("key", "")
        if isinstance(key, list):
            for i, name in enumerate(col_names):
                row[name] = key[i] if i < len(key) else ""
        else:
            row[col_names[0]] = key

        row["count"] = b.get("doc_count", 0)

        # Extract metric values
        if metric:
            func, _, field_str = metric.partition(":")
            for f in field_str.split(","):
                f = f.strip()
                metric_key = f"{func}_{f}"
                val = b.get(metric_key, {})
                row[f"{func}_{f}"] = val.get("value", 0) if isinstance(val, dict) else val

        rows.append(row)

    output.print_data(rows, fmt, fields=list(rows[0].keys()))


@app.command()
def top(
    query: Annotated[str, typer.Argument(help="Lucene query (field:value, AND/OR/NOT, wildcards).")],
    by: Annotated[str, typer.Option("--by", help="Sort metric: likes|shares|comments|views")] = "likes",
    platform: Annotated[str, typer.Option("--platform", "-p", help="Filter by platform (searches dashboard index).")] = "dashboard",
    from_date: Annotated[str, typer.Option("--from", help="Start date YYYY-MM-DD (required)")] = ...,
    to_date: ToOpt = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 10,
    fmt: FmtOpt = "table",
    quiet: QuietOpt = False,
    index: IndexOpt = None,
    base_url: BaseUrlOpt = None,
) -> None:
    """Top posts by engagement. Requires --from date."""
    api_platform, api_query, endpoint = _resolve_platform_and_query(platform, query, index)

    payload: dict = {
        "platform": api_platform,
        "query": api_query,
        "size": min(limit, 10000),
        "sort_field": ENGAGEMENT_FIELDS.get(by, "like_count"),
        "sort_type": "desc",
        "from_date": to_api_date(from_date),
    }
    if to_date:
        payload["to_date"] = to_api_date(to_date)

    data = api.request(endpoint, json_data=payload, base_url=base_url)
    hits = data if isinstance(data, list) else data.get("data", [])

    if not quiet:
        output.print_result_summary(hits[:limit])

    rows = [flatten_post(h) for h in hits[:limit]]
    output.print_data(rows, fmt, fields=["date", "platform", "handle", "likes", "shares", "views", "text"])


@app.command()
def seeds(
    collection: Annotated[Optional[str], typer.Option("--collection", "-c", help="Filter by collection")] = None,
    platform: Annotated[Optional[str], typer.Option("--platform", "-p", help="Filter by platform")] = None,
    province: Annotated[Optional[str], typer.Option("--province", help="Filter by province")] = None,
    fmt: FmtOpt = "table",
    limit: Annotated[int, typer.Option("--limit", "-n")] = 50,
    base_url: BaseUrlOpt = None,
) -> None:
    """List tracked seed accounts (politicians, news outlets, influencers)."""
    # /seedlist expects a SearchRequest with platform + Lucene query
    query_parts = []
    if collection:
        query_parts.append(f"Collection:{collection}")
    if platform:
        query_parts.append(f"Platform:{platform}")
    if province:
        query_parts.append(f"Province:{province}")

    params: dict = {
        "platform": "dashboard",
        "query": " AND ".join(query_parts) if query_parts else "*",
    }

    data = api.request("/seedlist", json_data=params, base_url=base_url)
    items = data if isinstance(data, list) else data.get("data", [])

    if len(items) > limit:
        typer.echo(
            f"Showing {limit} of {len(items)} seeds. Use -n to change limit (e.g. meo seeds -n {len(items)}).",
            err=True,
        )

    rows = [
        {
            "name": s.get("Name") or s.get("SeedName", ""),
            "handle": s.get("Handle", ""),
            "platform": s.get("Platform", ""),
            "collection": s.get("Collection", ""),
            "province": s.get("Province", ""),
        }
        for s in items[:limit]
    ]
    output.print_data(rows, fmt, fields=["name", "handle", "platform", "collection", "province"])


@app.command()
def scroll(
    query: Annotated[str, typer.Argument(help="Lucene query (field:value, AND/OR/NOT, wildcards).")],
    platform: Annotated[str, typer.Option("--platform", "-p", help="Filter by platform (searches dashboard index).")] = "dashboard",
    from_date: Annotated[str, typer.Option("--from", help="Start date YYYY-MM-DD (required)")] = ...,
    to_date: ToOpt = None,
    out: Annotated[Path, typer.Option("--out", "-o", help="Output .jsonl file (required)")] = ...,
    max_posts: Annotated[int, typer.Option("--max", help="Stop after this many posts (0 = no limit)")] = 0,
    full: Annotated[bool, typer.Option("--full", help="Return raw API response")] = False,
    quiet: QuietOpt = False,
    index: IndexOpt = None,
    base_url: BaseUrlOpt = None,
) -> None:
    """Bulk paginated export (>10k posts). Writes JSONL. Requires --from date."""
    api_platform, api_query, endpoint = _resolve_platform_and_query(platform, query, index)

    payload: dict = {
        "platform": api_platform,
        "query": api_query,
        "size": 10_000,
        "from_date": to_api_date(from_date),
    }
    if to_date:
        payload["to_date"] = to_api_date(to_date)

    total = 0
    scroll_id = None
    all_hits: list[dict] = []  # collect raw hits for final summary

    with open(out, "w") as out_f:
        try:
            while True:
                if max_posts and total >= max_posts:
                    break

                params = {"scroll_id": scroll_id} if scroll_id else None

                data = api.request(endpoint, json_data=payload, params=params, base_url=base_url)
                hits = data if isinstance(data, list) else data.get("data", [])
                if not hits:
                    break

                if not quiet:
                    all_hits.extend(hits)

                scroll_id = data.get("scroll_id") if isinstance(data, dict) else None

                for hit in hits:
                    row = hit if full else flatten_post(hit)
                    out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    total += 1
                    if max_posts and total >= max_posts:
                        break

                typer.echo(f"  {total:,} posts...", err=True)
                if not scroll_id or len(hits) < 10_000:
                    break
        except KeyboardInterrupt:
            pass

    if not quiet and all_hits:
        output.print_result_summary(all_hits)
    typer.echo(f"Wrote {total:,} posts to {out}", err=True)


@app.command()
def stats(
    fmt: FmtOpt = "table",
    base_url: BaseUrlOpt = None,
) -> None:
    """Show total post counts per platform."""
    rows = []
    for p in ["twitter", "facebook", "instagram", "youtube", "tiktok", "telegram", "bluesky"]:
        try:
            data = api.request(
                "/search", json_data={"platform": p, "query": "*", "size": 1}, base_url=base_url
            )
            n = data.get("recordsTotal") or data.get("recordsFiltered") or 0
            rows.append({"platform": p, "total_posts": n})
        except Exception as e:
            rows.append({"platform": p, "total_posts": f"error: {e}"})
    output.print_data(rows, fmt, fields=["platform", "total_posts"])


@app.command()
def mapping(
    platform: Annotated[str, typer.Argument(help="Platform name (e.g. twitter, facebook)")],
    fmt: FmtOpt = "json",
    base_url: BaseUrlOpt = None,
) -> None:
    """Show Elasticsearch field mapping for a platform."""
    data = api.request(f"/mapping/{platform}", method="GET", base_url=base_url)
    output.print_data(data, fmt)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
