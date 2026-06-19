from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.common.api_paths import (
    ensure_project_dirs,
    get_chunks_dir,
    get_original_dir,
    make_chunk_id,
)

DEFAULT_CHUNK_SIZE = 10


def derive_book_id(input_pdf: Path) -> str:
    """Derive a stable book ID from the PDF stem for chunk filenames."""
    name = input_pdf.stem.strip()
    name = re.sub(r"[^A-Za-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        raise ValueError(f"Could not derive book_id from filename: {input_pdf.name}")
    return name


def resolve_input_pdf(filename: Path) -> Path:
    """Resolve a user-provided PDF filename against data/original when relative."""
    if filename.is_absolute():
        return filename
    if filename.parent != Path("."):
        return filename
    return get_original_dir() / filename


def resolve_output_dir(output_dir: Path | None) -> Path | None:
    """Resolve a user-provided output directory against the project root."""
    if output_dir is None or output_dir.is_absolute():
        return output_dir
    return PROJECT_ROOT / output_dir


def split_pdf_chunks(
    input_pdf: Path,
    book_id: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    output_dir: Path | None = None,
) -> list[Path]:
    """Split a PDF into chunk files named with inclusive page ranges."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be 1 or greater.")
    if not input_pdf.is_file():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")

    ensure_project_dirs()
    chunks_dir = output_dir if output_dir is not None else get_chunks_dir()
    chunks_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(input_pdf))
    total_pages = len(reader.pages)
    resolved_book_id = book_id if book_id is not None else derive_book_id(input_pdf)
    output_paths: list[Path] = []

    for page_start in range(1, total_pages + 1, chunk_size):
        page_end = min(page_start + chunk_size - 1, total_pages)
        chunk_id = make_chunk_id(resolved_book_id, page_start, page_end)
        output_path = chunks_dir / f"{chunk_id}.pdf"

        writer = PdfWriter()
        for page_index in range(page_start - 1, page_end):
            writer.add_page(reader.pages[page_index])

        with output_path.open("wb") as output_file:
            writer.write(output_file)

        output_paths.append(output_path)

    return output_paths


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Split a source PDF into fixed-page chunks."
    )
    parser.add_argument(
        "filename",
        type=Path,
        help="PDF filename in data/original/, or a PDF path.",
    )
    parser.add_argument(
        "--book-id",
        default=None,
        help="Book ID used in chunk filenames. Default: derived from filename.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=f"Pages per chunk. Default: {DEFAULT_CHUNK_SIZE}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Default: data/chunks/",
    )
    return parser.parse_args()


def main() -> None:
    """Run PDF chunk splitting from CLI arguments."""
    args = parse_args()
    input_pdf = resolve_input_pdf(args.filename)
    output_paths = split_pdf_chunks(
        input_pdf=input_pdf,
        book_id=args.book_id,
        chunk_size=args.chunk_size,
        output_dir=resolve_output_dir(args.output_dir),
    )

    for output_path in output_paths:
        print(output_path)


if __name__ == "__main__":
    main()
