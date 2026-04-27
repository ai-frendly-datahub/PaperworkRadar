from __future__ import annotations

from paperworkradar.config_loader import load_category_config, load_category_quality_config


def test_real_paperwork_config_exposes_data_quality_overlay() -> None:
    metadata = load_category_quality_config("paperwork")

    data_quality = metadata["data_quality"]
    assert isinstance(data_quality, dict)
    assert data_quality["priority"] == "P0"
    assert data_quality["primary_motion"] == "compliance-risk"
    assert "form_revision" in data_quality["event_models"]
    assert "filing_deadline" in data_quality["event_models"]
    assert data_quality["canonical_keys"]["form"]["fields"]
    assert data_quality["quality_outputs"]["freshness_report"] == (
        "reports/paperwork_quality.json"
    )
    assert data_quality["quality_outputs"]["document_diff_report"] == (
        "reports/document_diffs/paperwork_document_diffs.json"
    )
    assert data_quality["quality_outputs"]["tracked_event_models"] == [
        "form_revision",
        "filing_deadline",
        "portal_service_change",
    ]

    backlog = metadata["source_backlog"]
    assert isinstance(backlog, dict)
    form_candidates = {candidate["id"] for candidate in backlog["form_diff_candidates"]}
    deadline_candidates = {
        candidate["id"] for candidate in backlog["deadline_calendar_candidates"]
    }
    assert form_candidates >= {"uscis_forms_updates_html", "irs_forms_publications"}
    assert deadline_candidates >= {
        "irs_tax_deadlines",
        "uk_companies_house_filing_deadlines",
    }


def test_real_paperwork_sources_preserve_operational_metadata() -> None:
    config = load_category_config("paperwork")
    sources = {source.name: source for source in config.sources}

    forms_focus = sources["Federal Register Forms Focus"]
    assert forms_focus.trust_tier == "T1_official"
    assert "form_diff" in forms_focus.info_purpose
    assert "operational_event" in forms_focus.info_purpose
    assert forms_focus.config["event_model"] == "form_revision"
    assert forms_focus.config["observed_date_field"] == "collected_at"
    assert forms_focus.config["canonical_key_fields"]

    hmrc = sources["GOV.UK HMRC"]
    assert "filing_deadline" in hmrc.info_purpose
    assert hmrc.config["event_model"] == "filing_deadline"
    assert hmrc.config["freshness_sla_days"] == 2

    gov24 = sources["정부24 서비스"]
    assert gov24.config["event_model"] == "portal_service_change"
    assert "required_document" in gov24.info_purpose
