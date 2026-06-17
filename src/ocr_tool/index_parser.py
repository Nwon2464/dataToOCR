"""Parser foundation for textbook Index keyword lines."""

from pathlib import Path
import re
import sqlite3

from ocr_tool.storage.db import insert_keyword, insert_keyword_ref

INDEX_LINE_RE = re.compile(
    r"^\s*(?P<keyword>.+?)\s+(?P<refs>\d+-\d+(?:\s*,\s*\d+-\d+)*)\s*$"
)
BODY_SENTENCE_RE = re.compile(
    r"\b(is|are|was|were|appears?|discussed|covered|explained|section)\b",
    re.IGNORECASE,
)


def parse_index_lines(lines: list[str]) -> list[dict[str, object]]:
    """Parse simple corrected textbook Index lines into keyword/ref records."""
    entries: list[dict[str, object]] = []
    for line in lines:
        match = INDEX_LINE_RE.match(line)
        if match is None:
            continue

        keyword = re.sub(r"\s+", " ", match.group("keyword")).strip()
        if not keyword or _looks_like_body_sentence(keyword):
            continue

        refs = [
            ref.strip()
            for ref in match.group("refs").split(",")
            if ref.strip()
        ]
        if not refs:
            continue

        entries.append({"keyword": keyword, "refs": refs})

    return entries


def import_index_lines(
    document_id: str,
    lines: list[str],
    database_path: Path | None = None,
) -> dict[str, int]:
    """Parse and import Index lines into keyword dictionary tables."""
    keyword_ids: set[str] = set()
    ref_ids: set[str] = set()

    for entry in parse_index_lines(lines):
        try:
            keyword_id = insert_keyword(
                document_id=document_id,
                keyword=str(entry["keyword"]),
                database_path=database_path,
            )
            keyword_ids.add(keyword_id)
            for ref in entry["refs"]:
                ref_id = insert_keyword_ref(
                    keyword_id=keyword_id,
                    ref_text=str(ref),
                    section_code=str(ref),
                    database_path=database_path,
                )
                ref_ids.add(ref_id)
        except (RuntimeError, ValueError, sqlite3.Error):
            continue

    return {"keywords": len(keyword_ids), "refs": len(ref_ids)}


def _looks_like_body_sentence(keyword: str) -> bool:
    if any(mark in keyword for mark in ".。!?！？"):
        return True
    return BODY_SENTENCE_RE.search(keyword) is not None
