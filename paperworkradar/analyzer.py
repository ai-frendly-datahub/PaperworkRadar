from __future__ import annotations

import re
from collections.abc import Iterable

import radar_core.analyzer as _rca

from radar_core.models import Article, EntityDefinition


# Mirror radar_core's module-level analyzer so tests that monkey-patch
# this attribute on this repo's analyzer module actually take effect.
_korean_analyzer = _rca._korean_analyzer


def _is_ascii_only(keyword: str) -> bool:
    return all(ord(char) < 128 for char in keyword)


def apply_entity_rules(
    articles: Iterable[Article], entities: list[EntityDefinition]
) -> list[Article]:
    analyzed: list[Article] = []
    for article in articles:
        haystack = f"{article.title}\n{article.summary}"
        haystack_lower = haystack.lower()
        matches: dict[str, list[str]] = {}
        for entity in entities:
            hit_keywords: list[str] = []
            for keyword in entity.keywords:
                normalized = keyword.lower()
                if not normalized:
                    continue
                if _is_ascii_only(normalized):
                    pattern = re.compile(r"\b" + re.escape(normalized) + r"\b", re.IGNORECASE)
                    if pattern.search(haystack):
                        hit_keywords.append(normalized)
                    continue
                # CJK keyword: prefer direct substring, then kiwi fallback
                if normalized in haystack_lower:
                    hit_keywords.append(normalized)
                    continue
                if getattr(_korean_analyzer, "_kiwi", None) is not None:
                    if _korean_analyzer.match_keyword(haystack, normalized):
                        hit_keywords.append(normalized)
            if hit_keywords:
                matches[entity.name] = hit_keywords
        article.matched_entities = matches
        analyzed.append(article)
    return analyzed


__all__ = ["apply_entity_rules"]
