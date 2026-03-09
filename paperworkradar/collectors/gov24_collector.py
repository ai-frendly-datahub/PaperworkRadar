from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Optional, Any
from urllib.parse import parse_qs, urlparse

import requests

from paperworkradar.models import Article, Source


def collect_gov24(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
) -> list[Article]:
    endpoint, params = _parse_source_url(source.url)

    api_key = os.getenv("GOV24_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GOV24_API_KEY is required for Gov24 Open API source")

    per_page = min(_as_int(params.get("perPage", "50"), default=50), 100)
    max_pages = max(_as_int(params.get("maxPages", "5"), default=5), 1)
    page_delay = max(_as_float(params.get("pageDelay", "0.2"), default=0.2), 0.0)

    articles: list[Article] = []
    for page in range(1, max_pages + 1):
        request_params: dict[str, Any] = {
            "serviceKey": api_key,
            "returnType": "JSON",
            "page": page,
            "perPage": per_page,
        }

        response = requests.get(endpoint, params=request_params, timeout=timeout)
        response.raise_for_status()
        payload = _json_dict(response)

        records = _extract_records(payload)
        if not records:
            break

        for record in records:
            article = _to_article(record, source=source, category=category)
            if article is not None:
                articles.append(article)
            if len(articles) >= limit:
                return articles

        if len(records) < per_page:
            break
        if page_delay > 0:
            time.sleep(page_delay)

    return articles


def _parse_source_url(source_url: str) -> tuple[str, dict[str, str]]:
    parsed = urlparse(source_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid Gov24 URL: {source_url}")
    params = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
    clean_url = parsed._replace(query="").geturl()
    return clean_url, params


def _json_dict(response: requests.Response) -> dict[str, Any]:
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Gov24 API returned non-dict payload")
    return payload


def _extract_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    records: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            records.append(item)
    return records


def _to_article(record: dict[str, Any], *, source: Source, category: str) -> Optional[Article]:
    title = _first_text(record, "serviceName", "서비스명", "name")
    if not title:
        return None

    summary = _first_text(
        record,
        "serviceSummary",
        "servicePurpose",
        "serviceTarget",
        "서비스목적",
        "서비스개요",
        "content",
    )
    service_id = _first_text(record, "serviceId", "svcId", "id")
    detail_url = _first_text(record, "serviceUrl", "landingUrl", "homepage")
    if not detail_url and service_id:
        detail_url = f"https://www.gov.kr/portal/rcvfvrSvc/dtlEx/{service_id}"

    published = _parse_datetime(_first_text(record, "updatedAt", "lastUpdated", "등록일시", "수정일시"))

    return Article(
        title=title,
        link=detail_url,
        summary=summary,
        published=published,
        source=source.name,
        category=category,
    )


def _first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return ""


def _as_int(value: str, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: str, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_datetime(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    normalized = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
