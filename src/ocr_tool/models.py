"""Core data models for the MVP."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DOCUMENT_STATUS_IMPORTED = "imported"

PAGE_STATUS_UNCHECKED = "unchecked"
PAGE_STATUS_REVIEWING = "reviewing"
PAGE_STATUS_CHECKED = "checked"

REVIEW_STATUS_UNCHECKED = "unchecked"
REVIEW_STATUS_REVIEWING = "reviewing"
REVIEW_STATUS_CHECKED = "checked"
REVIEW_STATUS_NEEDS_REVIEW = "needs_review"

LAYOUT_TYPE_UNKNOWN = "unknown"
LAYOUT_TYPE_TEXT = "text"
LAYOUT_TYPE_TEXT_WITH_SIDEBAR = "text_with_sidebar"
LAYOUT_TYPE_TABLE = "table"
LAYOUT_TYPE_DIAGRAM = "diagram"
LAYOUT_TYPE_MIXED = "mixed"
LAYOUT_TYPE_QUESTION = "question"

OCR_MODE_AUTO = "auto"
OCR_MODE_MANUAL = "manual"


@dataclass
class Document:
    id: str
    original_filename: str
    stored_filename: str
    input_path: Path
    created_at: datetime
    status: str


@dataclass
class Page:
    id: str
    document_id: str
    page_number: int
    image_path: Path
    raw_ocr_text: str = ""
    corrected_text: str = ""
    status: str = PAGE_STATUS_UNCHECKED
    review_status: str = REVIEW_STATUS_UNCHECKED
    layout_type: str = LAYOUT_TYPE_UNKNOWN
    ocr_mode: str = OCR_MODE_AUTO
    needs_manual_review: bool = False
