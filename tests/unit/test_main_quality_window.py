from __future__ import annotations

from main import _quality_article_limit, _quality_lookback_days
from paperworkradar.models import Source


def test_quality_lookback_extends_beyond_report_window_and_source_sla() -> None:
    sources = [
        Source(
            name="Sparse Statutory Feed",
            type="rss",
            url="https://example.com/feed",
            config={"event_model": "filing_deadline", "freshness_sla_days": 14},
        )
    ]

    lookback_days = _quality_lookback_days(
        {
            "data_quality": {
                "freshness_sla": {
                    "filing_deadline": {"max_age_days": 2},
                    "form_revision": {"max_age_days": 3},
                }
            }
        },
        sources=sources,
        minimum_days=7,
    )

    assert lookback_days == 42
    assert _quality_article_limit(sources) == 1000


def test_quality_article_limit_scales_for_large_source_catalog() -> None:
    sources = [
        Source(
            name=f"Source {index}",
            type="rss",
            url=f"https://example.com/{index}",
        )
        for index in range(31)
    ]

    assert _quality_article_limit(sources) == 6200
