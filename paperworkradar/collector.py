from __future__ import annotations

import html
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Tuple, cast

import feedparser
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .collectors.gov24_collector import collect_gov24
from .models import Article, Source


_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (compatible; PaperworkRadarBot/1.0; +https://github.com/zzragida/ai-frendly-datahub)",
}


def _fetch_url_with_retry(
    url: str,
    timeout: int,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    """Fetch URL with retry logic on transient errors."""
    merged = {**_DEFAULT_HEADERS, **(headers or {})}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        reraise=True,
    )
    def _fetch() -> requests.Response:
        response = requests.get(url, timeout=timeout, headers=merged)
        response.raise_for_status()
        return response

    return _fetch()


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
            articles.extend(
                _collect_single(source, category=category, limit=limit_per_source, timeout=timeout)
            )
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
    source_type = source.type.lower()
    if source_type == "rss":
        return _collect_rss(source, category=category, limit=limit, timeout=timeout)

    if source_type in {"api", "api_source"}:
        if (
            "gov24" in source.url.lower()
            or "gov24" in source.name.lower()
            or "odcloud.kr" in source.url.lower()
        ):
            return collect_gov24(source, category=category, limit=limit, timeout=timeout)
        raise ValueError(
            f"Unsupported API source '{source.name}'. Gov24 API sources are supported."
        )

    raise ValueError(
        f"Unsupported source type '{source.type}'. Supported types are 'rss', 'api', and 'api_source'."
    )


def _collect_rss(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
) -> List[Article]:
    response = _fetch_url_with_retry(source.url, timeout)

    feed = feedparser.parse(response.content)
    items: List[Article] = []

    for raw_entry in feed.entries[:limit]:
        entry = cast(dict[str, object], raw_entry)
        published = _extract_datetime(entry)
        summary = _as_text(entry.get("summary")) or _as_text(entry.get("description"))
        if not summary:
            _content = entry.get("content", [])
            if isinstance(_content, list) and _content:
                _first = _content[0]
                if isinstance(_first, dict):
                    summary = str(_first.get("value", ""))

        items.append(
            Article(
                title=html.unescape(_as_text(entry.get("title"))) or "(no title)",
                link=_as_text(entry.get("link")),
                summary=html.unescape(summary.strip()),
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
