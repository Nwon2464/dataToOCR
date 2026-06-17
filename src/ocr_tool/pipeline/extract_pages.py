"""PDF page extraction using PyMuPDF."""

from pathlib import Path

from ocr_tool.models import Page
from ocr_tool.storage.files import build_page_record, save_page_image

SUPPORTED_IMAGE_FORMATS = {"png", "jpg", "jpeg"}
MIN_DPI = 72
MAX_DPI = 600


def extract_pages_from_pdf(
    document_id: str,
    pdf_path: Path,
    dpi: int = 300,
    image_format: str = "png",
) -> list[Page]:
    """Extract PDF pages into image files and return page records.

    Behavior:
    - Read the PDF file at `pdf_path` using PyMuPDF.
    - Render each PDF page at `dpi`.
    - Save each rendered image under `data/pages/{document_id}/` using
      1-based page numbering, such as `page_0001.png`, `page_0002.png`.
    - Return a `Page` dataclass for each saved page image.

    Parameters:
        document_id: Stable document identifier used for output directory names.
        pdf_path: Path to the already-saved source PDF, usually
            `Document.input_path`.
        dpi: Render resolution. Must be between 72 and 600.
        image_format: Output image format. Supported values are `png`, `jpg`,
            and `jpeg`, with or without a leading dot.

    Returns:
        A list of `Page` records. `Page.page_number` is 1-based,
        `Page.image_path` points to the saved image, `Page.status` is unchecked,
        and raw/corrected text fields remain empty.

    Constraints:
        This function must not perform OCR, text correction, UI work, or
        database persistence.
    """
    validate_dpi(dpi)
    normalized_format = normalize_image_format(image_format)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    import fitz

    pages: list[Page] = []
    with fitz.open(str(pdf_path)) as pdf_document:
        for page_index, pdf_page in enumerate(pdf_document, start=1):
            pixmap = pdf_page.get_pixmap(dpi=dpi, alpha=False)
            image_bytes = pixmap.tobytes(output=normalized_format)
            image_path = save_page_image(
                document_id=document_id,
                page_number=page_index,
                image_bytes=image_bytes,
                extension=f".{normalized_format}",
            )
            pages.append(build_page_record(document_id, page_index, image_path))

    return pages


def normalize_image_format(image_format: str) -> str:
    """Normalize and validate page image output format."""
    normalized = image_format.lower().removeprefix(".")
    if normalized not in SUPPORTED_IMAGE_FORMATS:
        raise ValueError(
            f"Unsupported image format: {image_format}. "
            f"Supported formats: {', '.join(sorted(SUPPORTED_IMAGE_FORMATS))}"
        )
    return normalized


def validate_dpi(dpi: int) -> int:
    """Validate PDF render DPI."""
    if dpi < MIN_DPI or dpi > MAX_DPI:
        raise ValueError(f"dpi must be between {MIN_DPI} and {MAX_DPI}")
    return dpi
