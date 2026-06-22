from __future__ import annotations

from typing import Any


def collect_image_count(page: dict[str, Any]) -> int:
    count = 0
    for group in ("blocks", "side_notes", "meta"):
        for block in page.get(group, []):
            if block.get("image"):
                count += 1
    return count


def is_tiny_empty_figure(block: dict[str, Any]) -> bool:
    block_type = block.get("type")
    source_type = block.get("source_type")
    text = (block.get("text") or "").strip()
    has_image = bool(block.get("image"))
    bbox = block.get("bbox")

    if block_type != "figure" or source_type != "image":
        return False
    if text or has_image:
        return False
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False

    try:
        width = abs(float(bbox[2]) - float(bbox[0]))
        height = abs(float(bbox[3]) - float(bbox[1]))
    except (TypeError, ValueError):
        return False

    # Small empty figure boxes are usually decorative icons such as arrows,
    # pins, or margin markers, not OCR/export quality problems.
    return width <= 80 and height <= 80


def collect_empty_text_blocks(page: dict[str, Any]) -> int:
    count = 0
    for block in page.get("blocks", []):
        if is_tiny_empty_figure(block):
            continue

        block_type = block.get("type")
        text = (block.get("text") or "").strip()
        has_image = bool(block.get("image"))

        if block_type in {"figure", "table", "table_or_figure", "chart"} and has_image:
            continue

        if not text:
            count += 1

    return count


def block_text_length(block: dict[str, Any]) -> int:
    return len((block.get("text") or "").strip())


def page_text_length(page: dict[str, Any]) -> int:
    total = 0
    for group in ("blocks", "side_notes"):
        for block in page.get(group, []):
            total += block_text_length(block)
    return total


def page_image_count(page: dict[str, Any]) -> int:
    return collect_image_count(page)


def classify_page_quality(page: dict[str, Any]) -> tuple[str, list[str]]:
    blocks = page.get("blocks", [])
    side_notes = page.get("side_notes", [])
    meta = page.get("meta", [])
    text_len = page_text_length(page)
    images = page_image_count(page)
    empty_blocks = collect_empty_text_blocks(page)

    reasons: list[str] = []

    # A page with no real content blocks, notes, text, or images is usually a
    # real blank source page. Some MinerU outputs still include metadata-only
    # records for such pages, so metadata alone should not make the page BAD.
    if text_len == 0 and images == 0 and not blocks and not side_notes:
        if meta:
            return "BLANK", ["metadata only"]
        return "BLANK", ["no content blocks"]

    # A page with no extracted text but at least one image/preview is usually
    # image-only content. It should be reviewed less urgently than BAD.
    if text_len == 0 and images > 0:
        return "IMAGE_ONLY", ["image without extracted text"]

    if text_len == 0 and images == 0:
        reasons.append("no text and no image")

    if blocks and empty_blocks >= max(3, len(blocks) // 2):
        reasons.append("many empty blocks")

    if text_len < 40 and images == 0:
        reasons.append("very short text without image")

    for block in blocks:
        if is_tiny_empty_figure(block):
            continue

        block_type = block.get("type")
        block_text = (block.get("text") or "").strip()
        block_image = block.get("image")

        if block_type in {"table", "chart", "table_or_figure", "figure"} and not block_text and not block_image:
            reasons.append(f"empty {block_type}")
            break

    # Many side notes alone usually means the page has rich marginal notes,
    # not that OCR/export quality is bad. Keep it as an informational signal only
    # when another quality issue already exists.
    if len(side_notes) >= 8 and reasons:
        reasons.append("many side notes")

    if any(r in reasons for r in ["no text and no image"]):
        return "BAD", reasons

    if reasons:
        return "CHECK", reasons

    return "OK", []
