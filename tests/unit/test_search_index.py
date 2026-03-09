from __future__ import annotations

import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Optional, Protocol, cast

import yaml



class _Settings(Protocol):
    search_db_path: Path


class _LoadSettings(Protocol):
    def __call__(self, config_path: Optional[Path] = None) -> _Settings: ...


load_settings = cast(_LoadSettings, import_module("paperworkradar.config_loader").load_settings)


class _SearchResult(Protocol):
    link: str
    title: str
    snippet: str
    rank: float


class _SearchIndex(Protocol):
    def upsert(self, link: str, title: str, body: str) -> None: ...

    def search(self, query: str, *, limit: int = 20) -> list[_SearchResult]: ...

    def close(self) -> None: ...

    def __enter__(self) -> _SearchIndex: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...


class _SearchIndexCtor(Protocol):
    def __call__(self, db_path: Path) -> _SearchIndex: ...


SearchIndex = cast(_SearchIndexCtor, import_module("paperworkradar.search_index").SearchIndex)


def test_index_creation_creates_tables_fts_and_triggers(tmp_path: Path) -> None:
    db_path = tmp_path / "search_index.db"

    with SearchIndex(db_path):
        pass

    conn = sqlite3.connect(db_path)
    try:
        rows = cast(
            list[tuple[str, str]],
            conn.execute("SELECT name, type FROM sqlite_master").fetchall(),
        )
    finally:
        conn.close()

    objects = {(name, object_type) for name, object_type in rows}
    assert ("documents", "table") in objects
    assert ("documents_fts", "table") in objects
    assert ("documents_ai", "trigger") in objects
    assert ("documents_ad", "trigger") in objects
    assert ("documents_au", "trigger") in objects


def test_upsert_and_search_returns_matching_results(tmp_path: Path) -> None:
    index = SearchIndex(tmp_path / "search_index.db")
    index.upsert(
        link="https://example.com/a",
        title="Visa process update",
        body="The visa processing timeline has changed.",
    )

    results = index.search("visa")
    index.close()

    assert len(results) == 1
    assert results[0].link == "https://example.com/a"
    assert results[0].title == "Visa process update"
    assert "<b>visa</b>" in results[0].snippet.lower()
    assert isinstance(results[0].rank, float)


def test_search_returns_empty_list_when_no_match(tmp_path: Path) -> None:
    index = SearchIndex(tmp_path / "search_index.db")
    index.upsert(
        link="https://example.com/a",
        title="Coffee market update",
        body="No admin content here.",
    )

    results = index.search("visa")
    index.close()

    assert results == []


def test_search_supports_korean_text(tmp_path: Path) -> None:
    index = SearchIndex(tmp_path / "search_index.db")
    index.upsert(
        link="https://example.com/ko",
        title="비자 서류 뉴스",
        body="비자 서류 요건이 변경되었습니다.",
    )

    results = index.search("비자 서류")
    index.close()

    assert len(results) == 1
    assert results[0].link == "https://example.com/ko"


def test_upsert_same_link_twice_updates_document(tmp_path: Path) -> None:
    index = SearchIndex(tmp_path / "search_index.db")
    link = "https://example.com/article"

    index.upsert(link=link, title="Old title", body="first version body")
    index.upsert(link=link, title="New title", body="second version body")

    new_results = index.search("second")
    old_results = index.search("first")
    index.close()

    assert len(new_results) == 1
    assert new_results[0].title == "New title"
    assert old_results == []


def test_search_respects_limit_parameter(tmp_path: Path) -> None:
    index = SearchIndex(tmp_path / "search_index.db")
    for idx in range(5):
        index.upsert(
            link=f"https://example.com/{idx}",
            title=f"Document {idx}",
            body="visa paperwork term",
        )

    results = index.search("visa", limit=2)
    index.close()

    assert len(results) == 2


def test_context_manager_supports_open_and_close(tmp_path: Path) -> None:
    db_path = tmp_path / "search_index.db"

    with SearchIndex(db_path) as index:
        index.upsert(
            link="https://example.com/a",
            title="Inside context",
            body="context manager test",
        )
        assert len(index.search("context")) == 1

    try:
        _ = index.search("context")
        assert False, "Expected sqlite3.ProgrammingError after connection close"
    except sqlite3.ProgrammingError:
        pass


def test_search_ranking_places_more_relevant_document_first(tmp_path: Path) -> None:
    index = SearchIndex(tmp_path / "search_index.db")
    index.upsert(
        link="https://example.com/high",
        title="Visa permit from Korea",
        body="Visa permit from Korea details. Visa permit checklist and permit timeline.",
    )
    index.upsert(
        link="https://example.com/low",
        title="Visa overview",
        body="This article mentions visa once.",
    )

    results = index.search("visa OR permit", limit=2)
    index.close()

    assert len(results) == 2
    assert results[0].link == "https://example.com/high"
    assert results[0].rank <= results[1].rank


def test_load_settings_reads_search_db_path_and_default() -> None:
    settings = load_settings()
    project_root = Path(__file__).resolve().parents[2]

    assert settings.search_db_path == (project_root / "data" / "search_index.db").resolve()


def test_load_settings_reads_custom_search_db_path(tmp_path: Path) -> None:
    custom_path = (tmp_path / "custom_search.db").resolve()
    config_path = tmp_path / "config.yaml"
    _ = config_path.write_text(
        yaml.safe_dump(
            {
                "database_path": "data/radar_data.duckdb",
                "report_dir": "reports",
                "raw_data_dir": "data/raw",
                "search_db_path": str(custom_path),
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.search_db_path == custom_path
