from datetime import datetime, timezone
from pathlib import Path

from ocr_tool.index_parser import import_index_lines, parse_index_lines
from ocr_tool.models import DOCUMENT_STATUS_IMPORTED, Document
from ocr_tool.storage.db import initialize_database, insert_document, list_keywords


def _document() -> Document:
    return Document(
        id="doc123",
        original_filename="source.pdf",
        stored_filename="doc123_source.pdf",
        input_path=Path("data/input/doc123_source.pdf"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        status=DOCUMENT_STATUS_IMPORTED,
    )


def test_parse_index_lines_parses_single_ref():
    entries = parse_index_lines(["Business judgment rule 9-20"])

    assert entries == [{"keyword": "Business judgment rule", "refs": ["9-20"]}]


def test_parse_index_lines_parses_multiple_refs():
    entries = parse_index_lines(["Strict liability 1-3, 3-9, 3-12"])

    assert entries == [
        {"keyword": "Strict liability", "refs": ["1-3", "3-9", "3-12"]}
    ]


def test_parse_index_lines_ignores_malformed_lines():
    entries = parse_index_lines(["", "Contracts", "Contracts two-one", "2-1"])

    assert entries == []


def test_parse_index_lines_trims_whitespace():
    entries = parse_index_lines(["  Actual   damages   10-4,   10-5  "])

    assert entries == [{"keyword": "Actual damages", "refs": ["10-4", "10-5"]}]


def test_parse_index_lines_does_not_parse_body_sentence():
    entries = parse_index_lines(["This is a normal body sentence 1-3"])

    assert entries == []


def test_import_index_lines_inserts_keyword_and_refs(tmp_path):
    database_path = tmp_path / "app.db"
    initialize_database(database_path)
    insert_document(_document(), database_path)

    counts = import_index_lines(
        "doc123",
        ["Strict liability 1-3, 3-9, 3-12"],
        database_path,
    )

    keywords = list_keywords("doc123", database_path)
    assert counts == {"keywords": 1, "refs": 3}
    assert keywords[0]["keyword"] == "Strict liability"
    assert [ref["ref_text"] for ref in keywords[0]["refs"]] == [
        "1-3",
        "3-12",
        "3-9",
    ]
