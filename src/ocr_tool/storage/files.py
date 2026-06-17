"""Local file storage helpers."""

from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from ocr_tool.config import CORRECTED_DIR, DATA_DIR, INPUT_DIR, OCR_RAW_DIR, PAGES_DIR
from ocr_tool.models import DOCUMENT_STATUS_IMPORTED, PAGE_STATUS_UNCHECKED, Document, Page


def ensure_data_directories() -> None:
    """Create local data directories when explicitly requested."""
    for directory in (DATA_DIR, INPUT_DIR, PAGES_DIR, OCR_RAW_DIR, CORRECTED_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def sanitize_filename(filename: str) -> str:
    """Return a filename safe for local storage."""
    name = PurePosixPath(filename.replace("\\", "/")).name.strip()
    sanitized = "".join(
        character
        if character.isalnum() or character in {" ", "-", "_", "."}
        else "_"
        for character in name
    )

    if sanitized in {"", ".", ".."}:
        return "uploaded_file"

    return sanitized


def generate_document_id() -> str:
    """Return a unique document ID."""
    return uuid4().hex


def build_stored_input_filename(document_id: str, original_filename: str) -> str:
    """Prefix sanitized original filename with document ID."""
    return f"{document_id}_{sanitize_filename(original_filename)}"


def save_uploaded_file(original_filename: str, content: bytes) -> Document:
    """Save uploaded file bytes and return document metadata."""
    document_id = generate_document_id()
    sanitized_filename = sanitize_filename(original_filename)
    # build_stored_input_filename also sanitizes, so callers may pass raw or sanitized names.
    stored_filename = build_stored_input_filename(document_id, sanitized_filename)
    destination_path = get_input_path(stored_filename)

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(content)

    return Document(
        id=document_id,
        original_filename=sanitized_filename,
        stored_filename=stored_filename,
        input_path=destination_path,
        created_at=datetime.now(),
        status=DOCUMENT_STATUS_IMPORTED,
    )


def save_page_image(
    document_id: str,
    page_number: int,
    image_bytes: bytes,
    extension: str = ".png",
) -> Path:
    """Save already-generated page image bytes."""
    destination_path = get_page_image_path(document_id, page_number, extension)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(image_bytes)
    return destination_path


def save_raw_ocr_text(document_id: str, page_number: int, text: str) -> Path:
    """Save raw OCR text without touching corrected text."""
    path = get_raw_ocr_text_path(document_id, page_number)
    save_text(path, text)
    return path


def save_corrected_text(document_id: str, page_number: int, text: str) -> Path:
    """Save corrected text without touching raw OCR text."""
    path = get_corrected_text_path(document_id, page_number)
    save_text(path, text)
    return path


def load_raw_ocr_text(document_id: str, page_number: int) -> str:
    """Load raw OCR text."""
    return read_text(get_raw_ocr_text_path(document_id, page_number))


def raw_ocr_exists(document_id: str, page_number: int) -> bool:
    """Return True when raw OCR text exists and contains non-whitespace text."""
    path = get_raw_ocr_text_path(document_id, page_number)
    if not path.exists():
        return False
    return bool(path.read_text(encoding="utf-8").strip())


def load_corrected_text(document_id: str, page_number: int) -> str:
    """Load corrected text."""
    return read_text(get_corrected_text_path(document_id, page_number))


def build_page_record(
    document_id: str,
    page_number: int,
    image_path: Path,
    raw_ocr_text: str = "",
    corrected_text: str = "",
) -> Page:
    """Build a Page dataclass without persistence."""
    _validate_page_number(page_number)
    return Page(
        id=f"{document_id}_page_{page_number:04d}",
        document_id=document_id,
        page_number=page_number,
        image_path=image_path,
        raw_ocr_text=raw_ocr_text,
        corrected_text=corrected_text,
        status=PAGE_STATUS_UNCHECKED,
    )


def get_input_path(stored_filename: str) -> Path:
    """Return input file path without creating directories."""
    return INPUT_DIR / stored_filename


def get_page_image_path(
    document_id: str, page_number: int, extension: str = ".png"
) -> Path:
    """Return page image path without creating directories."""
    _validate_page_number(page_number)
    normalized_extension = _normalize_extension(extension)
    return PAGES_DIR / document_id / f"page_{page_number:04d}{normalized_extension}"


def get_raw_ocr_text_path(document_id: str, page_number: int) -> Path:
    """Return raw OCR text path without creating directories."""
    _validate_page_number(page_number)
    return OCR_RAW_DIR / document_id / f"page_{page_number:04d}.txt"


def get_corrected_text_path(document_id: str, page_number: int) -> Path:
    """Return corrected text path without creating directories."""
    _validate_page_number(page_number)
    return CORRECTED_DIR / document_id / f"page_{page_number:04d}.txt"


def save_text(path: Path, text: str) -> None:
    """Save UTF-8 text, creating the parent directory first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_text(path: Path) -> str:
    """Read UTF-8 text."""
    return path.read_text(encoding="utf-8")


def _validate_page_number(page_number: int) -> None:
    if page_number < 1:
        raise ValueError("page_number must be 1 or greater")


def _normalize_extension(extension: str) -> str:
    if not extension:
        return ""
    if extension.startswith("."):
        return extension
    return f".{extension}"
