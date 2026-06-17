import importlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import ocr_tool.config as config
import ocr_tool.storage.db as db
from ocr_tool.models import (
    DOCUMENT_STATUS_IMPORTED,
    LAYOUT_TYPE_DIAGRAM,
    LAYOUT_TYPE_MIXED,
    LAYOUT_TYPE_TABLE,
    LAYOUT_TYPE_TEXT,
    LAYOUT_TYPE_UNKNOWN,
    OCR_MODE_AUTO,
    OCR_MODE_SIDEBAR_SPLIT,
    PAGE_STATUS_UNCHECKED,
    REVIEW_STATUS_CHECKED,
    REVIEW_STATUS_NEEDS_REVIEW,
    REVIEW_STATUS_REVIEWING,
    REVIEW_STATUS_UNCHECKED,
    Document,
    Page,
)
from ocr_tool.storage.db import (
    find_next_page_for_review,
    get_document,
    get_page_review_summary,
    initialize_database,
    insert_document,
    insert_pages,
    list_pages,
    update_page_review_metadata,
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


def _pages() -> list[Page]:
    return [
        Page(
            id="doc123_page_0001",
            document_id="doc123",
            page_number=1,
            image_path=Path("data/pages/doc123/page_0001.png"),
        ),
        Page(
            id="doc123_page_0002",
            document_id="doc123",
            page_number=2,
            image_path=Path("data/pages/doc123/page_0002.png"),
        ),
    ]


def _review_pages() -> list[Page]:
    return [
        Page(
            id="doc123_page_0001",
            document_id="doc123",
            page_number=1,
            image_path=Path("data/pages/doc123/page_0001.png"),
            review_status=REVIEW_STATUS_CHECKED,
            layout_type=LAYOUT_TYPE_TEXT,
        ),
        Page(
            id="doc123_page_0002",
            document_id="doc123",
            page_number=2,
            image_path=Path("data/pages/doc123/page_0002.png"),
            review_status=REVIEW_STATUS_UNCHECKED,
            layout_type=LAYOUT_TYPE_TABLE,
            needs_manual_review=True,
        ),
        Page(
            id="doc123_page_0003",
            document_id="doc123",
            page_number=3,
            image_path=Path("data/pages/doc123/page_0003.png"),
            review_status=REVIEW_STATUS_NEEDS_REVIEW,
            layout_type=LAYOUT_TYPE_DIAGRAM,
            needs_manual_review=True,
        ),
        Page(
            id="doc123_page_0004",
            document_id="doc123",
            page_number=4,
            image_path=Path("data/pages/doc123/page_0004.png"),
            review_status=REVIEW_STATUS_REVIEWING,
            layout_type=LAYOUT_TYPE_MIXED,
            needs_manual_review=True,
        ),
    ]


def test_initialize_database_creates_db_file_and_tables(tmp_path):
    database_path = tmp_path / "app.db"

    initialize_database(database_path)

    assert database_path.exists()
    with sqlite3.connect(database_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"documents", "pages"}.issubset(table_names)


def test_initialize_database_is_idempotent(tmp_path):
    database_path = tmp_path / "app.db"

    initialize_database(database_path)
    initialize_database(database_path)

    assert database_path.exists()


def test_insert_and_get_document_roundtrip(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    document = _document()

    insert_document(document, database_path)

    saved = get_document("doc123", database_path)
    assert saved == document


def test_insert_and_list_pages_roundtrip(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)
    pages = _pages()

    insert_pages(pages, database_path)

    saved_pages = list_pages("doc123", database_path)
    assert saved_pages == pages


def test_page_defaults_include_review_layout_ocr_metadata():
    page = _pages()[0]

    assert page.status == PAGE_STATUS_UNCHECKED
    assert page.review_status == REVIEW_STATUS_UNCHECKED
    assert page.layout_type == LAYOUT_TYPE_UNKNOWN
    assert page.ocr_mode == OCR_MODE_AUTO
    assert page.needs_manual_review is False


def test_update_page_review_metadata_updates_only_provided_fields(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)
    insert_pages(_pages(), database_path)

    update_page_review_metadata(
        "doc123",
        1,
        review_status=REVIEW_STATUS_NEEDS_REVIEW,
        needs_manual_review=True,
        database_path=database_path,
    )

    page = list_pages("doc123", database_path)[0]
    assert page.review_status == REVIEW_STATUS_NEEDS_REVIEW
    assert page.needs_manual_review is True
    assert page.layout_type == LAYOUT_TYPE_UNKNOWN
    assert page.ocr_mode == OCR_MODE_AUTO


def test_update_page_review_metadata_can_update_layout_and_ocr_mode(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)
    insert_pages(_pages(), database_path)

    update_page_review_metadata(
        "doc123",
        1,
        layout_type=LAYOUT_TYPE_TABLE,
        ocr_mode=OCR_MODE_SIDEBAR_SPLIT,
        database_path=database_path,
    )

    page = list_pages("doc123", database_path)[0]
    assert page.layout_type == LAYOUT_TYPE_TABLE
    assert page.ocr_mode == OCR_MODE_SIDEBAR_SPLIT
    assert page.review_status == REVIEW_STATUS_UNCHECKED
    assert page.needs_manual_review is False


def test_insert_pages_replaces_duplicate_document_page(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)
    insert_pages(_pages(), database_path)

    replacement = Page(
        id="doc123_page_0001_replaced",
        document_id="doc123",
        page_number=1,
        image_path=Path("data/pages/doc123/page_0001_replaced.png"),
        layout_type=LAYOUT_TYPE_TABLE,
    )
    insert_pages([replacement], database_path)

    saved_pages = list_pages("doc123", database_path)
    assert len(saved_pages) == 2
    assert saved_pages[0].id == "doc123_page_0001_replaced"
    assert saved_pages[0].image_path == replacement.image_path
    assert saved_pages[0].layout_type == LAYOUT_TYPE_TABLE


def test_get_page_review_summary_returns_counts(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)
    insert_pages(_review_pages(), database_path)

    summary = get_page_review_summary("doc123", database_path)

    assert summary["total_pages"] == 4
    assert summary["review_status_counts"] == {
        REVIEW_STATUS_CHECKED: 1,
        REVIEW_STATUS_NEEDS_REVIEW: 1,
        REVIEW_STATUS_REVIEWING: 1,
        REVIEW_STATUS_UNCHECKED: 1,
    }
    assert summary["layout_type_counts"] == {
        LAYOUT_TYPE_DIAGRAM: 1,
        LAYOUT_TYPE_MIXED: 1,
        LAYOUT_TYPE_TABLE: 1,
        LAYOUT_TYPE_TEXT: 1,
    }
    assert summary["needs_manual_review_count"] == 3


def test_get_page_review_summary_handles_document_with_no_pages(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)

    summary = get_page_review_summary("doc123", database_path)

    assert summary == {
        "total_pages": 0,
        "review_status_counts": {},
        "layout_type_counts": {},
        "needs_manual_review_count": 0,
    }


def test_find_next_page_for_review_returns_unchecked_page(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)
    insert_pages(_pages(), database_path)

    page = find_next_page_for_review("doc123", database_path=database_path)

    assert page is not None
    assert page.page_number == 1


def test_find_next_page_for_review_prioritizes_needs_review(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)
    insert_pages(_review_pages(), database_path)

    page = find_next_page_for_review("doc123", database_path=database_path)

    assert page is not None
    assert page.page_number == 3


def test_find_next_page_for_review_skips_checked_pages(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)
    pages = [
        Page(
            id="doc123_page_0001",
            document_id="doc123",
            page_number=1,
            image_path=Path("data/pages/doc123/page_0001.png"),
            review_status=REVIEW_STATUS_CHECKED,
        ),
        Page(
            id="doc123_page_0002",
            document_id="doc123",
            page_number=2,
            image_path=Path("data/pages/doc123/page_0002.png"),
            review_status=REVIEW_STATUS_REVIEWING,
        ),
    ]
    insert_pages(pages, database_path)

    page = find_next_page_for_review("doc123", database_path=database_path)

    assert page is not None
    assert page.page_number == 2


def test_find_next_page_for_review_wraps_after_current_page(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)
    pages = [
        Page(
            id="doc123_page_0001",
            document_id="doc123",
            page_number=1,
            image_path=Path("data/pages/doc123/page_0001.png"),
        ),
        Page(
            id="doc123_page_0002",
            document_id="doc123",
            page_number=2,
            image_path=Path("data/pages/doc123/page_0002.png"),
        ),
    ]
    insert_pages(pages, database_path)

    page = find_next_page_for_review(
        "doc123",
        current_page_number=2,
        database_path=database_path,
    )

    assert page is not None
    assert page.page_number == 1


def test_find_next_page_for_review_returns_none_when_all_checked(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)
    pages = [
        Page(
            id="doc123_page_0001",
            document_id="doc123",
            page_number=1,
            image_path=Path("data/pages/doc123/page_0001.png"),
            review_status=REVIEW_STATUS_CHECKED,
        )
    ]
    insert_pages(pages, database_path)

    page = find_next_page_for_review("doc123", database_path=database_path)

    assert page is None


def test_importing_db_module_does_not_create_database(tmp_path, monkeypatch):
    original_database_path = config.DATABASE_PATH
    database_path = tmp_path / "app.db"
    monkeypatch.setattr(config, "DATABASE_PATH", database_path)

    importlib.reload(db)

    assert not database_path.exists()

    monkeypatch.setattr(config, "DATABASE_PATH", original_database_path)
    importlib.reload(db)
