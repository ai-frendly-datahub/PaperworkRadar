from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from paperworkradar.models import Article, CategoryConfig, Source
from paperworkradar.quality_report import build_quality_report, write_quality_report


def _source(name: str, event_model: str, sla_days: int | None = None) -> Source:
    config: dict[str, object] = {"event_model": event_model}
    if sla_days is not None:
        config["freshness_sla_days"] = sla_days
    return Source(name=name, type="rss", url=f"https://example.com/{name}", config=config)


def test_build_quality_report_tracks_form_deadline_and_diff_statuses() -> None:
    now = datetime(2026, 4, 12, tzinfo=UTC)
    category = CategoryConfig(
        category_name="paperwork",
        display_name="Paperwork",
        sources=[
            _source("Form Source", "form_revision", 2),
            _source("Deadline Source", "filing_deadline", 1),
            _source("Missing Deadline", "filing_deadline", 1),
            _source("Portal News", "portal_service_change", 3),
        ],
        entities=[],
    )
    articles = [
        Article(
            title="Updated immigration form",
            link="https://example.com/forms/i-130",
            summary="Form edition changed",
            published=now - timedelta(hours=6),
            collected_at=now,
            source="Form Source",
            category="paperwork",
        ),
        Article(
            title="Annual filing reminder",
            link="https://example.com/deadlines/annual",
            summary="File by the stated deadline",
            published=now - timedelta(days=3),
            collected_at=now,
            source="Deadline Source",
            category="paperwork",
        ),
        Article(
            title="Portal service notice",
            link="https://www.gov.uk/apply-renew-passport",
            summary="Required document list changed for online passport renewal.",
            published=now,
            collected_at=now,
            source="Portal News",
            category="paperwork",
            matched_entities={"RequiredDocument": ["photo ID and proof of address"]},
        ),
    ]

    report = build_quality_report(
        category=category,
        articles=articles,
        errors=["Deadline Source: timeout after retry"],
        quality_config={
            "data_quality": {
                "quality_outputs": {
                    "tracked_event_models": [
                        "form_revision",
                        "filing_deadline",
                        "portal_service_change",
                    ]
                }
            }
        },
        generated_at=now,
    )

    assert report["summary"]["fresh_sources"] == 2
    assert report["summary"]["stale_sources"] == 1
    assert report["summary"]["missing_sources"] == 1
    assert report["summary"]["not_tracked_sources"] == 0
    assert report["summary"]["form_revision_events"] == 1
    assert report["summary"]["filing_deadline_events"] == 1
    assert report["summary"]["portal_service_change_events"] == 1
    assert report["summary"]["fresh_paperwork_events"] == 2
    assert report["summary"]["stale_paperwork_events"] == 1
    assert report["summary"]["undated_paperwork_events"] == 0
    assert report["summary"]["unique_paperwork_event_key_count"] == 3
    assert report["summary"]["unique_portal_service_count"] == 1
    assert report["summary"]["document_diff_count"] == 1
    assert report["summary"]["events_with_evidence_url"] == 3
    assert report["summary"]["events_missing_evidence_url"] == 0
    assert report["summary"]["form_revision_events_with_content_hash"] == 1
    assert report["summary"]["filing_deadline_events_with_due_date"] == 0
    assert report["summary"]["portal_service_change_events_with_service_key"] == 1
    assert report["summary"]["collection_error_count"] == 1
    assert report["summary"]["daily_review_item_count"] == 5

    statuses = {row["source"]: row["status"] for row in report["sources"]}
    assert statuses == {
        "Form Source": "fresh",
        "Deadline Source": "stale",
        "Missing Deadline": "missing",
        "Portal News": "fresh",
    }
    portal_event = next(
        row for row in report["events"] if row["event_model"] == "portal_service_change"
    )
    assert portal_event["portal"] == "gov.uk"
    assert portal_event["service_id"] == "apply-renew-passport"
    assert portal_event["service_name"] == "Portal service notice"
    assert portal_event["requirement_summary"] == "photo ID and proof of address"
    assert len(portal_event["content_hash"]) == 64
    assert portal_event["event_status"] == "fresh"
    assert portal_event["paperwork_event_key"].startswith(
        "portal-service-change:portal-news"
    )

    source_rows = {row["source"]: row for row in report["sources"]}
    assert source_rows["Portal News"]["latest_portal"] == "gov.uk"
    assert source_rows["Portal News"]["latest_service_id"] == "apply-renew-passport"
    assert source_rows["Portal News"]["latest_requirement_summary"] == (
        "photo ID and proof of address"
    )
    document = report["document_diffs"][0]
    assert document["document_url"] == "https://example.com/forms/i-130"
    assert len(document["content_hash"]) == 64
    form_event = next(row for row in report["events"] if row["event_model"] == "form_revision")
    assert form_event["evidence_url"] == "https://example.com/forms/i-130"
    assert len(form_event["content_hash"]) == 64
    deadline_event = next(
        row for row in report["events"] if row["event_model"] == "filing_deadline"
    )
    assert deadline_event["event_status"] == "stale"
    assert deadline_event["due_date"] == ""
    daily_reasons = [item["reason"] for item in report["daily_review_items"]]
    assert "source_status_stale" in daily_reasons
    assert "source_status_missing" in daily_reasons
    assert "source_collection_error" in daily_reasons
    assert "event_status_stale" in daily_reasons
    assert "filing_deadline_missing_due_date" in daily_reasons


def test_build_quality_report_does_not_use_generic_portal_routes_as_service_ids() -> None:
    now = datetime(2026, 4, 12, tzinfo=UTC)
    category = CategoryConfig(
        category_name="paperwork",
        display_name="Paperwork",
        sources=[_source("정부24 서비스", "portal_service_change", 3)],
        entities=[],
    )
    report = build_quality_report(
        category=category,
        articles=[
            Article(
                title="메인 | 정부24",
                link="https://www.gov.kr/portal/main/nologin",
                summary="정부24 메인 페이지",
                published=now,
                collected_at=now,
                source="정부24 서비스",
                category="paperwork",
            )
        ],
        quality_config={
            "data_quality": {
                "quality_outputs": {"tracked_event_models": ["portal_service_change"]}
            }
        },
        generated_at=now,
    )

    event = report["events"][0]
    assert event["service_id"] == ""
    assert event["portal_service_key"] == "gov.kr:메인-정부24"
    assert event["event_status"] == "fresh"


def test_source_freshness_uses_generated_at_for_collected_at_browser_capture() -> None:
    now = datetime(2026, 4, 12, tzinfo=UTC)
    category = CategoryConfig(
        category_name="paperwork",
        display_name="Paperwork",
        sources=[
            Source(
                name="정부24 서비스",
                type="javascript",
                url="https://www.gov.kr/portal/main/nologin",
                config={
                    "event_model": "portal_service_change",
                    "event_date_field": "collected_at",
                    "freshness_sla_days": 4,
                },
            )
        ],
        entities=[],
    )

    report = build_quality_report(
        category=category,
        articles=[
            Article(
                title="메인 | 정부24",
                link="https://www.gov.kr/portal/main/nologin",
                summary="정부24 메인 페이지",
                published=None,
                collected_at=None,
                source="정부24 서비스",
                category="paperwork",
            )
        ],
        quality_config={
            "data_quality": {
                "quality_outputs": {"tracked_event_models": ["portal_service_change"]}
            }
        },
        generated_at=now,
    )

    source = report["sources"][0]
    assert source["status"] == "fresh"
    assert source["latest_event_at"] == now.isoformat()


def test_build_quality_report_excludes_disabled_sources_from_active_tracked_count() -> None:
    now = datetime(2026, 4, 12, tzinfo=UTC)
    category = CategoryConfig(
        category_name="paperwork",
        display_name="Paperwork",
        sources=[
            Source(
                name="Disabled Form Feed",
                type="rss",
                url="https://example.com/disabled",
                enabled=False,
                config={
                    "event_model": "form_revision",
                    "skip_reason": "blocked upstream",
                    "reenable_gate": "browser fixture and document hash diff",
                },
            )
        ],
        entities=[],
    )

    report = build_quality_report(
        category=category,
        articles=[
            Article(
                title="Old disabled source article",
                link="https://example.com/disabled/form-a",
                summary="Should not produce an active event",
                published=now,
                collected_at=now,
                source="Disabled Form Feed",
                category="paperwork",
            )
        ],
        quality_config={
            "data_quality": {
                "quality_outputs": {"tracked_event_models": ["form_revision"]}
            }
        },
        generated_at=now,
    )

    assert report["summary"]["tracked_sources"] == 0
    assert report["summary"]["skipped_disabled_sources"] == 1
    assert report["summary"]["form_revision_events"] == 0
    assert report["summary"]["document_diff_count"] == 0
    assert report["summary"]["daily_review_item_count"] == 1
    source = report["sources"][0]
    assert source["tracked"] is False
    assert source["status"] == "skipped_disabled"
    assert source["skip_reason"] == "blocked upstream"
    assert source["reenable_gate"] == "browser fixture and document hash diff"
    assert report["daily_review_items"][0]["reason"] == "disabled_source_gate"


def test_build_quality_report_uses_freshness_articles_without_inflating_events() -> None:
    now = datetime(2026, 4, 12, tzinfo=UTC)
    category = CategoryConfig(
        category_name="paperwork",
        display_name="Paperwork",
        sources=[
            _source("Sparse Statutory Feed", "filing_deadline", 7),
        ],
        entities=[],
    )
    older_article = Article(
        title="Statutory instrument from prior report window",
        link="https://example.com/statutory/prior",
        summary="The instrument changes a filing requirement.",
        published=now - timedelta(days=9),
        collected_at=now,
        source="Sparse Statutory Feed",
        category="paperwork",
    )

    report = build_quality_report(
        category=category,
        articles=[],
        freshness_articles=[older_article],
        quality_config={
            "data_quality": {
                "quality_outputs": {"tracked_event_models": ["filing_deadline"]}
            }
        },
        generated_at=now,
    )

    assert report["summary"]["missing_sources"] == 0
    assert report["summary"]["stale_sources"] == 1
    assert report["summary"]["filing_deadline_events"] == 0
    assert report["summary"]["daily_review_item_count"] == 1
    assert report["sources"][0]["latest_title"] == (
        "Statutory instrument from prior report window"
    )


def test_write_quality_report_writes_latest_dated_and_diff_files(tmp_path) -> None:
    report = {
        "category": "paperwork",
        "generated_at": "2026-04-12T03:04:05+00:00",
        "summary": {},
        "sources": [],
        "events": [],
        "document_diffs": [
            {
                "source": "Form Source",
                "title": "Form A",
                "document_url": "https://example.com/form-a",
                "content_hash": "a" * 64,
                "status": "observed",
            },
            {
                "source": "Form Source",
                "title": "Form B",
                "document_url": "https://example.com/form-b",
                "content_hash": "b" * 64,
                "status": "observed",
            },
        ],
        "daily_review_items": [],
        "errors": [],
    }

    paths = write_quality_report(report, output_dir=tmp_path, category_name="paperwork")

    assert paths["latest"] == tmp_path / "paperwork_quality.json"
    assert paths["dated"] == tmp_path / "paperwork_20260412_quality.json"
    assert paths["document_diff_latest"] == (
        tmp_path / "document_diffs" / "paperwork_document_diffs.json"
    )
    assert paths["document_diff_dated"] == (
        tmp_path / "document_diffs" / "paperwork_20260412_document_diffs.json"
    )
    first_payload = json.loads(paths["latest"].read_text(encoding="utf-8"))
    assert first_payload["summary"]["new_document_count"] == 2
    assert {row["status"] for row in first_payload["document_diffs"]} == {"new"}

    second_report = {
        "category": "paperwork",
        "generated_at": "2026-04-13T03:04:05+00:00",
        "summary": {},
        "sources": [],
        "events": [],
        "document_diffs": [
            {
                "source": "Form Source",
                "title": "Form A",
                "document_url": "https://example.com/form-a",
                "content_hash": "a" * 64,
                "status": "observed",
            },
            {
                "source": "Form Source",
                "title": "Form B revised",
                "document_url": "https://example.com/form-b",
                "content_hash": "c" * 64,
                "status": "observed",
            },
        ],
        "errors": [],
    }
    second_paths = write_quality_report(
        second_report,
        output_dir=tmp_path,
        category_name="paperwork",
    )
    second_payload = json.loads(second_paths["latest"].read_text(encoding="utf-8"))
    statuses = {row["document_url"]: row for row in second_payload["document_diffs"]}

    assert second_payload["summary"]["changed_document_count"] == 1
    assert second_payload["summary"]["unchanged_document_count"] == 1
    assert statuses["https://example.com/form-a"]["status"] == "unchanged"
    assert statuses["https://example.com/form-b"]["status"] == "changed"
    assert statuses["https://example.com/form-b"]["previous_content_hash"] == "b" * 64
