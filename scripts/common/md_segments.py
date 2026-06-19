from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape


_IMAGE_LINE_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]+\)\s*$")
_FENCE_LINE_RE = re.compile(r"^\s*`{3,}")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*(.*?)\s*#*\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-+*]|[0-9０-９]+[)）.．])\s*(.*)$")
_TABLE_CELL_RE = re.compile(
    r"<(?P<tag>td|th)\b[^>]*>(?P<text>.*?)</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG_ONLY_RE = re.compile(r"^\s*</?[A-Za-z][A-Za-z0-9:-]*(?:\s+[^>]*)?>\s*$")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class MarkdownSegment:
    """One extracted Markdown text segment for OCR review."""

    type: str
    line_no: int
    text: str
    checkable: bool


def _is_image_line(line: str) -> bool:
    """Return True when line is a Markdown image link."""
    return bool(_IMAGE_LINE_RE.match(line))


def _strip_heading_marker(line: str) -> str | None:
    """Remove Markdown heading marker and return heading text."""
    match = _HEADING_RE.match(line)
    if match is None:
        return None
    return match.group(1).strip()


def _strip_list_marker(line: str) -> str | None:
    """Remove Markdown list marker and return item text."""
    match = _LIST_ITEM_RE.match(line)
    if match is None:
        return None
    return match.group(1).strip()


def _strip_html_tags(text: str) -> str:
    """Remove HTML tags and unescape entities from text."""
    return unescape(_HTML_TAG_RE.sub("", text)).strip()


def _extract_table_cells(line: str) -> list[str]:
    """Extract text values from HTML td/th cells in a line."""
    cells: list[str] = []
    for match in _TABLE_CELL_RE.finditer(line):
        text = _strip_html_tags(match.group("text"))
        cells.append(text)
    return cells


def _is_html_tag_only_line(line: str) -> bool:
    """Return True when line contains only one HTML tag."""
    return bool(_HTML_TAG_ONLY_RE.match(line))


def extract_markdown_segments(markdown: str) -> list[MarkdownSegment]:
    """Split Markdown text into checkable and non-checkable OCR review segments."""
    segments: list[MarkdownSegment] = []
    in_code_block = False

    for line_no, line in enumerate(markdown.splitlines(), start=1):
        if _FENCE_LINE_RE.match(line):
            segments.append(
                MarkdownSegment(
                    type="code",
                    line_no=line_no,
                    text=line,
                    checkable=False,
                )
            )
            in_code_block = not in_code_block
            continue

        if in_code_block:
            segments.append(
                MarkdownSegment(
                    type="code",
                    line_no=line_no,
                    text=line,
                    checkable=False,
                )
            )
            continue

        if line.strip() == "":
            segments.append(
                MarkdownSegment(
                    type="blank",
                    line_no=line_no,
                    text="",
                    checkable=False,
                )
            )
            continue

        if _is_image_line(line):
            segments.append(
                MarkdownSegment(
                    type="image",
                    line_no=line_no,
                    text=line.strip(),
                    checkable=False,
                )
            )
            continue

        table_cells = _extract_table_cells(line)
        if table_cells:
            for cell in table_cells:
                segments.append(
                    MarkdownSegment(
                        type="table_cell",
                        line_no=line_no,
                        text=cell,
                        checkable=True,
                    )
                )
            continue

        if _is_html_tag_only_line(line):
            segments.append(
                MarkdownSegment(
                    type="html",
                    line_no=line_no,
                    text=line.strip(),
                    checkable=False,
                )
            )
            continue

        heading = _strip_heading_marker(line)
        if heading is not None:
            segments.append(
                MarkdownSegment(
                    type="heading",
                    line_no=line_no,
                    text=heading,
                    checkable=True,
                )
            )
            continue

        list_item = _strip_list_marker(line)
        if list_item is not None:
            segments.append(
                MarkdownSegment(
                    type="list_item",
                    line_no=line_no,
                    text=list_item,
                    checkable=True,
                )
            )
            continue

        segments.append(
            MarkdownSegment(
                type="paragraph",
                line_no=line_no,
                text=line.strip(),
                checkable=True,
            )
        )

    return segments
