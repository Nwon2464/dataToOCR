#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional


def clean_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def block_text(block: dict[str, Any]) -> str:
    """
    Prefer human-readable text.
    Fallback to markdown/raw_text/html only when text is empty.
    """
    for key in ["text", "markdown"]:
        value = clean_text(block.get(key))
        if value:
            return value

    source = block.get("source")
    if isinstance(source, dict):
        raw = clean_text(source.get("raw_text"))
        if raw:
            return raw

    html = clean_text(block.get("html"))
    if html:
        html = re.sub(r"<[^>]+>", " ", html)
        html = clean_text(html)
        if html:
            return html

    return ""


def is_content_block(block: dict[str, Any]) -> bool:
    """
    Skip obvious decorative blocks like page numbers.
    But do not over-filter; Chapter headings and 本章のポイント must remain.
    """
    role = str(block.get("role") or "").lower()
    block_type = str(block.get("block_type") or "").lower()
    kind = str(block.get("kind") or "").lower()

    if block_type == "page_number":
        return False

    if role == "decorative" and block_type not in {"title", "text"}:
        return False

    if kind == "decorative":
        return False

    return True

def page_number(page: dict[str, Any], blocks: list[dict[str, Any]]) -> Optional[int]:
    """
    Bookmark page priority:
    1. page.page        -> global combined PDF page
    2. block.page       -> global combined PDF page
    3. page.source_page -> fallback only
    4. block.source_page -> fallback only

    In render_all.json, source_page can be chunk-local.
    For GoodNotes bookmarks, we need the global page number.
    """
    for key in ["page"]:
        value = page.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)

    for block in blocks:
        value = block.get("page")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)

    for key in ["source_page"]:
        value = page.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)

    for block in blocks:
        value = block.get("source_page")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)

    return None


def extract_title_from_same_text(text: str, chapter_no: int) -> Optional[str]:
    """
    "Chapter 7 Secured Transaction" -> "Secured Transaction"
    """
    pattern = re.compile(
        rf"chapter\s*{chapter_no}\s*[:.\-–—]?\s*(.+)$",
        re.IGNORECASE,
    )
    m = pattern.search(text)
    if not m:
        return None

    title = clean_title(m.group(1))
    return title or None


def clean_title(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = clean_text(text)
    return text.strip(" .:-–—")


def is_title_candidate(text: str, chapter_no: int, marker: str) -> bool:
    text = clean_title(text)

    if not text:
        return False

    if marker in text:
        return False

    if re.fullmatch(rf"chapter\s*{chapter_no}", text, re.IGNORECASE):
        return False

    if re.fullmatch(rf"chapter\s*{chapter_no}\s*contents?", text, re.IGNORECASE):
        return False

    if re.fullmatch(r"[\W_0-9\s]+", text):
        return False

    # Long paragraphs are usually not chapter titles.
    if len(text) > 120:
        return False

    return True


def extract_title(
    blocks: list[dict[str, Any]],
    chapter_no: int,
    chapter_block_index: int,
    marker: str,
) -> tuple[str, Optional[str], str]:
    """
    Title priority:
    1. Same block: Chapter X Title
    2. Next nearby meaningful block before 本章のポイント
    3. Previous nearby meaningful block
    4. Fallback: Chapter X
    """
    chapter_text = block_text(blocks[chapter_block_index])

    same = extract_title_from_same_text(chapter_text, chapter_no)
    if same and is_title_candidate(same, chapter_no, marker):
        return same, same, "OK"

    # Next blocks until marker.
    for i in range(chapter_block_index + 1, min(len(blocks), chapter_block_index + 8)):
        text = block_text(blocks[i])

        if marker in text:
            break

        if is_title_candidate(text, chapter_no, marker):
            return clean_title(text), text, "OK"

    # Sometimes title can be just before Chapter X.
    for i in range(max(0, chapter_block_index - 3), chapter_block_index):
        text = block_text(blocks[i])

        if is_title_candidate(text, chapter_no, marker):
            return clean_title(text), text, "OK"

    return f"Chapter {chapter_no}", None, "TITLE_NOT_FOUND"


def find_chapter_on_page(
    page: dict[str, Any],
    chapter_regex: re.Pattern[str],
    marker: str,
    export_page_offset: int,
) -> Optional[dict[str, Any]]:
    raw_blocks = page.get("blocks")
    if not isinstance(raw_blocks, list):
        return None

    blocks = [b for b in raw_blocks if isinstance(b, dict) and is_content_block(b)]
    if not blocks:
        return None

    texts = [block_text(b) for b in blocks]
    page_text = "\n".join(t for t in texts if t)

    if marker not in page_text:
        return None

    chapter_block_index = None
    chapter_match = None

    for i, text in enumerate(texts):
        m = chapter_regex.search(text)
        if m:
            chapter_block_index = i
            chapter_match = m
            break

    if chapter_match is None or chapter_block_index is None:
        return None

    chapter_no = int(chapter_match.group(1))
    title_body, matched_title_text, title_status = extract_title(
        blocks,
        chapter_no,
        chapter_block_index,
        marker,
    )

    source_page = page_number(page, blocks)
    final_page = source_page + export_page_offset if source_page is not None else None

    status = title_status
    if final_page is None:
        status = "PAGE_UNKNOWN"

    chunk_id = page.get("chunk_id")
    page_title = clean_text(page.get("title"))

    sample = clean_text(page_text)
    if len(sample) > 500:
        sample = sample[:500] + "..."

    return {
        "chapter_no": chapter_no,
        "title": f"{chapter_no} {title_body}",
        "page": final_page,
        "source_page": source_page,
        "level": 1,
        "status": status,
        "page_title": page_title,
        "chunk_id": chunk_id,
        "match_source": "render_all.json",
        "matched_chapter_text": chapter_match.group(0),
        "matched_title_text": matched_title_text,
        "matched_marker_text": marker,
        "chapter_block_id": blocks[chapter_block_index].get("id"),
        "chapter_block_index": chapter_block_index,
        "detection_method": "render_all_pages_chapter_marker",
        "export_page_offset": export_page_offset,
        "raw_text_sample": sample,
    }


def dedupe_by_chapter(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for item in items:
        grouped[item["chapter_no"]].append(item)

    result: list[dict[str, Any]] = []

    for chapter_no in sorted(grouped):
        candidates = grouped[chapter_no]

        def score(item: dict[str, Any]) -> tuple[int, int, int]:
            has_page = 1 if item.get("page") is not None else 0
            is_ok = 1 if item.get("status") == "OK" else 0
            source_page = item.get("source_page")
            page_score = -int(source_page) if isinstance(source_page, int) else 0
            return has_page, is_ok, page_score

        best = dict(sorted(candidates, key=score, reverse=True)[0])

        if len(candidates) > 1:
            if best["status"] == "OK":
                best["status"] = "DUPLICATE"
            best["duplicate_count"] = len(candidates)
            best["duplicate_candidates"] = [
                {
                    "title": x.get("title"),
                    "page": x.get("page"),
                    "source_page": x.get("source_page"),
                    "status": x.get("status"),
                    "chunk_id": x.get("chunk_id"),
                    "page_title": x.get("page_title"),
                }
                for x in candidates
            ]
        else:
            best["duplicate_count"] = 1
            best["duplicate_candidates"] = []

        result.append(best)

    return result


def build_minimal_toc(toc_full: list[dict[str, Any]]) -> list[dict[str, Any]]:
    toc: list[dict[str, Any]] = []

    for item in toc_full:
        if item.get("page") is None:
            continue

        toc.append(
            {
                "title": item["title"],
                "page": item["page"],
                "level": 1,
            }
        )

    return toc


def validate_toc(toc_full: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []

    prev_page = None
    prev_title = None

    for item in toc_full:
        title = item.get("title")
        page = item.get("page")

        if page is None:
            warnings.append(f"Missing page: {title}")
            continue

        if prev_page is not None and page < prev_page:
            warnings.append(
                f"Page order warning: {title} page={page} "
                f"comes after {prev_title} page={prev_page}"
            )

        prev_page = page
        prev_title = title

    return warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract chapter TOC from render_all.json using Chapter X + 本章のポイント."
    )

    parser.add_argument(
        "--render-all",
        default="data/processed/render_all.json",
        help="Path to combined render_all.json.",
    )

    parser.add_argument(
        "--out-full",
        default="data/processed/toc_full.json",
        help="Debug-rich TOC output path.",
    )

    parser.add_argument(
        "--out",
        default="data/processed/toc.json",
        help="Minimal bookmark TOC output path.",
    )

    parser.add_argument(
        "--chapter-marker",
        default="本章のポイント",
        help="Marker text that confirms chapter start.",
    )

    parser.add_argument(
        "--chapter-regex",
        default=r"Chapter\s*(\d+)",
        help="Regex for Chapter X. Must capture chapter number.",
    )

    parser.add_argument(
        "--export-page-offset",
        type=int,
        default=0,
        help="Add offset to source_page when writing bookmark page.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    render_all_path = Path(args.render_all)
    out_full_path = Path(args.out_full)
    out_path = Path(args.out)

    if not render_all_path.exists():
        raise SystemExit(f"render_all.json not found: {render_all_path}")

    try:
        chapter_regex = re.compile(args.chapter_regex, re.IGNORECASE)
    except re.error as e:
        raise SystemExit(f"Invalid --chapter-regex: {e}") from e

    data = load_json(render_all_path)

    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, list):
        raise SystemExit("Invalid render_all.json: top-level pages[] not found.")

    raw_items: list[dict[str, Any]] = []

    for page in pages:
        if not isinstance(page, dict):
            continue

        item = find_chapter_on_page(
            page,
            chapter_regex=chapter_regex,
            marker=args.chapter_marker,
            export_page_offset=args.export_page_offset,
        )

        if item is not None:
            raw_items.append(item)

    toc_full = dedupe_by_chapter(raw_items)
    toc = build_minimal_toc(toc_full)
    warnings = validate_toc(toc_full)

    out_full_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    out_full_path.write_text(
        json.dumps(toc_full, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    out_path.write_text(
        json.dumps(toc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    status_counts: dict[str, int] = defaultdict(int)
    for item in toc_full:
        status_counts[item.get("status", "UNKNOWN")] += 1

    print(f"render_all: {render_all_path}")
    print(f"pages: {len(pages)}")
    print(f"raw chapter candidates: {len(raw_items)}")
    print(f"final chapters: {len(toc_full)}")
    print(f"wrote full: {out_full_path}")
    print(f"wrote min : {out_path}")

    print("status counts:")
    for status in sorted(status_counts):
        print(f"  {status}: {status_counts[status]}")

    if warnings:
        print("warnings:")
        for warning in warnings:
            print(f"  - {warning}")


if __name__ == "__main__":
    main()
