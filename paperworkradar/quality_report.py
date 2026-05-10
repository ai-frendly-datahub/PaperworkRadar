from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import Article, CategoryConfig, Source


TRACKED_EVENT_MODELS = {"form_revision", "filing_deadline", "portal_service_change"}
GENERIC_SERVICE_ROUTE_TAILS = {
    "about-us",
    "main",
    "news",
    "newsroom",
    "nologin",
    "portal",
    "updates",
}


def build_quality_report(
    *,
    category: CategoryConfig,
    articles: Iterable[Article],
    freshness_articles: Iterable[Article] | None = None,
    errors: Iterable[str] | None = None,
    quality_config: Mapping[str, object] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = _as_utc(generated_at or datetime.now(UTC))
    articles_list = list(articles)
    freshness_articles_list = (
        list(freshness_articles) if freshness_articles is not None else articles_list
    )
    errors_list = [str(error) for error in (errors or [])]
    quality = _dict(quality_config or {}, "data_quality")
    freshness_sla = _dict(quality, "freshness_sla")
    tracked_event_models = _tracked_event_models(quality)

    source_rows = [
        _build_source_row(
            source=source,
            articles=freshness_articles_list,
            errors=errors_list,
            freshness_sla=freshness_sla,
            tracked_event_models=tracked_event_models,
            generated_at=generated,
        )
        for source in category.sources
    ]
    events = _build_event_rows(
        sources=category.sources,
        articles=articles_list,
        tracked_event_models=tracked_event_models,
        freshness_sla=freshness_sla,
        generated_at=generated,
    )
    documents = _build_document_diff_rows(
        sources=category.sources,
        articles=articles_list,
        tracked_event_models=tracked_event_models,
    )

    status_counts = Counter(str(row["status"]) for row in source_rows)
    event_counts = Counter(str(row["event_model"]) for row in events)
    event_status_counts = Counter(str(row["event_status"]) for row in events)
    event_keys = {
        str(row["paperwork_event_key"])
        for row in events
        if str(row.get("paperwork_event_key") or "")
    }
    portal_service_keys = {
        str(row["portal_service_key"])
        for row in events
        if row.get("event_model") == "portal_service_change"
        and str(row.get("portal_service_key") or "")
    }
    report = {
        "category": category.category_name,
        "generated_at": generated.isoformat(),
        "summary": {
            "total_sources": len(source_rows),
            "tracked_sources": sum(1 for row in source_rows if row["tracked"]),
            "fresh_sources": status_counts.get("fresh", 0),
            "stale_sources": status_counts.get("stale", 0),
            "missing_sources": status_counts.get("missing", 0),
            "unknown_event_date_sources": status_counts.get("unknown_event_date", 0),
            "not_tracked_sources": status_counts.get("not_tracked", 0),
            "skipped_disabled_sources": status_counts.get("skipped_disabled", 0),
            "form_revision_events": event_counts.get("form_revision", 0),
            "filing_deadline_events": event_counts.get("filing_deadline", 0),
            "portal_service_change_events": event_counts.get("portal_service_change", 0),
            "fresh_paperwork_events": event_status_counts.get("fresh", 0),
            "stale_paperwork_events": event_status_counts.get("stale", 0),
            "undated_paperwork_events": event_status_counts.get("unknown_event_date", 0),
            "unique_paperwork_event_key_count": len(event_keys),
            "unique_portal_service_count": len(portal_service_keys),
            "document_diff_count": len(documents),
            "changed_document_count": 0,
            "new_document_count": 0,
            "unchanged_document_count": 0,
            "events_with_evidence_url": sum(1 for row in events if row.get("evidence_url")),
            "events_missing_evidence_url": sum(
                1 for row in events if not row.get("evidence_url")
            ),
            "form_revision_events_with_content_hash": sum(
                1
                for row in events
                if row.get("event_model") == "form_revision"
                and row.get("content_hash")
            ),
            "filing_deadline_events_with_due_date": sum(
                1
                for row in events
                if row.get("event_model") == "filing_deadline"
                and row.get("due_date")
            ),
            "portal_service_change_events_with_service_key": sum(
                1
                for row in events
                if row.get("event_model") == "portal_service_change"
                and row.get("portal_service_key")
            ),
            "collection_error_count": len(errors_list),
        },
        "sources": source_rows,
        "events": events,
        "document_diffs": documents,
        "errors": errors_list,
    }
    report["daily_review_items"] = _build_daily_review_items(
        source_rows=source_rows,
        events=events,
        documents=documents,
    )
    report["summary"]["daily_review_item_count"] = len(report["daily_review_items"])
    return report


def write_quality_report(
    report: dict[str, Any],
    *,
    output_dir: Path,
    category_name: str,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = _parse_datetime(str(report.get("generated_at") or "")) or datetime.now(UTC)
    date_stamp = _as_utc(generated_at).strftime("%Y%m%d")

    latest_path = output_dir / f"{category_name}_quality.json"
    dated_path = output_dir / f"{category_name}_{date_stamp}_quality.json"
    diff_dir = output_dir / "document_diffs"
    diff_dir.mkdir(parents=True, exist_ok=True)
    diff_latest_path = diff_dir / f"{category_name}_document_diffs.json"
    diff_dated_path = diff_dir / f"{category_name}_{date_stamp}_document_diffs.json"

    _apply_document_diff_status(report, previous_manifest_path=diff_latest_path)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    latest_path.write_text(encoded + "\n", encoding="utf-8")
    dated_path.write_text(encoded + "\n", encoding="utf-8")

    diff_manifest = {
        "category": report.get("category", category_name),
        "generated_at": report.get("generated_at"),
        "documents": report.get("document_diffs", []),
    }
    diff_encoded = json.dumps(diff_manifest, ensure_ascii=False, indent=2, default=str)
    diff_latest_path.write_text(diff_encoded + "\n", encoding="utf-8")
    diff_dated_path.write_text(diff_encoded + "\n", encoding="utf-8")

    return {
        "latest": latest_path,
        "dated": dated_path,
        "document_diff_latest": diff_latest_path,
        "document_diff_dated": diff_dated_path,
    }


def _build_source_row(
    *,
    source: Source,
    articles: list[Article],
    errors: list[str],
    freshness_sla: Mapping[str, object],
    tracked_event_models: set[str],
    generated_at: datetime,
) -> dict[str, Any]:
    source_articles = [article for article in articles if article.source == source.name]
    source_errors = [error for error in errors if error.startswith(f"{source.name}:")]
    event_model = _source_event_model(source)
    tracked = _is_tracked_source(source, event_model, tracked_event_models)
    latest_article = _latest_article(source_articles)
    latest_event_at = _event_datetime(latest_article, source) if latest_article else None
    if (
        latest_article is not None
        and latest_event_at is None
        and str(source.config.get("event_date_field") or "") == "collected_at"
    ):
        latest_event_at = generated_at
    latest_portal_service = (
        _portal_service_fields(latest_article, source)
        if latest_article and event_model == "portal_service_change"
        else {}
    )
    sla_days = _source_sla_days(source, event_model, freshness_sla)
    age_days = _age_days(generated_at, latest_event_at) if latest_event_at else None
    status = _source_status(
        source=source,
        tracked=tracked,
        article_count=len(source_articles),
        latest_event_at=latest_event_at,
        sla_days=sla_days,
        age_days=age_days,
    )

    return {
        "source": source.name,
        "source_type": source.type,
        "enabled": source.enabled,
        "tracked": tracked,
        "event_model": event_model,
        "freshness_sla_days": sla_days,
        "status": status,
        "article_count": len(source_articles),
        "latest_event_at": latest_event_at.isoformat() if latest_event_at else None,
        "age_days": round(age_days, 2) if age_days is not None else None,
        "latest_title": latest_article.title if latest_article else "",
        "latest_url": latest_article.link if latest_article else "",
        "latest_evidence_url": latest_article.link if latest_article else "",
        "latest_portal": latest_portal_service.get("portal", ""),
        "latest_service_id": latest_portal_service.get("service_id", ""),
        "latest_service_name": latest_portal_service.get("service_name", ""),
        "latest_portal_service_key": latest_portal_service.get("portal_service_key", ""),
        "latest_requirement_summary": latest_portal_service.get("requirement_summary", ""),
        "skip_reason": str(source.config.get("skip_reason") or "").strip(),
        "reenable_gate": str(source.config.get("reenable_gate") or "").strip(),
        "errors": source_errors,
    }


def _build_event_rows(
    *,
    sources: list[Source],
    articles: list[Article],
    tracked_event_models: set[str],
    freshness_sla: Mapping[str, object],
    generated_at: datetime,
) -> list[dict[str, Any]]:
    sources_by_name = {source.name: source for source in sources}
    rows: list[dict[str, Any]] = []
    for article in articles:
        source = sources_by_name.get(article.source)
        if source is None:
            continue
        event_model = _source_event_model(source)
        if not _is_tracked_source(source, event_model, tracked_event_models):
            continue
        event_at = _paperwork_event_datetime(article, source, event_model)
        sla_days = _source_sla_days(source, event_model, freshness_sla)
        age_days = _age_days(generated_at, event_at) if event_at else None
        row = {
            "source": source.name,
            "event_model": event_model,
            "title": article.title,
            "url": article.link,
            "evidence_url": article.link,
            "evidence_url_present": bool(article.link),
            "event_at": event_at.isoformat() if event_at else None,
            "event_age_days": round(age_days, 2) if age_days is not None else None,
            "event_freshness_sla_days": sla_days,
            "event_status": _event_status(
                event_at=event_at,
                age_days=age_days,
                sla_days=sla_days,
            ),
            "paperwork_event_key": _paperwork_event_key(
                article=article,
                source=source,
                event_model=event_model,
            ),
            "due_date": _due_date(article),
            "document_url": article.link if event_model == "form_revision" else "",
            "content_hash": (
                _document_content_hash(article)
                if event_model in {"form_revision", "portal_service_change"}
                else ""
            ),
        }
        if event_model == "portal_service_change":
            row.update(_portal_service_fields(article, source))
        rows.append(row)
    return rows


def _build_daily_review_items(
    *,
    source_rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in source_rows:
        source_name = str(row.get("source") or "")
        status = str(row.get("status") or "")
        event_model = str(row.get("event_model") or "")
        if status in {"missing", "stale", "unknown_event_date"}:
            items.append(
                {
                    "reason": f"source_status_{status}",
                    "source": source_name,
                    "event_model": event_model,
                    "freshness_sla_days": row.get("freshness_sla_days"),
                    "age_days": row.get("age_days"),
                    "latest_event_at": row.get("latest_event_at"),
                    "detail": "Tracked paperwork source needs collection or freshness follow-up.",
                }
            )

        if status == "skipped_disabled" and event_model in TRACKED_EVENT_MODELS:
            items.append(
                {
                    "reason": "disabled_source_gate",
                    "source": source_name,
                    "event_model": event_model,
                    "skip_reason": row.get("skip_reason"),
                    "reenable_gate": row.get("reenable_gate"),
                }
            )

        for error in _list(row.get("errors")):
            items.append(
                {
                    "reason": "source_collection_error",
                    "source": source_name,
                    "event_model": event_model,
                    "error": error,
                }
            )

    for event in events:
        event_model = str(event.get("event_model") or "")
        event_status = str(event.get("event_status") or "")
        if event_status in {"stale", "unknown_event_date"}:
            items.append(
                {
                    "reason": f"event_status_{event_status}",
                    "source": event.get("source"),
                    "event_model": event_model,
                    "event_at": event.get("event_at"),
                    "event_age_days": event.get("event_age_days"),
                    "event_freshness_sla_days": event.get("event_freshness_sla_days"),
                    "evidence_url": event.get("evidence_url"),
                    "title": event.get("title"),
                }
            )
        if not event.get("evidence_url"):
            items.append(
                {
                    "reason": "event_missing_evidence_url",
                    "source": event.get("source"),
                    "event_model": event_model,
                    "paperwork_event_key": event.get("paperwork_event_key"),
                    "title": event.get("title"),
                }
            )
        if event_model == "form_revision" and (
            not event.get("document_url") or not event.get("content_hash")
        ):
            items.append(
                {
                    "reason": "form_revision_missing_document_hash",
                    "source": event.get("source"),
                    "event_model": event_model,
                    "paperwork_event_key": event.get("paperwork_event_key"),
                    "evidence_url": event.get("evidence_url"),
                    "title": event.get("title"),
                }
            )
        if event_model == "filing_deadline" and not event.get("due_date"):
            items.append(
                {
                    "reason": "filing_deadline_missing_due_date",
                    "source": event.get("source"),
                    "event_model": event_model,
                    "paperwork_event_key": event.get("paperwork_event_key"),
                    "evidence_url": event.get("evidence_url"),
                    "title": event.get("title"),
                }
            )
        if event_model == "portal_service_change" and not event.get("portal_service_key"):
            items.append(
                {
                    "reason": "portal_service_change_missing_service_key",
                    "source": event.get("source"),
                    "event_model": event_model,
                    "paperwork_event_key": event.get("paperwork_event_key"),
                    "evidence_url": event.get("evidence_url"),
                    "title": event.get("title"),
                }
            )

    for document in documents:
        if not document.get("content_hash"):
            items.append(
                {
                    "reason": "document_missing_content_hash",
                    "source": document.get("source"),
                    "document_url": document.get("document_url"),
                    "title": document.get("title"),
                }
            )

    return items[:100]


def _build_document_diff_rows(
    *,
    sources: list[Source],
    articles: list[Article],
    tracked_event_models: set[str],
) -> list[dict[str, Any]]:
    sources_by_name = {source.name: source for source in sources}
    rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for article in articles:
        source = sources_by_name.get(article.source)
        if source is None:
            continue
        event_model = _source_event_model(source)
        if event_model != "form_revision" or not _is_tracked_source(
            source,
            event_model,
            tracked_event_models,
        ):
            continue
        document_url = article.link.strip()
        if not document_url or document_url in seen_urls:
            continue
        seen_urls.add(document_url)
        content_hash = _document_content_hash(article)
        rows.append(
            {
                "source": source.name,
                "title": article.title,
                "document_url": document_url,
                "source_url": article.link,
                "content_hash": content_hash,
                "revision_date": _iso_or_empty(article.published),
                "collected_at": _iso_or_empty(article.collected_at),
                "status": "observed",
            }
        )
    return rows


def _apply_document_diff_status(
    report: dict[str, Any],
    *,
    previous_manifest_path: Path,
) -> None:
    previous_hashes = _previous_document_hashes(previous_manifest_path)
    documents = report.get("document_diffs")
    if not isinstance(documents, list):
        documents = []
        report["document_diffs"] = documents

    status_counts: Counter[str] = Counter()
    for item in documents:
        if not isinstance(item, dict):
            continue
        document_url = str(item.get("document_url") or "")
        content_hash = str(item.get("content_hash") or "")
        previous_hash = previous_hashes.get(document_url)
        if previous_hash is None:
            status = "new"
        elif previous_hash != content_hash:
            status = "changed"
            item["previous_content_hash"] = previous_hash
        else:
            status = "unchanged"
        item["status"] = status
        status_counts[status] += 1

    summary = report.get("summary")
    if isinstance(summary, dict):
        summary["document_diff_count"] = len(documents)
        summary["changed_document_count"] = status_counts.get("changed", 0)
        summary["new_document_count"] = status_counts.get("new", 0)
        summary["unchanged_document_count"] = status_counts.get("unchanged", 0)


def _previous_document_hashes(manifest_path: Path) -> dict[str, str]:
    if not manifest_path.exists():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    documents = payload.get("documents") if isinstance(payload, dict) else None
    if not isinstance(documents, list):
        return {}

    hashes: dict[str, str] = {}
    for item in documents:
        if not isinstance(item, dict):
            continue
        document_url = str(item.get("document_url") or "")
        content_hash = str(item.get("content_hash") or "")
        if document_url and content_hash:
            hashes[document_url] = content_hash
    return hashes


def _source_status(
    *,
    source: Source,
    tracked: bool,
    article_count: int,
    latest_event_at: datetime | None,
    sla_days: int | None,
    age_days: float | None,
) -> str:
    if not source.enabled:
        return "skipped_disabled"
    if not tracked:
        return "not_tracked"
    if article_count == 0:
        return "missing"
    if latest_event_at is None or age_days is None:
        return "unknown_event_date"
    if sla_days is not None and age_days > sla_days:
        return "stale"
    return "fresh"


def _tracked_event_models(quality: Mapping[str, object]) -> set[str]:
    outputs = _dict(quality, "quality_outputs")
    raw = outputs.get("tracked_event_models")
    if isinstance(raw, list):
        values = {str(item).strip() for item in raw if str(item).strip()}
        return values & TRACKED_EVENT_MODELS or set(TRACKED_EVENT_MODELS)
    return set(TRACKED_EVENT_MODELS)


def _is_tracked_source(
    source: Source,
    event_model: str,
    tracked_event_models: set[str],
) -> bool:
    return source.enabled and event_model in tracked_event_models


def _source_event_model(source: Source) -> str:
    raw = source.config.get("event_model")
    return str(raw).strip() if raw is not None else ""


def _source_sla_days(
    source: Source,
    event_model: str,
    freshness_sla: Mapping[str, object],
) -> int | None:
    raw_source_sla = source.config.get("freshness_sla_days")
    parsed_source_sla = _as_int(raw_source_sla)
    if parsed_source_sla is not None:
        return parsed_source_sla

    model_sla = freshness_sla.get(event_model)
    if isinstance(model_sla, Mapping):
        return _as_int(model_sla.get("max_age_days"))
    return None


def _latest_article(articles: list[Article]) -> Article | None:
    dated: list[tuple[datetime, Article]] = []
    undated: list[Article] = []
    for article in articles:
        article_time = article.published or article.collected_at
        event_at = _as_utc(article_time) if article_time else None
        if event_at:
            dated.append((event_at, article))
        else:
            undated.append(article)
    if dated:
        return max(dated, key=lambda item: item[0])[1]
    return undated[0] if undated else None


def _event_datetime(article: Article | None, source: Source) -> datetime | None:
    if article is None:
        return None
    field = str(source.config.get("event_date_field") or "")
    if field == "collected_at":
        return _as_utc(article.collected_at) if article.collected_at else None
    article_time = article.published or article.collected_at
    return _as_utc(article_time) if article_time else None


def _paperwork_event_datetime(
    article: Article | None,
    source: Source,
    event_model: str,
) -> datetime | None:
    if article is None:
        return None
    if event_model == "filing_deadline":
        due_date = _parse_datetime(_due_date(article))
        if due_date is not None:
            return due_date
    return _event_datetime(article, source)


def _event_status(
    *,
    event_at: datetime | None,
    age_days: float | None,
    sla_days: int | None,
) -> str:
    if event_at is None or age_days is None:
        return "unknown_event_date"
    if sla_days is not None and age_days > sla_days:
        return "stale"
    return "fresh"


def _paperwork_event_key(*, article: Article, source: Source, event_model: str) -> str:
    date_part = _due_date(article) if event_model == "filing_deadline" else ""
    if not date_part and article.published:
        date_part = article.published.date().isoformat()
    key_parts = [
        event_model,
        source.country,
        source.name,
        date_part,
        _first_entity(article, "ServiceName"),
        _first_entity(article, "Form"),
        article.title or article.link,
    ]
    return ":".join(_normalize_key_text(part) for part in key_parts if str(part).strip())


def _due_date(article: Article) -> str:
    for key in ("DueDate", "FilingDeadline", "Deadline", "PolicyEffectiveDate", "EffectiveDate"):
        value = _first_entity(article, key)
        if value:
            return value
    return ""


def _document_content_hash(article: Article) -> str:
    content = "\n".join([article.link, article.title, article.summary or ""])
    return sha256(content.encode("utf-8")).hexdigest()


def _portal_service_fields(article: Article, source: Source) -> dict[str, str]:
    portal = _portal_name(article.link, source)
    service_id = _service_id(article.link)
    service_name = _first_entity(article, "ServiceName") or _compact_text(article.title)
    requirement_summary = _requirement_summary(article)
    content_hash = _document_content_hash(article)
    service_key = _portal_service_key(
        portal=portal,
        service_id=service_id,
        service_name=service_name,
        jurisdiction=source.country,
        url=article.link,
    )
    return {
        "portal": portal,
        "jurisdiction": source.country,
        "service_id": service_id,
        "service_name": service_name,
        "portal_service_key": service_key,
        "requirement_summary": requirement_summary,
        "content_hash": content_hash,
    }


def _portal_name(url: str, source: Source) -> str:
    host = urlparse(url).netloc.lower()
    source_url_host = urlparse(source.url).netloc.lower()
    if "gov.kr" in host or "gov.kr" in source_url_host or "정부24" in source.name:
        return "gov.kr"
    if "gov.uk" in host or "gov.uk" in source_url_host:
        return "gov.uk"
    if "gsa.gov" in host or "gsa.gov" in source_url_host:
        return "gsa.gov"
    return source_url_host or host or source.name


def _service_id(url: str) -> str:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return ""
    marker_indexes = [
        index
        for index, part in enumerate(path_parts)
        if part.lower() in {"dtlex", "service", "services", "forms"}
    ]
    if marker_indexes and marker_indexes[-1] + 1 < len(path_parts):
        return path_parts[marker_indexes[-1] + 1]
    tail = path_parts[-1]
    if tail.lower() in GENERIC_SERVICE_ROUTE_TAILS:
        return ""
    return tail if len(tail) <= 80 else ""


def _requirement_summary(article: Article) -> str:
    for key in ("RequirementSummary", "RequiredDocument", "Form"):
        value = _first_entity(article, key)
        if value:
            return value
    return _compact_text(article.summary or article.title, limit=180)


def _portal_service_key(
    *,
    portal: str,
    service_id: str,
    service_name: str,
    jurisdiction: str,
    url: str,
) -> str:
    if service_id:
        return f"{portal}:{jurisdiction}:{service_id}" if jurisdiction else f"{portal}:{service_id}"
    normalized_name = _normalize_key_text(service_name or url)
    if not normalized_name:
        return ""
    return (
        f"{portal}:{jurisdiction}:{normalized_name}"
        if jurisdiction
        else f"{portal}:{normalized_name}"
    )


def _first_entity(article: Article, key: str) -> str:
    values = article.matched_entities.get(key, [])
    if isinstance(values, list) and values:
        return str(values[0])
    return ""


def _list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _compact_text(text: str, *, limit: int = 120) -> str:
    return " ".join(text.split())[:limit]


def _normalize_key_text(text: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in text)
    return "-".join(part for part in normalized.split("-") if part)


def _iso_or_empty(value: datetime | None) -> str:
    return _as_utc(value).isoformat() if value else ""


def _age_days(generated_at: datetime, event_at: datetime) -> float:
    return max(0.0, (_as_utc(generated_at) - _as_utc(event_at)).total_seconds() / 86400)


def _dict(mapping: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = mapping.get(key)
    return value if isinstance(value, Mapping) else {}


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None
