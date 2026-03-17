"""Output formatting: JSON, JSONL, CSV, table."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Sequence

import typer


def print_data(
    data: Any,
    fmt: str,
    fields: list[str] | None = None,
) -> None:
    """Print data to stdout in the requested format."""
    if fmt == "json":
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
    elif fmt == "jsonl":
        _print_jsonl(data)
    elif fmt == "csv":
        _print_csv(data, fields)
    elif fmt == "table":
        _print_table(data, fields)
    else:
        typer.echo(str(data))


def _print_jsonl(data: Any) -> None:
    items = data if isinstance(data, list) else [data]
    for item in items:
        typer.echo(json.dumps(item, ensure_ascii=False))


def _print_csv(data: Any, fields: list[str] | None = None) -> None:
    items: list[dict] = data if isinstance(data, list) else [data]
    if not items:
        return
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=fields or list(items[0].keys()), extrasaction="ignore"
    )
    writer.writeheader()
    writer.writerows(items)
    typer.echo(buf.getvalue().rstrip())


def _print_table(data: Any, fields: list[str] | None = None) -> None:
    items: list[dict] = data if isinstance(data, list) else [data]
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


def write_jsonl(rows: Sequence[dict], path: str) -> int:
    """Write rows as JSONL to a file. Returns count written."""
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def print_result_summary(hits: list[dict]) -> None:
    """Print a compact breakdown of search results to stderr.

    Extracts seed metadata from raw API hits and shows counts by
    collection, main type, and platform so analysts understand what
    they're looking at without knowing the data schema.
    """
    if not hits:
        typer.echo("0 results.", err=True)
        return

    collections: dict[str, int] = {}
    main_types: dict[str, int] = {}
    platforms: dict[str, int] = {}

    for h in hits:
        seed = h.get("seed") or {}

        col = seed.get("Collection") or "unknown"
        collections[col] = collections.get(col, 0) + 1

        mt = seed.get("MainType") or seed.get("Maintype") or ""
        if mt:
            main_types[mt] = main_types.get(mt, 0) + 1

        plat = h.get("platform") or seed.get("Platform") or "unknown"
        platforms[plat] = platforms.get(plat, 0) + 1

    lines = [f"{len(hits)} results"]

    if len(platforms) > 1 or (len(platforms) == 1 and "unknown" not in platforms):
        breakdown = ", ".join(f"{v} {k}" for k, v in _top_n(platforms, 5))
        lines.append(f"  platforms:   {breakdown}")

    if collections and not (len(collections) == 1 and "unknown" in collections):
        breakdown = ", ".join(f"{v} {k}" for k, v in _top_n(collections, 5))
        lines.append(f"  collections: {breakdown}")

    if main_types:
        breakdown = ", ".join(f"{v} {k}" for k, v in _top_n(main_types, 5))
        lines.append(f"  types:       {breakdown}")

    typer.echo("\n".join(lines), err=True)


def _top_n(counts: dict[str, int], n: int) -> list[tuple[str, int]]:
    """Return top-n items sorted by count descending, with '+ X more' if truncated."""
    sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    result = sorted_items[:n]
    remaining = len(sorted_items) - n
    if remaining > 0:
        result.append((f"+{remaining} more", sum(v for _, v in sorted_items[n:])))
    return result
