from __future__ import annotations

from datetime import UTC, datetime

from paperworkradar.models import Article, CategoryConfig
from paperworkradar.reporter import generate_report


def test_generate_report_injects_paperwork_quality_panel(tmp_path, monkeypatch) -> None:
    fixed_now = datetime(2026, 4, 12, 9, 30, tzinfo=UTC)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    monkeypatch.setattr("radar_core.report_utils.datetime", FixedDateTime)

    output_path = tmp_path / "reports" / "paperwork_report.html"
    category = CategoryConfig(
        category_name="paperwork",
        display_name="Paperwork",
        sources=[],
        entities=[],
    )
    article = Article(
        title="Updated immigration form",
        link="https://example.com/forms/i-130",
        summary="Form edition changed",
        published=fixed_now,
        collected_at=fixed_now,
        source="Federal Register Forms Focus",
        category="paperwork",
        matched_entities={"Form": ["I-130"]},
    )
    quality_report = {
        "summary": {
            "fresh_sources": 1,
            "stale_sources": 1,
            "missing_sources": 0,
            "form_revision_events": 1,
            "filing_deadline_events": 1,
            "portal_service_change_events": 1,
            "unique_portal_service_count": 1,
            "changed_document_count": 1,
            "new_document_count": 1,
            "fresh_paperwork_events": 2,
            "stale_paperwork_events": 1,
            "unique_paperwork_event_key_count": 3,
            "events_with_evidence_url": 3,
            "daily_review_item_count": 1,
        },
        "sources": [
            {
                "source": "GOV.UK HMRC",
                "status": "stale",
                "event_model": "filing_deadline",
                "age_days": 3,
            }
        ],
        "document_diffs": [
            {
                "source": "Federal Register Forms Focus",
                "title": "Updated immigration form",
                "document_url": "https://example.com/forms/i-130",
                "content_hash": "a" * 64,
                "status": "changed",
            }
        ],
        "events": [
            {
                "source": "Federal Register Forms Focus",
                "event_model": "form_revision",
                "title": "Updated immigration form",
                "event_at": "2026-04-12T09:30:00+00:00",
                "evidence_url": "https://example.com/forms/i-130",
                "content_hash": "a" * 64,
                "event_status": "fresh",
                "paperwork_event_key": "form-revision:federal-register-forms-focus:updated-immigration-form",
            },
            {
                "source": "GOV.UK HMRC",
                "event_model": "filing_deadline",
                "title": "HMRC deadline reminder",
                "event_at": "2026-04-10T09:30:00+00:00",
                "evidence_url": "https://example.com/deadlines/hmrc",
                "content_hash": "",
                "due_date": "2026-04-30",
                "event_status": "stale",
                "paperwork_event_key": "filing-deadline:gov-uk-hmrc:2026-04-30",
            },
            {
                "source": "GOV.UK Government Digital Service",
                "event_model": "portal_service_change",
                "title": "Passport service update",
                "portal": "gov.uk",
                "service_name": "Passport service update",
                "portal_service_key": "gov.uk:UK:apply-renew-passport",
                "requirement_summary": "Required document list changed.",
            }
        ],
        "daily_review_items": [
            {
                "reason": "filing_deadline_missing_due_date",
                "source": "GOV.UK HMRC",
                "event_model": "filing_deadline",
                "title": "HMRC deadline reminder",
                "evidence_url": "https://example.com/deadlines/hmrc",
            }
        ],
    }

    generate_report(
        category=category,
        articles=[article],
        output_path=output_path,
        stats={"sources": 1, "collected": 1, "matched": 1, "window_days": 7},
        quality_report=quality_report,
    )

    html = output_path.read_text(encoding="utf-8")
    dated_html = (tmp_path / "reports" / "paperwork_20260412.html").read_text(
        encoding="utf-8"
    )

    for rendered in (html, dated_html):
        assert 'id="paperwork-quality"' in rendered
        assert "Paperwork Quality" in rendered
        assert "paperwork_quality.json" in rendered
        assert "document_diffs" in rendered
        assert "portal_service_change" in rendered
        assert "portal changes" in rendered
        assert "daily review" in rendered
        assert "event keys" in rendered
        assert "evidence URLs" in rendered
        assert "filing_deadline_missing_due_date" in rendered
        assert "https://example.com/forms/i-130" in rendered
        assert "Passport service update" in rendered
        assert "GOV.UK HMRC" in rendered
        assert "Updated immigration form" in rendered

    summary = (tmp_path / "reports" / "paperwork_20260412_summary.json").read_text(
        encoding="utf-8"
    )
    assert '"repo": "PaperworkRadar"' in summary
    assert '"ontology_version": "0.1.0"' in summary
    assert '"paperwork.form_revision"' in summary
