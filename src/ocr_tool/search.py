"""Simple file-based search over corrected text."""

from pathlib import Path
import re

from ocr_tool.storage.db import list_pages
from ocr_tool.storage.files import get_corrected_text_path, load_corrected_text


def search_corrected_text(
    document_id: str,
    query: str,
    database_path: Path | None = None,
    max_results: int = 50,
) -> list[dict[str, object]]:
    """Search corrected text files for one document."""
    normalized_query = query.strip()
    if not normalized_query or max_results <= 0:
        return []

    results: list[dict[str, object]] = []
    for page in list_pages(document_id, database_path=database_path):
        try:
            corrected_text = load_corrected_text(document_id, page.page_number)
        except FileNotFoundError:
            continue

        if not corrected_text.strip():
            continue

        match_index = corrected_text.casefold().find(normalized_query.casefold())
        if match_index == -1:
            continue

        results.append(
            {
                "document_id": document_id,
                "page_number": page.page_number,
                "matched_text": corrected_text[
                    match_index : match_index + len(normalized_query)
                ],
                "snippet": build_search_snippet(corrected_text, normalized_query),
                "corrected_text_path": str(
                    get_corrected_text_path(document_id, page.page_number)
                ),
                "layout_type": page.layout_type,
                "review_status": page.review_status,
                "needs_manual_review": page.needs_manual_review,
            }
        )
        if len(results) >= max_results:
            break

    return results


def build_search_snippet(
    text: str,
    query: str,
    context_chars: int = 40,
) -> str:
    """Return compact context around first case-insensitive match."""
    if context_chars < 0:
        context_chars = 0

    normalized_query = query.strip()
    match_index = (
        text.casefold().find(normalized_query.casefold()) if normalized_query else -1
    )

    if match_index == -1:
        snippet = text[: max(context_chars * 2, 80)]
    else:
        start = max(match_index - context_chars, 0)
        end = min(match_index + len(normalized_query) + context_chars, len(text))
        snippet = text[start:end]

    return re.sub(r"\s+", " ", snippet).strip()
