from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Tuple, cast

import feedparser
import requests

from .models import Article, Source


def collect_sources(
    sources: List[Source],
    *,
    category: str,
    limit_per_source: int = 30,
    timeout: int = 15,
) -> Tuple[List[Article], List[str]]:
    """Fetch items from all configured sources, returning articles and errors."""
    articles: List[Article] = []
    errors: List[str] = []

    for source in sources:
        try:
            articles.extend(_collect_single(source, category=category, limit=limit_per_source, timeout=timeout))
        except Exception as exc:  # noqa: BLE001 - surface errors to the caller
            errors.append(f"{source.name}: {exc}")

    return articles, errors


def _collect_single(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
) -> List[Article]:
    if source.type.lower() != "rss":
        raise ValueError(f"Unsupported source type '{source.type}'. Only 'rss' is supported in the template.")

    response = requests.get(source.url, timeout=timeout)
    response.raise_for_status()

    feed = feedparser.parse(response.content)
    items: List[Article] = []

    for raw_entry in feed.entries[:limit]:
        entry = cast(dict[str, object], raw_entry)
        published = _extract_datetime(entry)
        summary = _as_text(entry.get("summary")) or _as_text(entry.get("description"))

        items.append(
            Article(
                title=_as_text(entry.get("title")) or "(no title)",
                link=_as_text(entry.get("link")),
                summary=summary.strip(),
                published=published,
                source=source.name,
                category=category,
            )
        )

    return items


def _as_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _extract_datetime(entry: dict[str, object]) -> datetime | None:
    """Parse a feed entry date into a timezone-aware datetime."""
    published_parsed = entry.get("published_parsed")
    if isinstance(published_parsed, tuple):
        return datetime.fromtimestamp(time.mktime(published_parsed), tz=timezone.utc)

    updated_parsed = entry.get("updated_parsed")
    if isinstance(updated_parsed, tuple):
        return datetime.fromtimestamp(time.mktime(updated_parsed), tz=timezone.utc)

    for key in ("published", "updated", "date"):
        raw = entry.get(key)
        if raw:
            try:
                dt = parsedate_to_datetime(str(raw))
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                continue
    return None
