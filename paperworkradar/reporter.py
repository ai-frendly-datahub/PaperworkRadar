from __future__ import annotations

from collections.abc import Iterable
from html import escape
from pathlib import Path
from typing import Any, Mapping

from radar_core.ontology import build_summary_ontology_metadata
from radar_core.report_utils import (
    generate_index_html as _core_generate_index_html,
)
from radar_core.report_utils import (
    generate_report as _core_generate_report,
)

from .models import Article, CategoryConfig


def generate_report(
    *,
    category: CategoryConfig,
    articles: Iterable[Article],
    output_path: Path,
    stats: dict[str, int],
    errors: list[str] | None = None,
    store=None,
    quality_report: Mapping[str, Any] | None = None,
) -> Path:
    """Generate HTML report (delegates to radar-core)."""
    articles_list = list(articles)
    plugin_charts = []

    # --- Universal plugins (entity heatmap + source reliability) ---
    try:
        from radar_core.plugins.entity_heatmap import get_chart_config as _heatmap_config

        _heatmap = _heatmap_config(articles=articles_list)
        if _heatmap is not None:
            plugin_charts.append(_heatmap)
    except Exception:
        pass
    try:
        from radar_core.plugins.source_reliability import get_chart_config as _reliability_config

        _reliability = _reliability_config(store=store)
        if _reliability is not None:
            plugin_charts.append(_reliability)
    except Exception:
        pass

    result = _core_generate_report(
        category=category,
        articles=articles_list,
        output_path=output_path,
        stats=stats,
        errors=errors,
        plugin_charts=plugin_charts if plugin_charts else None,
        ontology_metadata=build_summary_ontology_metadata(
            "PaperworkRadar",
            category_name=category.category_name,
            search_from=Path(__file__).resolve(),
        ),
    )
    if quality_report:
        _inject_paperwork_quality_panel(result, quality_report)
        _inject_latest_dated_report_panel(result, category.category_name, quality_report)
    return result


def generate_index_html(
    report_dir: Path,
    summaries_dir: Path | None = None,
) -> Path:
    """Generate index.html (delegates to radar-core)."""
    radar_name = "Paperwork Radar"
    return _core_generate_index_html(report_dir, radar_name)


def _inject_latest_dated_report_panel(
    output_path: Path,
    category_name: str,
    quality_report: Mapping[str, Any],
) -> None:
    dated_reports = sorted(
        output_path.parent.glob(
            f"{category_name}_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].html"
        ),
        key=lambda path: path.stat().st_mtime,
    )
    if dated_reports:
        _inject_paperwork_quality_panel(dated_reports[-1], quality_report)


def _inject_paperwork_quality_panel(
    output_path: Path,
    quality_report: Mapping[str, Any],
) -> None:
    if not output_path.exists():
        return
    html = output_path.read_text(encoding="utf-8")
    if 'id="paperwork-quality"' in html:
        return

    marker = '<section id="entities"'
    if marker not in html:
        return

    panel = _render_paperwork_quality_panel(quality_report)
    updated_html = html.replace(marker, panel + "\n      " + marker, 1)
    normalized_html = "\n".join(line.rstrip() for line in updated_html.splitlines()) + "\n"
    output_path.write_text(normalized_html, encoding="utf-8")


def _render_paperwork_quality_panel(quality_report: Mapping[str, Any]) -> str:
    summary = quality_report.get("summary")
    summary_map = summary if isinstance(summary, Mapping) else {}
    sources = [row for row in _list(quality_report.get("sources")) if isinstance(row, Mapping)]
    documents = [
        row for row in _list(quality_report.get("document_diffs")) if isinstance(row, Mapping)
    ]
    events = [row for row in _list(quality_report.get("events")) if isinstance(row, Mapping)]
    daily_review_items = [
        row for row in _list(quality_report.get("daily_review_items")) if isinstance(row, Mapping)
    ]
    flagged_sources = [
        row
        for row in sources
        if str(row.get("status")) in {"stale", "missing", "unknown_event_date", "skipped_disabled"}
        or _list(row.get("errors"))
    ][:8]
    changed_documents = [
        row for row in documents if str(row.get("status")) in {"new", "changed"}
    ][:6]
    tracked_events = [
        row for row in events if str(row.get("event_model")) in {"form_revision", "filing_deadline"}
    ][:6]
    portal_events = [
        row for row in events if row.get("event_model") == "portal_service_change"
    ][:6]

    chips = [
        ("fresh", summary_map.get("fresh_sources", 0)),
        ("stale", summary_map.get("stale_sources", 0)),
        ("missing", summary_map.get("missing_sources", 0)),
        ("form revisions", summary_map.get("form_revision_events", 0)),
        ("filing deadlines", summary_map.get("filing_deadline_events", 0)),
        ("portal changes", summary_map.get("portal_service_change_events", 0)),
        ("portal services", summary_map.get("unique_portal_service_count", 0)),
        ("doc changes", summary_map.get("changed_document_count", 0)),
        ("new docs", summary_map.get("new_document_count", 0)),
        ("fresh events", summary_map.get("fresh_paperwork_events", 0)),
        ("stale events", summary_map.get("stale_paperwork_events", 0)),
        ("event keys", summary_map.get("unique_paperwork_event_key_count", 0)),
        ("evidence URLs", summary_map.get("events_with_evidence_url", 0)),
        ("daily review", summary_map.get("daily_review_item_count", len(daily_review_items))),
    ]
    chip_html = "\n".join(
        f'<span class="chip"><strong>{escape(label)}</strong> {escape(str(value))}</span>'
        for label, value in chips
    )
    return f"""
      <section id="paperwork-quality" class="section" aria-label="Paperwork quality">
        <div class="section-hd">
          <h2>Paperwork Quality</h2>
          <div class="right">
            <span class="kbd">paperwork_quality.json</span>
            <span class="kbd">document_diffs</span>
            <span class="kbd">portal_service_change</span>
          </div>
        </div>
        <article class="panel">
          <header class="panel-hd">
            <div>
              <p class="panel-title">Form Revision, Deadline, and Portal Checks</p>
              <p class="panel-sub">source freshness, stale signals, portal changes, and document hash diff trace</p>
            </div>
          </header>
            <div class="panel-bd">
              <div class="row" aria-label="Paperwork quality summary">
              {chip_html}
            </div>
            {_render_quality_sources(flagged_sources)}
            {_render_tracked_events(tracked_events)}
            {_render_portal_service_changes(portal_events)}
            {_render_document_diffs(changed_documents)}
            {_render_daily_review_items(daily_review_items[:8])}
          </div>
        </article>
      </section>
"""


def _render_quality_sources(flagged_sources: list[Mapping[str, Any]]) -> str:
    if not flagged_sources:
        return '<p class="muted small">No stale or missing tracked sources in this run.</p>'

    items: list[str] = []
    for row in flagged_sources:
        source = escape(str(row.get("source", "")))
        status = escape(str(row.get("status", "")))
        model = escape(str(row.get("event_model", "")))
        age = row.get("age_days")
        age_text = "" if age is None else f", age {escape(str(age))}d"
        errors = _list(row.get("errors"))
        details = "" if not errors else ": error " + escape(str(errors[0]))
        items.append(
            f"<li><strong>{source}</strong>: {status} ({model}{age_text}){details}</li>"
        )
    return "<ul>" + "\n".join(items) + "</ul>"


def _render_document_diffs(documents: list[Mapping[str, Any]]) -> str:
    if not documents:
        return '<p class="muted small">No new or changed form documents in this run.</p>'

    items: list[str] = []
    for document in documents:
        title = escape(str(document.get("title", "")))
        status = escape(str(document.get("status", "")))
        source = escape(str(document.get("source", "")))
        digest = escape(str(document.get("content_hash", ""))[:12])
        items.append(f"<li><strong>{status}</strong> {title} ({source}, hash {digest})</li>")
    return "<ul>" + "\n".join(items) + "</ul>"


def _render_tracked_events(events: list[Mapping[str, Any]]) -> str:
    if not events:
        return '<p class="muted small">No form revision or filing deadline events were extracted in this run.</p>'

    items: list[str] = []
    for event in events:
        model = escape(str(event.get("event_model", "")))
        title = escape(str(event.get("title", "")))
        source = escape(str(event.get("source", "")))
        event_at = escape(str(event.get("event_at", "") or "event date unavailable"))
        evidence_url = escape(str(event.get("evidence_url", "") or str(event.get("url", ""))))
        digest = escape(str(event.get("content_hash", ""))[:12])
        due_date = escape(str(event.get("due_date", "")))
        event_status = escape(str(event.get("event_status", "")))
        event_key = escape(str(event.get("paperwork_event_key", ""))[:64])
        evidence_text = f"evidence {evidence_url}" if evidence_url else "evidence unavailable"
        hash_text = f", hash {digest}" if digest else ""
        due_text = f", due {due_date}" if due_date else ""
        status_text = f", event {event_status}" if event_status else ""
        key_text = f", key {event_key}" if event_key else ""
        items.append(
            f"<li><strong>{model}</strong> {title} ({source}, {event_at}; "
            f"{evidence_text}{hash_text}{due_text}{status_text}{key_text})</li>"
        )
    return "<ul>" + "\n".join(items) + "</ul>"


def _render_portal_service_changes(events: list[Mapping[str, Any]]) -> str:
    if not events:
        return '<p class="muted small">No portal service changes in this run.</p>'

    items: list[str] = []
    for event in events:
        portal = escape(str(event.get("portal", "")))
        service = escape(str(event.get("service_name", "") or event.get("title", "")))
        service_key = escape(str(event.get("portal_service_key", "")))
        summary = escape(str(event.get("requirement_summary", "")))
        detail = summary or service_key or "service detail unavailable"
        items.append(f"<li><strong>{portal}</strong>: {service} ({detail})</li>")
    return "<ul>" + "\n".join(items) + "</ul>"


def _render_daily_review_items(items: list[Mapping[str, Any]]) -> str:
    if not items:
        return '<p class="muted small">No paperwork daily review items in this run.</p>'

    rows: list[str] = []
    for item in items:
        reason = escape(str(item.get("reason", "")))
        source = escape(str(item.get("source", "")))
        model = escape(str(item.get("event_model", "")))
        title = escape(str(item.get("title", "")))
        evidence = escape(str(item.get("evidence_url", "")))
        detail = title or evidence or escape(str(item.get("error", "")))
        rows.append(f"<li><strong>{reason}</strong> {source} ({model}) {detail}</li>")
    return "<ul>" + "\n".join(rows) + "</ul>"


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []
