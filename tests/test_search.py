from datetime import datetime, timezone
from pathlib import Path

import ocr_tool.storage.files as files
from ocr_tool.models import (
    DOCUMENT_STATUS_IMPORTED,
    LAYOUT_TYPE_TABLE,
    REVIEW_STATUS_CHECKED,
    Document,
    Page,
)
from ocr_tool.search import build_search_snippet, search_corrected_text
from ocr_tool.storage.db import initialize_database, insert_document, insert_pages
from ocr_tool.storage.files import save_raw_ocr_text, save_corrected_text


def _document() -> Document:
    return Document(
        id="doc123",
        original_filename="source.pdf",
        stored_filename="doc123_source.pdf",
        input_path=Path("data/input/doc123_source.pdf"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        status=DOCUMENT_STATUS_IMPORTED,
    )


def _pages() -> list[Page]:
    return [
        Page(
            id="doc123_page_0001",
            document_id="doc123",
            page_number=1,
            image_path=Path("data/pages/doc123/page_0001.png"),
            review_status=REVIEW_STATUS_CHECKED,
            layout_type=LAYOUT_TYPE_TABLE,
            needs_manual_review=True,
        ),
        Page(
            id="doc123_page_0002",
            document_id="doc123",
            page_number=2,
            image_path=Path("data/pages/doc123/page_0002.png"),
        ),
    ]


def _setup_database(tmp_path, monkeypatch):
    database_path = tmp_path / "app.db"
    monkeypatch.setattr(files, "CORRECTED_DIR", tmp_path / "corrected")
    monkeypatch.setattr(files, "OCR_RAW_DIR", tmp_path / "ocr_raw")
    initialize_database(database_path)
    insert_document(_document(), database_path)
    insert_pages(_pages(), database_path)
    return database_path


def test_search_corrected_text_returns_page_number_and_snippet(tmp_path, monkeypatch):
    database_path = _setup_database(tmp_path, monkeypatch)
    save_corrected_text("doc123", 1, "before impairment loss after")

    results = search_corrected_text("doc123", "impairment", database_path)

    assert len(results) == 1
    assert results[0]["page_number"] == 1
    assert "impairment loss" in results[0]["snippet"]


def test_search_corrected_text_is_case_insensitive(tmp_path, monkeypatch):
    database_path = _setup_database(tmp_path, monkeypatch)
    save_corrected_text("doc123", 1, "Deferred Tax Asset")

    results = search_corrected_text("doc123", "tax asset", database_path)

    assert len(results) == 1
    assert results[0]["matched_text"] == "Tax Asset"


def test_search_corrected_text_skips_pages_without_corrected_text(
    tmp_path, monkeypatch
):
    database_path = _setup_database(tmp_path, monkeypatch)
    save_corrected_text("doc123", 1, "matching text")

    results = search_corrected_text("doc123", "matching", database_path)

    assert [result["page_number"] for result in results] == [1]


def test_search_corrected_text_does_not_search_raw_ocr(tmp_path, monkeypatch):
    database_path = _setup_database(tmp_path, monkeypatch)
    save_raw_ocr_text("doc123", 1, "raw-only keyword")

    results = search_corrected_text("doc123", "raw-only", database_path)

    assert results == []


def test_search_corrected_text_max_results_limits_matches(tmp_path, monkeypatch):
    database_path = _setup_database(tmp_path, monkeypatch)
    save_corrected_text("doc123", 1, "keyword one")
    save_corrected_text("doc123", 2, "keyword two")

    results = search_corrected_text(
        "doc123",
        "keyword",
        database_path,
        max_results=1,
    )

    assert len(results) == 1


def test_search_corrected_text_empty_query_returns_empty(tmp_path, monkeypatch):
    database_path = _setup_database(tmp_path, monkeypatch)
    save_corrected_text("doc123", 1, "keyword")

    assert search_corrected_text("doc123", "   ", database_path) == []


def test_build_search_snippet_collapses_whitespace():
    snippet = build_search_snippet("alpha\n\n   beta\tgamma", "beta")

    assert snippet == "alpha beta gamma"


def test_search_corrected_text_includes_page_metadata(tmp_path, monkeypatch):
    database_path = _setup_database(tmp_path, monkeypatch)
    save_corrected_text("doc123", 1, "metadata keyword")

    result = search_corrected_text("doc123", "keyword", database_path)[0]

    assert result["layout_type"] == LAYOUT_TYPE_TABLE
    assert result["review_status"] == REVIEW_STATUS_CHECKED
    assert result["needs_manual_review"] is True
    assert result["corrected_text_path"].endswith("doc123/page_0001.txt")
