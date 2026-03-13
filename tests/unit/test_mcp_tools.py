from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

import duckdb


class _SearchIndex(Protocol):
    def upsert(self, link: str, title: str, body: str) -> None: ...

    def close(self) -> None: ...

    def __enter__(self) -> _SearchIndex: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...


class _SearchIndexCtor(Protocol):
    def __call__(self, db_path: Path) -> _SearchIndex: ...


SearchIndex = cast(_SearchIndexCtor, import_module("paperworkradar.search_index").SearchIndex)
_tools = import_module("paperworkradar.mcp_server.tools")


def _init_articles_table(db_path: Path) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        _ = conn.execute(
            """
            CREATE TABLE articles (
                id BIGINT PRIMARY KEY,
                category TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                link TEXT NOT NULL UNIQUE,
                summary TEXT,
                published TIMESTAMP,
                collected_at TIMESTAMP NOT NULL,
                entities_json TEXT
            )
            """
        )
    finally:
        conn.close()


def _seed_article(
    *,
    db_path: Path,
    article_id: int,
    title: str,
    link: str,
    collected_at: datetime,
    entities: dict[str, list[str]] | None = None,
) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        _ = conn.execute(
            """
            INSERT INTO articles (id, category, source, title, link, summary, published, collected_at, entities_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                article_id,
                "paperwork",
                "Test Source",
                title,
                link,
                "summary",
                None,
                collected_at,
                json.dumps(entities or {}, ensure_ascii=False),
            ],
        )
    finally:
        conn.close()


def test_handle_search(tmp_path: Path) -> None:
    handle_search = cast(Callable[..., str], _tools.handle_search)

    db_path = tmp_path / "radar.duckdb"
    search_db_path = tmp_path / "search.db"
    _init_articles_table(db_path)

    now = datetime.now()
    recent_link = "https://example.com/recent"
    old_link = "https://example.com/old"

    _seed_article(
        db_path=db_path,
        article_id=1,
        title="Recent filing requirement",
        link=recent_link,
        collected_at=now - timedelta(days=2),
    )
    _seed_article(
        db_path=db_path,
        article_id=2,
        title="Old filing requirement",
        link=old_link,
        collected_at=now - timedelta(days=20),
    )

    with SearchIndex(search_db_path) as idx:
        idx.upsert(recent_link, "Recent filing requirement", "Tax filing deadline update")
        idx.upsert(old_link, "Old filing requirement", "Old filing process")

    output = handle_search(
        search_db_path=search_db_path,
        db_path=db_path,
        query="last 7 days filing",
        limit=10,
    )

    assert "Recent filing requirement" in output
    assert "Old filing requirement" not in output


def test_handle_recent_updates(tmp_path: Path) -> None:
    handle_recent_updates = cast(Callable[..., str], _tools.handle_recent_updates)

    db_path = tmp_path / "radar.duckdb"
    _init_articles_table(db_path)
    now = datetime.now()

    _seed_article(
        db_path=db_path,
        article_id=1,
        title="Most recent",
        link="https://example.com/1",
        collected_at=now - timedelta(hours=1),
    )
    _seed_article(
        db_path=db_path,
        article_id=2,
        title="Older",
        link="https://example.com/2",
        collected_at=now - timedelta(days=2),
    )

    output = handle_recent_updates(db_path=db_path, days=1, limit=10)

    assert "Most recent" in output
    assert "Older" not in output


def test_handle_sql_select(tmp_path: Path) -> None:
    handle_sql = cast(Callable[..., str], _tools.handle_sql)

    db_path = tmp_path / "radar.duckdb"
    _init_articles_table(db_path)

    output = handle_sql(db_path=db_path, query="SELECT COUNT(*) AS total FROM articles")

    assert "total" in output
    assert "0" in output


def test_handle_sql_blocked(tmp_path: Path) -> None:
    handle_sql = cast(Callable[..., str], _tools.handle_sql)

    db_path = tmp_path / "radar.duckdb"
    _init_articles_table(db_path)

    output = handle_sql(db_path=db_path, query="DROP TABLE articles")

    assert "Only SELECT/WITH/EXPLAIN queries are allowed" in output


def test_handle_top_trends(tmp_path: Path) -> None:
    handle_top_trends = cast(Callable[..., str], _tools.handle_top_trends)

    db_path = tmp_path / "radar.duckdb"
    _init_articles_table(db_path)
    now = datetime.now()

    _seed_article(
        db_path=db_path,
        article_id=1,
        title="a",
        link="https://example.com/a",
        collected_at=now - timedelta(days=1),
        entities={"TaxDocs": ["tax filing", "irs"], "Deadline": ["deadline"]},
    )
    _seed_article(
        db_path=db_path,
        article_id=2,
        title="b",
        link="https://example.com/b",
        collected_at=now - timedelta(days=1),
        entities={"TaxDocs": ["tax form"]},
    )

    output = handle_top_trends(db_path=db_path, days=7, limit=10)

    assert "TaxDocs" in output
    assert "3" in output
    assert "Deadline" in output
    assert "1" in output


def test_handle_doc_checklist(tmp_path: Path) -> None:
    handle_doc_checklist = cast(Callable[..., str], _tools.handle_doc_checklist)

    db_path = tmp_path / "radar.duckdb"
    _init_articles_table(db_path)
    now = datetime.now()

    _seed_article(
        db_path=db_path,
        article_id=1,
        title="Tax filing update",
        link="https://example.com/tax",
        collected_at=now - timedelta(days=1),
        entities={"TaxDocs": ["tax filing"], "Deadline": ["due date"]},
    )
    _seed_article(
        db_path=db_path,
        article_id=2,
        title="Visa permit notice",
        link="https://example.com/visa",
        collected_at=now - timedelta(days=2),
        entities={"Visa": ["work permit"]},
    )

    output = handle_doc_checklist(db_path=db_path, days=30, limit=5)

    assert "Document checklist (last 30 days):" in output
    assert "[TaxDocs]" in output
    assert "Tax filing update (Test Source)" in output
    assert "[Visa]" in output
