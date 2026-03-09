from __future__ import annotations

from importlib import import_module
from typing import Optional, Protocol, cast


class _ParsedQuery(Protocol):
    search_text: str
    days: Optional[int]
    limit: Optional[int]
    category: Optional[str]


class _ParseQuery(Protocol):
    def __call__(self, raw: str) -> _ParsedQuery: ...


parse_query = cast(_ParseQuery, import_module("paperworkradar.nl_query").parse_query)


def test_parse_time_filter_days() -> None:
    parsed = parse_query("최근 3일 비자")

    assert parsed.days == 3
    assert "비자" in parsed.search_text


def test_parse_time_filter_weeks() -> None:
    parsed = parse_query("최근 1주 행정 뉴스")

    assert parsed.days == 7
    assert "행정" in parsed.search_text


def test_parse_time_filter_months() -> None:
    parsed = parse_query("지난 3개월 등록")

    assert parsed.days == 90
    assert "등록" in parsed.search_text


def test_parse_time_filter_english() -> None:
    parsed = parse_query("last 7 days visa updates")

    assert parsed.days == 7
    assert "visa" in parsed.search_text


def test_parse_limit_korean() -> None:
    parsed = parse_query("행정 뉴스 10개")

    assert parsed.limit == 10
    assert "행정" in parsed.search_text


def test_parse_limit_english() -> None:
    parsed = parse_query("top 5 permits")

    assert parsed.limit == 5
    assert "permits" in parsed.search_text


def test_parse_combined_filters() -> None:
    parsed = parse_query("최근 2주 비자 서류 5개")

    assert parsed.days == 14
    assert parsed.limit == 5
    assert parsed.search_text == "비자 서류"


def test_parse_no_filters() -> None:
    parsed = parse_query("tax filing")

    assert parsed.days is None
    assert parsed.limit is None
    assert parsed.search_text == "tax filing"


def test_parse_category_always_none() -> None:
    parsed = parse_query("최근 1주 서류")

    assert parsed.category is None


def test_parse_empty_string() -> None:
    parsed = parse_query("")

    assert parsed.search_text == ""
    assert parsed.days is None
    assert parsed.limit is None
    assert parsed.category is None


def test_parse_whitespace_cleanup() -> None:
    parsed = parse_query("  최근 2주   비자   서류   5개  ")

    assert parsed.days == 14
    assert parsed.limit == 5
    assert parsed.search_text == "비자 서류"
