"""SQLite metadata storage."""

from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

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

            CREATE TABLE IF NOT EXISTS keywords (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                keyword TEXT NOT NULL,
                normalized_keyword TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'unknown',
                source TEXT NOT NULL DEFAULT 'textbook_index',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id),
                UNIQUE(document_id, normalized_keyword, source)
            );

            CREATE TABLE IF NOT EXISTS keyword_refs (
                id TEXT PRIMARY KEY,
                keyword_id TEXT NOT NULL,
                ref_text TEXT NOT NULL,
                section_code TEXT NOT NULL DEFAULT '',
                target_page_number INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(keyword_id) REFERENCES keywords(id)
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


def normalize_keyword(keyword: str) -> str:
    """Normalize keyword text for matching and uniqueness."""
    return re.sub(r"\s+", " ", keyword.strip()).lower()


def insert_keyword(
    document_id: str,
    keyword: str,
    language: str = "unknown",
    source: str = "textbook_index",
    note: str = "",
    database_path: Path | None = None,
) -> str:
    """Insert a keyword and return its ID, reusing duplicates."""
    normalized_keyword = normalize_keyword(keyword)
    if not normalized_keyword:
        raise ValueError("keyword must not be empty")

    now = _utc_now()
    keyword_id = f"keyword_{uuid4().hex}"
    with get_connection(database_path) as connection:
        connection.execute(
            """
            INSERT INTO keywords (
                id,
                document_id,
                keyword,
                normalized_keyword,
                language,
                source,
                note,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id, normalized_keyword, source) DO UPDATE SET
                keyword = excluded.keyword,
                language = excluded.language,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (
                keyword_id,
                document_id,
                keyword.strip(),
                normalized_keyword,
                language,
                source,
                note,
                now,
                now,
            ),
        )
        row = connection.execute(
            """
            SELECT id
            FROM keywords
            WHERE document_id = ? AND normalized_keyword = ? AND source = ?
            """,
            (document_id, normalized_keyword, source),
        ).fetchone()

    if row is None:
        raise RuntimeError("keyword insert failed")
    return row["id"]


def insert_keyword_ref(
    keyword_id: str,
    ref_text: str,
    section_code: str = "",
    target_page_number: int | None = None,
    database_path: Path | None = None,
) -> str:
    """Insert a keyword reference and return its ID, reusing exact duplicates."""
    cleaned_ref_text = ref_text.strip()
    if not cleaned_ref_text:
        raise ValueError("ref_text must not be empty")
    cleaned_section_code = section_code.strip()

    with get_connection(database_path) as connection:
        existing = connection.execute(
            """
            SELECT id
            FROM keyword_refs
            WHERE keyword_id = ?
                AND ref_text = ?
                AND section_code = ?
                AND (
                    target_page_number = ?
                    OR (target_page_number IS NULL AND ? IS NULL)
                )
            """,
            (
                keyword_id,
                cleaned_ref_text,
                cleaned_section_code,
                target_page_number,
                target_page_number,
            ),
        ).fetchone()
        if existing is not None:
            return existing["id"]

        now = _utc_now()
        keyword_ref_id = f"keyword_ref_{uuid4().hex}"
        connection.execute(
            """
            INSERT INTO keyword_refs (
                id,
                keyword_id,
                ref_text,
                section_code,
                target_page_number,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                keyword_ref_id,
                keyword_id,
                cleaned_ref_text,
                cleaned_section_code,
                target_page_number,
                now,
                now,
            ),
        )

    return keyword_ref_id


def list_keywords(
    document_id: str,
    database_path: Path | None = None,
) -> list[dict[str, object]]:
    """List keywords with refs for one document."""
    with get_connection(database_path) as connection:
        keyword_rows = connection.execute(
            """
            SELECT
                id,
                document_id,
                keyword,
                normalized_keyword,
                language,
                source,
                note
            FROM keywords
            WHERE document_id = ?
            ORDER BY normalized_keyword
            """,
            (document_id,),
        ).fetchall()
        ref_rows = connection.execute(
            """
            SELECT
                keyword_id,
                id,
                ref_text,
                section_code,
                target_page_number
            FROM keyword_refs
            WHERE keyword_id IN (
                SELECT id FROM keywords WHERE document_id = ?
            )
            ORDER BY ref_text
            """,
            (document_id,),
        ).fetchall()

    refs_by_keyword: dict[str, list[dict[str, object]]] = {}
    for row in ref_rows:
        refs_by_keyword.setdefault(row["keyword_id"], []).append(_keyword_ref_dict(row))

    return [
        _keyword_dict(row, refs_by_keyword.get(row["id"], []))
        for row in keyword_rows
    ]


def search_keywords(
    document_id: str,
    query: str,
    database_path: Path | None = None,
) -> list[dict[str, object]]:
    """Search normalized keyword text for one document."""
    normalized_query = normalize_keyword(query)
    if not normalized_query:
        return []

    with get_connection(database_path) as connection:
        keyword_rows = connection.execute(
            """
            SELECT
                id,
                document_id,
                keyword,
                normalized_keyword,
                language,
                source,
                note
            FROM keywords
            WHERE document_id = ? AND normalized_keyword LIKE ?
            ORDER BY normalized_keyword
            """,
            (document_id, f"%{normalized_query}%"),
        ).fetchall()
        keyword_ids = [row["id"] for row in keyword_rows]
        ref_rows = []
        if keyword_ids:
            placeholders = ", ".join("?" for _ in keyword_ids)
            ref_rows = connection.execute(
                f"""
                SELECT
                    keyword_id,
                    id,
                    ref_text,
                    section_code,
                    target_page_number
                FROM keyword_refs
                WHERE keyword_id IN ({placeholders})
                ORDER BY ref_text
                """,
                keyword_ids,
            ).fetchall()

    refs_by_keyword: dict[str, list[dict[str, object]]] = {}
    for row in ref_rows:
        refs_by_keyword.setdefault(row["keyword_id"], []).append(_keyword_ref_dict(row))

    return [
        _keyword_dict(row, refs_by_keyword.get(row["id"], []))
        for row in keyword_rows
    ]


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


def _keyword_ref_dict(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "ref_text": row["ref_text"],
        "section_code": row["section_code"],
        "target_page_number": row["target_page_number"],
    }


def _keyword_dict(
    row: sqlite3.Row,
    refs: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "id": row["id"],
        "document_id": row["document_id"],
        "keyword": row["keyword"],
        "normalized_keyword": row["normalized_keyword"],
        "language": row["language"],
        "source": row["source"],
        "note": row["note"],
        "refs": refs,
    }
