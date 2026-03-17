"""Lightweight data helpers — no heavy ORM, just dict transforms."""

from __future__ import annotations

PLATFORMS = [
    "twitter",
    "facebook",
    "instagram",
    "youtube",
    "tiktok",
    "telegram",
    "bluesky",
    "dashboard",
]

ENGAGEMENT_FIELDS = {
    "likes": "like_count",
    "shares": "share_count",
    "comments": "comment_count",
    "views": "view_count",
}


def to_api_date(d: str) -> str:
    """Convert YYYY-MM-DD → DD-MM-YYYY as required by the MEO API."""
    if not d:
        return d
    parts = d.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return d


def flatten_post(hit: dict) -> dict:
    """Flatten a raw API post into a consistent minimal row."""
    seed = hit.get("seed") or {}
    return {
        "id": hit.get("id", ""),
        "platform": hit.get("platform", ""),
        "date": hit.get("date", ""),
        "text": (
            hit.get("text_all")
            or hit.get("rawContent")
            or hit.get("message")
            or hit.get("description")
            or hit.get("text")
            or ""
        )[:280],
        "likes": hit.get("like_count", 0) or 0,
        "shares": hit.get("share_count", 0) or 0,
        "comments": hit.get("comment_count", 0) or 0,
        "views": hit.get("view_count", 0) or 0,
        "handle": (
            seed.get("Handle")
            or seed.get("SeedName")
            or hit.get("user_name")
            or ""
        ),
        "collection": seed.get("Collection", ""),
        "url": hit.get("url") or hit.get("postUrl") or "",
    }
