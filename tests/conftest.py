from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import structlog


@pytest.fixture(autouse=True)
def reset_structlog() -> object:
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


@pytest.fixture(autouse=True)
def isolated_crawl_health(tmp_path, monkeypatch):
    """Per-test crawl-health DB so disable thresholds don't bleed across
    tests and the production data/radar_data.duckdb is never touched."""
    health_db = tmp_path / "_crawl_health.duckdb"
    monkeypatch.setenv("RADAR_CRAWL_HEALTH_DB_PATH", str(health_db))
    yield


@pytest.fixture
def sample_source() -> object:
    from paperworkradar.models import Source

    return Source(name="Example RSS", type="rss", url="https://example.com/feed.xml")


@pytest.fixture
def sample_entity() -> object:
    from paperworkradar.models import EntityDefinition

    return EntityDefinition(name="topic", display_name="Topic", keywords=["ai", "cloud", "python"])


@pytest.fixture
def sample_article() -> object:
    from paperworkradar.models import Article

    return Article(
        title="AI and cloud market update",
        link="https://example.com/article-1",
        summary="Python tooling and AI adoption continue to grow.",
        published=datetime.now(UTC) - timedelta(days=2),
        source="Example RSS",
        category="tech",
        matched_entities={"topic": ["ai", "cloud", "python"]},
    )


@pytest.fixture
def tmp_duckdb(tmp_path: Path) -> Path:
    return tmp_path / "test_radar_data.duckdb"


@pytest.fixture
def tmp_search_db(tmp_path: Path) -> Path:
    return tmp_path / "test_search_index.db"


@pytest.fixture
def tmp_storage(tmp_duckdb: Path) -> object:
    from paperworkradar.storage import RadarStorage

    storage = RadarStorage(tmp_duckdb)
    try:
        yield storage
    finally:
        storage.close()


@pytest.fixture
def tmp_search_index(tmp_search_db: Path) -> object:
    from paperworkradar.search_index import SearchIndex

    index = SearchIndex(tmp_search_db)
    try:
        yield index
    finally:
        index.close()
