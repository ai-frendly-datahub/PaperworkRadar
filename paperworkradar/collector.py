from __future__ import annotations

import html
import os
import threading
import time
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import feedparser
import requests
from pybreaker import CircuitBreakerError
from requests.adapters import HTTPAdapter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from urllib3.util.retry import Retry

from .exceptions import NetworkError, ParseError, SourceError
from .models import Article, Source
from .resilience import get_circuit_breaker_manager


_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (compatible; PaperworkRadarBot/1.0; +https://github.com/zzragida/ai-frendly-datahub)",
}


class RateLimiter:
    def __init__(self, min_interval: float = 0.5):
        self._min_interval: float = min_interval
        self._last_request: float = 0.0
        self._lock: threading.Lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_request = time.monotonic()


def _resolve_max_workers(max_workers: int | None = None) -> int:
    if max_workers is None:
        raw_value = os.environ.get("RADAR_MAX_WORKERS", "5")
        try:
            parsed = int(raw_value)
        except ValueError:
            parsed = 5
    else:
        parsed = max_workers

    return max(1, min(parsed, 10))


def _create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)

    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


def _fetch_url_with_retry(
    url: str,
    timeout: int,
    headers: dict[str, str] | None = None,
    session: requests.Session | None = None,
) -> requests.Response:
    merged = {**_DEFAULT_HEADERS, **(headers or {})}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        reraise=True,
    )
    def _fetch() -> requests.Response:
        if session is not None:
            response = session.get(url, timeout=timeout, headers=merged)
        else:
            response = requests.get(url, timeout=timeout, headers=merged)
        response.raise_for_status()
        return response

    return _fetch()


def collect_sources(
    sources: list[Source],
    *,
    category: str,
    limit_per_source: int = 30,
    timeout: int = 15,
    min_interval_per_host: float = 0.5,
    max_workers: int | None = None,
) -> tuple[list[Article], list[str]]:
    articles: list[Article] = []
    errors: list[str] = []
    manager = get_circuit_breaker_manager()

    workers = _resolve_max_workers(max_workers)
    source_hosts: dict[str, str] = {
        source.name: (urlparse(source.url).netloc.lower() or source.name) for source in sources
    }
    rate_limiters: dict[str, RateLimiter] = {
        host: RateLimiter(min_interval=min_interval_per_host) for host in set(source_hosts.values())
    }
    session = _create_session()

    def _collect_for_source(source: Source) -> tuple[list[Article], list[str]]:
        host = source_hosts[source.name]
        rate_limiters[host].acquire()

        try:
            breaker = manager.get_breaker(source.name)
            result = breaker.call(
                _collect_single,
                source,
                category=category,
                limit=limit_per_source,
                timeout=timeout,
                session=session,
            )
            return result, []
        except CircuitBreakerError:
            return [], [f"{source.name}: Circuit breaker open (source unavailable)"]
        except SourceError as exc:
            return [], [str(exc)]
        except (NetworkError, ParseError) as exc:
            return [], [f"{source.name}: {exc}"]
        except Exception as exc:
            return [], [f"{source.name}: Unexpected error - {type(exc).__name__}: {exc}"]

    try:
        if workers == 1:
            for source in sources:
                source_articles, source_errors = _collect_for_source(source)
                articles.extend(source_articles)
                errors.extend(source_errors)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_map: list[Future[tuple[list[Article], list[str]]]] = [
                    executor.submit(_collect_for_source, source) for source in sources
                ]

                for future in future_map:
                    source_articles, source_errors = future.result()
                    articles.extend(source_articles)
                    errors.extend(source_errors)
    finally:
        session.close()

    return articles, errors


def _collect_single(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
    session: requests.Session | None = None,
) -> list[Article]:
    source_type = source.type.lower()
    if source_type == "rss":
        return _collect_rss(
            source, category=category, limit=limit, timeout=timeout, session=session
        )

    if source_type in {"api", "api_source"}:
        if (
            "gov24" in source.url.lower()
            or "gov24" in source.name.lower()
            or "odcloud.kr" in source.url.lower()
        ):
            return _collect_gov24(source, category=category, limit=limit, timeout=timeout)
        raise SourceError(
            source.name,
            f"Unsupported API source '{source.name}'. Gov24 API sources are supported.",
        )

    raise SourceError(
        source.name,
        f"Unsupported source type '{source.type}'. Supported types are 'rss', 'api', and 'api_source'.",
    )


def _collect_rss(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
    session: requests.Session | None = None,
) -> list[Article]:
    try:
        response = _fetch_url_with_retry(source.url, timeout, session=session)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise NetworkError(f"Network error fetching {source.name}: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise SourceError(source.name, f"Request failed: {exc}", exc) from exc

    try:
        feed = feedparser.parse(response.content)
        items: list[Article] = []

        for raw_entry in feed.entries[:limit]:
            entry = _entry_dict(raw_entry)
            published = _extract_datetime(entry)
            summary = _entry_text(entry, "summary") or _entry_text(entry, "description")
            if not summary:
                _content = entry.get("content", [])
                if isinstance(_content, list) and _content:
                    first_item = _content[0]
                    if isinstance(first_item, Mapping):
                        value = first_item.get("value")
                        if isinstance(value, str):
                            summary = value

            items.append(
                Article(
                    title=html.unescape(_entry_text(entry, "title").strip()) or "(no title)",
                    link=_entry_text(entry, "link").strip(),
                    summary=html.unescape(summary.strip()),
                    published=published,
                    source=source.name,
                    category=category,
                )
            )

        return items
    except Exception as exc:
        raise ParseError(f"Failed to parse feed from {source.name}: {exc}") from exc


def _collect_gov24(source: Source, *, category: str, limit: int, timeout: int) -> list[Article]:
    endpoint, params = _parse_source_url(source.url)

    api_key = os.getenv("GOV24_API_KEY", "").strip()
    if not api_key:
        raise SourceError(source.name, "GOV24_API_KEY is required for Gov24 Open API source")

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

        try:
            response = requests.get(endpoint, params=request_params, timeout=timeout)
            response.raise_for_status()
            payload = _json_dict(response)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            raise NetworkError(f"Network error fetching {source.name}: {exc}") from exc
        except requests.exceptions.RequestException as exc:
            raise SourceError(source.name, f"Request failed: {exc}", exc) from exc
        except ValueError as exc:
            raise ParseError(f"Failed to parse API response from {source.name}: {exc}") from exc

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


def _entry_dict(entry: object) -> dict[str, object]:
    if isinstance(entry, dict):
        return {str(key): value for key, value in entry.items()}
    return {}


def _entry_text(entry: Mapping[str, object], key: str) -> str:
    value = entry.get(key)
    return value if isinstance(value, str) else ""


def _extract_datetime(entry: Mapping[str, object]) -> datetime | None:
    published_parsed = entry.get("published_parsed")
    if isinstance(published_parsed, tuple):
        return datetime.fromtimestamp(time.mktime(published_parsed), tz=UTC)

    updated_parsed = entry.get("updated_parsed")
    if isinstance(updated_parsed, tuple):
        return datetime.fromtimestamp(time.mktime(updated_parsed), tz=UTC)

    for key in ("published", "updated", "date"):
        raw = entry.get(key)
        if raw:
            try:
                dt = parsedate_to_datetime(str(raw))
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt
            except Exception:
                continue
    return None


def _parse_source_url(source_url: str) -> tuple[str, dict[str, str]]:
    parsed = urlparse(source_url)
    if not parsed.scheme or not parsed.netloc:
        raise SourceError(source_url, f"Invalid Gov24 URL: {source_url}")
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


def _to_article(record: dict[str, Any], *, source: Source, category: str) -> Article | None:
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

    published = _parse_datetime(
        _first_text(record, "updatedAt", "lastUpdated", "등록일시", "수정일시")
    )

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


def _parse_datetime(raw: str) -> datetime | None:
    if not raw:
        return None
    normalized = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
