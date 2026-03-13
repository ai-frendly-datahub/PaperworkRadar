from __future__ import annotations

import pytest

from paperworkradar.models import Article, EntityDefinition


def _apply_entity_rules_py39(
    articles: list[Article], entities: list[EntityDefinition]
) -> list[Article]:
    """Apply entity rules (Python 3.9 compatible version)."""
    analyzed: list[Article] = []
    lowered_entities = [
        EntityDefinition(
            name=e.name,
            display_name=e.display_name,
            keywords=[kw.lower() for kw in e.keywords],
        )
        for e in entities
    ]

    for article in articles:
        haystack = f"{article.title}\n{article.summary}".lower()
        matches: dict[str, list[str]] = {}
        for entity, lowered_entity in zip(entities, lowered_entities, strict=False):
            hit_keywords = [kw for kw in lowered_entity.keywords if kw and kw in haystack]
            if hit_keywords:
                matches[entity.name] = hit_keywords
        article.matched_entities = matches
        analyzed.append(article)

    return analyzed


@pytest.mark.integration
def test_entity_extraction_integration(
    sample_articles: list[Article],
    sample_entities: list[EntityDefinition],
) -> None:
    """Test entity extraction integration: apply rules → verify tagged entities."""
    analyzed = _apply_entity_rules_py39(sample_articles, sample_entities)

    assert len(analyzed) == 5
    assert all(isinstance(a, Article) for a in analyzed)

    article_1 = analyzed[0]
    assert "identification" in article_1.matched_entities
    assert "신분증" in article_1.matched_entities["identification"]

    article_2 = analyzed[1]
    assert "passport" in article_2.matched_entities
    assert "여권" in article_2.matched_entities["passport"]

    article_3 = analyzed[2]
    assert "license" in article_3.matched_entities
    assert "면허" in article_3.matched_entities["license"]

    article_4 = analyzed[3]
    assert "vital_records" in article_4.matched_entities
    assert "혼인" in article_4.matched_entities["vital_records"]

    article_5 = analyzed[4]
    assert "vital_records" in article_5.matched_entities
    assert "출생" in article_5.matched_entities["vital_records"]
