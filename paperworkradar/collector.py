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
import structlog
from pybreaker import CircuitBreakerError
from radar_core import AdaptiveThrottler, CrawlHealthStore
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .exceptions import NetworkError, ParseError, SourceError
from .models import Article, Source
from .resilience import get_circuit_breaker_manager


logger = structlog.get_logger(__name__)

_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (compatible; RadarTemplateBot/1.0; +https://github.com/zzragida/ai-frendly-datahub)",
}
_DEFAULT_HEALTH_DB_PATH = "data/radar_data.duckdb"
_COLLECTION_CONTROL_LOCK = threading.Lock()
_ACTIVE_THROTTLER: AdaptiveThrottler | None = None
_ACTIVE_HEALTH_STORE: CrawlHealthStore | None = None


def _set_collection_controls(throttler: AdaptiveThrottler, health_store: CrawlHealthStore) -> None:
    global _ACTIVE_THROTTLER, _ACTIVE_HEALTH_STORE
    with _COLLECTION_CONTROL_LOCK:
        _ACTIVE_THROTTLER = throttler
        _ACTIVE_HEALTH_STORE = health_store


def _clear_collection_controls() -> None:
    global _ACTIVE_THROTTLER, _ACTIVE_HEALTH_STORE
    with _COLLECTION_CONTROL_LOCK:
        _ACTIVE_THROTTLER = None
        _ACTIVE_HEALTH_STORE = None


def _get_collection_controls() -> tuple[AdaptiveThrottler | None, CrawlHealthStore | None]:
    with _COLLECTION_CONTROL_LOCK:
        return _ACTIVE_THROTTLER, _ACTIVE_HEALTH_STORE


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
        status_forcelist=[408, 429, 500, 502, 503, 504, 522, 524],
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
    source_name: str | None = None,
    throttler: AdaptiveThrottler | None = None,
    health_store: CrawlHealthStore | None = None,
    max_attempts: int = 3,
) -> requests.Response:
    """Fetch URL with retry logic on transient errors."""
    merged = {**_DEFAULT_HEADERS, **(headers or {})}
    if throttler is None or health_store is None:
        active_throttler, active_health_store = _get_collection_controls()
        throttler = throttler or active_throttler
        health_store = health_store or active_health_store

    retryable_errors = (
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.HTTPError,
    )

    for attempt in range(max_attempts):
        if source_name is not None and throttler is not None:
            throttler.acquire(source_name)

        try:
            if session is not None:
                response = session.get(url, timeout=timeout, headers=merged)
            else:
                response = requests.get(url, timeout=timeout, headers=merged)
            response.raise_for_status()

            if source_name is not None and throttler is not None:
                throttler.record_success(source_name)
                if health_store is not None:
                    delay = throttler.get_current_delay(source_name)
                    health_store.record_success(source_name, delay)

            return response
        except retryable_errors as exc:
            if source_name is not None and throttler is not None:
                retry_after: int | str | None = None
                if isinstance(exc, requests.exceptions.HTTPError):
                    response = exc.response
                    if response is not None and response.status_code == 429:
                        retry_after = _parse_retry_after(response.headers.get("Retry-After"))

                throttler.record_failure(source_name, retry_after=retry_after)
                if health_store is not None:
                    delay = throttler.get_current_delay(source_name)
                    health_store.record_failure(source_name, str(exc), delay)

            if attempt == max_attempts - 1:
                raise

    raise RuntimeError("Retry loop exited unexpectedly")


def _parse_retry_after(value: str | None) -> int | str | None:
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    if stripped.isdigit():
        return int(stripped)

    return stripped


def _source_bool(source: Source, key: str) -> bool:
    value = source.config.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _collect_reddit_pass(
    sources: list[Source],
    *,
    category: str,
    limit_per_source: int,
    timeout: int,
    health_db_path: str | None,
) -> tuple[list[Article], list[str]]:
    from radar_core.reddit_collector import collect_reddit_sources

    return collect_reddit_sources(
        sources=sources,
        category=category,
        limit=limit_per_source,
        timeout=timeout,
        health_db_path=health_db_path,
    )


def collect_sources(
    sources: list[Source],
    *,
    category: str,
    limit_per_source: int = 30,
    timeout: int = 15,
    min_interval_per_host: float = 0.5,
    max_workers: int | None = None,
    health_db_path: str | None = None,
) -> tuple[list[Article], list[str]]:
    """Fetch items from all configured sources, returning articles and errors."""
    articles: list[Article] = []
    errors: list[str] = []
    _js_types = {"javascript", "browser", "html", "js", "web"}
    _standard_types = {"rss", "api_source", "api"}
    enabled_sources = [source for source in sources if source.enabled]
    standard_sources = [
        source for source in enabled_sources if source.type.lower() in _standard_types
    ]
    js_sources = [source for source in enabled_sources if source.type.lower() in _js_types]
    reddit_sources = [source for source in enabled_sources if source.type.lower() == "reddit"]
    unsupported_sources = [
        source
        for source in enabled_sources
        if source.type.lower() not in {*_standard_types, *_js_types, "reddit"}
    ]
    manager = get_circuit_breaker_manager()
    workers = _resolve_max_workers(max_workers)
    resolved_health_db_path = health_db_path or os.environ.get(
        "RADAR_CRAWL_HEALTH_DB_PATH", _DEFAULT_HEALTH_DB_PATH
    )
    source_hosts: dict[str, str] = {
        source.name: (urlparse(source.url).netloc.lower() or source.name)
        for source in standard_sources
    }
    rate_limiters: dict[str, RateLimiter] = {
        host: RateLimiter(min_interval=min_interval_per_host) for host in set(source_hosts.values())
    }
    throttler = AdaptiveThrottler(min_delay=max(0.001, min_interval_per_host))
    health_store = CrawlHealthStore(resolved_health_db_path)
    _set_collection_controls(throttler, health_store)
    session = _create_session()

    def _collect_for_source(source: Source) -> tuple[list[Article], list[str]]:
        if (
            not _source_bool(source, "bypass_crawl_health")
            and health_store.is_disabled(source.name)
        ):
            return [], [f"{source.name}: Source disabled (crawl health threshold reached)"]

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
            for source in standard_sources:
                source_articles, source_errors = _collect_for_source(source)
                articles.extend(source_articles)
                errors.extend(source_errors)
        else:
            if standard_sources:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    future_map: list[Future[tuple[list[Article], list[str]]]] = [
                        executor.submit(_collect_for_source, source)
                        for source in standard_sources
                    ]

                    for future in future_map:
                        source_articles, source_errors = future.result()
                        articles.extend(source_articles)
                        errors.extend(source_errors)

        if js_sources:
            try:
                from .browser_collector import collect_browser_sources

                js_articles, js_errors = collect_browser_sources(
                    js_sources,
                    category,
                    timeout=max(1_000, timeout * 1_000),
                    health_db_path=resolved_health_db_path,
                )
                articles.extend(js_articles)
                errors.extend(js_errors)
            except ImportError:
                logger.warning(
                    "playwright_unavailable",
                    js_source_count=len(js_sources),
                    hint="pip install 'radar-core[browser]'",
                )

        if reddit_sources:
            try:
                reddit_articles, reddit_errors = _collect_reddit_pass(
                    reddit_sources,
                    category=category,
                    limit_per_source=limit_per_source,
                    timeout=timeout,
                    health_db_path=resolved_health_db_path,
                )
                articles.extend(reddit_articles)
                errors.extend(reddit_errors)
            except ImportError:
                errors.append(
                    f"Reddit collection unavailable for {len(reddit_sources)} source(s). "
                    "Ensure radar-core reddit support is installed."
                )

        for source in unsupported_sources:
            errors.append(
                f"{source.name}: Source type '{source.type}' is cataloged but not collected by the paperwork pipeline"
            )
    finally:
        session.close()
        health_store.close()
        _clear_collection_controls()

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

    # Handle RSS feeds
    if source_type == "rss":
        return _collect_rss(
            source, category=category, limit=limit, timeout=timeout, session=session
        )

    # Handle API sources
    if source_type in {"api_source", "api"}:
        return _collect_api_source(
            source, category=category, limit=limit, timeout=timeout, session=session
        )

    raise SourceError(source.name, f"Unsupported source type '{source.type}'")


def _collect_rss(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
    session: requests.Session | None = None,
) -> list[Article]:
    """Collect articles from RSS feeds."""
    try:
        response = _fetch_url_with_retry(
            source.url,
            timeout,
            session=session,
            source_name=source.name,
        )
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
        raise NetworkError(f"Network error fetching {source.name}: {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise SourceError(source.name, f"Request failed: {exc}", exc) from exc

    try:
        feed = feedparser.parse(response.content)
        items: list[Article] = []

        for entry in feed.entries[:limit]:
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

            title = html.unescape(_entry_text(entry, "title").strip()) or "(no title)"
            link = _entry_text(entry, "link").strip()

            # Skip entries with empty title or link
            if not title or title == "(no title)" or not link:
                continue

            if not summary.strip():
                summary = title

            items.append(
                Article(
                    title=title,
                    link=link,
                    summary=html.unescape(summary.strip()),
                    published=published,
                    source=source.name,
                    category=category,
                )
            )

        return items
    except Exception as exc:
        raise ParseError(f"Failed to parse feed from {source.name}: {exc}") from exc


def _collect_api_source(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
    session: requests.Session | None = None,
) -> list[Article]:
    """Collect articles from API sources (e.g., Gov24 Open API)."""

    if source.name == "Gov24 Open API":
        return _collect_gov24_api_source(
            source,
            category=category,
            limit=limit,
            timeout=timeout,
        )

    try:
        response = _fetch_url_with_retry(
            source.url,
            timeout,
            session=session,
            source_name=source.name,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise NetworkError(f"API request failed for {source.name}: {exc}") from exc

    try:
        # Verify response code for Gov24 API
        if source.name == "Gov24 Open API":
            data = response.json()

            # Check for API error codes
            if "code" in data:
                code = data["code"]
                if code != "0000":
                    message = data.get("message", "Unknown error")
                    raise SourceError(source.name, f"Gov24 API error: {code} - {message}")

            # Parse Gov24 response
            items: list[Article] = []
            results = data.get("results", [])

            for result in results[:limit]:
                title = result.get("serviceNm", "")
                if not title:
                    continue

                # Build link from service ID
                service_id = result.get("serviceId", "")
                link = f"https://www.gov24.go.kr/main/service/{service_id}" if service_id else ""

                # Get description
                summary = result.get("serviceIntro", "") or ""

                # Extract publish date (if available)
                published = None
                reg_dt = result.get("regDt", "")
                if reg_dt:
                    try:
                        # Gov24 date format: YYYYMMDD
                        published = datetime.strptime(reg_dt, "%Y%m%d").replace(tzinfo=UTC)
                    except (ValueError, AttributeError):
                        pass

                items.append(
                    Article(
                        title=title,
                        link=link,
                        summary=summary,
                        published=published,
                        source=source.name,
                        category=category,
                    )
                )

            return items
        else:
            # Generic API source handling
            data = response.json()
            items: list[Article] = []

            # Try common JSON structures
            if isinstance(data, dict):
                results = data.get("results", data.get("items", data.get("data", [])))
            elif isinstance(data, list):
                results = data
            else:
                raise ParseError(f"Unexpected response format from {source.name}")

            for result in results[:limit]:
                if isinstance(result, dict):
                    title = result.get("title", result.get("name", ""))
                    link = result.get("link", result.get("url", result.get("id", "")))
                    summary = result.get("summary", result.get("description", ""))

                    # Skip entries with empty title or link
                    if not title or not link:
                        continue

                    items.append(
                        Article(
                            title=str(title),
                            link=str(link),
                            summary=str(summary) if summary else "",
                            published=None,
                            source=source.name,
                            category=category,
                        )
                    )

            return items

    except ValueError as exc:
        raise ParseError(f"Failed to parse JSON response from {source.name}: {exc}") from exc
    except Exception as exc:
        raise ParseError(f"Failed to parse API response from {source.name}: {exc}") from exc


def _collect_gov24_api_source(
    source: Source,
    *,
    category: str,
    limit: int,
    timeout: int,
) -> list[Article]:
    parsed = urlparse(source.url)
    if not parsed.scheme or not parsed.netloc:
        raise SourceError(source.name, f"Invalid Gov24 URL: {source.url}")

    params = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
    endpoint = parsed._replace(query="").geturl()
    api_key = os.getenv("GOV24_API_KEY", "").strip()
    if not api_key:
        raise SourceError(source.name, "GOV24_API_KEY is required")

    per_page = min(_parse_int(params.get("perPage"), default=50), 100)
    max_pages = max(_parse_int(params.get("maxPages"), default=5), 1)
    page_delay = max(_parse_float(params.get("pageDelay"), default=0.2), 0.0)

    items: list[Article] = []
    for page in range(1, max_pages + 1):
        try:
            response = requests.get(
                endpoint,
                params={
                    "serviceKey": api_key,
                    "returnType": "JSON",
                    "page": page,
                    "perPage": per_page,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as exc:
            raise NetworkError(f"API request failed for {source.name}: {exc}") from exc
        except ValueError as exc:
            raise ParseError(f"Failed to parse JSON response from {source.name}: {exc}") from exc

        if not isinstance(payload, dict):
            raise ParseError(f"Unexpected response format from {source.name}")

        records = _extract_gov24_records(payload)
        if not records:
            break

        for record in records:
            title = _first_text(record, "serviceName", "서비스명", "name")
            if not title:
                continue

            service_id = _first_text(record, "serviceId", "svcId", "id")
            link = _first_text(record, "serviceUrl", "landingUrl", "homepage")
            if not link and service_id:
                link = f"https://www.gov.kr/portal/rcvfvrSvc/dtlEx/{service_id}"

            items.append(
                Article(
                    title=title,
                    link=link,
                    summary=_first_text(
                        record,
                        "serviceSummary",
                        "servicePurpose",
                        "serviceTarget",
                        "서비스목적",
                        "서비스개요",
                        "content",
                    ),
                    published=_parse_gov24_datetime(
                        _first_text(record, "updatedAt", "lastUpdated", "등록일시", "수정일시")
                    ),
                    source=source.name,
                    category=category,
                )
            )
            if len(items) >= limit:
                return items

        if len(records) < per_page:
            break
        if page_delay > 0:
            time.sleep(page_delay)

    return items


def _extract_gov24_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return ""


def _parse_int(value: str | None, *, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _parse_float(value: str | None, *, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _parse_gov24_datetime(raw: str) -> datetime | None:
    if not raw:
        return None
    normalized = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _extract_datetime(entry: Mapping[str, Any]) -> datetime | None:
    """Parse a feed entry date into a timezone-aware datetime."""
    published_parsed = entry.get("published_parsed")
    if isinstance(published_parsed, time.struct_time):
        return datetime.fromtimestamp(time.mktime(published_parsed), tz=UTC)

    updated_parsed = entry.get("updated_parsed")
    if isinstance(updated_parsed, time.struct_time):
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


def _entry_text(entry: Mapping[str, Any], key: str) -> str:
    value = entry.get(key)
    return value if isinstance(value, str) else ""
