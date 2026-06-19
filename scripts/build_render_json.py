from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.api_paths import (
    ensure_project_dirs,
    get_mineru_api_chunk_dir,
    get_mineru_api_output_dir,
    get_processed_chunk_dir,
)


IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")
UNORDERED_LIST_RE = re.compile(r"^\s*[-*+]\s+")
ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
NUMERIC_MARKER_RE = re.compile(r"^\s*(?:[（(]\s*)?(\d+)(?:\s*[）)]|[.)．）])\s*")
WORD_MARKER_RE = re.compile(r"^\s*(?:[（(]\s*)?([A-Za-z]+)(?:\s*[）)]|[.)．）])\s*")
BULLET_MARKER_RE = re.compile(r"^\s*([・•]|[-*+])\s+")
MARKDOWN_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!])")
PAGE_NUMBER_RE = re.compile(r"^\s*(?:\d+|[ivxlcdmIVXLCDM]+)\s*$")
ALPHA_SECTION_RE = re.compile(r"^[a-z]\)\s*")
NUMBERED_SECTION_RE = re.compile(r"^\d+[）)]\s*")
LATEX_DELIMITER_RE = re.compile(r"^\s*(?:\$\$.*\$\$|\\\(.*\\\)|\\\[.*\\\])\s*$", re.DOTALL)
LATEX_SIGNAL_RE = re.compile(r"(?:\\[A-Za-z]+|[_^{}]|\$)")
NUMERIC_COORD_TEXT_RE = re.compile(r"^\s*(?:-?\d+(?:\.\d+)?\s*){4,}$")
NUMBER_TEXT_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
ROMAN_MARKERS = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
}
SEMANTIC_TEXT_KEYS = (
    "text",
    "content",
    "markdown",
    "html",
    "title_content",
    "paragraph_content",
    "page_header_content",
    "page_footer_content",
    "page_number_content",
    "page_aside_text_content",
    "table_caption",
    "image_caption",
    "list_items",
    "math_content",
    "latex",
    "latex_content",
)
EQUATION_TYPES = {
    "equation_interline",
    "interline_equation",
    "inline_equation",
    "equation",
    "formula",
    "math",
    "latex",
}
IMPORTANT_IMAGE_KEYWORDS = (
    "Input期",
    "Output期",
    "推奨学習パターン",
    "トレーニング",
    "学習",
    "flow",
    "pattern",
)
ICON_IMAGE_KEYWORDS = (
    "アイコンについて",
    "補足",
    "用語",
    "参照",
    "MC",
    "TBS",
)

BLOCK_CLASS = {
    "header": "custom-block-header",
    "title": "custom-block-title",
    "text": "custom-block-text",
    "table_body": "custom-block-table_body",
    "image": "custom-block-image",
    "equation": "custom-block-equation",
    "formula": "custom-block-formula",
    "aside_text": "custom-block-aside_text",
    "page_number": "custom-block-page_number",
    "footer": "custom-block-footer",
    "list": "custom-block-text",
    "code": "custom-block-text",
    "raw_html": "custom-block-text",
    "unknown": "custom-block-text",
}

THEME = {
    "header": [164, 164, 164],
    "page_number": [164, 164, 164],
    "footer": [164, 164, 164],
    "title": [13, 83, 222],
    "text": [13, 83, 222],
    "list": [13, 83, 222],
    "code": [13, 83, 222],
    "raw_html": [13, 83, 222],
    "unknown": [13, 83, 222],
    "table_body": [103, 194, 63],
    "image": [89, 92, 220],
    "equation": [79, 70, 229],
    "formula": [79, 70, 229],
    "aside_text": [164, 164, 164],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build web-optimized render.json files from extracted MinerU chunk output."
    )
    parser.add_argument(
        "chunks",
        nargs="*",
        help="Chunk IDs to process. Omit with --all to process every extracted chunk.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all chunk directories under data/mineru_api_output.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Write indented JSON for debugging. Default is compact JSON for web rendering.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Also build data/processed/{chunk_id}/render_preview.html after render.json.",
    )
    return parser.parse_args()


def unescape_markdown(value: str) -> str:
    return MARKDOWN_ESCAPE_RE.sub(r"\1", value)


def normalize_asset_path(src: str) -> str:
    value = str(src).strip().replace("\\", "/")
    if value.startswith("./"):
        return value[2:]
    return value


def parse_inline_parts(value: str) -> list[dict[str, str]]:
    parts: list[dict[str, str]] = []
    cursor = 0

    for match in IMAGE_RE.finditer(value):
        if match.start() > cursor:
            parts.append({"type": "text", "text": unescape_markdown(value[cursor : match.start()])})
        parts.append(
            {
                "type": "image",
                "alt": match.group(1) or "",
                "src": normalize_asset_path(match.group(2) or ""),
            }
        )
        cursor = match.end()

    if cursor < len(value):
        parts.append({"type": "text", "text": unescape_markdown(value[cursor:])})

    return parts or [{"type": "text", "text": ""}]


def is_unordered_list(line: str) -> bool:
    return bool(UNORDERED_LIST_RE.match(line))


def is_ordered_list(line: str) -> bool:
    return bool(ORDERED_LIST_RE.match(line))


def list_item_text(line: str) -> str:
    return LIST_ITEM_RE.sub("", line, count=1)


def parse_list_marker(line: str) -> dict[str, Any] | None:
    text = str(line or "")
    bullet = BULLET_MARKER_RE.match(text)
    if bullet:
        return {
            "marker_type": "bullet",
            "marker_value": bullet.group(1),
            "list_start": None,
            "text": text[bullet.end() :].strip(),
        }

    numeric = NUMERIC_MARKER_RE.match(text)
    if numeric:
        return {
            "marker_type": "numeric",
            "marker_value": numeric.group(1),
            "list_start": int(numeric.group(1)),
            "text": text[numeric.end() :].strip(),
        }

    word = WORD_MARKER_RE.match(text)
    if not word:
        return None
    marker = word.group(1)
    lower = marker.lower()
    if lower in ROMAN_MARKERS:
        return {
            "marker_type": "roman",
            "marker_value": marker,
            "list_start": ROMAN_MARKERS[lower],
            "text": text[word.end() :].strip(),
        }
    if len(marker) == 1 and marker.isalpha():
        return {
            "marker_type": "alpha",
            "marker_value": marker,
            "list_start": ord(lower) - ord("a") + 1,
            "text": text[word.end() :].strip(),
        }
    return None


def normalize_list_segments(lines: list[str]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for raw_line in lines:
        line = str(raw_line or "").strip()
        if not line:
            continue
        marker = parse_list_marker(line)
        if not marker:
            segments.append(
                {
                    "segment_type": "paragraph",
                    "text": line,
                    "normalization_reason": "unmarked_text_split_from_list",
                }
            )
            continue

        segment_type = "unordered" if marker["marker_type"] == "bullet" else "ordered"
        previous = segments[-1] if segments else None
        can_merge = (
            previous
            and previous.get("segment_type") == segment_type
            and previous.get("marker_type") == marker["marker_type"]
        )
        if can_merge:
            previous["items"].append(marker["text"])
            continue

        segments.append(
            {
                "segment_type": segment_type,
                "marker_type": marker["marker_type"],
                "marker_value": marker["marker_value"],
                "list_start": marker["list_start"],
                "items": [marker["text"]],
                "normalization_reason": "marker_based_list_item",
            }
        )
    return segments


def list_tag_attrs(segment: dict[str, Any]) -> str:
    attrs: list[str] = []
    marker_type = segment.get("marker_type")
    start = segment.get("list_start")
    if marker_type == "alpha":
        attrs.append('type="a"')
    elif marker_type == "roman":
        attrs.append('type="i"')
    if isinstance(start, int) and start > 1:
        attrs.append(f'start="{start}"')
    return (" " + " ".join(attrs)) if attrs else ""


def render_list_segments(segments: list[dict[str, Any]]) -> tuple[str, str, str]:
    html_parts: list[str] = []
    markdown_parts: list[str] = []
    text_parts: list[str] = []
    for segment in segments:
        if segment.get("segment_type") == "paragraph":
            text = str(segment.get("text") or "").strip()
            if text:
                html_parts.append(f"<p>{html.escape(text)}</p>")
                markdown_parts.append(text)
                text_parts.append(text)
            continue

        items = [str(item).strip() for item in segment.get("items") or [] if str(item).strip()]
        if not items:
            continue
        if segment.get("segment_type") == "unordered":
            html_parts.append("<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>")
            markdown_parts.extend(f"- {item}" for item in items)
        else:
            html_parts.append(
                f"<ol{list_tag_attrs(segment)}>"
                + "".join(f"<li>{html.escape(item)}</li>" for item in items)
                + "</ol>"
            )
            start = int(segment.get("list_start") or 1)
            markdown_parts.extend(f"{start + index}. {item}" for index, item in enumerate(items))
        text_parts.extend(items)
    return "".join(html_parts), "\n".join(markdown_parts), "\n".join(text_parts)


def first_list_metadata(segments: list[dict[str, Any]]) -> dict[str, Any]:
    for segment in segments:
        if segment.get("segment_type") in {"ordered", "unordered"}:
            return {
                "marker_type": segment.get("marker_type"),
                "marker_value": segment.get("marker_value"),
                "list_start": segment.get("list_start"),
                "normalization_reason": segment.get("normalization_reason"),
            }
    return {
        "marker_type": None,
        "marker_value": None,
        "list_start": None,
        "normalization_reason": None,
    }


def is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if "|" not in stripped:
        return False
    cells = stripped.removeprefix("|").removesuffix("|").split("|")
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and "|" in stripped[1:-1]


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().removeprefix("|").removesuffix("|").split("|")]


def parse_markdown_table(lines: list[str]) -> list[list[dict[str, Any]]]:
    rows = []
    for line in lines:
        if is_table_separator(line):
            continue
        rows.append([{"text": cell, "parts": parse_inline_parts(cell)} for cell in split_table_row(line)])
    return rows


def finalize_blocks(blocks: list[dict[str, Any]], chunk_id: str) -> list[dict[str, Any]]:
    return [{**block, "legacy_id": f"{chunk_id}-{index}"} for index, block in enumerate(blocks)]


def parse_markdown(markdown: str, chunk_id: str) -> list[dict[str, Any]]:
    lines = markdown.splitlines()
    blocks: list[dict[str, Any]] = []
    paragraph: list[str] = []
    i = 0

    def flush_paragraph() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        blocks.append(
            {
                "type": "paragraph",
                "lines": [{"text": line, "parts": parse_inline_parts(line)} for line in paragraph],
            }
        )
        paragraph = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            language = stripped[3:].strip()
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            blocks.append({"type": "code", "language": language, "code": "\n".join(code)})
            continue

        if stripped.startswith("<table"):
            flush_paragraph()
            table_lines = [line]
            i += 1
            if "</table>" not in line:
                while i < len(lines):
                    table_lines.append(lines[i])
                    if "</table>" in lines[i]:
                        i += 1
                        break
                    i += 1
            blocks.append({"type": "html-table", "html": "\n".join(table_lines)})
            continue

        if stripped.startswith("<details"):
            flush_paragraph()
            detail_lines = [line]
            i += 1
            while i < len(lines):
                detail_lines.append(lines[i])
                if lines[i].strip() == "</details>":
                    i += 1
                    break
                i += 1
            blocks.append({"type": "raw-html", "html": "\n".join(detail_lines)})
            continue

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        heading = HEADING_RE.match(stripped)
        if heading:
            flush_paragraph()
            text = heading.group(2).strip()
            blocks.append(
                {
                    "type": "heading",
                    "level": len(heading.group(1)),
                    "text": text,
                    "parts": parse_inline_parts(text),
                }
            )
            i += 1
            continue

        if stripped in {"---", "***", "___"}:
            flush_paragraph()
            blocks.append({"type": "hr"})
            i += 1
            continue

        if is_table_row(line) and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
            flush_paragraph()
            table_lines = [line, lines[i + 1]]
            i += 2
            while i < len(lines) and is_table_row(lines[i]):
                table_lines.append(lines[i])
                i += 1
            blocks.append({"type": "markdown-table", "rows": parse_markdown_table(table_lines)})
            continue

        if is_unordered_list(line) or is_ordered_list(line):
            flush_paragraph()
            ordered = is_ordered_list(line)
            items = []
            while i < len(lines):
                if ordered and not is_ordered_list(lines[i]):
                    break
                if not ordered and not is_unordered_list(lines[i]):
                    break
                text = list_item_text(lines[i])
                items.append({"text": text, "parts": parse_inline_parts(text)})
                i += 1
            blocks.append({"type": "list", "ordered": ordered, "items": items})
            continue

        paragraph.append(line)
        i += 1

    flush_paragraph()
    return finalize_blocks(blocks, chunk_id)


def first_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_number_sequence(value: Any, length: int | None = None) -> bool:
    if not isinstance(value, list):
        return False
    if length is not None and len(value) != length:
        return False
    return bool(value) and all(is_number(item) for item in value)


def is_coordinate_sequence(value: Any) -> bool:
    return is_number_sequence(value, 4) or is_number_sequence(value, 8)


def text_from_parts(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if is_coordinate_sequence(value):
            return ""
        return "\n".join(part for part in (text_from_parts(item) for item in value) if part)
    if isinstance(value, dict):
        for key in SEMANTIC_TEXT_KEYS:
            if key in value and isinstance(value[key], (str, int, float)):
                return str(value[key])
        chunks: list[str] = []
        for key in SEMANTIC_TEXT_KEYS:
            nested = value.get(key)
            if isinstance(nested, (dict, list)):
                nested_text = text_from_parts(nested)
                if nested_text:
                    chunks.append(nested_text)
        return "\n".join(chunks)
    return ""


def split_bbox_tail(text: str) -> tuple[str, list[int] | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 5:
        return text, None
    tail = lines[-4:]
    if all(NUMBER_TEXT_RE.match(line) for line in tail):
        coords = [int(float(line)) for line in tail]
        return "\n".join(lines[:-4]), coords
    return text, None


def raw_type_name(raw: dict[str, Any]) -> str:
    return str(first_value(raw, ("type", "category", "block_type")) or "").lower().strip()


def is_equation_type(raw_type: str) -> bool:
    normalized = (raw_type or "").lower().strip().replace("-", "_")
    return normalized in EQUATION_TYPES or "equation" in normalized


def first_nested_value(raw: dict[str, Any], keys: tuple[str, ...]) -> Any:
    value = first_value(raw, keys)
    if value is not None:
        return value
    content = raw.get("content")
    if isinstance(content, dict):
        return first_value(content, keys)
    return None


def looks_like_latex(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    return bool(LATEX_DELIMITER_RE.match(text) or LATEX_SIGNAL_RE.search(text))


def looks_like_numeric_coords(value: str) -> bool:
    return bool(NUMERIC_COORD_TEXT_RE.match(value.replace("\n", " ")))


def extract_math_content(raw: dict[str, Any], raw_index: int, warnings: list[str]) -> tuple[str, str | None]:
    math_content = first_nested_value(raw, ("math_content",))
    if isinstance(math_content, (str, int, float)) and str(math_content).strip():
        return str(math_content).strip(), "math_content"

    for key in ("latex", "latex_content", "text"):
        value = first_nested_value(raw, (key,))
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text and looks_like_latex(text):
                return text, key

    content = raw.get("content")
    if isinstance(content, (str, int, float)):
        text = str(content).strip()
        if text and looks_like_latex(text):
            return text, "content"

    fallback_text = text_from_parts(raw).strip()
    if fallback_text and looks_like_numeric_coords(fallback_text):
        warnings.append(f"equation block {raw_index} has coordinate-like numeric text; math_content missing")
        return "", "coordinate_text_suppressed"
    if fallback_text and looks_like_latex(fallback_text):
        return fallback_text, "fallback_latex"

    warnings.append(f"equation block {raw_index} has no usable math content")
    return "", None


def extract_text(raw: dict[str, Any]) -> str:
    raw_type = raw_type_name(raw)
    if is_equation_type(raw_type):
        return ""
    direct = first_value(raw, ("text", "content", "markdown", "html"))
    if isinstance(direct, str):
        return direct
    if isinstance(direct, (int, float)):
        return str(direct)

    content = raw.get("content")
    if isinstance(content, dict):
        for key in (
            "title_content",
            "paragraph_content",
            "page_header_content",
            "page_footer_content",
            "page_number_content",
            "table_caption",
            "image_caption",
            "list_items",
        ):
            if key in content:
                text = text_from_parts(content[key])
                if text:
                    return text

    if raw_type in {"image", "figure"}:
        return ""

    return text_from_parts(raw)


def extract_list_items(raw: dict[str, Any]) -> list[str]:
    items = first_value(raw, ("list_items", "items"))
    content = raw.get("content")
    if items is None and isinstance(content, dict):
        items = content.get("list_items")
    if not isinstance(items, list):
        return []

    result: list[str] = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            value = first_value(item, ("text", "content", "item_content"))
            result.append(text_from_parts(value))
        else:
            result.append(text_from_parts(item))
    return [item for item in result if item]


def raw_bbox_value(raw: dict[str, Any]) -> Any:
    return first_value(raw, ("bbox", "poly", "points", "position", "coordinates"))


def bbox_from_points(points: list[Any]) -> list[float] | None:
    if not points:
        return None
    if is_number_sequence(points, 4):
        return [float(value) for value in points]
    if is_number_sequence(points, 8):
        xs = [float(points[index]) for index in range(0, 8, 2)]
        ys = [float(points[index]) for index in range(1, 8, 2)]
        return [min(xs), min(ys), max(xs), max(ys)]
    if all(isinstance(point, list) and len(point) >= 2 and is_number(point[0]) and is_number(point[1]) for point in points):
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
        return [min(xs), min(ys), max(xs), max(ys)]
    return None


def extract_bbox(raw: dict[str, Any]) -> Any:
    value = raw_bbox_value(raw)
    return bbox_from_points(value) if isinstance(value, list) else value


def extract_polygon(raw: dict[str, Any]) -> Any:
    value = first_value(raw, ("poly", "points", "coordinates"))
    if isinstance(value, list) and not is_number_sequence(value, 4):
        return value
    return None


def extract_image_path(raw: dict[str, Any]) -> str | None:
    value = first_value(raw, ("img_path", "image_path", "path", "src"))
    content = raw.get("content")
    if value is None and isinstance(content, dict):
        image_source = content.get("image_source")
        if isinstance(image_source, dict):
            value = first_value(image_source, ("img_path", "image_path", "path", "src"))
    return normalize_asset_path(str(value)) if value else None


def extract_level(raw: dict[str, Any]) -> int | None:
    value = first_value(raw, ("level", "text_level"))
    content = raw.get("content")
    if value is None and isinstance(content, dict):
        value = content.get("level")
    if isinstance(value, int):
        return max(1, min(value, 6))
    return None


def is_page_number_text(text: str) -> bool:
    return bool(PAGE_NUMBER_RE.match(text or ""))


def map_raw_type(raw_type: str, text: str, level: int | None) -> tuple[str, str, str]:
    normalized = (raw_type or "").lower().strip()

    if is_equation_type(normalized):
        return "formula" if "formula" in normalized else "equation", "math", "content"
    if normalized in {"aside_text", "page_aside_text", "aside-text", "page-aside-text"}:
        return "aside_text", "aside", "decorative"
    if normalized in {"page_number", "page-number"} or is_page_number_text(text):
        return "page_number", "decorative", "decorative"
    if normalized in {"footer", "page_footer"}:
        return "footer", "decorative", "decorative"
    if normalized in {"header", "page_header"}:
        return "header", "paragraph", "decorative"
    if normalized in {"title", "heading"} or level is not None:
        return "title", "heading", "content"
    if normalized in {"table", "table_body", "html-table", "markdown-table"}:
        return "table_body", "table", "content"
    if normalized in {"image", "figure"}:
        return "image", "figure", "content"
    if normalized == "list":
        return "list", "list", "content"
    if normalized == "code":
        return "code", "code", "content"
    if normalized in {"raw_html", "raw-html"}:
        return "raw_html", "raw_html", "content"
    if normalized in {"text", "paragraph"}:
        return "text", "paragraph", "content" if text.strip() else "decorative"
    return "unknown", "unknown", "content" if text.strip() else "decorative"


def html_table_container(table_html: str) -> str:
    body = table_html or "<table></table>"
    return f'<div class="max-w-full overflow-x-auto table-container scrollbar-thin">{body}</div>'


def markdown_table(rows: list[list[dict[str, Any]]]) -> str:
    if not rows:
        return ""
    values = [[str(cell.get("text", "")) for cell in row] for row in rows]
    if len(values) == 1:
        return "| " + " | ".join(values[0]) + " |"
    separator = "| " + " | ".join("---" for _ in values[0]) + " |"
    return "\n".join(["| " + " | ".join(values[0]) + " |", separator, *("| " + " | ".join(row) + " |" for row in values[1:])])


def html_markdown_text(
    block_type: str,
    kind: str,
    text: str,
    raw: dict[str, Any],
    level: int | None,
    image_path: str | None,
    list_segments: list[dict[str, Any]] | None = None,
) -> tuple[str, str, str]:
    existing_html = first_value(raw, ("html", "table_body"))
    content = raw.get("content")
    if existing_html is None and isinstance(content, dict):
        existing_html = first_value(content, ("html", "table_body"))
    existing_markdown = raw.get("markdown")

    if block_type == "title":
        heading_level = level or 2
        markdown = str(existing_markdown) if existing_markdown else f"{'#' * heading_level} {text}"
        return (
            f"<h{heading_level}>{html.escape(text)}</h{heading_level}>",
            markdown,
            text,
        )
    if block_type == "table_body":
        table_html = str(existing_html) if existing_html else ""
        if not table_html and "rows" in raw:
            rows = raw.get("rows") or []
            table_html = "<table>" + "".join(
                "<tr>" + "".join(f"<td>{html.escape(str(cell.get('text', '')))}</td>" for cell in row) + "</tr>"
                for row in rows
            ) + "</table>"
        markdown = str(existing_markdown) if existing_markdown else markdown_table(raw.get("rows") or [])
        table_text = " ".join(re.sub(r"<[^>]+>", " ", table_html).split())
        clean_text = table_text or text
        return html_table_container(table_html), markdown, " ".join(clean_text.split())
    if block_type == "image":
        src = image_path or ""
        alt = text or "extracted figure"
        markdown = str(existing_markdown) if existing_markdown else f"![{alt}]({src})"
        return f'<p><img src="{html.escape(src)}"></p>', markdown, text
    if block_type in {"equation", "formula"}:
        math_text = text.strip()
        markdown = str(existing_markdown) if existing_markdown else math_text
        html_value = f'<pre class="math-block">{html.escape(math_text)}</pre>' if math_text else ""
        return html_value, markdown, math_text
    if block_type == "list":
        items = extract_list_items(raw)
        if not items and text:
            items = [line for line in text.splitlines() if line.strip()]
        segments = list_segments if list_segments is not None else normalize_list_segments(items)
        if not segments and items:
            segments = [
                {
                    "segment_type": "unordered" if not raw.get("ordered") else "ordered",
                    "marker_type": "bullet" if not raw.get("ordered") else "numeric",
                    "marker_value": None,
                    "list_start": 1 if raw.get("ordered") else None,
                    "items": items,
                    "normalization_reason": "legacy_list_without_marker",
                }
            ]
        return render_list_segments(segments)
    if kind == "code":
        language = raw.get("language") or ""
        code = raw.get("code") or text
        return f"<pre><code>{html.escape(str(code))}</code></pre>", f"```{language}\n{code}\n```", str(code)
    if kind == "raw_html":
        raw_html = str(existing_html or text)
        return raw_html, str(existing_markdown or raw_html), text
    if kind == "decorative":
        return f"<p>{html.escape(text)}</p>" if text else "", text, text
    return f"<p>{html.escape(text)}</p>" if text else "", str(existing_markdown or text), text


def normalize_page(raw_page: Any, warnings: list[str], raw_index: int) -> int:
    if isinstance(raw_page, int):
        return raw_page + 1 if raw_page == 0 else raw_page
    if isinstance(raw_page, str) and raw_page.strip().isdigit():
        page = int(raw_page.strip())
        return page + 1 if page == 0 else page
    warnings.append(f"missing page number at raw block {raw_index}")
    return 1


def make_block(raw: dict[str, Any], page: int, raw_index: int, warnings: list[str]) -> dict[str, Any]:
    raw_type = str(first_value(raw, ("type", "category", "block_type")) or "")
    level = extract_level(raw)
    math_content: str | None = None
    classification_reason: str | None = None
    if is_equation_type(raw_type):
        math_content, classification_reason = extract_math_content(raw, raw_index, warnings)
        text = math_content
    else:
        text = extract_text(raw).strip()
        cleaned_text, bbox_tail = split_bbox_tail(text)
        if bbox_tail:
            text = cleaned_text
            classification_reason = "bbox_tail_removed_from_text"
            warnings.append(f"block {raw_index} had bbox-like numeric tail removed from text")
    raw_text = text
    if raw_type.lower().strip() == "list" and not raw_text:
        raw_text = "\n".join(extract_list_items(raw))
    image_path = extract_image_path(raw)
    if raw_type.lower() in {"image"} and not text:
        text = ""

    normalized_raw_type = raw_type.lower().strip()
    if normalized_raw_type in {"paragraph", "text"} and level is None and parse_list_marker(text):
        raw_type = "list"
        classification_reason = classification_reason or "paragraph_marker_promoted_to_list"

    block_type, kind, role = map_raw_type(raw_type, text, level)
    list_segments = []
    if block_type == "list":
        items = extract_list_items(raw)
        if not items and text:
            items = [line for line in text.splitlines() if line.strip()]
        list_segments = normalize_list_segments(items)
        if any(segment.get("segment_type") == "paragraph" for segment in list_segments):
            classification_reason = classification_reason or "list_split_marker_items_and_paragraphs"
            warnings.append(f"list block {raw_index} split marker items and unmarked paragraphs")
        elif list_segments:
            classification_reason = classification_reason or "marker_based_list_normalized"
    list_meta = first_list_metadata(list_segments)
    html_value, markdown, text = html_markdown_text(block_type, kind, text, raw, level, image_path, list_segments)
    fill = THEME[block_type]

    return {
        "id": "",
        "seq": 0,
        "page": page,
        "block_type": block_type,
        "kind": kind,
        "role": role,
        "className": BLOCK_CLASS[block_type],
        "theme": {"fill": fill, "stroke": fill},
        "level": level,
        "text": text,
        "markdown": markdown,
        "html": html_value,
        "image_path": image_path,
        "bbox": extract_bbox(raw),
        "polygon": extract_polygon(raw),
        "bbox_norm": None,
        "parts": raw.get("parts"),
        "source": {
            "original_type": str(first_value(raw, ("type", "category", "block_type")) or "") or None,
            "raw_index": raw_index,
            "classification_reason": classification_reason,
            "raw_bbox": raw_bbox_value(raw),
            "raw_text": raw_text,
        },
        "math_content": math_content,
        "marker_type": list_meta["marker_type"],
        "marker_value": list_meta["marker_value"],
        "list_start": list_meta["list_start"],
        "indent_level": None,
        "list_segments": list_segments or None,
        "normalization_reason": list_meta["normalization_reason"],
    }


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def find_source_files(chunk_dir: Path) -> dict[str, Path | None]:
    return {
        "content_list_v2": next(iter(sorted(chunk_dir.glob("*_content_list_v2.json"))), None),
        "content_list": next(iter(sorted(chunk_dir.glob("*_content_list.json"))), None),
        "layout_json": next(iter(sorted(chunk_dir.glob("*_layout.json"))), None) or (chunk_dir / "layout.json" if (chunk_dir / "layout.json").exists() else None),
        "full_md": chunk_dir / "full.md" if (chunk_dir / "full.md").exists() else None,
    }


def parse_content_list_v2(data: Any, warnings: list[str]) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise ValueError("content_list_v2 root is not a list")

    blocks: list[dict[str, Any]] = []
    raw_index = 0
    if all(isinstance(page_items, list) for page_items in data):
        for page_index, page_items in enumerate(data, start=1):
            for item in page_items:
                if isinstance(item, dict):
                    blocks.append(make_block(item, page_index, raw_index, warnings))
                else:
                    warnings.append(f"unexpected non-object block at raw block {raw_index}")
                raw_index += 1
        return blocks

    for item in data:
        if isinstance(item, dict):
            page = normalize_page(first_value(item, ("page", "page_idx", "page_id", "page_no")), warnings, raw_index)
            blocks.append(make_block(item, page, raw_index, warnings))
        else:
            warnings.append(f"unexpected non-object block at raw block {raw_index}")
        raw_index += 1
    return blocks


def parse_content_list(data: Any, warnings: list[str]) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise ValueError("content_list root is not a list")
    blocks: list[dict[str, Any]] = []
    for raw_index, item in enumerate(data):
        if not isinstance(item, dict):
            warnings.append(f"unexpected non-object block at raw block {raw_index}")
            continue
        page = normalize_page(first_value(item, ("page", "page_idx", "page_id", "page_no")), warnings, raw_index)
        blocks.append(make_block(item, page, raw_index, warnings))
    return blocks


def spans_text(raw: dict[str, Any]) -> str:
    chunks: list[str] = []
    for line in raw.get("lines") or []:
        if not isinstance(line, dict):
            continue
        for span in line.get("spans") or []:
            if isinstance(span, dict) and span.get("content"):
                chunks.append(str(span["content"]))
    return "\n".join(chunks)


def parse_layout(data: Any, warnings: list[str]) -> list[dict[str, Any]]:
    if not isinstance(data, dict) or not isinstance(data.get("pdf_info"), list):
        raise ValueError("layout root has no pdf_info list")

    blocks: list[dict[str, Any]] = []
    raw_index = 0
    for page_info in data["pdf_info"]:
        if not isinstance(page_info, dict):
            continue
        page = normalize_page(page_info.get("page_idx"), warnings, raw_index)
        for section in ("para_blocks", "discarded_blocks"):
            for item in page_info.get(section) or []:
                if not isinstance(item, dict):
                    continue
                raw = dict(item)
                raw.setdefault("text", spans_text(raw))
                blocks.append(make_block(raw, page, raw_index, warnings))
                raw_index += 1
    return blocks


def markdown_fallback_blocks(markdown: str, chunk_id: str, warnings: list[str]) -> list[dict[str, Any]]:
    warnings.append("full.md fallback used; page information may be inaccurate")
    parsed = parse_markdown(markdown, chunk_id)
    blocks: list[dict[str, Any]] = []
    for raw_index, item in enumerate(parsed):
        raw = dict(item)
        raw_type = raw.get("type")
        if raw_type == "heading":
            raw["type"] = "title"
        elif raw_type == "paragraph":
            raw["type"] = "text"
            raw["text"] = "\n".join(line.get("text", "") for line in raw.get("lines", []))
        elif raw_type == "markdown-table":
            raw["type"] = "table_body"
        elif raw_type == "html-table":
            raw["type"] = "table_body"
        elif raw_type == "raw-html":
            raw["type"] = "raw_html"
        elif raw_type == "hr":
            raw["type"] = "unknown"
            raw["text"] = ""
        blocks.append(make_block(raw, 1, raw_index, warnings))
    return blocks


def assign_ids(blocks: list[dict[str, Any]]) -> None:
    page_counts: dict[int, int] = {}
    for seq, block in enumerate(blocks, start=1):
        page = int(block.get("page") or 1)
        page_counts[page] = page_counts.get(page, 0) + 1
        block["seq"] = seq
        block["id"] = f"p{page:03d}-{page_counts[page]:04d}"


def block_text(block: dict[str, Any]) -> str:
    return " ".join(str(block.get("text") or "").split())


def is_alpha_section_block(block: dict[str, Any]) -> bool:
    return bool(ALPHA_SECTION_RE.match(block_text(block)))


def is_numbered_section_block(block: dict[str, Any]) -> bool:
    return bool(NUMBERED_SECTION_RE.match(block_text(block)))


def image_class_for_block(block: dict[str, Any], index: int, page_blocks: list[dict[str, Any]]) -> str | None:
    if block.get("block_type") != "image":
        return None
    start = max(0, index - 4)
    context = "\n".join(block_text(item) for item in page_blocks[start:index] if isinstance(item, dict))
    context_lower = context.lower()
    if any(keyword in context for keyword in ICON_IMAGE_KEYWORDS):
        return "icon-image"
    if any(keyword in context for keyword in IMPORTANT_IMAGE_KEYWORDS) or any(
        keyword.lower() in context_lower for keyword in IMPORTANT_IMAGE_KEYWORDS
    ):
        return "important-image"
    return "normal-image"


def indent_classes_for_block(block: dict[str, Any], index: int, page_blocks: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    block_type = str(block.get("block_type") or "")
    kind = str(block.get("kind") or "")
    role = str(block.get("role") or "content")
    if role == "decorative" or block_type in {"title", "table_body", "image"}:
        return None, None

    if block_type == "list":
        marker_type = str(block.get("marker_type") or "")
        if marker_type == "alpha":
            return None, "section-alpha"
        if marker_type in {"numeric", "roman"}:
            return None, "section-numbered"
        return None, None

    if is_alpha_section_block(block):
        return None, "section-alpha"
    if is_numbered_section_block(block):
        return "indent-level-1", "section-numbered"
    if block_type != "text" or kind != "paragraph":
        return None, None

    previous_numbered = False
    in_alpha_section = False
    for previous in reversed(page_blocks[:index]):
        if not isinstance(previous, dict):
            continue
        previous_type = str(previous.get("block_type") or "")
        previous_role = str(previous.get("role") or "content")
        if previous_role == "decorative" or previous_type in {"image", "table_body"}:
            continue
        if previous_type == "title":
            break
        if is_alpha_section_block(previous):
            in_alpha_section = True
            break
        if is_numbered_section_block(previous):
            previous_numbered = True
            continue

    if previous_numbered:
        return "indent-level-2", None
    if in_alpha_section:
        return "indent-level-1", None
    return None, None


def annotate_render_classes(blocks: list[dict[str, Any]]) -> None:
    page_numbers = sorted({int(block.get("page") or 1) for block in blocks})
    for page in page_numbers:
        page_blocks = [block for block in blocks if int(block.get("page") or 1) == page]
        for index, block in enumerate(page_blocks):
            image_class = image_class_for_block(block, index, page_blocks)
            indent_class, section_class = indent_classes_for_block(block, index, page_blocks)
            extra_classes = [value for value in (image_class, indent_class, section_class) if value]
            block["imageClassName"] = image_class
            block["indentClassName"] = indent_class
            block["sectionClassName"] = section_class
            block["extraClassName"] = " ".join(extra_classes) if extra_classes else None


def page_title(page: int, blocks: list[dict[str, Any]]) -> str:
    excluded_types = {"table_body", "image", "page_number", "footer", "header"}

    def clean_candidate(block: dict[str, Any]) -> str:
        if block.get("role") != "content" or block.get("block_type") in excluded_types:
            return ""
        text = " ".join(str(block.get("text") or "").split())
        if not text or is_page_number_text(text):
            return ""
        if len(text) > 60:
            return f"{text[:60]}..."
        return text

    for block in blocks:
        if block.get("block_type") == "title":
            title = clean_candidate(block)
            if title:
                return title

    for block in blocks:
        if block.get("block_type") in {"text", "list"}:
            title = clean_candidate(block)
            if title:
                return title

    return f"Page {page}"


def build_pages(blocks: list[dict[str, Any]], min_page_count: int = 0) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    page_numbers = set(range(1, min_page_count + 1))
    page_numbers.update(int(block.get("page") or 1) for block in blocks)
    sorted_page_numbers = sorted(page_numbers) or [1]
    for page in sorted_page_numbers:
        page_blocks = [block for block in blocks if int(block.get("page") or 1) == page]
        pages.append({"page": page, "title": page_title(page, page_blocks), "blocks": page_blocks})
    return pages


def filter_renderable_blocks(blocks: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    renderable: list[dict[str, Any]] = []
    for block in blocks:
        text = str(block.get("text") or "").strip()
        html_value = str(block.get("html") or "").strip()
        markdown = str(block.get("markdown") or "").strip()
        block_type = str(block.get("block_type") or "")
        if text or html_value or markdown or block_type in {"image", "table_body", "equation", "formula"}:
            renderable.append(block)
            continue

        source = block.get("source") if isinstance(block.get("source"), dict) else {}
        raw_index = source.get("raw_index")
        reason = "bbox-only/empty block suppressed from render output"
        if block.get("bbox") is not None:
            warnings.append(f"block {raw_index} has bbox but no semantic text; suppressed from render output")
        else:
            warnings.append(f"block {raw_index} has no semantic text; suppressed from render output")
        source["classification_reason"] = source.get("classification_reason") or reason
        block["source"] = source
    return renderable


def source_hash(paths: dict[str, Path | None], source_path: Path | None) -> str:
    hasher = hashlib.sha256()
    for path in (source_path, paths.get("full_md"), paths.get("layout_json")):
        if path and path.exists():
            hasher.update(path.name.encode("utf-8"))
            hasher.update(path.read_bytes())
    return hasher.hexdigest()


def copy_chunk_images(chunk_dir: Path, output_dir: Path, warnings: list[str]) -> int:
    source_images_dir = chunk_dir / "images"
    if not source_images_dir.exists():
        return 0

    output_images_dir = output_dir / "images"
    output_images_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source_path in sorted(path for path in source_images_dir.iterdir() if path.is_file()):
        target_path = output_images_dir / source_path.name
        try:
            shutil.copy2(source_path, target_path)
            copied += 1
        except OSError as exc:
            warnings.append(f"failed to copy image {source_path.name}: {exc}")
    return copied


def infer_source_page_count(label: str, data: Any, blocks: list[dict[str, Any]]) -> int:
    if label == "content_list_v2" and isinstance(data, list) and all(isinstance(item, list) for item in data):
        return len(data)
    if label == "layout_json" and isinstance(data, dict) and isinstance(data.get("pdf_info"), list):
        return len(data["pdf_info"])
    return max((int(block.get("page") or 1) for block in blocks), default=1)


def build_blocks_from_best_source(
    chunk_id: str, chunk_dir: Path, warnings: list[str]
) -> tuple[list[dict[str, Any]], str, Path | None, dict[str, Path | None], int]:
    paths = find_source_files(chunk_dir)

    for label, parser in (
        ("content_list_v2", parse_content_list_v2),
        ("content_list", parse_content_list),
        ("layout_json", parse_layout),
    ):
        path = paths[label]
        if not path:
            continue
        try:
            data = read_json(path)
            blocks = parser(data, warnings)
            if blocks:
                return blocks, label, path, paths, infer_source_page_count(label, data, blocks)
            warnings.append(f"{label} produced no blocks, fallback to next source")
        except Exception as exc:
            warnings.append(f"failed to parse {label}, fallback to next source: {exc}")

    markdown_path = paths["full_md"]
    if not markdown_path:
        raise FileNotFoundError(f"{chunk_dir}/full.md not found")
    markdown = markdown_path.read_text(encoding="utf-8")
    return markdown_fallback_blocks(markdown, chunk_id, warnings), "full.md fallback", markdown_path, paths, 1


def build_render_json(chunk_id: str, pretty: bool = False) -> Path:
    chunk_dir = get_mineru_api_chunk_dir(chunk_id)
    if not chunk_dir.exists():
        raise FileNotFoundError(f"{chunk_dir} not found")

    print(f"[input] {chunk_id}")
    warnings: list[str] = []
    blocks, source_label, source_path, paths, page_count_hint = build_blocks_from_best_source(chunk_id, chunk_dir, warnings)
    blocks = filter_renderable_blocks(blocks, warnings)
    assign_ids(blocks)
    annotate_render_classes(blocks)
    pages = build_pages(blocks, page_count_hint)

    output_dir = get_processed_chunk_dir(chunk_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_count = copy_chunk_images(chunk_dir, output_dir, warnings)

    payload = {
        "schema_version": 2,
        "render_model": "mineru_block_v1",
        "chunk_id": chunk_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": {
            "full_md": paths["full_md"].name if paths["full_md"] else None,
            "content_list": paths["content_list_v2"].name if paths["content_list_v2"] else (paths["content_list"].name if paths["content_list"] else None),
            "layout_json": paths["layout_json"].name if paths["layout_json"] else None,
            "sha256": source_hash(paths, source_path),
        },
        "stats": {
            "page_count": len(pages),
            "block_count": len(blocks),
            "content_block_count": sum(1 for block in blocks if block.get("role") == "content"),
        },
        "pages": pages,
        "blocks": blocks,
        "warnings": warnings,
    }

    output_path = output_dir / "render.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":")),
        encoding="utf-8",
    )

    source_name = source_path.name if source_path else "none"
    if source_label == "full.md fallback":
        print("[source] full.md fallback")
    else:
        print(f"[source] {source_label}: {source_name}")
    print(f"[pages] {len(pages)}")
    print(f"[blocks] {len(blocks)}")
    print(f"[images] {image_count}")
    print(f"[write] {output_path.as_posix()}")
    if warnings:
        print(f"[warnings] {len(warnings)}")
        for warning in warnings:
            print(f"- {warning}")
    print("[done]")
    return output_path


def iter_all_chunk_ids() -> list[str]:
    root = get_mineru_api_output_dir()
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir() and any(find_source_files(path).values()))


def main() -> int:
    args = parse_args()
    ensure_project_dirs()

    chunk_ids = iter_all_chunk_ids() if args.all else args.chunks
    if not chunk_ids:
        raise SystemExit("No chunks specified. Use --all or pass chunk IDs.")

    for chunk_id in chunk_ids:
        build_render_json(chunk_id, pretty=args.pretty)
        if args.preview:
            from build_render_preview import build_render_preview

            build_render_preview(chunk_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
