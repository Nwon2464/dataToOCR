"""SQLite metadata storage."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from ocr_tool.config import DATABASE_PATH
from ocr_tool.models import (
    Document,
    Page,
    REVIEW_STATUS_NEEDS_REVIEW,
    REVIEW_STATUS_REVIEWING,
    REVIEW_STATUS_UNCHECKED,
)
from ocr_tool.storage.files import get_corrected_text_path, get_raw_ocr_text_path


def get_connection(database_path: Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection without global import-time state."""
    path = _resolve_database_path(database_path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_path: Path | None = None) -> None:
    """Create metadata tables if missing."""
    path = _resolve_database_path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                input_path TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pages (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                raw_ocr_path TEXT NOT NULL,
                corrected_text_path TEXT NOT NULL,
                status TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT 'unchecked',
                layout_type TEXT NOT NULL DEFAULT 'unknown',
                ocr_mode TEXT NOT NULL DEFAULT 'auto',
                needs_manual_review INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id),
                UNIQUE(document_id, page_number)
            );

            """
        )


def insert_document(document: Document, database_path: Path | None = None) -> None:
    """Insert or replace a document metadata row."""
    now = _utc_now()
    with get_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO documents (
                id,
                original_filename,
                stored_filename,
                input_path,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                original_filename = excluded.original_filename,
                stored_filename = excluded.stored_filename,
                input_path = excluded.input_path,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                document.id,
                document.original_filename,
                document.stored_filename,
                str(document.input_path),
                document.status,
                _format_datetime(document.created_at),
                now,
            ),
        )


def insert_pages(pages: list[Page], database_path: Path | None = None) -> None:
    """Insert or replace page metadata rows."""
    now = _utc_now()
    with get_connection(database_path) as connection:
        for page in pages:
            connection.execute(
                """
                INSERT INTO pages (
                    id,
                    document_id,
                    page_number,
                    image_path,
                    raw_ocr_path,
                    corrected_text_path,
                    status,
                    review_status,
                    layout_type,
                    ocr_mode,
                    needs_manual_review,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id, page_number) DO UPDATE SET
                    id = excluded.id,
                    image_path = excluded.image_path,
                    raw_ocr_path = excluded.raw_ocr_path,
                    corrected_text_path = excluded.corrected_text_path,
                    status = excluded.status,
                    review_status = excluded.review_status,
                    layout_type = excluded.layout_type,
                    ocr_mode = excluded.ocr_mode,
                    needs_manual_review = excluded.needs_manual_review,
                    updated_at = excluded.updated_at
                """,
                (
                    page.id,
                    page.document_id,
                    page.page_number,
                    str(page.image_path),
                    str(get_raw_ocr_text_path(page.document_id, page.page_number)),
                    str(get_corrected_text_path(page.document_id, page.page_number)),
                    page.status,
                    page.review_status,
                    page.layout_type,
                    page.ocr_mode,
                    int(page.needs_manual_review),
                    now,
                    now,
                ),
            )


def get_document(
    document_id: str, database_path: Path | None = None
) -> Document | None:
    """Return a document by ID."""
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT id, original_filename, stored_filename, input_path, status, created_at
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()

    if row is None:
        return None

    return Document(
        id=row["id"],
        original_filename=row["original_filename"],
        stored_filename=row["stored_filename"],
        input_path=Path(row["input_path"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        status=row["status"],
    )


def list_pages(document_id: str, database_path: Path | None = None) -> list[Page]:
    """List pages for a document ordered by page number."""
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                document_id,
                page_number,
                image_path,
                status,
                review_status,
                layout_type,
                ocr_mode,
                needs_manual_review
            FROM pages
            WHERE document_id = ?
            ORDER BY page_number
            """,
            (document_id,),
        ).fetchall()

    return [_page_from_row(row) for row in rows]


def get_page_review_summary(
    document_id: str,
    database_path: Path | None = None,
) -> dict[str, object]:
    """Return compact review/layout counts for one document."""
    with get_connection(database_path) as connection:
        total_pages = connection.execute(
            "SELECT COUNT(*) FROM pages WHERE document_id = ?",
            (document_id,),
        ).fetchone()[0]
        review_rows = connection.execute(
            """
            SELECT review_status, COUNT(*) AS page_count
            FROM pages
            WHERE document_id = ?
            GROUP BY review_status
            """,
            (document_id,),
        ).fetchall()
        layout_rows = connection.execute(
            """
            SELECT layout_type, COUNT(*) AS page_count
            FROM pages
            WHERE document_id = ?
            GROUP BY layout_type
            """,
            (document_id,),
        ).fetchall()
        needs_manual_review_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM pages
            WHERE document_id = ? AND needs_manual_review = 1
            """,
            (document_id,),
        ).fetchone()[0]

    return {
        "total_pages": total_pages,
        "review_status_counts": {
            row["review_status"]: row["page_count"] for row in review_rows
        },
        "layout_type_counts": {
            row["layout_type"]: row["page_count"] for row in layout_rows
        },
        "needs_manual_review_count": needs_manual_review_count,
    }


def find_next_page_for_review(
    document_id: str,
    current_page_number: int | None = None,
    database_path: Path | None = None,
) -> Page | None:
    """Return next non-checked page by review priority, wrapping if needed."""
    review_priority = [
        REVIEW_STATUS_NEEDS_REVIEW,
        REVIEW_STATUS_UNCHECKED,
        REVIEW_STATUS_REVIEWING,
    ]
    placeholders = ", ".join("?" for _ in review_priority)

    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                id,
                document_id,
                page_number,
                image_path,
                status,
                review_status,
                layout_type,
                ocr_mode,
                needs_manual_review
            FROM pages
            WHERE document_id = ? AND review_status IN ({placeholders})
            ORDER BY
                CASE review_status
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    WHEN ? THEN 2
                    ELSE 3
                END,
                page_number
            """,
            (
                document_id,
                *review_priority,
                *review_priority,
            ),
        ).fetchall()

    if not rows:
        return None

    for review_status in review_priority:
        status_rows = [row for row in rows if row["review_status"] == review_status]
        if current_page_number is not None:
            for row in status_rows:
                if row["page_number"] > current_page_number:
                    return _page_from_row(row)
        if status_rows:
            return _page_from_row(status_rows[0])

    return None


def update_page_review_metadata(
    document_id: str,
    page_number: int,
    review_status: str | None = None,
    layout_type: str | None = None,
    ocr_mode: str | None = None,
    needs_manual_review: bool | None = None,
    database_path: Path | None = None,
) -> None:
    """Update selected page review/layout metadata fields."""
    updates = []
    values: list[object] = []

    if review_status is not None:
        updates.append("review_status = ?")
        values.append(review_status)
    if layout_type is not None:
        updates.append("layout_type = ?")
        values.append(layout_type)
    if ocr_mode is not None:
        updates.append("ocr_mode = ?")
        values.append(ocr_mode)
    if needs_manual_review is not None:
        updates.append("needs_manual_review = ?")
        values.append(int(needs_manual_review))

    if not updates:
        return

    updates.append("updated_at = ?")
    values.append(_utc_now())
    values.extend([document_id, page_number])

    with get_connection(database_path) as connection:
        connection.execute(
            f"""
            UPDATE pages
            SET {", ".join(updates)}
            WHERE document_id = ? AND page_number = ?
            """,
            values,
        )


def _resolve_database_path(database_path: Path | None) -> Path:
    return database_path if database_path is not None else DATABASE_PATH


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _page_from_row(row: sqlite3.Row) -> Page:
    return Page(
        id=row["id"],
        document_id=row["document_id"],
        page_number=row["page_number"],
        image_path=Path(row["image_path"]),
        status=row["status"],
        review_status=row["review_status"],
        layout_type=row["layout_type"],
        ocr_mode=row["ocr_mode"],
        needs_manual_review=bool(row["needs_manual_review"]),
    )
