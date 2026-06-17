"""Manual PDF extraction check.

Run from the project root:
    python scripts/manual_check_extract.py data/input/sample.pdf
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from ocr_tool.storage.files import generate_document_id


MISSING_PYMUPDF_MESSAGE = (
    "PyMuPDF is not installed. Install project dependencies before running this "
    "manual check."
)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python scripts/manual_check_extract.py <path-to-pdf>")
        return 1

    pdf_path = Path(argv[1])
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}")
        return 1

    try:
        from ocr_tool.pipeline.extract_pages import extract_pages_from_pdf

        document_id = generate_document_id()
        pages = extract_pages_from_pdf(
            document_id=document_id,
            pdf_path=pdf_path,
            dpi=300,
            image_format="png",
        )
    except ImportError as error:
        if error.name == "fitz":
            print(MISSING_PYMUPDF_MESSAGE)
            return 1
        raise

    print(f"document_id: {document_id}")
    print(f"pages_extracted: {len(pages)}")
    for page in pages:
        print(f"page {page.page_number}: {page.image_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
