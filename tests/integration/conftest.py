from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from paperworkradar.models import Article, CategoryConfig, EntityDefinition, Source
from paperworkradar.storage import RadarStorage


@pytest.fixture
def tmp_storage(tmp_path: Path) -> RadarStorage:
    """Create a temporary RadarStorage instance for testing."""
    db_path = tmp_path / "test.duckdb"
    storage = RadarStorage(db_path)
    yield storage
    storage.close()


@pytest.fixture
def sample_articles() -> list[Article]:
    """Create sample articles with realistic government paperwork data."""
    now = datetime.now(UTC)
    return [
        Article(
            title="신분증 발급 절차 안내",
            link="https://gov.kr/paperwork/id-card-2024",
            summary="신분증 발급을 위한 필요 서류 및 절차를 안내합니다. 주민등록증, 운전면허증 등.",
            published=now,
            source="gov24",
            category="paperwork",
            matched_entities={},
        ),
        Article(
            title="여권 신청 방법 및 수수료",
            link="https://gov.kr/paperwork/passport-2024",
            summary="여권 신청에 필요한 서류와 수수료 정보입니다. 일반여권, 긴급여권 등.",
            published=now,
            source="gov24",
            category="paperwork",
            matched_entities={},
        ),
        Article(
            title="운전면허증 갱신 안내",
            link="https://gov.kr/paperwork/license-renewal-2024",
            summary="운전면허증 갱신 절차 및 필요 서류를 안내합니다.",
            published=now,
            source="gov24",
            category="paperwork",
            matched_entities={},
        ),
        Article(
            title="혼인신고 서류 준비",
            link="https://gov.kr/paperwork/marriage-2024",
            summary="혼인신고에 필요한 서류 목록과 신청 절차입니다.",
            published=now,
            source="gov24",
            category="paperwork",
            matched_entities={},
        ),
        Article(
            title="출생신고 방법 안내",
            link="https://gov.kr/paperwork/birth-2024",
            summary="신생아 출생신고 절차 및 필요 서류를 안내합니다.",
            published=now,
            source="gov24",
            category="paperwork",
            matched_entities={},
        ),
    ]


@pytest.fixture
def sample_entities() -> list[EntityDefinition]:
    """Create sample entities with government paperwork keywords."""
    return [
        EntityDefinition(
            name="identification",
            display_name="신분증",
            keywords=["신분증", "주민등록증", "신분", "증명"],
        ),
        EntityDefinition(
            name="passport",
            display_name="여권",
            keywords=["여권", "해외", "국제", "여행"],
        ),
        EntityDefinition(
            name="license",
            display_name="면허증",
            keywords=["면허", "운전", "면허증", "갱신"],
        ),
        EntityDefinition(
            name="vital_records",
            display_name="호적서류",
            keywords=["혼인", "출생", "신고", "호적"],
        ),
        EntityDefinition(
            name="government_services",
            display_name="정부서비스",
            keywords=["정부", "민원", "서비스", "신청"],
        ),
    ]


@pytest.fixture
def sample_config(tmp_path: Path, sample_entities: list[EntityDefinition]) -> CategoryConfig:
    """Create a sample CategoryConfig for testing."""
    sources = [
        Source(
            name="gov24",
            type="api",
            url="https://api.gov.kr/paperwork",
        ),
    ]
    return CategoryConfig(
        category_name="paperwork",
        display_name="정부 민원 서류",
        sources=sources,
        entities=sample_entities,
    )
