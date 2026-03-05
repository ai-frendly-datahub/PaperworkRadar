from __future__ import annotations

import re
from typing import Iterable, List

from .models import Article, EntityDefinition


def apply_entity_rules(articles: Iterable[Article], entities: List[EntityDefinition]) -> List[Article]:
    """Attach matched entity keywords to each article via simple keyword search."""
    analyzed: List[Article] = []
    normalized_entities = [
        EntityDefinition(
            name=e.name,
            display_name=e.display_name,
            keywords=list(dict.fromkeys(_normalize_text(kw) for kw in e.keywords if kw.strip())),
        )
        for e in entities
    ]

    for article in articles:
        haystack = _normalize_text(f"{article.title}\n{article.summary}")
        matches: dict[str, list[str]] = {}
        for entity, normalized_entity in zip(entities, normalized_entities, strict=False):
            hit_keywords = [kw for kw in normalized_entity.keywords if kw and kw in haystack]
            if hit_keywords:
                matches[entity.name] = hit_keywords
        article.matched_entities = matches
        analyzed.append(article)

    return analyzed


def _normalize_text(text: str) -> str:
    normalized = text.casefold()
    normalized = normalized.replace("-", " ").replace("_", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()
