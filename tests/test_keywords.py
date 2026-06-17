import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ocr_tool.index_parser import import_index_lines
from ocr_tool.models import DOCUMENT_STATUS_IMPORTED, Document
from ocr_tool.storage.db import (
    initialize_database,
    insert_document,
    insert_keyword,
    insert_keyword_ref,
    list_keywords,
    search_keywords,
)


def _document() -> Document:
    return Document(
        id="doc123",
        original_filename="source.pdf",
        stored_filename="doc123_source.pdf",
        input_path=Path("data/input/doc123_source.pdf"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        status=DOCUMENT_STATUS_IMPORTED,
    )


def test_initialize_database_creates_keyword_tables(tmp_path):
    database_path = tmp_path / "app.db"

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"keywords", "keyword_refs"}.issubset(table_names)


def test_insert_keyword_returns_id_and_reuses_duplicate_normalized_keyword(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)

    first_id = insert_keyword(
        "doc123",
        "Business Judgment Rule",
        database_path=database_path,
    )
    second_id = insert_keyword(
        "doc123",
        " business   judgment rule ",
        database_path=database_path,
    )

    assert first_id == second_id
    assert len(list_keywords("doc123", database_path)) == 1


def test_insert_keyword_ref_stores_refs_with_null_target_page_number(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)
    keyword_id = insert_keyword("doc123", "Contracts", database_path=database_path)

    insert_keyword_ref(
        keyword_id,
        "2-1",
        section_code="2-1",
        database_path=database_path,
    )

    keyword = list_keywords("doc123", database_path)[0]
    assert keyword["refs"] == [
        {
            "id": keyword["refs"][0]["id"],
            "ref_text": "2-1",
            "section_code": "2-1",
            "target_page_number": None,
        }
    ]


def test_list_keywords_includes_refs(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)
    keyword_id = insert_keyword("doc123", "Actual damages", database_path=database_path)
    insert_keyword_ref(
        keyword_id,
        "10-4",
        section_code="10-4",
        database_path=database_path,
    )
    insert_keyword_ref(
        keyword_id,
        "10-5",
        section_code="10-5",
        database_path=database_path,
    )

    keywords = list_keywords("doc123", database_path)

    assert keywords[0]["keyword"] == "Actual damages"
    assert [ref["ref_text"] for ref in keywords[0]["refs"]] == ["10-4", "10-5"]


def test_search_keywords_is_case_insensitive(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)
    insert_keyword("doc123", "Strict Liability", database_path=database_path)

    results = search_keywords("doc123", "liability", database_path)

    assert [result["keyword"] for result in results] == ["Strict Liability"]


def test_import_index_lines_inserts_keyword_ref_counts(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)

    counts = import_index_lines(
        "doc123",
        [
            "Business judgment rule 9-20",
            "Strict liability 1-3, 3-9, 3-12",
        ],
        database_path,
    )

    assert counts == {"keywords": 2, "refs": 4}
