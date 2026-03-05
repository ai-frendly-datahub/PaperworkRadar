from __future__ import annotations

from paperworkradar.analyzer import apply_entity_rules
from paperworkradar.models import Article, EntityDefinition


def test_apply_entity_rules_matches_case_insensitive_and_separator_variants() -> None:
    article = Article(
        title="New E Government application deadline announced",
        link="https://example.com/notice",
        summary="Digital GOVERNMENT filing process and permit registration details.",
        published=None,
        source="Test Source",
        category="paperwork",
    )
    entities = [
        EntityDefinition(name="DigitalGov", display_name="전자정부", keywords=["e-government"]),
        EntityDefinition(name="Deadline", display_name="마감/기한", keywords=["application-deadline"]),
    ]

    analyzed = apply_entity_rules([article], entities)

    assert "DigitalGov" in analyzed[0].matched_entities
    assert "Deadline" in analyzed[0].matched_entities
